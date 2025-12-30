#!/usr/bin/env python3
"""
NES Open Tournament Golf - Course Data Dumper

Extracts course data from ROM and saves as human-readable JSON files.
"""

import sys
from pathlib import Path
from typing import Tuple

from golf.core.rom_reader import (
    RomReader,
    COURSES,
    HOLES_PER_COURSE,
    TOTAL_HOLES,
    TABLE_COURSE_HOLE_OFFSET,
    TABLE_COURSE_BANK_TERRAIN,
    TABLE_TERRAIN_START_PTR,
    TABLE_TERRAIN_END_PTR,
    TABLE_GREENS_PTR,
    TABLE_PAR,
    TABLE_HANDICAP,
    TABLE_DISTANCE_100,
    TABLE_DISTANCE_10,
    TABLE_DISTANCE_1,
    TABLE_SCROLL_LIMIT,
    TABLE_GREEN_X,
    TABLE_GREEN_Y,
    TABLE_TEE_X,
    TABLE_TEE_Y,
    TABLE_FLAG_Y_OFFSET,
    TABLE_FLAG_X_OFFSET,
)
from golf.core.decompressor import (
    TerrainDecompressor,
    GreensDecompressor,
    DecompressionStats,
    unpack_attributes,
    bcd_to_int,
)
from golf.core.palettes import (
    TERRAIN_ROW_WIDTH,
    ATTR_TOTAL_BYTES,
)
from golf.formats import compact_json as json
from golf.formats.hex_utils import format_hex_rows


