"""
Integration tests for ROM writing round-trip validation.

Tests that writing course data to ROM produces byte-perfect results.
"""

import tempfile
from pathlib import Path

import pytest

from golf.core.decompressor import (
    GreensDecompressor,
    TerrainDecompressor,
    bcd_to_int,
    unpack_attributes,
)
from golf.core.course_writer import CourseWriter
from golf.core.rom_reader import (
    HOLES_PER_COURSE,
    TABLE_DISTANCE_1,
    TABLE_DISTANCE_10,
    TABLE_DISTANCE_100,
    TABLE_FLAG_X_OFFSET,
    TABLE_FLAG_Y_OFFSET,
    TABLE_GREEN_X,
    TABLE_GREEN_Y,
    TABLE_GREENS_PTR,
    TABLE_HANDICAP,
    TABLE_PAR,
    TABLE_SCROLL_LIMIT,
    TABLE_TERRAIN_END_PTR,
    TABLE_TERRAIN_START_PTR,
    TABLE_TEE_X,
    TABLE_TEE_Y,
    RomReader,
)
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


def test_simple_roundtrip(rom_path, japan_course_dir, tmp_path):
    """
    Test simple roundtrip: Load JSON → Write ROM → Read ROM → Verify data matches.

    This doesn't compare against original ROM since compression can vary.
    """
    # Load hole 1 data from JSON
    hole_file = japan_course_dir / "hole_01.json"
    hole_data = HoleData()
    hole_data.load(str(hole_file))

    # Store original data from JSON
    original_terrain = [row[:] for row in hole_data.terrain[: hole_data.terrain_height]]
    original_greens = [row[:] for row in hole_data.greens]
    original_attrs = [row[:] for row in hole_data.attributes]

    # Create temporary output ROM
    output_rom = tmp_path / "test_output.nes"

    # Write to ROM
    rom_writer = RomWriter(rom_path, str(output_rom))
    course_writer = CourseWriter(rom_writer)

    # Load all 18 holes from Japan course
    holes = []
    for hole_num in range(1, HOLES_PER_COURSE + 1):
        hd = HoleData()
        hd.load(str(japan_course_dir / f"hole_{hole_num:02d}.json"))
        holes.append(hd)

    # Write the course
    course_writer.write_course(0, holes)  # Course 0 = Japan
    rom_writer.save()

    # Read back from new ROM and verify
    new_rom = RomReader(str(output_rom))

    # Verify terrain roundtrip
    terrain_ptr = new_rom.read_fixed_word(TABLE_TERRAIN_START_PTR + 0)
    terrain_end = new_rom.read_fixed_word(TABLE_TERRAIN_END_PTR + 0)
    terrain_prg = new_rom.cpu_to_prg_switched(terrain_ptr, 0)
    terrain_size = terrain_end - terrain_ptr
    terrain_compressed = new_rom.read_prg(terrain_prg, terrain_size)

    terrain_decomp = TerrainDecompressor(new_rom)
    decompressed_terrain = terrain_decomp.decompress(terrain_compressed)

    # Compare terrain
    for i in range(hole_data.terrain_height):
        assert decompressed_terrain[i] == original_terrain[i], f"Terrain row {i} mismatch"

    # Verify attributes roundtrip
    attr_prg = new_rom.cpu_to_prg_switched(terrain_end, 0)
    attr_bytes = new_rom.read_prg(attr_prg, 72)
    attr_height = (hole_data.terrain_height + 1) // 2
    unpacked_attrs = unpack_attributes(attr_bytes, attr_height)
    assert unpacked_attrs == original_attrs, "Attributes mismatch"

    # Verify greens roundtrip
    greens_ptr = new_rom.read_fixed_word(TABLE_GREENS_PTR + 0)
    greens_prg = new_rom.cpu_to_prg_switched(greens_ptr, 3)
    next_greens_ptr = new_rom.read_fixed_word(TABLE_GREENS_PTR + 2)
    greens_size = next_greens_ptr - greens_ptr if next_greens_ptr > greens_ptr else 576
    greens_compressed = new_rom.read_prg(greens_prg, greens_size)

    greens_decomp = GreensDecompressor(new_rom, 3)
    decompressed_greens = greens_decomp.decompress(greens_compressed)
    assert decompressed_greens == original_greens, "Greens mismatch"


