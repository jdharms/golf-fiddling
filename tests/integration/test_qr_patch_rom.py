"""
Integration: the scorecard QR patches against the real vanilla ROM.

`scorecard_qr` installs the screen with its credentials unfilled,
`qr_credentials` finishes it, and `qr_disable` turns it off for a guest ROM.
The last test is the one that matters — it reads the feature back out of a
*finished ROM file*, runs it in the simulator, and decodes the resulting screen
with zxing. That closes the loop from the patches to a scannable code.
"""

import random
from pathlib import Path

import pytest

from golf.core.patches import (
    COURSE_MIRRORS_PATCH,
    QR_DISABLE_PATCH,
    SCORECARD_QR_PATCH,
    PatchError,
    QrCredentials,
    mercy_tap_in_patches,
    practice_swing_patch,
    qr_credentials_patch,
    seeded_wind_patch,
)
from golf.core.patches.qr_credentials import PLACEHOLDERS, placeholder_offset
from golf.core.patches.scorecard_qr import TRAMPOLINE_CPU_ADDR
from golf.core.rom_writer import RomWriter
from golf.qr import encoder, nes, port, sample
from golf.qr.decode import DECODERS
from golf.qr.payload import RoundPayload
from golf.qr.port import layout
from golf.qr.port.sim import Machine
from golf.qr.render import render_screen

ROM_PATH = "nes_open_us.nes"
HEADER = 0x10

pytestmark = pytest.mark.skipif(
    not Path(ROM_PATH).exists(), reason=f"{ROM_PATH} not present"
)

CREDENTIALS = QrCredentials.random(random.Random(0xC0FFEE))
PATCH = SCORECARD_QR_PATCH


def mirrored_writer(out: Path) -> RomWriter:
    writer = RomWriter(ROM_PATH, str(out))
    COURSE_MIRRORS_PATCH.apply(writer)
    return writer


def unfinished_writer(out: Path) -> RomWriter:
    writer = mirrored_writer(out)
    PATCH.apply(writer)
    return writer


def apply_to_rom(tmp_path: Path, name: str = "qr.nes") -> Path:
    out = tmp_path / name
    unfinished_writer(out).save()
    return out


def changed_bytes(before: bytes, after: bytes) -> set[int]:
    assert len(before) == len(after)
    return {index for index in range(len(before)) if before[index] != after[index]}


def file_range(prg_offset: int, length: int) -> range:
    return range(HEADER + prg_offset, HEADER + prg_offset + length)


# --------------------------------------------------------------------------
# scorecard_qr
# --------------------------------------------------------------------------


def test_the_vanilla_rom_has_the_hook_site_this_patch_expects() -> None:
    writer = RomWriter(ROM_PATH, "/dev/null")
    assert PATCH.can_apply(writer)


def test_requires_course_mirrors(tmp_path) -> None:
    writer = RomWriter(ROM_PATH, str(tmp_path / "vanilla.nes"))
    with pytest.raises(PatchError, match="requires course_mirrors"):
        PATCH.apply(writer)
    assert not PATCH.is_applied(writer)


def test_apply_and_reload(tmp_path) -> None:
    out = apply_to_rom(tmp_path)
    reloaded = RomWriter(str(out), str(tmp_path / "unused.nes"))
    assert PATCH.is_applied(reloaded)
    assert not PATCH.can_apply(reloaded)


def test_applying_twice_changes_nothing(tmp_path) -> None:
    once = apply_to_rom(tmp_path, "once.nes")
    writer = RomWriter(str(once), str(tmp_path / "twice.nes"))
    PATCH.apply(writer)
    writer.save()
    assert (tmp_path / "twice.nes").read_bytes() == once.read_bytes()


def test_only_the_three_regions_change(tmp_path) -> None:
    mirrored = mirrored_writer(tmp_path / "mirrored.nes")
    mirrored.save()
    before = (tmp_path / "mirrored.nes").read_bytes()
    patched = apply_to_rom(tmp_path).read_bytes()

    allowed = set()
    for offset, length in (
        (PATCH.image_offset, len(PATCH.image)),
        (PATCH.trampoline_offset, len(PATCH.trampoline)),
        (PATCH.splice_offset, 2),
    ):
        allowed.update(file_range(offset, length))

    changed = changed_bytes(before, patched)
    assert changed <= allowed
    # The splice and the trampoline must actually have changed; the image may
    # coincide with vanilla data in a byte here and there but not overall.
    assert changed & set(file_range(PATCH.splice_offset, 2))
    assert len(changed) > len(PATCH.image) // 2


