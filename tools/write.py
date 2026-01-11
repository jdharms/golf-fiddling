#!/usr/bin/env python3
"""
NES Open Tournament Golf - ROM Writer

Writes course data from JSON files back to ROM.
"""

import argparse
import sys
from pathlib import Path

from golf.core.rom_reader import COURSES, HOLES_PER_COURSE, PRG_BANK_SIZE
from golf.core.rom_writer import BankOverflowError, RomWriter
from golf.formats import compact_json as json
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

    for hole_num in range(1, HOLES_PER_COURSE + 1):
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


def detect_course_index(course_dir: Path) -> int:
    """
    Auto-detect course index from course.json.

    Args:
        course_dir: Course directory

    Returns:
        Course index (0-2)
    """
    course_meta = course_dir / "course.json"
    if course_meta.exists():
        with open(course_meta) as f:
            meta = json.load(f)
            hole_offset = meta.get("hole_offset", 0)
            return hole_offset // HOLES_PER_COURSE
    return 0


def validate_only(
    rom_path: str, course_dir: Path, course_idx: int, verbose: bool
) -> bool:
    """
    Validate that course data will fit without writing.

    Args:
        rom_path: ROM file path
        course_dir: Course directory
        course_idx: Course index (0-2)
        verbose: Show detailed statistics

    Returns:
        True if validation passes, False otherwise
    """
    print(f"Validation mode: checking if course will fit...")
    print(f"ROM: {rom_path}")
    print(f"Course: {course_dir} (index {course_idx})")
    print()

    try:
        # Load course data
        holes = load_course_data(course_dir)

        # Create writer
        writer = RomWriter(rom_path, "/dev/null")  # Dummy output

        # Attempt to write (this compresses and validates)
        stats = writer.write_course(course_idx, holes)

        # Report statistics
        print(f"Course: {stats['course']}")
        print(
            f"Terrain bank usage: {stats['terrain_bank_usage']:,} / {PRG_BANK_SIZE:,} bytes "
            f"({stats['terrain_bank_usage'] / PRG_BANK_SIZE * 100:.1f}%)"
        )
        print(f"Greens bank usage (this course): {stats['greens_bytes']:,} bytes")
        print()

        if verbose:
            print("Per-hole statistics:")
            for hole in stats["holes"]:
                print(
                    f"  Hole {hole['hole']:2d}: "
                    f"terrain {hole['terrain_bytes']:4d} bytes, "
                    f"greens {hole['greens_bytes']:3d} bytes"
                )
            print()

        print("Validation PASSED - course will fit in ROM")
        return True

    except BankOverflowError as e:
        print(f"Validation FAILED: {e}")
        return False
    except Exception as e:
        print(f"Validation FAILED: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Write course data from JSON files back to NES ROM"
    )

    parser.add_argument("rom_file", help="Source ROM file (read-only)")
    parser.add_argument(
        "course_dir", help="Course directory containing hole_01.json through hole_18.json"
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Output ROM file (default: <rom>.modified.nes)",
        default=None,
    )
    parser.add_argument(
        "-c",
        "--course",
        type=int,
        help="Course index 0-2 (default: auto-detect from course.json)",
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

    args = parser.parse_args()

    # Validate inputs
    rom_path = Path(args.rom_file)
    if not rom_path.exists():
        print(f"Error: ROM file not found: {rom_path}")
        sys.exit(1)

    course_dir = Path(args.course_dir)
    if not course_dir.is_dir():
        print(f"Error: Course directory not found: {course_dir}")
        sys.exit(1)

    # Determine course index
    if args.course is not None:
        course_idx = args.course
        if not 0 <= course_idx <= 2:
            print(f"Error: Course index must be 0-2, got {course_idx}")
            sys.exit(1)
    else:
        course_idx = detect_course_index(course_dir)

    # Determine output path
    if args.output:
        output_path = args.output
    else:
        output_path = str(rom_path.with_suffix("")) + ".modified.nes"

    # Handle validation mode
    if args.validate_only:
        success = validate_only(str(rom_path), course_dir, course_idx, args.verbose)
        sys.exit(0 if success else 1)

    # Normal write mode
    try:
        print(f"Loading ROM: {rom_path}")
        print(f"Loading course: {course_dir} ({COURSES[course_idx]['display_name']}, course index {course_idx})")
        print()

        # Load course data
        holes = load_course_data(course_dir)
        print(f"Loaded {len(holes)} holes")

        # Create writer
        writer = RomWriter(str(rom_path), output_path)

        # Compress and write course
        print("Compressing course data...")
        stats = writer.write_course(course_idx, holes)

        if args.verbose:
            print()
            print("Compression statistics:")
            for hole in stats["holes"]:
                print(
                    f"  Hole {hole['hole']:2d}: "
                    f"terrain {hole['terrain_bytes']:4d} bytes, "
                    f"greens {hole['greens_bytes']:3d} bytes"
                )

        print()
        print(
            f"Total terrain bank usage: {stats['terrain_bank_usage']:,} / {PRG_BANK_SIZE:,} bytes "
            f"({stats['terrain_bank_usage'] / PRG_BANK_SIZE * 100:.1f}%)"
        )
        print(
            f"Total greens bank usage (this course): {stats['greens_bytes']:,} bytes"
        )

        # Save ROM
        print()
        writer.save()
        print()
        print("Done!")

    except FileNotFoundError as e:
        print(f"Error: {e}")
        sys.exit(1)
    except BankOverflowError as e:
        print(f"Error: {e}")
        print()
        print("Course data is too large to fit in ROM bank.")
        print("Try simplifying course designs to reduce compressed size.")
        sys.exit(1)
    except ValueError as e:
        print(f"Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
