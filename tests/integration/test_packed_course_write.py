"""
Integration tests for PackedCourseWriter.

Tests that writing courses with the packed writer produces correct data
that can be read back and verified.
"""

from pathlib import Path

import pytest

from golf.core import rom_utils
from golf.core.decompressor import (
    GreensDecompressor,
    TerrainDecompressor,
    bcd_to_int,
    unpack_attributes,
)
from golf.core.packed_course_writer import (
    BANK_TABLE_CPU_ADDR,
    BANK_TABLE_SIZE,
    PackedCourseWriter,
)
from golf.core.patches import COURSE3_MIRROR_PATCH, MULTI_BANK_CODE_PATCH
from golf.core.rom_reader import RomReader
from golf.core.rom_writer import RomWriter
from golf.formats.hole_data import HoleData


@pytest.fixture
def rom_path():
    """Path to test ROM file."""
    return "nes_open_us.nes"


@pytest.fixture
def japan_course_dir():
    """Path to Japan course data."""
    return Path("courses/japan")


@pytest.fixture
def us_course_dir():
    """Path to US course data."""
    return Path("courses/us")


def load_course_holes(course_dir: Path) -> list[HoleData]:
    """Load all 18 holes from a course directory."""
    holes = []
    for hole_num in range(1, rom_utils.HOLES_PER_COURSE + 1):
        hole_data = HoleData()
        hole_data.load(str(course_dir / f"hole_{hole_num:02d}.json"))
        holes.append(hole_data)
    return holes


def test_single_course_roundtrip(rom_path, japan_course_dir, tmp_path):
    """
    Test single course packed write: Load → Write → Read → Verify.

    Writes 1 course in packed mode and verifies all data roundtrips correctly.
    """
    # Load Japan course
    holes = load_course_holes(japan_course_dir)

    # Store original data for comparison
    original_terrain = [
        [row[:] for row in hole.terrain[:hole.terrain_height]]
        for hole in holes
    ]
    original_greens = [[row[:] for row in hole.greens] for hole in holes]
    original_attrs = [[row[:] for row in hole.attributes] for hole in holes]

    # Create output ROM
    output_rom = tmp_path / "packed_single.nes"

    # Write with packed writer
    rom_writer = RomWriter(rom_path, str(output_rom))
    packed_writer = PackedCourseWriter(rom_writer, apply_patches=True)
    stats = packed_writer.write_courses([holes], verbose=False)
    rom_writer.save()

    # Verify statistics
    assert stats.num_courses == 1
    assert stats.num_holes == 18
    assert len(stats.bank_assignments) == 18

    # Read back from new ROM
    new_rom = RomReader(str(output_rom))

    # Verify patches were applied
    assert MULTI_BANK_CODE_PATCH.is_applied(rom_writer)
    assert COURSE3_MIRROR_PATCH.is_applied(rom_writer)

    # Verify per-hole bank table exists
    # Bank table at PRG offset for $A700 in bank 3
    table_prg = 3 * 0x4000 + (BANK_TABLE_CPU_ADDR - 0x8000)
    bank_table = new_rom.read_prg(table_prg, BANK_TABLE_SIZE)

    # All holes should have a valid bank (0-2) in their doubled index
    for hole_idx in range(18):
        bank = bank_table[hole_idx * 2]
        assert bank in [0, 1, 2], f"Hole {hole_idx} has invalid bank {bank}"

    # Verify terrain for first and last hole
    for hole_idx in [0, 17]:
        terrain_ptr = new_rom.read_fixed_word(rom_utils.TABLE_TERRAIN_START_PTR + hole_idx * 2)
        terrain_end = new_rom.read_fixed_word(rom_utils.TABLE_TERRAIN_END_PTR + hole_idx * 2)

        # Get bank from table
        bank = bank_table[hole_idx * 2]

        terrain_prg = rom_utils.cpu_to_prg_switched(terrain_ptr, bank)
        terrain_size = terrain_end - terrain_ptr
        terrain_compressed = new_rom.read_prg(terrain_prg, terrain_size)

        terrain_decomp = TerrainDecompressor(new_rom)
        decompressed = terrain_decomp.decompress(terrain_compressed)

        # Compare terrain (up to terrain_height)
        terrain_height = holes[hole_idx].terrain_height
        for row_idx in range(terrain_height):
            assert decompressed[row_idx] == original_terrain[hole_idx][row_idx], (
                f"Hole {hole_idx} terrain row {row_idx} mismatch"
            )

    # Verify greens for first hole
    greens_ptr = new_rom.read_fixed_word(rom_utils.TABLE_GREENS_PTR + 0)
    greens_prg = rom_utils.cpu_to_prg_switched(greens_ptr, 3)

    # Read enough for greens (they're sequential, so use next pointer)
    next_ptr = new_rom.read_fixed_word(rom_utils.TABLE_GREENS_PTR + 2)
    greens_size = next_ptr - greens_ptr if next_ptr > greens_ptr else 400

    greens_compressed = new_rom.read_prg(greens_prg, greens_size)
    greens_decomp = GreensDecompressor(new_rom, 3)
    decompressed_greens = greens_decomp.decompress(greens_compressed)

    assert decompressed_greens == original_greens[0], "Hole 0 greens mismatch"