def test_the_patched_rom_carries_the_image_and_the_hook(tmp_path) -> None:
    out = apply_to_rom(tmp_path)
    reloaded = RomWriter(str(out), str(tmp_path / "unused.nes"))
    assert reloaded.read_prg(PATCH.image_offset, len(PATCH.image)) == PATCH.image
    assert reloaded.read_prg(PATCH.splice_offset, 2) == bytes(
        [TRAMPOLINE_CPU_ADDR & 0xFF, TRAMPOLINE_CPU_ADDR >> 8]
    )
    # The trampoline's far call names bank 2 and the routine's entry point.
    trampoline = reloaded.read_prg(PATCH.trampoline_offset, len(PATCH.trampoline))
    assert trampoline[6] == 2
    assert trampoline[7] | (trampoline[8] << 8) == PATCH.entry


def test_the_unfinished_rom_holds_the_fill_in_the_placeholders(tmp_path) -> None:
    writer = unfinished_writer(tmp_path / "unfinished.nes")
    for _, symbol, length in PLACEHOLDERS:
        assert (
            writer.read_prg(placeholder_offset(symbol), length)
            == bytes([port.PATCH_FILL]) * length
        )


def test_coexists_with_the_bank_13_tail_patches(tmp_path) -> None:
    """Mercy tap-in, seeded wind and practice swing fill bank 13's tail; the
    QR trampoline lives in the fixed bank instead."""
    writer = mirrored_writer(tmp_path / "all.nes")
    others = [
        *mercy_tap_in_patches(mercy_point=10),
        seeded_wind_patch("qr"),
        practice_swing_patch(),
    ]
    for other in others:
        other.apply(writer)

    assert PATCH.can_apply(writer)
    PATCH.apply(writer)

    assert PATCH.is_applied(writer)
    for other in others:
        assert other.is_applied(writer), other.name


def test_a_modified_hook_site_is_refused(tmp_path) -> None:
    writer = RomWriter(ROM_PATH, str(tmp_path / "stomped.nes"))
    writer.write_prg(PATCH.splice_offset, b"\x00\x00")
    assert not PATCH.can_apply(writer)
    assert not PATCH.is_applied(writer)


def test_used_trampoline_slots_are_refused(tmp_path) -> None:
    writer = mirrored_writer(tmp_path / "taken.nes")
    writer.write_prg(PATCH.trampoline_offset, b"\xea")
    assert not PATCH.can_apply(writer)
    with pytest.raises(PatchError):
        PATCH.apply(writer)


# --------------------------------------------------------------------------
# qr_credentials
# --------------------------------------------------------------------------


def test_credentials_change_only_the_placeholders(tmp_path) -> None:
    unfinished = apply_to_rom(tmp_path, "unfinished.nes")
    writer = RomWriter(str(unfinished), str(tmp_path / "finished.nes"))
    qr_credentials_patch(CREDENTIALS).apply(writer)
    writer.save()

    allowed = set()
    for _, symbol, length in PLACEHOLDERS:
        allowed.update(file_range(placeholder_offset(symbol), length))
    changed = changed_bytes(
        unfinished.read_bytes(), (tmp_path / "finished.nes").read_bytes()
    )
    assert changed <= allowed
    assert len(changed) > len(allowed) // 2
    assert PATCH.is_applied(writer)
    assert qr_credentials_patch(CREDENTIALS).is_applied(writer)


def test_credentials_require_scorecard_qr(tmp_path) -> None:
    writer = mirrored_writer(tmp_path / "mirrored.nes")
    with pytest.raises(PatchError, match="requires scorecard_qr"):
        qr_credentials_patch(CREDENTIALS).apply(writer)


def test_a_finished_rom_refuses_other_credentials(tmp_path) -> None:
    writer = unfinished_writer(tmp_path / "finished.nes")
    qr_credentials_patch(CREDENTIALS).apply(writer)
    other = qr_credentials_patch(QrCredentials.random(random.Random(1)))
    assert not other.can_apply(writer)
    with pytest.raises(PatchError, match="qr_credentials"):
        other.apply(writer)


