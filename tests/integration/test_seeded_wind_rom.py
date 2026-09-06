"""Integration tests: seeded wind patch against the real vanilla ROM."""

from pathlib import Path

import pytest

from golf.core.patches import (
    COURSE3_MIRROR_PATCH,
    PatchError,
    mercy_tap_in_patches,
    seeded_wind_patch,
)
from golf.core.rom_writer import RomWriter

ROM_PATH = "nes_open_us.nes"

pytestmark = pytest.mark.skipif(
    not Path(ROM_PATH).exists(), reason=f"{ROM_PATH} not present"
)


def test_vanilla_rom_has_expected_bytes_at_every_site(tmp_path):
    writer = RomWriter(ROM_PATH, str(tmp_path / "out.nes"))
    patch = seeded_wind_patch("integration")
    for sub in patch.patches:
        assert sub.can_apply(writer), sub.name


def test_apply_and_reload(tmp_path):
    out = tmp_path / "seeded.nes"
    writer = RomWriter(ROM_PATH, str(out))
    COURSE3_MIRROR_PATCH.apply(writer)
    patch = seeded_wind_patch("integration")
    patch.apply(writer)
    writer.save()

    reloaded = RomWriter(str(out), str(tmp_path / "unused.nes"))
    assert patch.is_applied(reloaded)
    assert COURSE3_MIRROR_PATCH.is_applied(reloaded)


def test_coexists_with_mercy_tap_in(tmp_path):
    """Both patches use bank 13 tail padding; they must not overlap."""
    writer = RomWriter(ROM_PATH, str(tmp_path / "both.nes"))
    for p in mercy_tap_in_patches(mercy_point=10):
        p.apply(writer)
    patch = seeded_wind_patch("integration")
    assert patch.can_apply(writer)
    patch.apply(writer)
    assert patch.is_applied(writer)
    for p in mercy_tap_in_patches(mercy_point=10):
        assert p.is_applied(writer)


def test_reset_stub_untouched(tmp_path):
    writer = RomWriter(ROM_PATH, str(tmp_path / "stub.nes"))
    stub_before = writer.read_prg(0x37FF3, 13)
    seeded_wind_patch("integration").apply(writer)
    assert writer.read_prg(0x37FF3, 13) == stub_before
    assert stub_before[:1] == bytes([0x78])  # SEI


def test_conflict_when_trampoline_space_is_taken(tmp_path):
    writer = RomWriter(ROM_PATH, str(tmp_path / "conflict.nes"))
    writer.write_prg(0x37FAF, bytes([0x00]))
    with pytest.raises(PatchError):
        seeded_wind_patch("integration").apply(writer)
