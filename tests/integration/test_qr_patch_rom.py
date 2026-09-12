"""
Integration: the scorecard QR patch against the real vanilla ROM.

The last test is the one that matters — it reads the feature back out of the
*patched ROM file*, runs it in the simulator, and decodes the resulting screen
with zxing. That closes the loop from `golf-patch-qr` to a scannable code.
"""

import random
from pathlib import Path

import pytest

from golf.core.patches import QrCredentials, ScorecardQrPatch
from golf.core.patches.scorecard_qr import TRAMPOLINE_CPU_ADDR
from golf.core.rom_writer import RomWriter
from golf.qr import encoder, nes, sample
from golf.qr.decode import DECODERS
from golf.qr.payload import RoundPayload
from golf.qr.port import layout
from golf.qr.port.sim import Machine
from golf.qr.render import render_screen

ROM_PATH = "nes_open_us.nes"

pytestmark = pytest.mark.skipif(
    not Path(ROM_PATH).exists(), reason=f"{ROM_PATH} not present"
)

CREDENTIALS = QrCredentials.random(random.Random(0xC0FFEE))


def apply_to_rom(tmp_path: Path, name: str = "qr.nes") -> Path:
    out = tmp_path / name
    writer = RomWriter(ROM_PATH, str(out))
    ScorecardQrPatch(CREDENTIALS).apply(writer)
    writer.save()
    return out


def test_the_vanilla_rom_has_the_hook_site_this_patch_expects() -> None:
    writer = RomWriter(ROM_PATH, "/dev/null")
    assert ScorecardQrPatch(CREDENTIALS).can_apply(writer)


def test_apply_and_reload(tmp_path) -> None:
    out = apply_to_rom(tmp_path)
    patch = ScorecardQrPatch(CREDENTIALS)
    reloaded = RomWriter(str(out), str(tmp_path / "unused.nes"))
    assert patch.is_applied(reloaded)
    assert not patch.can_apply(reloaded)


def test_applying_twice_changes_nothing(tmp_path) -> None:
    once = apply_to_rom(tmp_path, "once.nes")
    writer = RomWriter(str(once), str(tmp_path / "twice.nes"))
    ScorecardQrPatch(CREDENTIALS).apply(writer)
    writer.save()
    assert (tmp_path / "twice.nes").read_bytes() == once.read_bytes()


def test_only_the_three_regions_change(tmp_path) -> None:
    vanilla = Path(ROM_PATH).read_bytes()
    patched = apply_to_rom(tmp_path).read_bytes()
    assert len(patched) == len(vanilla)

    patch = ScorecardQrPatch(CREDENTIALS)
    header = 0x10
    allowed = set()
    for offset, length in (
        (patch.image_offset, len(patch.image)),
        (patch.trampoline_offset, len(patch.trampoline)),
        (patch.splice_offset, 2),
    ):
        allowed.update(range(header + offset, header + offset + length))

    changed = {
        index for index in range(len(vanilla)) if vanilla[index] != patched[index]
    }
    assert changed <= allowed
    # The splice and the trampoline must actually have changed; the image may
    # coincide with vanilla data in a byte here and there but not overall.
    assert changed & set(
        range(header + patch.splice_offset, header + patch.splice_offset + 2)
    )
    assert len(changed) > len(patch.image) // 2


def test_the_patched_rom_carries_the_image_and_the_hook(tmp_path) -> None:
    out = apply_to_rom(tmp_path)
    patch = ScorecardQrPatch(CREDENTIALS)
    reloaded = RomWriter(str(out), str(tmp_path / "unused.nes"))
    assert reloaded.read_prg(patch.image_offset, len(patch.image)) == patch.image
    assert reloaded.read_prg(patch.splice_offset, 2) == bytes(
        [TRAMPOLINE_CPU_ADDR & 0xFF, TRAMPOLINE_CPU_ADDR >> 8]
    )
    # The trampoline's far call names bank 2 and the routine's entry point.
    trampoline = reloaded.read_prg(patch.trampoline_offset, len(patch.trampoline))
    assert trampoline[6] == 2
    assert trampoline[7] | (trampoline[8] << 8) == patch.entry


def test_a_modified_hook_site_is_refused(tmp_path) -> None:
    out = tmp_path / "stomped.nes"
    writer = RomWriter(ROM_PATH, str(out))
    patch = ScorecardQrPatch(CREDENTIALS)
    writer.write_prg(patch.splice_offset, b"\x00\x00")
    assert not patch.can_apply(writer)
    assert not patch.is_applied(writer)


def test_the_feature_in_the_patched_rom_draws_a_scannable_code(tmp_path) -> None:
    """
    Pull bank 2 back out of the patched ROM, run it, and scan what it draws.
    """
    out = apply_to_rom(tmp_path)
    patch = ScorecardQrPatch(CREDENTIALS)
    reloaded = RomWriter(str(out), str(tmp_path / "unused.nes"))
    image = reloaded.read_prg(patch.image_offset, len(patch.image))

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