def dump_course(rom: RomReader, course_idx: int, output_dir: Path) -> Tuple[DecompressionStats, DecompressionStats]:
    """Dump all holes for a single course. Returns (terrain_stats, greens_stats)."""
    course = COURSES[course_idx]
    course_dir = output_dir / course["name"]
    course_dir.mkdir(parents=True, exist_ok=True)

    # Read course-level data
    hole_offset = rom.read_fixed_byte(TABLE_COURSE_HOLE_OFFSET + course_idx)
    terrain_bank = rom.read_fixed_byte(TABLE_COURSE_BANK_TERRAIN + course_idx)

    # Greens use bank 3 based on the code analysis
    greens_bank = 3

    # Write course metadata
    course_meta = {
        "name": course["display_name"],
        "hole_offset": hole_offset,
        "terrain_bank": terrain_bank,
        "greens_bank": greens_bank
    }

    with open(course_dir / "course.json", 'w') as f:
        json.dump(course_meta, f, indent=2)

    print(f"\nDumping {course['display_name']} course (bank {terrain_bank})...")

    # Create decompressors
    terrain_decomp = TerrainDecompressor(rom)
    greens_decomp = GreensDecompressor(rom, greens_bank)

    # Create statistics collectors
    terrain_stats = DecompressionStats()
    greens_stats = DecompressionStats()

    # Dump each hole
    for hole_in_course in range(HOLES_PER_COURSE):
        hole_idx = hole_offset + hole_in_course  # Absolute hole index 0-53
        hole_num = hole_in_course + 1  # Display number 1-18

        # Set stats context
        terrain_stats.set_hole_context(course["name"], hole_num)
        greens_stats.set_hole_context(course["name"], hole_num)

        print(f"  Hole {hole_num}...", end=" ")

        # Read metadata from fixed bank tables
        par = rom.read_fixed_byte(TABLE_PAR + hole_idx)
        handicap = rom.read_fixed_byte(TABLE_HANDICAP + hole_idx)

        dist_100 = rom.read_fixed_byte(TABLE_DISTANCE_100 + hole_idx)
        dist_10 = rom.read_fixed_byte(TABLE_DISTANCE_10 + hole_idx)
        dist_1 = rom.read_fixed_byte(TABLE_DISTANCE_1 + hole_idx)
        distance = bcd_to_int(dist_100, dist_10, dist_1)

        scroll_limit = rom.read_fixed_byte(TABLE_SCROLL_LIMIT + hole_idx)
        green_x = rom.read_fixed_byte(TABLE_GREEN_X + hole_idx)
        green_y = rom.read_fixed_byte(TABLE_GREEN_Y + hole_idx)
        tee_x = rom.read_fixed_byte(TABLE_TEE_X + hole_idx)
        tee_y = rom.read_fixed_word(TABLE_TEE_Y + (hole_idx * 2))

        # Read flag positions (4 per hole)
        flag_positions = []
        for i in range(4):
            flag_y_off = rom.read_fixed_byte(TABLE_FLAG_Y_OFFSET + (hole_idx * 4) + i)
            flag_x_off = rom.read_fixed_byte(TABLE_FLAG_X_OFFSET + (hole_idx * 4) + i)
            flag_positions.append({"x_offset": flag_x_off, "y_offset": flag_y_off})

        # Read pointers
        terrain_start_ptr = rom.read_fixed_word(TABLE_TERRAIN_START_PTR + (hole_idx * 2))
        terrain_end_ptr = rom.read_fixed_word(TABLE_TERRAIN_END_PTR + (hole_idx * 2))
        greens_ptr = rom.read_fixed_word(TABLE_GREENS_PTR + (hole_idx * 2))

        # Calculate compressed terrain size
        terrain_compressed_size = terrain_end_ptr - terrain_start_ptr

        # Read compressed terrain data
        terrain_prg = rom.cpu_to_prg_switched(terrain_start_ptr, terrain_bank)
        terrain_compressed = rom.read_prg(terrain_prg, terrain_compressed_size)

        # Read attribute data (72 bytes after terrain)
        attr_prg = rom.cpu_to_prg_switched(terrain_end_ptr, terrain_bank)
        attr_bytes = rom.read_prg(attr_prg, ATTR_TOTAL_BYTES)

        # Decompress terrain
        terrain_rows = terrain_decomp.decompress(terrain_compressed, stats=terrain_stats)
        terrain_height = len(terrain_rows)

        # Unpack attributes
        attr_height = (terrain_height + 1) // 2  # Supertile rows
        attr_rows = unpack_attributes(attr_bytes, attr_height)

        # Read and decompress greens
        # In the game itself this routine runs until the *output* buffer is filled.
        # So we'll grab a generous buffer to pass to the decompress function.
        if hole_idx < TOTAL_HOLES - 1:
            next_greens_ptr = rom.read_fixed_word(TABLE_GREENS_PTR + ((hole_idx + 1) * 2))
            # Handle course boundaries where pointer table wraps
            if next_greens_ptr > greens_ptr:
                greens_size = next_greens_ptr - greens_ptr
            else:
                greens_size = 576  # (worst case: 1 byte = 1 tile)
        else:
            greens_size = 576  # Conservative fallback for last hole

        greens_prg = rom.cpu_to_prg_switched(greens_ptr, greens_bank)
        greens_compressed = rom.read_prg(greens_prg, greens_size)

        try:
            greens_rows = greens_decomp.decompress(greens_compressed, stats=greens_stats)
        except Exception as e:
            print(f"(greens decompress error: {e})")
            greens_rows = []

        # Build hole JSON
        hole_data = {
            "hole": hole_num,
            "par": par,
            "distance": distance,
            "handicap": handicap,
            "scroll_limit": scroll_limit,

            "green": {"x": green_x, "y": green_y},
            "tee": {"x": tee_x, "y": tee_y},
            "flag_positions": flag_positions,

            "terrain": {
                "width": TERRAIN_ROW_WIDTH,
                "height": terrain_height,
                "rows": format_hex_rows(terrain_rows)
            },

            "attributes": {
                "width": len(attr_rows[0]) if attr_rows else 11,
                "height": len(attr_rows),
                "rows": attr_rows
            },

            "greens": {
                "width": 24,
                "height": len(greens_rows),
                "rows": format_hex_rows(greens_rows)
            },

            "_debug": {
                "terrain_ptr": f"${terrain_start_ptr:04X}",
                "terrain_end_ptr": f"${terrain_end_ptr:04X}",
                "terrain_compressed_size": terrain_compressed_size,
                "greens_ptr": f"${greens_ptr:04X}",
                "attr_raw": ' '.join(f'{b:02X}' for b in attr_bytes)
            }
        }

        # Write hole file
        filename = f"hole_{hole_num:02d}.json"
        with open(course_dir / filename, 'w') as f:
            json.dump(hole_data, f, indent=2)

        print(f"OK ({terrain_height} rows, {terrain_compressed_size} bytes compressed)")

    return terrain_stats, greens_stats


def main():
    if len(sys.argv) < 2:
        print("Usage: python dump.py <rom_file> [output_dir]")
        print("\nDumps all course data from NES Open Tournament Golf ROM to JSON files.")
        sys.exit(1)

    rom_path = sys.argv[1]
    output_dir = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("courses")

    print(f"Loading ROM: {rom_path}")
    rom = RomReader(rom_path)

    print(f"Output directory: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    # Create global stats collectors
    global_terrain_stats = DecompressionStats()
    global_greens_stats = DecompressionStats()

    # Dump all three courses
    for course_idx in range(len(COURSES)):
        terrain_stats, greens_stats = dump_course(rom, course_idx, output_dir)

        # Merge into global stats
        global_terrain_stats.merge(terrain_stats)
        global_greens_stats.merge(greens_stats)

    # Write global metadata
    global_meta = {
        "rom": rom_path,
        "total_courses": len(COURSES),
        "total_holes": TOTAL_HOLES,
        "statistics": {
            "terrain": global_terrain_stats.to_dict(),
            "greens": global_greens_stats.to_dict()
        }
    }

    with open(output_dir / "meta.json", 'w') as f:
        json.dump(global_meta, f, indent=2)

    print(f"\nWrote statistics to {output_dir}/meta.json")
    print("\nDone!")


if __name__ == "__main__":
    main()
