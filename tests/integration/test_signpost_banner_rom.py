"""Integration tests: remove-course-banner patch against the real vanilla ROM."""

from pathlib import Path

import pytest

from golf.core.patches import remove_course_banner_patches
from golf.core.rom_writer import RomWriter

ROM_PATH = "nes_open_us.nes"

pytestmark = pytest.mark.skipif(
    not Path(ROM_PATH).exists(), reason=f"{ROM_PATH} not present"
)


def test_vanilla_rom_has_expected_bytes_at_every_site(tmp_path):
    writer = RomWriter(ROM_PATH, str(tmp_path / "out.nes"))
    for sub in remove_course_banner_patches().patches:
        assert sub.can_apply(writer), sub.name


def test_apply_and_reload(tmp_path):
    out = tmp_path / "no_banner.nes"
    writer = RomWriter(ROM_PATH, str(out))
    patch = remove_course_banner_patches()
    patch.apply(writer)
    writer.save()

    reloaded = RomWriter(str(out), str(tmp_path / "unused.nes"))
    assert patch.is_applied(reloaded)


def test_skip_draw_jumps_to_hole_number_section(tmp_path):
    """$AC5D should become JMP $AC84, the byte right after the original block."""
    writer = RomWriter(ROM_PATH, str(tmp_path / "unused.nes"))
    sub = remove_course_banner_patches().patches[0]
    sub.apply(writer)
    patched = writer.read_prg(sub.prg_offset, 3)
    assert patched[0] == 0x4C  # JMP
    target = patched[1] | (patched[2] << 8)
    assert target == 0xAC84


def test_object_count_and_pointer_skip_record_0(tmp_path):
    """After patching, AllocateObjectRecords reads 3 records starting at $B079
    (records 1-3, the HOLE/PAR/yards chain links) - record 0 ($B070, the
    banner-to-HOLE link) is untouched in ROM but no longer referenced."""
    writer = RomWriter(ROM_PATH, str(tmp_path / "unused.nes"))
    patch = remove_course_banner_patches()
    patch.apply(writer)

    count_offset = patch.patches[1].prg_offset
    assert writer.read_prg(count_offset, 1) == bytes([0x03])

    ptr_offset = patch.patches[2].prg_offset
    ptr = writer.read_prg(ptr_offset, 2)
    assert ptr[0] | (ptr[1] << 8) == 0xB079

    record0 = writer.read_prg(0x33070, 9)
    record1 = writer.read_prg(0x33079, 9)
    assert record0 == bytes([0x77, 0x4F, 0x01, 0x00, 0x00, 0xC7, 0x80, 0xA9, 0x80])
    assert record1 == bytes([0x77, 0x67, 0x01, 0x00, 0x00, 0xC7, 0x80, 0xA9, 0x80])
