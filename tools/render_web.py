#!/usr/bin/env python3
"""
NES Open Tournament Golf - Web App Renderer

Batch renders all course holes as PNG images for the web-based measurement tool.
Generates metadata.json with course and hole information.
"""

import argparse
import json
import sys
from pathlib import Path

from golf.core.chr_tile import TilesetData
from golf.rendering.pil_renderer import (
    render_hole_to_image,
    render_greens_to_image,
    render_all_flags_to_images,
)
from golf.rendering.pil_sprite import PILSprite


# Course directories to process
COURSE_NAMES = ["japan", "us", "uk"]


def load_sprites() -> dict[str, PILSprite]:
    """Load all sprites from data/sprites/."""
    sprite_dir = Path(__file__).parent.parent / "data" / "sprites"
    sprites = {}

    sprite_files = {
        # Terrain sprites
        "tee": "tee-block.json",
        "ball": "ball.json",
        "flag": "flag.json",
        # Green view sprites
        "green-flag": "green-flag.json",
        "green-cup": "green-cup.json",
    }

    for name, filename in sprite_files.items():
        sprite_path = sprite_dir / filename
        if sprite_path.exists():
            try:
                sprites[name] = PILSprite(str(sprite_path))
            except Exception as e:
                print(f"Warning: Failed to load sprite {name}: {e}")
        else:
            print(f"Warning: Sprite file not found: {sprite_path}")

    return sprites


def render_all_courses(
    tileset_path: str,
    greens_tileset_path: str,
    courses_dir: str,
    output_dir: str,
    flag_index: int = 0,
):
    """Render all holes from all courses for the web app."""
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

    for course_name in COURSE_NAMES:
        course_dir = courses_path / course_name
        if not course_dir.exists():
            print(f"Warning: Course directory not found: {course_dir}")
            continue

        # Read course metadata
        course_json_path = course_dir / "course.json"
        if course_json_path.exists():
            with open(course_json_path) as f:
                course_data = json.load(f)
        else:
            course_data = {"name": course_name.capitalize()}

        # Create output directory for this course
        course_output_dir = output_path / "images" / course_name
        course_output_dir.mkdir(parents=True, exist_ok=True)

        # Initialize course metadata
        metadata["courses"][course_name] = {
            "name": course_data.get("name", course_name.capitalize()),
            "holes": []
        }

        # Render all holes for this course
        hole_files = sorted(course_dir.glob("hole_*.json"))

        if not hole_files:
            print(f"Warning: No hole files found in {course_dir}")
            continue

        print(f"\nRendering {course_name.upper()} course ({len(hole_files)} holes)...")

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
            if sprites.get("green-flag"):
                flag_overlays = render_all_flags_to_images(
                    hole_data,
                    sprites["green-flag"],
                    cup_sprite=sprites.get("green-cup"),
                )
                for i, flag_img in enumerate(flag_overlays):
                    flag_filename = f"{hole_name}_flag_{i}.png"
                    flag_path = course_output_dir / flag_filename
                    flag_img.save(flag_path)
                    flag_images.append(f"images/{course_name}/{flag_filename}")

            # Add to metadata
            hole_metadata = {
                "number": hole_data.get("hole", 1),
                "par": hole_data.get("par", 4),
                "distance": hole_data.get("distance", 0),
                "image": f"images/{course_name}/{image_filename}",
                "width": img.width,
                "height": img.height,
                "green_image": f"images/{course_name}/{green_filename}",
                "flag_images": flag_images,
            }
            metadata["courses"][course_name]["holes"].append(hole_metadata)

            print(f"  ✓ {hole_name}: {img.width}x{img.height}px + green + 4 flags")

    # Write metadata.json
    metadata_path = output_path / "metadata.json"
    with open(metadata_path, 'w') as f:
        json.dump(metadata, f, indent=2)

    print(f"\n✓ Metadata written to: {metadata_path}")
    print(f"✓ All images saved to: {output_path / 'images'}")

    # Print summary
    total_holes = sum(len(course["holes"]) for course in metadata["courses"].values())
    print(f"\nSummary: Rendered {total_holes} holes across {len(metadata['courses'])} courses")


def main():
    parser = argparse.ArgumentParser(
        description="Batch render all golf course holes for web app",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example:
  python render_web.py data/chr-ram.bin data/green-ram.bin courses/ web/

This will create:
  web/images/japan/hole_01.png ... hole_18.png
  web/images/japan/hole_01_green.png ... hole_18_green.png
  web/images/japan/hole_01_flag_0.png ... hole_18_flag_3.png
  (same for us/ and uk/)
  web/metadata.json
        """,
    )
    parser.add_argument("tileset", help="Path to terrain CHR tileset binary file")
    parser.add_argument("greens_tileset", help="Path to greens CHR tileset binary file")
    parser.add_argument("courses", help="Path to courses directory")
    parser.add_argument("output", help="Output directory for web app")
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
