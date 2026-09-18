#!/usr/bin/env python3
"""
NES Open Tournament Golf - ROM Writer

Writes one course from JSON files back to ROM.

Applies the course patch (golf/core/patches/courses.py), which packs the
course's terrain across banks 0 and 1, after the code patches it requires:
multi-bank lookup, course mirrors and attribute streaming.
"""

import argparse
import sys
from pathlib import Path

from golf.core import rom_utils
from golf.core.course_validation import InvalidTileError
from golf.core.instrumented_io import InstrumentedRomWriter
from golf.core.patches import CoursePatch, CourseWriteStats, PatchError
from golf.core.rom_writer import BankOverflowError, RomWriter
from golf.formats.hole_data import HoleData


def load_course_data(course_dir: Path) -> list[HoleData]:
    """
    Load all 18 hole JSON files from course directory.

    Args:
        course_dir: Directory containing hole_01.json through hole_18.json

    Returns:
        List of 18 HoleData objects

    Raises:
        FileNotFoundError: If any hole file is missing
    """
    holes = []
    missing_files = []

    for hole_num in range(1, rom_utils.HOLES_PER_COURSE + 1):
        hole_file = course_dir / f"hole_{hole_num:02d}.json"
        if not hole_file.exists():
            missing_files.append(f"hole_{hole_num:02d}.json")
        else:
            hole_data = HoleData()
            hole_data.load(str(hole_file))
            holes.append(hole_data)

    if missing_files:
        raise FileNotFoundError(
            f"Missing hole files in {course_dir}: {', '.join(missing_files)}"
        )

    return holes


def print_stats(stats: CourseWriteStats) -> None:
    """Print how the holes were packed."""
    print()
    print("Bank usage:")
    for bank, capacity in stats.bank_capacity.items():
        used = stats.bank_usage.get(bank, 0)
        pct = (used / capacity * 100) if capacity > 0 else 0
        print(f"  Bank {bank}: {used:,} / {capacity:,} bytes ({pct:.1f}%)")

    total_capacity = sum(stats.bank_capacity.values())
    total_pct = (
        (stats.total_terrain_bytes / total_capacity * 100) if total_capacity > 0 else 0
    )
    print(
        f"  Total:  {stats.total_terrain_bytes:,} / {total_capacity:,} bytes ({total_pct:.1f}%)"
    )
    print()
    print(f"Greens: {stats.total_greens_bytes:,} bytes")


def report_requirements(patch: CoursePatch, rom_writer: RomWriter) -> bool:
    """Print each required patch's state. Returns False if any is blocked."""
    ok = True
    for required in patch.requires:
        if required.is_applied(rom_writer):
            state = "already applied"
        elif required.can_apply(rom_writer):
            state = "pending"
        else:
            state = "CONFLICT (unexpected bytes)"
            ok = False
        print(f"  [{state:27}] {required.name}: {required.description}")
    return ok


def main():
    parser = argparse.ArgumentParser(
        description="Write one course from JSON files back to NES ROM",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Write a course (all 3 course slots play it)
  golf-write rom.nes courses/japan/ -o output.nes

  # Validate without writing
  golf-write rom.nes courses/japan/ --validate-only --verbose
""",
    )

    parser.add_argument("rom_file", help="Source ROM file (read-only)")
    parser.add_argument(
        "course_dir", help="Course directory (hole_01.json-hole_18.json)"
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Output ROM file (default: <rom>.modified.nes)",
        default=None,
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Compress and validate without writing",
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Show detailed compression statistics"
    )
    parser.add_argument(
        "--trace-io",
        action="store_true",
        help="Output ROM write trace to write_trace.json",
    )

    args = parser.parse_args()

    rom_path = Path(args.rom_file)
    if not rom_path.exists():
        print(f"Error: ROM file not found: {rom_path}")
        sys.exit(1)

    course_dir = Path(args.course_dir)
    if not course_dir.is_dir():
        print(f"Error: Course directory not found: {course_dir}")
        sys.exit(1)

    output_path = args.output or str(rom_path.with_suffix("")) + ".modified.nes"

    try:
        print(f"ROM: {rom_path}")
        holes = load_course_data(course_dir)
        print(f"Loaded {len(holes)} holes from {course_dir}")
        print("Compressing course data...")
        patch = CoursePatch(holes)
        if args.verbose:
            print_stats(patch.stats)

        if args.trace_io and not args.validate_only:
            rom_writer = InstrumentedRomWriter(str(rom_path), output_path)
        else:
            rom_writer = RomWriter(str(rom_path), output_path)

        print()
        print("Required patches:")
        requirements_ok = report_requirements(patch, rom_writer)

        if args.validate_only:
            if not requirements_ok:
                print(
                    "Validation FAILED: a required patch cannot be applied to this ROM"
                )
                sys.exit(1)
            print("Validation PASSED - course will fit in ROM")
            sys.exit(0)

        for required in patch.requires:
            required.apply(rom_writer)
        patch.apply(rom_writer)
        rom_writer.save()

        if isinstance(rom_writer, InstrumentedRomWriter):
            trace_path = str(Path(output_path).parent / "write_trace.json")
            rom_writer.write_trace(trace_path)

        print()
        print("Done!")

    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)
    except InvalidTileError as e:
        print(f"Error: {e}")
        sys.exit(1)
    except BankOverflowError as e:
        print(f"Error: {e}")
        print()
        print("Course data is too large to fit.")
        print("Try simplifying course designs to reduce compressed size.")
        sys.exit(1)
    except PatchError as e:
        print(f"Patch error: {e}")
        sys.exit(1)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