def test_two_course_roundtrip(rom_path, japan_course_dir, us_course_dir, tmp_path):
    """
    Test two course packed write: Load → Write → Read → Verify.

    Writes 2 courses in packed mode (36 holes) and verifies data integrity.
    """
    # Load both courses
    japan_holes = load_course_holes(japan_course_dir)
    us_holes = load_course_holes(us_course_dir)

    # Store original data
    all_original_terrain = []
    all_original_greens = []

    for holes in [japan_holes, us_holes]:
        for hole in holes:
            all_original_terrain.append(
                [row[:] for row in hole.terrain[:hole.terrain_height]]
            )
            all_original_greens.append([row[:] for row in hole.greens])

    # Create output ROM
    output_rom = tmp_path / "packed_two.nes"

    # Write with packed writer
    rom_writer = RomWriter(rom_path, str(output_rom))
    packed_writer = PackedCourseWriter(rom_writer, apply_patches=True)
    stats = packed_writer.write_courses([japan_holes, us_holes], verbose=False)
    rom_writer.save()

    # Verify statistics
    assert stats.num_courses == 2
    assert stats.num_holes == 36
    assert len(stats.bank_assignments) == 36

    # Verify banks are used (with 36 holes, should use multiple banks)
    banks_used = set(stats.bank_assignments)
    assert len(banks_used) >= 2, "Expected at least 2 banks used for 36 holes"

    # Read back from new ROM
    new_rom = RomReader(str(output_rom))

    # Get bank table
    table_prg = 3 * 0x4000 + (BANK_TABLE_CPU_ADDR - 0x8000)
    bank_table = new_rom.read_prg(table_prg, BANK_TABLE_SIZE)

    # Verify terrain decompression for a sample of holes
    terrain_decomp = TerrainDecompressor(new_rom)
    all_holes = japan_holes + us_holes

    for hole_idx in [0, 17, 18, 35]:  # First/last of each course
        terrain_ptr = new_rom.read_fixed_word(rom_utils.TABLE_TERRAIN_START_PTR + hole_idx * 2)
        terrain_end = new_rom.read_fixed_word(rom_utils.TABLE_TERRAIN_END_PTR + hole_idx * 2)

        bank = bank_table[hole_idx * 2]
        terrain_prg = rom_utils.cpu_to_prg_switched(terrain_ptr, bank)
        terrain_size = terrain_end - terrain_ptr
        terrain_compressed = new_rom.read_prg(terrain_prg, terrain_size)

        decompressed = terrain_decomp.decompress(terrain_compressed)

        terrain_height = all_holes[hole_idx].terrain_height
        for row_idx in range(terrain_height):
            assert decompressed[row_idx] == all_original_terrain[hole_idx][row_idx], (
                f"Hole {hole_idx} terrain row {row_idx} mismatch"
            )


