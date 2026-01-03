#!/usr/bin/env python3
"""
NES Open Tournament Golf - Course Visualizer

Renders course holes as PNG images using tileset and palette data.
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Dict, Optional

from golf.core.chr_tile import TilesetData
from golf.rendering.pil_renderer import render_hole_to_image
from golf.rendering.pil_sprite import PILSprite


def load_sprites() -> Dict[str, PILSprite]:
    """Load all terrain sprites from data/sprites/."""
    sprite_dir = Path(__file__).parent.parent / "data" / "sprites"
    sprites = {}

    sprite_files = {
        "tee": "tee-block.json",
        "ball": "ball.json",
        "flag": "flag.json",
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


def render_hole(
    hole_path: str,
    tileset: TilesetData,
    output_path: str,
    sprites: Optional[Dict[str, PILSprite]] = None,
    render_sprites: bool = True,
    flag_index: int = 0,
):
    """Render a single hole to PNG."""

    with open(hole_path, "r") as f:
        hole_data = json.load(f)

    # Render using shared PIL renderer
    img = render_hole_to_image(
        hole_data,
        tileset,
        sprites=sprites,
        render_sprites=render_sprites,
        selected_flag_index=flag_index,
    )

    # Save image
    img.save(output_path)
    print(f"Saved: {output_path} ({img.width}x{img.height})")


def render_course(
    course_dir: str,
    tileset: TilesetData,
    output_dir: str,
    sprites: Optional[Dict[str, PILSprite]] = None,
    render_sprites: bool = True,
    flag_index: int = 0,
):
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
        render_hole(
            str(hole_file),
            tileset,
            str(out_file),
            sprites=sprites,
            render_sprites=render_sprites,
            flag_index=flag_index,
        )


def main():
    parser = argparse.ArgumentParser(
        description="Render NES Open Tournament Golf course holes as PNG images",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Render single hole:
    python visualize.py chr-ram.bin courses/japan/hole_01.json
    python visualize.py chr-ram.bin courses/japan/hole_01.json output.png

  Render entire course:
    python visualize.py chr-ram.bin courses/japan/
    python visualize.py chr-ram.bin courses/japan/ renders/japan/

  Render without sprites:
    python visualize.py chr-ram.bin courses/japan/hole_01.json --no-sprites

  Render with specific flag position:
    python visualize.py chr-ram.bin courses/japan/hole_01.json -f 2
        """,
    )
    parser.add_argument("tileset", help="Path to CHR tileset binary file")
    parser.add_argument("input", help="Path to hole JSON file or course directory")
    parser.add_argument(
        "output", nargs="?", help="Output PNG file or directory (optional)"
    )
    parser.add_argument(
        "--no-sprites",
        action="store_true",
        help="Disable sprite rendering (tee, ball, flag)",
    )
    parser.add_argument(
        "-f",
        "--flag-pos",
        type=int,
        choices=[0, 1, 2, 3],
        default=0,
        help="Flag position to render (0-3, default: 0)",
    )

    args = parser.parse_args()

    # Load tileset
    tileset = TilesetData(args.tileset)

    # Load sprites unless disabled
    sprites = None
    render_sprites = not args.no_sprites
    if render_sprites:
        sprites = load_sprites()
        if not sprites:
            print("Warning: No sprites loaded, rendering without sprites")
            render_sprites = False

    # Determine input type and render
    input_p = Path(args.input)

    if input_p.is_file():
        # Single hole
        output_path = args.output if args.output else input_p.stem + ".png"
        render_hole(
            args.input,
            tileset,
            output_path,
            sprites=sprites,
            render_sprites=render_sprites,
            flag_index=args.flag_pos,
        )

    elif input_p.is_dir():
        # Entire course
        output_dir = args.output if args.output else f"renders/{input_p.name}"
        render_course(
            args.input,
            tileset,
            output_dir,
            sprites=sprites,
            render_sprites=render_sprites,
            flag_index=args.flag_pos,
        )

    else:
        print(f"Error: {args.input} not found")
        sys.exit(1)


if __name__ == "__main__":
    main()
