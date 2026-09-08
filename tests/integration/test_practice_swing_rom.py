"""Integration tests: practice swing patch against the real vanilla ROM."""

from pathlib import Path

import pytest

from golf.core.patches import (
    WRAM_EXPANSION_PATCH,
    mercy_tap_in_patches,
    practice_swing_patch,
    seeded_wind_patch,
    COURSE3_MIRROR_PATCH,
)
from golf.core.rom_writer import RomWriter

ROM_PATH = "nes_open_us.nes"

pytestmark = pytest.mark.skipif(
    not Path(ROM_PATH).exists(), reason=f"{ROM_PATH} not present"
)


def test_vanilla_rom_has_expected_bytes_at_every_site(tmp_path):
    writer = RomWriter(ROM_PATH, str(tmp_path / "out.nes"))
    for sub in practice_swing_patch().patches:
        assert sub.can_apply(writer), sub.name


def test_apply_and_reload(tmp_path):
    out = tmp_path / "practice.nes"
    writer = RomWriter(ROM_PATH, str(out))
    patch = practice_swing_patch()
    patch.apply(writer)
    writer.save()

    reloaded = RomWriter(str(out), str(tmp_path / "unused.nes"))
    assert patch.is_applied(reloaded)


def test_applies_on_top_of_wram_expansion(tmp_path):
    """The toggle routine lives in the tail of wram_expansion's $CA40 block."""
    writer = RomWriter(ROM_PATH, str(tmp_path / "wram_practice.nes"))
    WRAM_EXPANSION_PATCH.apply(writer)
    patch = practice_swing_patch()
    assert patch.can_apply(writer)
    patch.apply(writer)
    assert patch.is_applied(writer)
    assert WRAM_EXPANSION_PATCH.is_applied(writer)


def test_coexists_with_mercy_tap_in_and_seeded_wind(tmp_path):
    """All three share bank 13 tail padding; they must not overlap."""
    writer = RomWriter(ROM_PATH, str(tmp_path / "all.nes"))
    COURSE3_MIRROR_PATCH.apply(writer)
    for p in mercy_tap_in_patches(mercy_point=10):
        p.apply(writer)
    seeded = seeded_wind_patch("integration")
    seeded.apply(writer)

    patch = practice_swing_patch()
    assert patch.can_apply(writer)
    patch.apply(writer)

    assert patch.is_applied(writer)
    assert seeded.is_applied(writer)
    for p in mercy_tap_in_patches(mercy_point=10):
        assert p.is_applied(writer)


def test_reset_stub_untouched(tmp_path):
    """$BFF3 in every bank is the MMC1 reset stub."""
    out = tmp_path / "practice.nes"
    writer = RomWriter(ROM_PATH, str(out))
    practice_swing_patch().apply(writer)
    for bank in (8, 13):
        prg = bank * 0x4000 + 0x3FF3
        assert writer.read_prg(prg, 3) == bytes([0x78, 0xEE, 0xF4])


def test_only_expected_bytes_change(tmp_path):
    """No collateral edits: the diff must be exactly the patch spans."""
    out = tmp_path / "practice.nes"
    writer = RomWriter(ROM_PATH, str(out))
    patch = practice_swing_patch()
    patch.apply(writer)
    writer.save()

    before = Path(ROM_PATH).read_bytes()
    after = out.read_bytes()
    assert len(before) == len(after)

    header = 16
    changed = {i - header for i in range(header, len(before)) if before[i] != after[i]}
    covered = set()
    for p in patch.patches:
        covered |= set(range(p.prg_offset, p.prg_offset + len(p.patched)))
    assert changed <= covered


def test_no_patch_touches_the_seeded_wind_or_mercy_regions(tmp_path):
    """Bank 13 tail: mercy owns $BF83-$BFAE, seeded wind $BFAF-$BFBE."""
    reserved = set(range(0x37F83, 0x37FBF))
    for p in practice_swing_patch().patches:
        span = set(range(p.prg_offset, p.prg_offset + len(p.patched)))
        assert not (span & reserved), p.name