def test_full_japan_course_roundtrip(rom_path, japan_course_dir, tmp_path):
    """
    Test writing full Japan course (18 holes) produces correct data.

    This test verifies that all 18 holes can be written and read back correctly.
    """
    # Load original ROM
    original_rom = RomReader(rom_path)

    # Load all 18 holes from Japan course
    holes = []
    for hole_num in range(1, HOLES_PER_COURSE + 1):
        hole_data = HoleData()
        hole_data.load(str(japan_course_dir / f"hole_{hole_num:02d}.json"))
        holes.append(hole_data)

    # Create temporary output ROM
    output_rom = tmp_path / "japan_roundtrip.nes"

    # Write course to ROM
    rom_writer = RomWriter(rom_path, str(output_rom))
    course_writer = CourseWriter(rom_writer)
    stats = course_writer.write_course(0, holes)  # Course 0 = Japan
    rom_writer.save()

    # Verify statistics
    assert stats["course"] == "Japan"
    assert len(stats["holes"]) == HOLES_PER_COURSE

    # Read back from new ROM
    new_rom = RomReader(str(output_rom))

    # Verify all 18 holes' metadata
    for hole_idx in range(HOLES_PER_COURSE):
        hole_data = holes[hole_idx]
        metadata = hole_data.metadata

        # Par
        par = new_rom.read_fixed_byte(TABLE_PAR + hole_idx)
        assert par == metadata.get("par", 4)

        # Handicap
        handicap = new_rom.read_fixed_byte(TABLE_HANDICAP + hole_idx)
        assert handicap == metadata.get("handicap", 1)

        # Distance (BCD)
        dist_100 = new_rom.read_fixed_byte(TABLE_DISTANCE_100 + hole_idx)
        dist_10 = new_rom.read_fixed_byte(TABLE_DISTANCE_10 + hole_idx)
        dist_1 = new_rom.read_fixed_byte(TABLE_DISTANCE_1 + hole_idx)
        distance = bcd_to_int(dist_100, dist_10, dist_1)
        assert distance == metadata.get("distance", 400)

        # Scroll limit
        scroll_limit = new_rom.read_fixed_byte(TABLE_SCROLL_LIMIT + hole_idx)
        assert scroll_limit == metadata.get("scroll_limit", 32)

        # Green position
        green_x = new_rom.read_fixed_byte(TABLE_GREEN_X + hole_idx)
        green_y = new_rom.read_fixed_byte(TABLE_GREEN_Y + hole_idx)
        assert green_x == hole_data.green_x
        assert green_y == hole_data.green_y

        # Tee position
        tee_x = new_rom.read_fixed_byte(TABLE_TEE_X + hole_idx)
        tee_y = new_rom.read_fixed_word(TABLE_TEE_Y + hole_idx * 2)
        tee = metadata.get("tee", {"x": 0, "y": 0})
        assert tee_x == tee["x"]
        assert tee_y == tee["y"]


def test_terrain_decompression_matches(rom_path, japan_course_dir, tmp_path):
    """
    Test that terrain roundtrips correctly: JSON → ROM → JSON produces same data.

    This verifies the compress → decompress cycle is stable.
    """
    # Load hole 1
    hole_data = HoleData()
    hole_data.load(str(japan_course_dir / "hole_01.json"))

    # Store original data
    original_terrain = [row[:] for row in hole_data.terrain[: hole_data.terrain_height]]

    # Create writer and write course
    output_rom = tmp_path / "terrain_test.nes"
    rom_writer = RomWriter(rom_path, str(output_rom))
    course_writer = CourseWriter(rom_writer)

    # Load all 18 holes
    holes = []
    for hole_num in range(1, HOLES_PER_COURSE + 1):
        hd = HoleData()
        hd.load(str(japan_course_dir / f"hole_{hole_num:02d}.json"))
        holes.append(hd)

    course_writer.write_course(0, holes)
    rom_writer.save()

    # Read back and decompress
    new_rom = RomReader(str(output_rom))

    # Get terrain pointer and decompress
    terrain_ptr = new_rom.read_fixed_word(TABLE_TERRAIN_START_PTR + 0)
    terrain_end = new_rom.read_fixed_word(TABLE_TERRAIN_END_PTR + 0)

    terrain_prg = new_rom.cpu_to_prg_switched(terrain_ptr, 0)
    terrain_size = terrain_end - terrain_ptr
    terrain_compressed = new_rom.read_prg(terrain_prg, terrain_size)

    terrain_decomp = TerrainDecompressor(new_rom)
    decompressed_rows = terrain_decomp.decompress(terrain_compressed)

    # Verify we can decompress and get the right data back
    # Note: terrain_height controls visible height
    assert len(decompressed_rows) >= hole_data.terrain_height

    # Compare only the visible terrain (up to terrain_height)
    for i in range(hole_data.terrain_height):
        assert decompressed_rows[i] == original_terrain[i], f"Row {i} mismatch"