def test_finishing_twice_with_the_same_credentials_changes_nothing(tmp_path) -> None:
    writer = unfinished_writer(tmp_path / "once.nes")
    qr_credentials_patch(CREDENTIALS).apply(writer)
    writer.save()
    once = (tmp_path / "once.nes").read_bytes()

    again = RomWriter(str(tmp_path / "once.nes"), str(tmp_path / "twice.nes"))
    qr_credentials_patch(CREDENTIALS).apply(again)
    again.save()
    assert (tmp_path / "twice.nes").read_bytes() == once


# --------------------------------------------------------------------------
# qr_disable
# --------------------------------------------------------------------------


def test_disable_restores_the_vanilla_wait_and_nothing_else(tmp_path) -> None:
    unfinished = apply_to_rom(tmp_path, "unfinished.nes")
    writer = RomWriter(str(unfinished), str(tmp_path / "guest.nes"))
    QR_DISABLE_PATCH.apply(writer)
    writer.save()

    assert writer.read_prg(PATCH.splice_offset, 2) == PATCH.vanilla_splice_bytes
    changed = changed_bytes(
        unfinished.read_bytes(), (tmp_path / "guest.nes").read_bytes()
    )
    assert changed and changed <= set(file_range(PATCH.splice_offset, 2))
    assert writer.read_prg(PATCH.image_offset, len(PATCH.image)) == PATCH.image
    assert (
        writer.read_prg(PATCH.trampoline_offset, len(PATCH.trampoline))
        == PATCH.trampoline
    )

    # Neither applied nor applicable: a guest ROM cannot have the screen put back.
    assert not PATCH.is_applied(writer)
    assert not PATCH.can_apply(writer)


def test_disable_does_not_apply_to_vanilla(tmp_path) -> None:
    writer = RomWriter(ROM_PATH, str(tmp_path / "vanilla.nes"))
    assert not QR_DISABLE_PATCH.can_apply(writer)


def test_the_vanilla_splice_is_the_scorecard_wait() -> None:
    writer = RomWriter(ROM_PATH, "/dev/null")
    assert writer.read_prg(PATCH.splice_offset, 2) == QR_DISABLE_PATCH.patched


# --------------------------------------------------------------------------
# End to end
# --------------------------------------------------------------------------


def test_the_feature_in_the_finished_rom_draws_a_scannable_code(tmp_path) -> None:
    """
    Pull bank 2 back out of a finished ROM, run it, and scan what it draws.
    """
    unfinished = apply_to_rom(tmp_path, "unfinished.nes")
    finishing = RomWriter(str(unfinished), str(tmp_path / "finished.nes"))
    qr_credentials_patch(CREDENTIALS).apply(finishing)
    finishing.save()

    reloaded = RomWriter(str(tmp_path / "finished.nes"), str(tmp_path / "unused.nes"))
    image = reloaded.read_prg(PATCH.image_offset, len(PATCH.image))

    rng = random.Random(11)
    round_payload = sample.random_round(rng)

    machine = Machine()
    machine.write(layout.TABLE_ORIGIN, image)
    machine.set_round(
        [(hole.strokes, hole.putts) for hole in round_payload.holes],
        player=0,
        player_count=0,
    )
    machine.call(
        "QrShowCodes",
        on_frame=lambda frame: machine.poke(
            layout.CONTROLLER_CURRENT, layout.DISMISS_MASK
        ),
    )

    nametable = machine.bus.nametable()
    block = bytes(
        nametable[(layout.SCREEN_TILE_ROW + row) * 32 + layout.SCREEN_TILE_COL + col]
        for row in range(nes.TILE_COUNT)
        for col in range(nes.TILE_COUNT)
    )
    rows = nes.render_modules(
        machine.bus.pattern(layout.CHR_DEST, nes.QR_TILE_COUNT),
        block,
        base_tile=layout.TILE_BASE,
    )
    matrix = encoder.QrMatrix(bytearray(sum(rows, [])), 0)

    expected = RoundPayload(
        seed_id=CREDENTIALS.seed_id,
        player_id=CREDENTIALS.player_ids[0],
        holes=round_payload.holes,
    ).to_url(CREDENTIALS.keys[0])
    assert DECODERS["zxing"](render_screen(matrix)) == expected
