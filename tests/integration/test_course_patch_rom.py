"""
Integration tests for the course patch against the real ROM.

Writes a course, reads it back and checks the data roundtrips.
"""

from pathlib import Path

import pytest

from golf.core import rom_utils
from golf.core.decompressor import GreensDecompressor, TerrainDecompressor, bcd_to_int
from golf.core.patches import CoursePatch, PatchError
from golf.core.patches.course import BANK_TABLE_CPU_ADDR, BANK_TABLE_SIZE
from golf.core.rom_reader import RomReader
from golf.core.rom_writer import RomWriter
from golf.formats.hole_data import HoleData

ROM_PATH = "nes_open_us.nes"


def load_course_holes(course_dir: str) -> list[HoleData]:
    """Load all 18 holes from a course directory."""
    holes = []
    for hole_num in range(1, rom_utils.HOLES_PER_COURSE + 1):
        hole_data = HoleData()
        hole_data.load(str(Path(course_dir) / f"hole_{hole_num:02d}.json"))
        holes.append(hole_data)
    return holes


def write_rom(holes: list[HoleData], output: Path) -> tuple[CoursePatch, RomReader]:
    patch = CoursePatch(holes)
    rom_writer = RomWriter(ROM_PATH, str(output))
    for required in patch.requires:
        required.apply(rom_writer)
    patch.apply(rom_writer)
    rom_writer.save()
    return patch, RomReader(str(output))


def read_bank_table(rom: RomReader) -> bytes:
    return rom.read_prg(rom_utils.cpu_to_prg_switched(BANK_TABLE_CPU_ADDR, 3), BANK_TABLE_SIZE)


def assert_terrain_roundtrips(rom: RomReader, holes: list[HoleData]):
    bank_table = read_bank_table(rom)
    terrain_decomp = TerrainDecompressor(rom)
    for hole_idx, hole in enumerate(holes):
        start = rom.read_fixed_word(rom_utils.TABLE_TERRAIN_START_PTR + hole_idx * 2)
        end = rom.read_fixed_word(rom_utils.TABLE_TERRAIN_END_PTR + hole_idx * 2)
        bank = bank_table[hole_idx * 2]
        assert bank in (0, 1), f"Hole {hole_idx} in bank {bank}"
        compressed = rom.read_prg(rom_utils.cpu_to_prg_switched(start, bank), end - start)

        decompressed = terrain_decomp.decompress(compressed)
        for row in range(hole.terrain_height):
            assert decompressed[row] == hole.terrain[row], (
                f"Hole {hole_idx} terrain row {row} mismatch"
            )


@pytest.fixture(scope="module")
def japan_holes():
    return load_course_holes("courses/japan")


def test_course_roundtrip(japan_holes, tmp_path):
    patch, rom = write_rom(japan_holes, tmp_path / "course.nes")

    writer = RomWriter(str(tmp_path / "course.nes"), "/dev/null")
    assert patch.is_applied(writer)
    for required in patch.requires:
        assert required.is_applied(writer)

    assert_terrain_roundtrips(rom, japan_holes)

    bank_table = read_bank_table(rom)
    for hole_idx in range(18):
        assert bank_table[hole_idx * 2] == patch.stats.bank_assignments[hole_idx]

    greens_ptr = rom.read_fixed_word(rom_utils.TABLE_GREENS_PTR)
    next_ptr = rom.read_fixed_word(rom_utils.TABLE_GREENS_PTR + 2)
    compressed = rom.read_prg(rom_utils.cpu_to_prg_switched(greens_ptr, 3), next_ptr - greens_ptr)
    assert GreensDecompressor(rom, 3).decompress(compressed) == japan_holes[0].greens


def test_tall_course_roundtrip_spills_into_bank_1(tmp_path):
    holes = load_course_holes("courses/jp/jp_uk")
    patch, rom = write_rom(holes, tmp_path / "tall.nes")

    assert set(patch.stats.bank_assignments) == {0, 1}
    assert_terrain_roundtrips(rom, holes)


def test_metadata_roundtrip(japan_holes, tmp_path):
    _, rom = write_rom(japan_holes, tmp_path / "metadata.nes")

    for hole_idx, hole in enumerate(japan_holes):
        metadata = hole.metadata

        assert rom.read_fixed_byte(rom_utils.TABLE_PAR + hole_idx) == metadata.get("par", 4)
        assert rom.read_fixed_byte(rom_utils.TABLE_HANDICAP + hole_idx) == metadata.get(
            "handicap", 1
        )

        distance = bcd_to_int(
            rom.read_fixed_byte(rom_utils.TABLE_DISTANCE_100 + hole_idx),
            rom.read_fixed_byte(rom_utils.TABLE_DISTANCE_10 + hole_idx),
            rom.read_fixed_byte(rom_utils.TABLE_DISTANCE_1 + hole_idx),
        )
        assert distance == metadata.get("distance", 400)

        assert rom.read_fixed_byte(rom_utils.TABLE_SCROLL_LIMIT + hole_idx) == metadata.get(
            "scroll_limit", 32
        )
        assert rom.read_fixed_byte(rom_utils.TABLE_GREEN_X + hole_idx) == hole.green_x
        assert rom.read_fixed_byte(rom_utils.TABLE_GREEN_Y + hole_idx) == hole.green_y

        tee = metadata.get("tee", {"x": 0, "y": 0})
        assert rom.read_fixed_byte(rom_utils.TABLE_TEE_X + hole_idx) == tee["x"]
        assert rom.read_fixed_word(rom_utils.TABLE_TEE_Y + hole_idx * 2) == tee["y"]


def test_greens_sequential_in_bank3(japan_holes, tmp_path):
    _, rom = write_rom(japan_holes, tmp_path / "greens.nes")

    pointers = [rom.read_fixed_word(rom_utils.TABLE_GREENS_PTR + i * 2) for i in range(18)]
    assert pointers == sorted(set(pointers))
    assert pointers[0] >= 0x81C0
    assert pointers[-1] < BANK_TABLE_CPU_ADDR


def test_leaves_bank_2_and_holes_18_to_53_alone(tmp_path):
    """Bank 2's terrain region and the metadata for holes 18-53 stay free for
    other patches (the QR image, seeded wind's seed table)."""
    holes = load_course_holes("courses/jp/jp_uk")
    _, rom = write_rom(holes, tmp_path / "course.nes")
    vanilla = RomReader(ROM_PATH)

    bank2 = rom_utils.cpu_to_prg_switched(0x837F, 2)
    assert rom.read_prg(bank2, 0xA554 - 0x837F) == vanilla.read_prg(bank2, 0xA554 - 0x837F)

    for table, width in [
        (rom_utils.TABLE_PAR, 1),
        (rom_utils.TABLE_TERRAIN_START_PTR, 2),
        (rom_utils.TABLE_GREENS_PTR, 2),
        (rom_utils.TABLE_FLAG_X_OFFSET, 4),
    ]:
        start = table + 18 * width
        assert rom.read_fixed(start, 36 * width) == vanilla.read_fixed(start, 36 * width)


def test_refuses_vanilla_rom_without_requirements(japan_holes, tmp_path):
    patch = CoursePatch(japan_holes)
    writer = RomWriter(ROM_PATH, str(tmp_path / "unused.nes"))
    with pytest.raises(PatchError, match="multi_bank_lookup, course_mirrors, attr_streaming"):
        patch.apply(writer)
