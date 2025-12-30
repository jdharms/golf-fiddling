#!/usr/bin/env python3
"""
NES Open Tournament Golf - Course Visualizer

Renders course holes as PNG images using tileset and palette data.
"""

import json
import sys
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    print("Error: Pillow library required. Install with: pip install Pillow")
    sys.exit(1)

from golf.core.chr_tile import TilesetData
from golf.rendering.pil_renderer import render_hole_to_image


def render_hole(hole_path: str, tileset: TilesetData, output_path: str):
    """Render a single hole to PNG."""

    with open(hole_path, 'r') as f:
        hole_data = json.load(f)

    # Render using shared PIL renderer
    img = render_hole_to_image(hole_data, tileset)

    # Save image
    img.save(output_path)
    print(f"Saved: {output_path} ({img.width}x{img.height})")


def render_course(course_dir: str, tileset: TilesetData, output_dir: str):
    """Render all holes in a course."""
    course_path = Path(course_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Find all hole files
    hole_files = sorted(course_path.glob("hole_*.json"))

    if not hole_files:
        print(f"No hole files found in {course_dir}")
        return

    print(f"Rendering {len(hole_files)} holes from {course_dir}...")

    for hole_file in hole_files:
        hole_name = hole_file.stem  # e.g., "hole_01"
        out_file = output_path / f"{hole_name}.png"
        render_hole(str(hole_file), tileset, str(out_file))


def main():
    if len(sys.argv) < 3:
        print("Usage:")
        print("  Render single hole:")
        print("    python visualize.py <tileset.bin> <hole.json> [output.png]")
        print("")
        print("  Render entire course:")
        print("    python visualize.py <tileset.bin> <course_dir/> [output_dir/]")
        print("")
        print("Example:")
        print("  python visualize.py chr-ram.bin courses/japan/hole_01.json")
        print("  python visualize.py chr-ram.bin courses/japan/ renders/japan/")
        sys.exit(1)

    tileset_path = sys.argv[1]
    input_path = sys.argv[2]

    tileset = TilesetData(tileset_path)

    # Check if input is a file or directory
    input_p = Path(input_path)

    if input_p.is_file():
        # Single hole
        output_path = sys.argv[3] if len(sys.argv) > 3 else input_p.stem + ".png"
        render_hole(input_path, tileset, output_path)

    elif input_p.is_dir():
        # Entire course
        output_dir = sys.argv[3] if len(sys.argv) > 3 else f"renders/{input_p.name}"
        render_course(input_path, tileset, output_dir)

    else:
        print(f"Error: {input_path} not found")
        sys.exit(1)


if __name__ == "__main__":
    main()
