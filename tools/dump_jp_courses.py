#!/usr/bin/env python3
"""
NES Open Tournament Golf (Japan release / Mario Open Golf) - Course Data Dumper

Extracts course data from the JP ROM and saves as human-readable JSON files,
in the same schema tools/dump.py produces for the US ROM.
"""

import argparse
import sys
from pathlib import Path

from golf.core import jp_rom_utils, rom_utils
from golf.core.decompressor import (
    DecompressionStats,
    GreensDecompressor,
    TerrainDecompressor,
    bcd_to_int,
    unpack_attributes,
)
from golf.core.palettes import TERRAIN_ROW_WIDTH
from golf.core.rom_reader import RomReader
from golf.formats import compact_json as json
from golf.formats.hex_utils import format_hex_rows

GREENS_READ_SIZE = 576  # Conservative buffer; decompression stops at 24x24 output


def dump_jp_course(
    rom: RomReader, course_idx: int, output_dir: Path
) -> tuple[DecompressionStats, DecompressionStats]:
    """Dump all holes for a single JP course. Returns (terrain_stats, greens_stats)."""
    course = jp_rom_utils.COURSES[course_idx]
    course_dir = output_dir / course["name"]
    course_dir.mkdir(parents=True, exist_ok=True)

    hole_offset = rom.read_fixed_byte(jp_rom_utils.TABLE_COURSE_HOLE_OFFSET + course_idx)
    terrain_bank = rom.read_fixed_byte(jp_rom_utils.TABLE_COURSE_BANK_TERRAIN + course_idx)

    # JP stores greens in the same bank as terrain, not a shared bank like US
    greens_bank = terrain_bank

    course_meta = {
        "name": course["display_name"],
        "hole_offset": hole_offset,
        "terrain_bank": terrain_bank,
        "greens_bank": greens_bank,
    }

    with open(course_dir / "course.json", "w") as f:
        json.dump(course_meta, f, indent=2)

    print(f"\nDumping {course['display_name']} course (bank {terrain_bank})...")

    terrain_decomp = TerrainDecompressor(
        rom,
        horiz_addr=jp_rom_utils.TABLE_TERRAIN_HORIZ_TRANSITION,
        vert_addr=jp_rom_utils.TABLE_TERRAIN_VERT_CONTINUATION,
        dict_addr=jp_rom_utils.TABLE_TERRAIN_DICTIONARY,
    )
    greens_decomp = GreensDecompressor(
        rom,
        bank=greens_bank,
        horiz_addr=jp_rom_utils.TABLE_GREENS_HORIZ_TRANSITION,
        vert_addr=jp_rom_utils.TABLE_GREENS_VERT_CONTINUATION,
        dict_addr=jp_rom_utils.TABLE_GREENS_DICTIONARY,
        tables_in_fixed_bank=True,
    )

    terrain_stats = DecompressionStats()
    greens_stats = DecompressionStats()

    for hole_in_course in range(jp_rom_utils.HOLES_PER_COURSE):
        hole_idx = hole_offset + hole_in_course
        hole_num = hole_in_course + 1

        terrain_stats.set_hole_context(course["name"], hole_num)
        greens_stats.set_hole_context(course["name"], hole_num)

        print(f"  Hole {hole_num}...", end=" ")

        # Fixed-bank metadata
        par = rom.read_fixed_byte(jp_rom_utils.TABLE_PAR + hole_idx)
        handicap = rom.read_fixed_byte(jp_rom_utils.TABLE_HANDICAP + hole_idx)
        dist_100 = rom.read_fixed_byte(jp_rom_utils.TABLE_DISTANCE_100 + hole_idx)
        dist_10 = rom.read_fixed_byte(jp_rom_utils.TABLE_DISTANCE_10 + hole_idx)
        dist_1 = rom.read_fixed_byte(jp_rom_utils.TABLE_DISTANCE_1 + hole_idx)
        distance = bcd_to_int(dist_100, dist_10, dist_1)

        # Switched bank $0B metadata
        scroll_limit = jp_rom_utils.read_metadata_byte(
            rom, jp_rom_utils.TABLE_SCROLL_LIMIT, hole_idx
        )
        green_x = jp_rom_utils.read_metadata_byte(rom, jp_rom_utils.TABLE_GREEN_X, hole_idx)
        green_y = jp_rom_utils.read_metadata_byte(rom, jp_rom_utils.TABLE_GREEN_Y, hole_idx)
        tee_x = jp_rom_utils.read_metadata_byte(rom, jp_rom_utils.TABLE_TEE_X, hole_idx)
        tee_y = jp_rom_utils.read_metadata_word(rom, jp_rom_utils.TABLE_TEE_Y, hole_idx)

        flag_positions = []
        for i in range(4):
            flag_y_off = jp_rom_utils.read_metadata_byte(
                rom, jp_rom_utils.TABLE_FLAG_Y_OFFSET, hole_idx * 4 + i
            )
            flag_x_off = jp_rom_utils.read_metadata_byte(
                rom, jp_rom_utils.TABLE_FLAG_X_OFFSET, hole_idx * 4 + i
            )
            flag_positions.append({"x_offset": flag_x_off, "y_offset": flag_y_off})

        terrain_start_ptr = jp_rom_utils.read_metadata_word(
            rom, jp_rom_utils.TABLE_TERRAIN_START_PTR, hole_idx
        )
        terrain_end_ptr = jp_rom_utils.read_metadata_word(
            rom, jp_rom_utils.TABLE_TERRAIN_END_PTR, hole_idx
        )
        greens_ptr = jp_rom_utils.read_metadata_word(
            rom, jp_rom_utils.TABLE_GREENS_PTR, hole_idx
        )

        terrain_compressed_size = terrain_end_ptr - terrain_start_ptr
        terrain_prg = rom_utils.cpu_to_prg_switched(terrain_start_ptr, terrain_bank)
        terrain_compressed = rom.read_prg(terrain_prg, terrain_compressed_size)

        attr_prg = rom_utils.cpu_to_prg_switched(terrain_end_ptr, terrain_bank)
        attr_bytes = rom.read_prg(attr_prg, jp_rom_utils.JP_ATTR_BYTES)

        terrain_rows = terrain_decomp.decompress(terrain_compressed, stats=terrain_stats)
        terrain_height = len(terrain_rows)

        attr_height = (terrain_height + 1) // 2
        attr_rows = unpack_attributes(attr_bytes, attr_height)

        # Read a generous conservative buffer; decompression stops once it
        # has produced a full 24x24 tile grid, so overreading is harmless.
        greens_prg = rom_utils.cpu_to_prg_switched(greens_ptr, greens_bank)
        greens_compressed = rom.read_prg(greens_prg, GREENS_READ_SIZE)

        try:
            greens_rows = greens_decomp.decompress(greens_compressed, stats=greens_stats)
        except Exception as e:
            print(f"(greens decompress error: {e})")
            greens_rows = []

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
                "rows": format_hex_rows(terrain_rows),
            },
            "attributes": {
                "width": len(attr_rows[0]) if attr_rows else 11,
                "height": len(attr_rows),
                "rows": attr_rows,
            },
            "greens": {
                "width": 24,
                "height": len(greens_rows),
                "rows": format_hex_rows(greens_rows),
            },
            "_debug": {
                "terrain_ptr": f"${terrain_start_ptr:04X}",
                "terrain_end_ptr": f"${terrain_end_ptr:04X}",
                "terrain_compressed_size": terrain_compressed_size,
                "greens_ptr": f"${greens_ptr:04X}",
                "attr_raw": " ".join(f"{b:02X}" for b in attr_bytes),
            },
        }

        filename = f"hole_{hole_num:02d}.json"
        with open(course_dir / filename, "w") as f:
            json.dump(hole_data, f, indent=2)

        print(f"OK ({terrain_height} rows, {terrain_compressed_size} bytes compressed)")

    return terrain_stats, greens_stats


