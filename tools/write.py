#!/usr/bin/env python3
"""
NES Open Tournament Golf - ROM Writer

Writes course data from JSON files back to ROM.
"""

import argparse
import sys
from pathlib import Path

from golf.core.course_writer import CourseWriter
from golf.core.patches import AVAILABLE_PATCHES, PatchError
from golf.core.rom_reader import COURSES, HOLES_PER_COURSE, PRG_BANK_SIZE
from golf.core.rom_writer import BankOverflowError, RomWriter

# Terrain bank boundaries - must match course_writer.py TERRAIN_BOUNDS
# Each bank contains lookup tables that limit the terrain region
TERRAIN_AVAILABLE_SPACE = {
    0: 0xA23E - 0x8000,  # Japan: 8766 bytes
    1: 0xA1E6 - 0x8000,  # US: 8678 bytes
    2: 0xA554 - 0x837F,  # UK: 8661 bytes (starts at $837F, not $8000)
}
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


def main():
    parser = argparse.ArgumentParser(
        description="Write course data from JSON files back to NES ROM"
    )

    parser.add_argument("rom_file", nargs="?", help="Source ROM file (read-only)")
    parser.add_argument(
        "course_dir",
        nargs="?",
        help="Course directory containing hole_01.json through hole_18.json",
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
        help="Apply a ROM patch by name (can be repeated)",
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

    # Validate required arguments for normal operation
    if not args.rom_file:
        parser.error("the following arguments are required: rom_file")
    if not args.course_dir:
        parser.error("the following arguments are required: course_dir")

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

        # Create writers
        if args.trace_io:
            from golf.core.instrumented_io import InstrumentedRomWriter

            rom_writer = InstrumentedRomWriter(str(rom_path), output_path)
        else:
            rom_writer = RomWriter(str(rom_path), output_path)

        # Apply patches if requested
        if args.patches:
            print("Applying patches...")
            apply_patches(rom_writer, args.patches)
            print()

        course_writer = CourseWriter(rom_writer)

        # Compress and write course
        print("Compressing course data...")
        stats = course_writer.write_course(course_idx, holes)

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
        if args.trace_io and hasattr(rom_writer, "write_trace"):
            trace_path = str(Path(output_path).parent / "write_trace.json")
            rom_writer.write_trace(trace_path)

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
