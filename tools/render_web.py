#!/usr/bin/env python3
"""
NES Open Tournament Golf - Rangefinder Renderer

Batch renders all course holes as PNG images for the randomizer site's rangefinder.
Generates metadata.json with course and hole information.
"""

import argparse
import json
import sys
from pathlib import Path

from golf.core.chr_tile import TilesetData
from golf.rendering.pil_renderer import (
    render_all_flags_to_images,
    render_greens_to_image,
    render_hole_to_image,
)
from golf.rendering.pil_sprite import load_sprites

# Courses to process, in dropdown order: (course id, path under courses/, group label).
# The group label becomes an <optgroup> in the rangefinder's course selector, so the two
# games' courses stay visually separated even though both have a course named "Japan".
NES_OPEN_GROUP = "NES Open Tournament Golf"
MARIO_OPEN_GROUP = "Mario Open Golf (JP)"

COURSES = [
    ("japan", "japan", NES_OPEN_GROUP),
    ("us", "us", NES_OPEN_GROUP),
    ("uk", "uk", NES_OPEN_GROUP),
    ("jp_japan", "jp/jp_japan", MARIO_OPEN_GROUP),
    ("jp_australia", "jp/jp_australia", MARIO_OPEN_GROUP),
    ("jp_france", "jp/jp_france", MARIO_OPEN_GROUP),
    ("jp_hawaii", "jp/jp_hawaii", MARIO_OPEN_GROUP),
    ("jp_uk", "jp/jp_uk", MARIO_OPEN_GROUP),
]


def render_all_courses(
    tileset_path: str,
    greens_tileset_path: str,
    courses_dir: str,
    output_dir: str,
    flag_index: int = 0,
):
    """Render all holes from all courses for the rangefinder."""
    tileset = TilesetData(tileset_path)
    greens_tileset = TilesetData(greens_tileset_path)
    sprites = load_sprites()

    if not sprites:
        print("Warning: No sprites loaded, rendering without sprites")
        sprites = None

    courses_path = Path(courses_dir)
    output_path = Path(output_dir)

    # Metadata structure
    metadata = {"courses": {}}

    for course_id, course_subpath, group in COURSES:
        course_dir = courses_path / course_subpath
        if not course_dir.exists():
            print(f"Warning: Course directory not found: {course_dir}")
            continue

        # Read course metadata
        course_json_path = course_dir / "course.json"
        if course_json_path.exists():
            with open(course_json_path) as f:
                course_data = json.load(f)
        else:
            course_data = {"name": course_id.capitalize()}

        # Create output directory for this course
        course_output_dir = output_path / "images" / course_id
        course_output_dir.mkdir(parents=True, exist_ok=True)

        # Initialize course metadata
        metadata["courses"][course_id] = {
            "name": course_data.get("name", course_id.capitalize()),
            "group": group,
            "holes": [],
        }

        # Render all holes for this course
        hole_files = sorted(course_dir.glob("hole_*.json"))

        if not hole_files:
            print(f"Warning: No hole files found in {course_dir}")
            continue

        print(f"\nRendering {course_id.upper()} course ({len(hole_files)} holes)...")

        for hole_file in hole_files:
            hole_name = hole_file.stem  # e.g., "hole_01"

            # Read hole data
            with open(hole_file) as f:
                hole_data = json.load(f)

            # Render hole to image
            img = render_hole_to_image(
                hole_data,
                tileset,
                sprites=sprites,
                render_sprites=True,
                selected_flag_index=flag_index,
            )

            # Save terrain image
            image_filename = f"{hole_name}.png"
            image_path = course_output_dir / image_filename
            img.save(image_path)

            # Render greens image (192x192)
            greens_img = render_greens_to_image(hole_data, greens_tileset)
            green_filename = f"{hole_name}_green.png"
            green_path = course_output_dir / green_filename
            greens_img.save(green_path)

            # Render flag overlay images (4 transparent PNGs)
            flag_images = []
            green_flag = sprites.get("green-flag") if sprites else None
            if sprites and green_flag:
                flag_overlays = render_all_flags_to_images(
                    hole_data,
                    green_flag,
                    cup_sprite=sprites.get("green-cup"),
                )
                for i, flag_img in enumerate(flag_overlays):
                    flag_filename = f"{hole_name}_flag_{i}.png"
                    flag_path = course_output_dir / flag_filename
                    flag_img.save(flag_path)
                    flag_images.append(f"images/{course_id}/{flag_filename}")

            # Add to metadata
            hole_metadata = {
                "number": hole_data.get("hole", 1),
                "par": hole_data.get("par", 4),
                "distance": hole_data.get("distance", 0),
                "image": f"images/{course_id}/{image_filename}",
                "width": img.width,
                "height": img.height,
                "green_image": f"images/{course_id}/{green_filename}",
                "flag_images": flag_images,
            }
            metadata["courses"][course_id]["holes"].append(hole_metadata)

            print(f"  ✓ {hole_name}: {img.width}x{img.height}px + green + 4 flags")

    # Write metadata.json
    metadata_path = output_path / "metadata.json"
    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=2)

    print(f"\n✓ Metadata written to: {metadata_path}")
    print(f"✓ All images saved to: {output_path / 'images'}")

    # Print summary
    total_holes = sum(len(course["holes"]) for course in metadata["courses"].values())
    print(
        f"\nSummary: Rendered {total_holes} holes across {len(metadata['courses'])} courses"
    )


def main():
    parser = argparse.ArgumentParser(
        description="Batch render all golf course holes for the rangefinder",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example:
  golf-render-web data/chr-ram.bin data/green-ram.bin courses/ server/static/rangefinder/

This will create:
  server/static/rangefinder/images/japan/hole_01.png ... hole_18.png
  server/static/rangefinder/images/japan/hole_01_green.png ... hole_18_green.png
  server/static/rangefinder/images/japan/hole_01_flag_0.png ... hole_18_flag_3.png
  (same for us/, uk/, and the five Mario Open Golf courses jp_japan/,
   jp_australia/, jp_france/, jp_hawaii/, jp_uk/)
  server/static/rangefinder/metadata.json
        """,
    )
    parser.add_argument("tileset", help="Path to terrain CHR tileset binary file")
    parser.add_argument("greens_tileset", help="Path to greens CHR tileset binary file")
    parser.add_argument("courses", help="Path to courses directory")
    parser.add_argument(
        "output", help="Output directory for the rangefinder's static files"
    )
    parser.add_argument(
        "-f",
        "--flag-pos",
        type=int,
        choices=[0, 1, 2, 3],
        default=0,
        help="Flag position to render on terrain (0-3, default: 0)",
    )

    args = parser.parse_args()

    # Validate inputs
    tileset_path = Path(args.tileset)
    if not tileset_path.exists():
        print(f"Error: Tileset file not found: {args.tileset}")
        sys.exit(1)

    greens_tileset_path = Path(args.greens_tileset)
    if not greens_tileset_path.exists():
        print(f"Error: Greens tileset file not found: {args.greens_tileset}")
        sys.exit(1)

    courses_path = Path(args.courses)
    if not courses_path.exists():
        print(f"Error: Courses directory not found: {args.courses}")
        sys.exit(1)

    # Render all courses
    render_all_courses(
        args.tileset,
        args.greens_tileset,
        args.courses,
        args.output,
        flag_index=args.flag_pos,
    )


if __name__ == "__main__":
    main()
