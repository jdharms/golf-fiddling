#!/usr/bin/env python3
"""
NES Open Tournament Golf - ROM Writer

Writes course data from JSON files back to ROM.

Default mode (packed):
  - Writes 1 or 2 courses packed across 3 terrain banks
  - Uses per-hole bank lookup for maximum space efficiency
  - Automatically applies required ROM patches

Legacy mode (--legacy):
  - Writes a single course to its dedicated bank
  - No patches applied (vanilla ROM behavior)
  - Use -c to specify which course slot (0-2)
"""

import argparse
import sys
from pathlib import Path

from golf.core.course_writer import CourseWriter
from golf.core.packed_course_writer import PackedCourseWriter
from golf.core.patches import AVAILABLE_PATCHES, PatchError
from golf.core.rom_reader import COURSES, HOLES_PER_COURSE
from golf.core.rom_writer import BankOverflowError, RomWriter
from golf.formats import compact_json as json
from golf.formats.hole_data import HoleData


# Terrain bank boundaries - must match course_writer.py TERRAIN_BOUNDS
# Each bank contains lookup tables that limit the terrain region
TERRAIN_AVAILABLE_SPACE = {
    0: 0xA23E - 0x8000,  # Japan: 8766 bytes
    1: 0xA1E6 - 0x8000,  # US: 8678 bytes
    2: 0xA554 - 0x837F,  # UK: 8661 bytes (starts at $837F, not $8000)
}


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


def list_patches() -> None:
    """Print available patches and exit."""
    print("Available patches:")
    print()
    for name, patch in AVAILABLE_PATCHES.items():
        print(f"  {name}")
        print(f"    {patch.description}")
        print()


def apply_patches(rom_writer: RomWriter, patch_names: list[str]) -> list[str]:
    """
    Apply selected patches to ROM.

    Args:
        rom_writer: ROM writer to modify
        patch_names: List of patch names to apply

    Returns:
        List of patches that were applied (excludes already-applied)

    Raises:
        ValueError: If patch name is not recognized
        PatchError: If patch cannot be applied
    """
    applied = []

    for name in patch_names:
        if name not in AVAILABLE_PATCHES:
            raise ValueError(
                f"Unknown patch: '{name}'. Use --list-patches to see available patches."
            )

        patch = AVAILABLE_PATCHES[name]

        if patch.is_applied(rom_writer):
            print(f"Patch already applied: {name}")
        elif patch.can_apply(rom_writer):
            patch.apply(rom_writer)
            print(f"Applied patch: {name}")
            applied.append(name)
        else:
            raise PatchError(
                f"Cannot apply patch '{name}': ROM is in unexpected state"
            )

    return applied


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
    print("Validation mode (packed): checking if courses will fit...")
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


