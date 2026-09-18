#!/usr/bin/env python3
"""
NES Open Tournament Golf - Course Data Dumper

Extracts course data from ROM and saves as human-readable JSON files, with compression
statistics in meta.json. `golf-rehydrate` is the one-step way to dump and verify every
vanilla course; this is the research tool.
"""

import argparse
from pathlib import Path

from golf.core import rom_utils
from golf.core.course_dump import DumpStats, dump_us_courses, write_meta
from golf.core.instrumented_io import InstrumentedRomReader
from golf.core.rom_reader import RomReader


def main():
    parser = argparse.ArgumentParser(
        description="Dump all course data from NES Open Tournament Golf ROM to JSON files"
    )
    parser.add_argument("rom_file", help="Source ROM file")
    parser.add_argument(
        "output_dir",
        nargs="?",
        default="courses",
        help="Output directory (default: courses)",
    )
    parser.add_argument(
        "--trace-io",
        action="store_true",
        help="Output ROM read trace to read_trace.json",
    )
    args = parser.parse_args()

    output_dir = Path(args.output_dir)
    rom = (
        InstrumentedRomReader(args.rom_file)
        if args.trace_io
        else RomReader(args.rom_file)
    )
    stats = DumpStats.empty()
    dump_us_courses(rom, output_dir, stats, progress=print)
    write_meta(output_dir, args.rom_file, stats, len(rom_utils.COURSES))
    print(f"Wrote statistics to {output_dir}/meta.json")

    if isinstance(rom, InstrumentedRomReader):
        rom.write_trace(str(output_dir / "read_trace.json"))


if __name__ == "__main__":
    main()