def test_metadata_roundtrip(rom_path, japan_course_dir, tmp_path):
    """
    Test that metadata is correctly written for all holes.
    """
    # Load Japan course
    holes = load_course_holes(japan_course_dir)

    # Create output ROM
    output_rom = tmp_path / "packed_metadata.nes"

    # Write with packed writer
    rom_writer = RomWriter(rom_path, str(output_rom))
    packed_writer = PackedCourseWriter(rom_writer, apply_patches=True)
    packed_writer.write_courses([holes], verbose=False)
    rom_writer.save()

    # Read back and verify metadata
    new_rom = RomReader(str(output_rom))

    for hole_idx in range(18):
        hole = holes[hole_idx]
        metadata = hole.metadata

        # Par
        par = new_rom.read_fixed_byte(rom_utils.TABLE_PAR + hole_idx)
        assert par == metadata.get("par", 4), f"Hole {hole_idx} par mismatch"

        # Handicap
        handicap = new_rom.read_fixed_byte(rom_utils.TABLE_HANDICAP + hole_idx)
        assert handicap == metadata.get("handicap", 1), f"Hole {hole_idx} handicap mismatch"

        # Distance (BCD)
        dist_100 = new_rom.read_fixed_byte(rom_utils.TABLE_DISTANCE_100 + hole_idx)
        dist_10 = new_rom.read_fixed_byte(rom_utils.TABLE_DISTANCE_10 + hole_idx)
        dist_1 = new_rom.read_fixed_byte(rom_utils.TABLE_DISTANCE_1 + hole_idx)
        distance = bcd_to_int(dist_100, dist_10, dist_1)
        assert distance == metadata.get("distance", 400), f"Hole {hole_idx} distance mismatch"

        # Scroll limit
        scroll = new_rom.read_fixed_byte(rom_utils.TABLE_SCROLL_LIMIT + hole_idx)
        assert scroll == metadata.get("scroll_limit", 32), f"Hole {hole_idx} scroll mismatch"

        # Green position
        green_x = new_rom.read_fixed_byte(rom_utils.TABLE_GREEN_X + hole_idx)
        green_y = new_rom.read_fixed_byte(rom_utils.TABLE_GREEN_Y + hole_idx)
        assert green_x == hole.green_x, f"Hole {hole_idx} green_x mismatch"
        assert green_y == hole.green_y, f"Hole {hole_idx} green_y mismatch"

        # Tee position
        tee = metadata.get("tee", {"x": 0, "y": 0})
        tee_x = new_rom.read_fixed_byte(rom_utils.TABLE_TEE_X + hole_idx)
        tee_y = new_rom.read_fixed_word(rom_utils.TABLE_TEE_Y + hole_idx * 2)
        assert tee_x == tee["x"], f"Hole {hole_idx} tee_x mismatch"
        assert tee_y == tee["y"], f"Hole {hole_idx} tee_y mismatch"


def test_validation_passes_for_valid_courses(rom_path, japan_course_dir, tmp_path):
    """
    Test that validation passes for courses that will fit.
    """
    # Load Japan course
    holes = load_course_holes(japan_course_dir)

    # Create writer (validation doesn't need output)
    rom_writer = RomWriter(rom_path, str(tmp_path / "dummy.nes"))
    packed_writer = PackedCourseWriter(rom_writer, apply_patches=False)

    # Validate
    result = packed_writer.validate_courses([holes], verbose=False)

    assert result.valid is True
    assert result.stats is not None
    assert result.stats.num_courses == 1
    assert result.stats.num_holes == 18


