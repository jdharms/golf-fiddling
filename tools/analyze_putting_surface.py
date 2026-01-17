#!/usr/bin/env python3
"""
NES Open Tournament Golf - Putting Surface Size Analyzer

Analyzes all 54 vanilla holes and outputs putting surface tile counts
to a JSON file for use by the metadata dialog visualization.
"""

import sys
from pathlib import Path

from golf.formats import compact_json as json
from golf.formats.putting_surface import count_putting_surface_tiles


COURSES = ["japan", "us", "uk"]
HOLES_PER_COURSE = 18


def analyze_courses(courses_dir: Path) -> dict:
    """
    Analyze putting surface sizes for all holes.

    Args:
        courses_dir: Path to courses directory

    Returns:
        Dictionary with hole data and sizes array
    """
    holes = []
    sizes = []

    for course_name in COURSES:
        course_dir = courses_dir / course_name

        if not course_dir.exists():
            print(f"Warning: Course directory not found: {course_dir}")
            continue

        for hole_num in range(1, HOLES_PER_COURSE + 1):
            hole_file = course_dir / f"hole_{hole_num:02d}.json"

            if not hole_file.exists():
                print(f"Warning: Hole file not found: {hole_file}")
                continue

            # Load hole data
            with open(hole_file) as f:
                hole_data = json.load(f)

            # Parse greens data from hex strings
            greens = []
            greens_rows = hole_data.get("greens", {}).get("rows", [])
            for row_hex in greens_rows:
                row_values = [int(x, 16) for x in row_hex.split()]
                greens.append(row_values)

            # Count putting surface tiles
            size = count_putting_surface_tiles(greens)

            holes.append({
                "course": course_name,
                "hole": hole_num,
                "size": size,
            })
            sizes.append(size)

            print(f"{course_name.capitalize()} Hole {hole_num:2d}: {size} tiles")

    return {
        "description": "Putting surface tile counts for vanilla holes",
        "holes": holes,
        "sizes": sizes,
    }


def main():
    """Main entry point."""
    # Determine paths
    script_dir = Path(__file__).parent.parent
    courses_dir = script_dir / "courses"
    output_dir = script_dir / "data" / "statistics"

    if not courses_dir.exists():
        print(f"Error: Courses directory not found: {courses_dir}")
        sys.exit(1)

    # Ensure output directory exists
    output_dir.mkdir(parents=True, exist_ok=True)

    # Analyze all holes
    print("Analyzing putting surface sizes...\n")
    data = analyze_courses(courses_dir)

    # Calculate statistics
    sizes = data["sizes"]
    if sizes:
        min_size = min(sizes)
        max_size = max(sizes)
        avg_size = sum(sizes) / len(sizes)
        print(f"\nTotal holes analyzed: {len(sizes)}")
        print(f"Min: {min_size}, Max: {max_size}, Avg: {avg_size:.1f}")

    # Write output
    output_file = output_dir / "putting_surface_sizes.json"
    with open(output_file, "w") as f:
        json.dump(data, f, indent=2)

    print(f"\nOutput written to: {output_file}")


if __name__ == "__main__":
    main()