def validate_legacy(
    rom_path: str, course_dir: Path, course_idx: int, verbose: bool
) -> bool:
    """
    Validate that course data will fit without writing (legacy mode).

    Args:
        rom_path: ROM file path
        course_dir: Course directory
        course_idx: Course index (0-2)
        verbose: Show detailed statistics

    Returns:
        True if validation passes, False otherwise
    """
    print("Validation mode (legacy): checking if course will fit...")
    print(f"ROM: {rom_path}")
    print(f"Course: {course_dir} (index {course_idx})")
    print()

    try:
        # Load course data
        holes = load_course_data(course_dir)

        # Create writers
        rom_writer = RomWriter(rom_path, "/dev/null")  # Dummy output
        course_writer = CourseWriter(rom_writer)

        # Attempt to write (this compresses and validates)
        stats = course_writer.write_course(course_idx, holes)

        # Report statistics
        terrain_available = TERRAIN_AVAILABLE_SPACE[course_idx]
        print(f"Course: {stats['course']}")
        print(
            f"Terrain bank usage: {stats['terrain_bank_usage']:,} / {terrain_available:,} bytes "
            f"({stats['terrain_bank_usage'] / terrain_available * 100:.1f}%)"
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
    print(f"Writing {len(course_dirs)} course(s) in packed mode:")
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


def write_legacy(
    rom_path: str,
    course_dir: Path,
    course_idx: int,
    output_path: str,
    verbose: bool,
    trace_io: bool,
    patches: list[str] | None,
) -> None:
    """
    Write single course using legacy single-bank mode.

    Args:
        rom_path: Source ROM file
        course_dir: Course directory
        course_idx: Course index (0-2)
        output_path: Output ROM file
        verbose: Show detailed statistics
        trace_io: Output ROM write trace
        patches: List of patches to apply
    """
    print(f"Loading ROM: {rom_path}")
    print(f"Loading course: {course_dir} ({COURSES[course_idx]['display_name']}, course index {course_idx})")
    print()

    # Load course data
    holes = load_course_data(course_dir)
    print(f"Loaded {len(holes)} holes")

    # Create writers
    if trace_io:
        from golf.core.instrumented_io import InstrumentedRomWriter
        rom_writer = InstrumentedRomWriter(str(rom_path), output_path)
    else:
        rom_writer = RomWriter(str(rom_path), output_path)

    # Apply patches if requested
    if patches:
        print("Applying patches...")
        apply_patches(rom_writer, patches)
        print()

    course_writer = CourseWriter(rom_writer)

    # Compress and write course
    print("Compressing course data...")
    stats = course_writer.write_course(course_idx, holes)

    if verbose:
        print()
        print("Compression statistics:")
        for hole in stats["holes"]:
            print(
                f"  Hole {hole['hole']:2d}: "
                f"terrain {hole['terrain_bytes']:4d} bytes, "
                f"greens {hole['greens_bytes']:3d} bytes"
            )

    print()
    terrain_available = TERRAIN_AVAILABLE_SPACE[course_idx]
    print(
        f"Total terrain bank usage: {stats['terrain_bank_usage']:,} / {terrain_available:,} bytes "
        f"({stats['terrain_bank_usage'] / terrain_available * 100:.1f}%)"
    )
    print(
        f"Total greens bank usage (this course): {stats['greens_bytes']:,} bytes"
    )

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
  # Write 1 course in packed mode (default, UK mirrors Japan)
  golf-write rom.nes courses/japan/ -o output.nes

  # Write 2 courses in packed mode
  golf-write rom.nes courses/japan/ courses/us/ -o output.nes

  # Validate without writing
  golf-write rom.nes courses/japan/ courses/us/ --validate-only --verbose

  # Legacy mode: write single course to specific bank
  golf-write rom.nes courses/japan/ --legacy -c 0 -o output.nes
""",
    )

    parser.add_argument("rom_file", nargs="?", help="Source ROM file (read-only)")
    parser.add_argument(
        "course_dirs",
        nargs="*",
        help="Course directory/directories (1 or 2 for packed mode, 1 for legacy)",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Output ROM file (default: <rom>.modified.nes)",
        default=None,
    )
    parser.add_argument(
        "--legacy",
        action="store_true",
        help="Use legacy single-course mode (no patches, single bank)",
    )
    parser.add_argument(
        "-c",
        "--course",
        type=int,
        help="Course index 0-2 (legacy mode only, default: auto-detect)",
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
    parser.add_argument(
        "-p",
        "--patch",
        action="append",
        dest="patches",
        metavar="NAME",
        help="Apply a ROM patch by name (legacy mode only, can be repeated)",
    )
    parser.add_argument(
        "--list-patches",
        action="store_true",
        help="List available patches and exit",
    )

    args = parser.parse_args()

    # Handle --list-patches early exit
    if args.list_patches:
        list_patches()
        sys.exit(0)

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

    # Determine output path
    if args.output:
        output_path = args.output
    else:
        output_path = str(rom_path.with_suffix("")) + ".modified.nes"

    try:
        if args.legacy:
            # Legacy mode: single course to single bank
            if len(course_dirs) > 1:
                print("Error: Legacy mode only supports 1 course directory")
                sys.exit(1)

            course_dir = course_dirs[0]

            # Determine course index
            if args.course is not None:
                course_idx = args.course
                if not 0 <= course_idx <= 2:
                    print(f"Error: Course index must be 0-2, got {course_idx}")
                    sys.exit(1)
            else:
                course_idx = detect_course_index(course_dir)

            if args.validate_only:
                success = validate_legacy(
                    str(rom_path), course_dir, course_idx, args.verbose
                )
                sys.exit(0 if success else 1)

            write_legacy(
                str(rom_path),
                course_dir,
                course_idx,
                output_path,
                args.verbose,
                args.trace_io,
                args.patches,
            )

        else:
            # Packed mode: 1 or 2 courses across 3 banks
            if len(course_dirs) > 2:
                print("Error: Packed mode supports at most 2 course directories")
                sys.exit(1)

            if args.course is not None:
                print("Warning: -c/--course is ignored in packed mode")

            if args.patches:
                print("Warning: -p/--patch is ignored in packed mode (patches auto-applied)")

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
