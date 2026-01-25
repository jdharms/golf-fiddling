#!/usr/bin/env python3
"""
NES Open Tournament Golf - Course Visualizer

Renders course holes as PNG images using tileset and palette data.
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
from golf.rendering.pil_sprite import PILSprite


def load_sprites() -> dict[str, PILSprite]:
    """Load all terrain sprites from data/sprites/."""
    sprite_dir = Path(__file__).parent.parent / "data" / "sprites"
    sprites = {}

    sprite_files = {
        "tee": "tee-block.json",
        "ball": "ball.json",
        "flag": "flag.json",
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


def render_hole(
    hole_path: str,
    tileset: TilesetData,
    output_path: str,
    sprites: dict[str, PILSprite] | None = None,
    render_sprites: bool = True,
    flag_index: int = 0,
):
    """Render a single hole to PNG."""

    with open(hole_path) as f:
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
    sprites: dict[str, PILSprite] | None = None,
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


def render_hole_greens(
    hole_path: str,
    greens_tileset: TilesetData,
    output_path: str,
):
    """Render greens-only for a single hole."""
    with open(hole_path) as f:
        hole_data = json.load(f)

    img = render_greens_to_image(hole_data, greens_tileset)
    img.save(output_path)
    print(f"Saved: {output_path} ({img.width}x{img.height})")


def render_course_greens(
    course_dir: str,
    greens_tileset: TilesetData,
    output_dir: str,
):
    """Render greens-only for all holes in a course."""
    course_path = Path(course_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    hole_files = sorted(course_path.glob("hole_*.json"))

    if not hole_files:
        print(f"No hole files found in {course_dir}")
        return

    print(f"Rendering greens for {len(hole_files)} holes from {course_dir}...")

    for hole_file in hole_files:
        hole_name = hole_file.stem
        out_file = output_path / f"{hole_name}_greens.png"
        render_hole_greens(str(hole_file), greens_tileset, str(out_file))


def render_hole_flags(
    hole_path: str,
    output_base: str,
    flag_sprite: PILSprite,
    cup_sprite: PILSprite | None = None,
    debug_background: bool = False,
):
    """Render all 4 flags for a single hole."""
    with open(hole_path) as f:
        hole_data = json.load(f)

    images = render_all_flags_to_images(
        hole_data, flag_sprite, debug_background=debug_background, cup_sprite=cup_sprite
    )

    # output_base is like "hole_01" - we append _flag_N.png
    for i, img in enumerate(images):
        out_path = f"{output_base}_flag_{i}.png"
        img.save(out_path)
        print(f"Saved: {out_path} ({img.width}x{img.height})")


def render_course_flags(
    course_dir: str,
    output_dir: str,
    flag_sprite: PILSprite,
    cup_sprite: PILSprite | None = None,
    debug_background: bool = False,
):
    """Render all flags for all holes in a course."""
    course_path = Path(course_dir)
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    hole_files = sorted(course_path.glob("hole_*.json"))

    if not hole_files:
        print(f"No hole files found in {course_dir}")
        return

    print(f"Rendering flags for {len(hole_files)} holes from {course_dir}...")

    for hole_file in hole_files:
        hole_name = hole_file.stem
        output_base = str(output_path / hole_name)
        render_hole_flags(str(hole_file), output_base, flag_sprite, cup_sprite, debug_background)


def main():
    parser = argparse.ArgumentParser(
        description="Render NES Open Tournament Golf course holes as PNG images",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  Render single hole:
    golf-visualize chr-ram.bin courses/japan/hole_01.json
    golf-visualize chr-ram.bin courses/japan/hole_01.json output.png

  Render entire course:
    golf-visualize chr-ram.bin courses/japan/
    golf-visualize chr-ram.bin courses/japan/ renders/japan/

  Render without sprites:
    golf-visualize chr-ram.bin courses/japan/hole_01.json --no-sprites

  Render with specific flag position:
    golf-visualize chr-ram.bin courses/japan/hole_01.json -f 2

  Render greens only (single hole):
    golf-visualize data/chr-ram.bin courses/japan/hole_01.json \\
        --greens-only --greens-tileset data/green-ram.bin

  Render greens only (entire course):
    golf-visualize data/chr-ram.bin courses/japan/ \\
        --greens-only --greens-tileset data/green-ram.bin renders/japan_greens/

  Render flags only (produces 4 PNGs per hole):
    golf-visualize data/chr-ram.bin courses/japan/hole_01.json --flags-only
    golf-visualize data/chr-ram.bin courses/japan/ --flags-only renders/japan_flags/
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
    parser.add_argument(
        "--greens-only",
        action="store_true",
        help="Render only greens tiles (24x24 grid, 192x192px)",
    )
    parser.add_argument(
        "--flags-only",
        action="store_true",
        help="Render flag sprites on transparent background (4 files per hole)",
    )
    parser.add_argument(
        "--greens-tileset",
        type=str,
        help="Path to greens CHR tileset (required with --greens-only)",
    )
    parser.add_argument(
        "--debug-bg",
        action="store_true",
        help="Use gray background (#808080) instead of transparent (only with --flags-only)",
    )

    args = parser.parse_args()

    # Validate argument combinations
    if args.greens_only and args.flags_only:
        print("Error: --greens-only and --flags-only are mutually exclusive")
        sys.exit(1)

    if args.greens_only and not args.greens_tileset:
        print("Error: --greens-only requires --greens-tileset")
        sys.exit(1)

    # Determine input type
    input_p = Path(args.input)

    if not input_p.exists():
        print(f"Error: {args.input} not found")
        sys.exit(1)

    # Handle greens-only mode
    if args.greens_only:
        greens_tileset = TilesetData(args.greens_tileset)
        if input_p.is_file():
            output_path = (
                args.output if args.output else input_p.stem + "_greens.png"
            )
            render_hole_greens(args.input, greens_tileset, output_path)
        else:
            output_dir = (
                args.output if args.output else f"renders/{input_p.name}_greens"
            )
            render_course_greens(args.input, greens_tileset, output_dir)
        return

    # Handle flags-only mode
    if args.flags_only:
        sprites = load_sprites()
        flag_sprite = sprites.get("green-flag")
        cup_sprite = sprites.get("green-cup")
        if not flag_sprite:
            print("Error: Could not load green-flag sprite")
            sys.exit(1)
        if input_p.is_file():
            output_base = args.output if args.output else input_p.stem
            # Strip .png suffix if provided
            if output_base.endswith(".png"):
                output_base = output_base[:-4]
            render_hole_flags(args.input, output_base, flag_sprite, cup_sprite, args.debug_bg)
        else:
            output_dir = (
                args.output if args.output else f"renders/{input_p.name}_flags"
            )
            render_course_flags(args.input, output_dir, flag_sprite, cup_sprite, args.debug_bg)
        return

    # Default mode: full terrain rendering
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


if __name__ == "__main__":
    main()
