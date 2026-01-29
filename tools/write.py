#!/usr/bin/env python3
"""
NES Open Tournament Golf - ROM Writer

Writes course data from JSON files back to ROM.

Uses packed multi-bank mode:
  - Writes 1 or 2 courses packed across 3 terrain banks
  - Uses per-hole bank lookup for maximum space efficiency
  - Automatically applies required ROM patches
"""

import argparse
import sys
from pathlib import Path

from golf.core.course_validation import InvalidTileError
from golf.core.packed_course_writer import PackedCourseWriter
from golf.core.patches import PatchError
from golf.core.rom_reader import HOLES_PER_COURSE
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


def validate_packed(
    rom_path: str, course_dirs: list[Path], verbose: bool
) -> bool:
    """
    Validate packed courses will fit without writing.

    Args:
        rom_path: ROM file path
        course_dirs: List of 1 or 2 course directories
        verbose: Show detailed statistics

    Returns:
        True if validation passes, False otherwise
    """
    print("Validation mode: checking if courses will fit...")
    print(f"ROM: {rom_path}")
    for i, d in enumerate(course_dirs):
        print(f"Course {i+1}: {d}")
    print()

    try:
        # Load all courses
        courses = []
        for course_dir in course_dirs:
            holes = load_course_data(course_dir)
            courses.append(holes)

        # Create writers
        rom_writer = RomWriter(rom_path, "/dev/null")
        packed_writer = PackedCourseWriter(rom_writer, apply_patches=False)

        # Validate
        result = packed_writer.validate_courses(courses, verbose=verbose)

        if result.valid:
            print("Validation PASSED - courses will fit in ROM")
            return True
        else:
            print(f"Validation FAILED: {result.message}")
            return False

    except Exception as e:
        print(f"Validation FAILED: {e}")
        return False


def write_packed(
    rom_path: str,
    course_dirs: list[Path],
    output_path: str,
    verbose: bool,
    trace_io: bool,
) -> None:
    """
    Write 1 or 2 courses using packed multi-bank mode.

    Args:
        rom_path: Source ROM file
        course_dirs: List of 1 or 2 course directories
        output_path: Output ROM file
        verbose: Show detailed statistics
        trace_io: Output ROM write trace
    """
    print(f"Loading ROM: {rom_path}")
    print(f"Writing {len(course_dirs)} course(s):")
    for i, d in enumerate(course_dirs):
        print(f"  Course {i+1}: {d}")
    print()

    # Load all courses
    courses = []
    for course_dir in course_dirs:
        holes = load_course_data(course_dir)
        courses.append(holes)
        print(f"Loaded {len(holes)} holes from {course_dir}")

    # Create writers
    if trace_io:
        from golf.core.instrumented_io import InstrumentedRomWriter
        rom_writer = InstrumentedRomWriter(str(rom_path), output_path)
    else:
        rom_writer = RomWriter(str(rom_path), output_path)

    packed_writer = PackedCourseWriter(rom_writer, apply_patches=True)

    # Write courses
    print()
    print("Compressing and writing course data...")
    stats = packed_writer.write_courses(courses, verbose=verbose)

    # Save ROM
    print()
    rom_writer.save()

    # Write trace if instrumented
    if trace_io and hasattr(rom_writer, "write_trace"):
        trace_path = str(Path(output_path).parent / "write_trace.json")
        rom_writer.write_trace(trace_path)

    print()
    print("Done!")


def main():
    parser = argparse.ArgumentParser(
        description="Write course data from JSON files back to NES ROM",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Write 1 course (all 3 course slots show the same course)
  golf-write rom.nes courses/japan/ -o output.nes

  # Write 2 courses (Japan slot shows course 1, US slot shows course 2, UK mirrors Japan)
  golf-write rom.nes courses/japan/ courses/us/ -o output.nes

  # Validate without writing
  golf-write rom.nes courses/japan/ courses/us/ --validate-only --verbose
""",
    )

    parser.add_argument("rom_file", nargs="?", help="Source ROM file (read-only)")
    parser.add_argument(
        "course_dirs",
        nargs="*",
        help="Course directory/directories (1 or 2)",
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

    # Validate required arguments
    if not args.rom_file:
        parser.error("the following arguments are required: rom_file")
    if not args.course_dirs:
        parser.error("the following arguments are required: course_dirs")

    # Validate ROM exists
    rom_path = Path(args.rom_file)
    if not rom_path.exists():
        print(f"Error: ROM file not found: {rom_path}")
        sys.exit(1)

    # Validate course directories
    course_dirs = [Path(d) for d in args.course_dirs]
    for d in course_dirs:
        if not d.is_dir():
            print(f"Error: Course directory not found: {d}")
            sys.exit(1)

    # Validate course count
    if len(course_dirs) > 2:
        print("Error: At most 2 course directories are supported")
        sys.exit(1)

    # Determine output path
    if args.output:
        output_path = args.output
    else:
        output_path = str(rom_path.with_suffix("")) + ".modified.nes"

    try:
        if args.validate_only:
            success = validate_packed(str(rom_path), course_dirs, args.verbose)
            sys.exit(0 if success else 1)

        write_packed(
            str(rom_path),
            course_dirs,
            output_path,
            args.verbose,
            args.trace_io,
        )

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
    except Exception as e:
        print(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
