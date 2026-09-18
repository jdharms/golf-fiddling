#!/usr/bin/env python3
"""
NES Open Tournament Golf (Japan release / Mario Open Golf) - Course Data Dumper

Extracts course data from the JP ROM and saves as human-readable JSON files, in the same
schema golf-dump writes for the US ROM.
"""

import argparse
from pathlib import Path

from golf.core import jp_rom_utils
from golf.core.course_dump import DumpStats, dump_jp_courses, write_meta
from golf.core.rom_reader import RomReader


def main():
    parser = argparse.ArgumentParser(
        description="Dump JP course data from NES Open Tournament Golf (Mario Open Golf) ROM to JSON files"
    )
    parser.add_argument("rom_file", help="Source JP ROM file")
    parser.add_argument(
        "output_dir",
        nargs="?",
        default="courses/jp",
        help="Output directory (default: courses/jp)",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    stats = DumpStats.empty()
    dump_jp_courses(RomReader(args.rom_file), output_dir, stats, progress=print)
    write_meta(output_dir, args.rom_file, stats, len(jp_rom_utils.COURSES))
    print(f"Wrote statistics to {output_dir}/meta.json")


if __name__ == "__main__":
    main()