def test_validation_two_courses(rom_path, japan_course_dir, us_course_dir, tmp_path):
    """
    Test validation for two courses.
    """
    japan_holes = load_course_holes(japan_course_dir)
    us_holes = load_course_holes(us_course_dir)

    rom_writer = RomWriter(rom_path, str(tmp_path / "dummy.nes"))
    packed_writer = PackedCourseWriter(rom_writer, apply_patches=False)

    result = packed_writer.validate_courses([japan_holes, us_holes], verbose=False)

    assert result.valid is True
    assert result.stats.num_courses == 2
    assert result.stats.num_holes == 36


def test_bank_table_values_match_allocations(rom_path, japan_course_dir, us_course_dir, tmp_path):
    """
    Test that the bank table values match the reported allocations.
    """
    japan_holes = load_course_holes(japan_course_dir)
    us_holes = load_course_holes(us_course_dir)

    output_rom = tmp_path / "packed_bank_check.nes"

    rom_writer = RomWriter(rom_path, str(output_rom))
    packed_writer = PackedCourseWriter(rom_writer, apply_patches=True)
    stats = packed_writer.write_courses([japan_holes, us_holes], verbose=False)
    rom_writer.save()

    # Read bank table
    new_rom = RomReader(str(output_rom))
    table_prg = 3 * 0x4000 + (BANK_TABLE_CPU_ADDR - 0x8000)
    bank_table = new_rom.read_prg(table_prg, BANK_TABLE_SIZE)

    # Verify each hole's bank matches stats
    for hole_idx in range(36):
        expected_bank = stats.bank_assignments[hole_idx]
        actual_bank = bank_table[hole_idx * 2]
        assert actual_bank == expected_bank, (
            f"Hole {hole_idx}: table has bank {actual_bank}, stats say {expected_bank}"
        )


def test_greens_sequential_in_bank3(rom_path, japan_course_dir, tmp_path):
    """
    Test that greens are written sequentially in bank 3.
    """
    holes = load_course_holes(japan_course_dir)

    output_rom = tmp_path / "packed_greens.nes"

    rom_writer = RomWriter(rom_path, str(output_rom))
    packed_writer = PackedCourseWriter(rom_writer, apply_patches=True)
    packed_writer.write_courses([holes], verbose=False)
    rom_writer.save()

    new_rom = RomReader(str(output_rom))

    # Read all greens pointers and verify they're increasing
    prev_ptr = 0
    for hole_idx in range(18):
        ptr = new_rom.read_fixed_word(rom_utils.TABLE_GREENS_PTR + hole_idx * 2)
        assert ptr > prev_ptr, f"Greens pointer for hole {hole_idx} not increasing"
        prev_ptr = ptr

    # Verify greens pointers are all in valid range
    for hole_idx in range(18):
        ptr = new_rom.read_fixed_word(rom_utils.TABLE_GREENS_PTR + hole_idx * 2)
        assert ptr >= 0x81C0, f"Greens pointer {ptr:04X} before data start"
        assert ptr < BANK_TABLE_CPU_ADDR, f"Greens pointer {ptr:04X} in bank table region"


def test_stats_bank_usage_reasonable(rom_path, japan_course_dir, us_course_dir, tmp_path):
    """
    Test that bank usage statistics are reasonable.
    """
    japan_holes = load_course_holes(japan_course_dir)
    us_holes = load_course_holes(us_course_dir)

    output_rom = tmp_path / "packed_stats.nes"

    rom_writer = RomWriter(rom_path, str(output_rom))
    packed_writer = PackedCourseWriter(rom_writer, apply_patches=True)
    stats = packed_writer.write_courses([japan_holes, us_holes], verbose=False)
    rom_writer.save()

    # Check that total terrain bytes matches sum of per-hole
    expected_total = sum(stats.terrain_bytes_per_hole) + len(stats.terrain_bytes_per_hole) * 72
    assert stats.total_terrain_bytes == expected_total

    # Check bank usage doesn't exceed capacity
    for bank in [0, 1, 2]:
        if bank in stats.bank_usage:
            assert stats.bank_usage[bank] <= stats.bank_capacity[bank], (
                f"Bank {bank} usage {stats.bank_usage[bank]} exceeds capacity {stats.bank_capacity[bank]}"
            )