def main():
    parser = argparse.ArgumentParser(
        description="Dump JP course data from NES Open Tournament Golf (Mario Open Golf) ROM to JSON files"
    )
    parser.add_argument("rom_file", help="Source JP ROM file")
    parser.add_argument(
        "output_dir",
        nargs="?",
        default="courses_jp",
        help="Output directory (default: courses_jp)",
    )

    args = parser.parse_args()

    rom_path = args.rom_file
    output_dir = Path(args.output_dir)

    print(f"Loading ROM: {rom_path}")
    rom = RomReader(rom_path)

    print(f"Output directory: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    global_terrain_stats = DecompressionStats()
    global_greens_stats = DecompressionStats()

    for course_idx in range(len(jp_rom_utils.COURSES)):
        terrain_stats, greens_stats = dump_jp_course(rom, course_idx, output_dir)
        global_terrain_stats.merge(terrain_stats)
        global_greens_stats.merge(greens_stats)

    global_meta = {
        "rom": rom_path,
        "total_courses": len(jp_rom_utils.COURSES),
        "total_holes": jp_rom_utils.TOTAL_HOLES,
        "statistics": {
            "terrain": global_terrain_stats.to_dict(),
            "greens": global_greens_stats.to_dict(),
        },
    }

    with open(output_dir / "meta.json", "w") as f:
        json.dump(global_meta, f, indent=2)

    print(f"\nWrote statistics to {output_dir}/meta.json")
    print("\nDone!")


if __name__ == "__main__":
    main()