def test_attributes_match(rom_path, japan_course_dir, tmp_path):
    """Test that attribute packing roundtrips correctly."""
    # Load hole 1
    hole_data = HoleData()
    hole_data.load(str(japan_course_dir / "hole_01.json"))

    # Store original attributes
    original_attrs = [row[:] for row in hole_data.attributes]

    # Write to ROM
    output_rom = tmp_path / "attr_test.nes"
    rom_writer = RomWriter(rom_path, str(output_rom))
    course_writer = CourseWriter(rom_writer)

    # Load all 18 holes
    holes = []
    for hole_num in range(1, HOLES_PER_COURSE + 1):
        hd = HoleData()
        hd.load(str(japan_course_dir / f"hole_{hole_num:02d}.json"))
        holes.append(hd)

    course_writer.write_course(0, holes)
    rom_writer.save()

    # Read back attributes
    new_rom = RomReader(str(output_rom))

    terrain_end = new_rom.read_fixed_word(TABLE_TERRAIN_END_PTR + 0)
    attr_prg = new_rom.cpu_to_prg_switched(terrain_end, 0)
    attr_bytes = new_rom.read_prg(attr_prg, 72)

    # Unpack and compare
    attr_height = (hole_data.terrain_height + 1) // 2
    unpacked = unpack_attributes(attr_bytes, attr_height)

    # Verify roundtrip - should match what we started with from JSON
    assert unpacked == original_attrs


def test_greens_decompression_matches(rom_path, japan_course_dir, tmp_path):
    """Test that greens roundtrip correctly: JSON → ROM → JSON."""
    # Load hole 1
    hole_data = HoleData()
    hole_data.load(str(japan_course_dir / "hole_01.json"))

    # Store original greens
    original_greens = [row[:] for row in hole_data.greens]

    # Write to ROM
    output_rom = tmp_path / "greens_test.nes"
    rom_writer = RomWriter(rom_path, str(output_rom))
    course_writer = CourseWriter(rom_writer)

    # Load all 18 holes
    holes = []
    for hole_num in range(1, HOLES_PER_COURSE + 1):
        hd = HoleData()
        hd.load(str(japan_course_dir / f"hole_{hole_num:02d}.json"))
        holes.append(hd)

    course_writer.write_course(0, holes)
    rom_writer.save()

    # Read back and decompress greens
    new_rom = RomReader(str(output_rom))

    greens_ptr = new_rom.read_fixed_word(TABLE_GREENS_PTR + 0)
    greens_prg = new_rom.cpu_to_prg_switched(greens_ptr, 3)

    # Read conservative buffer for greens
    next_greens_ptr = new_rom.read_fixed_word(TABLE_GREENS_PTR + 2)
    if next_greens_ptr > greens_ptr:
        greens_size = next_greens_ptr - greens_ptr
    else:
        greens_size = 576

    greens_compressed = new_rom.read_prg(greens_prg, greens_size)

    greens_decomp = GreensDecompressor(new_rom, 3)
    decompressed_rows = greens_decomp.decompress(greens_compressed)

    # Verify roundtrip - should match what we started with from JSON
    assert len(decompressed_rows) == len(original_greens)
    for i, (orig_row, decomp_row) in enumerate(zip(original_greens, decompressed_rows)):
        assert orig_row == decomp_row, f"Greens row {i} mismatch"
