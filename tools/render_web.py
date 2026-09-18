#!/usr/bin/env python3
"""
NES Open Tournament Golf - Rangefinder Renderer

Batch renders all course holes as PNG images for the randomizer site's rangefinder.
Generates metadata.json with course and hole information. golf-rehydrate runs this after
dumping; it is here to re-render without dumping again.
"""

import argparse
import sys
from pathlib import Path

from golf.rendering.rangefinder import (
    DEFAULT_GREENS_TILESET,
    DEFAULT_TILESET,
    render_rangefinder,
)


def main():
    parser = argparse.ArgumentParser(
        description="Batch render all golf course holes for the rangefinder",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example:
  golf-render-web courses/ server/static/rangefinder/

This will replace server/static/rangefinder/images/ and metadata.json with:
  images/japan/hole_01.png ... hole_18.png
  images/japan/hole_01_green.png ... hole_18_green.png
  images/japan/hole_01_flag_0.png ... hole_18_flag_3.png
  (the same for us/ and uk/, and for the five Mario Open Golf courses jp_japan/,
   jp_australia/, jp_france/, jp_hawaii/ and jp_uk/ when they are dumped)
        """,
    )
    parser.add_argument("courses", type=Path, help="Path to courses directory")
    parser.add_argument(
        "output", type=Path, help="Output directory for the rangefinder's static files"
    )
    parser.add_argument(
        "--tileset",
        type=Path,
        default=DEFAULT_TILESET,
        help="terrain CHR tileset (default: data/chr-ram.bin)",
    )
    parser.add_argument(
        "--greens-tileset",
        type=Path,
        default=DEFAULT_GREENS_TILESET,
        help="greens CHR tileset (default: data/green-ram.bin)",
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

    for path in (args.tileset, args.greens_tileset, args.courses):
        if not path.exists():
            print(f"Error: not found: {path}")
            sys.exit(1)

    metadata = render_rangefinder(
        args.courses,
        args.output,
        args.tileset,
        args.greens_tileset,
        flag_index=args.flag_pos,
        progress=print,
    )
    total = sum(len(course["holes"]) for course in metadata["courses"].values())
    print(f"Rendered {total} holes across {len(metadata['courses'])} courses")


if __name__ == "__main__":
    main()
