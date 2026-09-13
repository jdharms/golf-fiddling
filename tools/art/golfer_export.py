"""
Export golfer animations as layered Aseprite files for redrawing.

Layout of the files and the JSON sidecar is described in
golf/core/golfer_export.py; see also docs/golfer_sprites.md.
"""

import argparse
import os

from golf.core.golfer_export import canvas_bounds, export_golfer
from golf.core.golfer_sprites import (
    GOLFER_NAMES,
    PUTTER_CLUB,
    SWING_CLUB_GROUPS,
    GolferSprites,
)
from golf.core.rom_reader import RomReader


def main():
    parser = argparse.ArgumentParser(
        description="Export golfer animations as layered Aseprite files"
    )
    parser.add_argument("rom")
    parser.add_argument("out_dir")
    parser.add_argument(
        "-g", "--golfer", default="all",
        help="name or index (default: all six)",
    )
    parser.add_argument(
        "-c", "--club", type=int, default=0,
        help="which club layer starts visible in the swing file (default: 0); "
             "every club group gets a layer regardless",
    )
    parser.add_argument(
        "-a", "--animation", choices=["swing", "putt", "both"], default="both"
    )
    args = parser.parse_args()

    if not 0 <= args.club < PUTTER_CLUB:
        parser.error(
            f"--club must be 0-{PUTTER_CLUB - 1}; putting always uses club {PUTTER_CLUB}"
        )

    rom = RomReader(args.rom)
    sprites = GolferSprites(rom)

    if args.golfer == "all":
        golfers = list(range(len(GOLFER_NAMES)))
    elif args.golfer.isdigit():
        golfers = [int(args.golfer)]
    else:
        lowered = [n.lower() for n in GOLFER_NAMES]
        if args.golfer.lower() not in lowered:
            parser.error(f"unknown golfer {args.golfer!r}; expected one of {GOLFER_NAMES}")
        golfers = [lowered.index(args.golfer.lower())]

    os.makedirs(args.out_dir, exist_ok=True)
    bounds = canvas_bounds(sprites)
    x0, y0, x1, y1 = bounds
    groups = ", ".join(f"{lo}-{hi}" for lo, hi in SWING_CLUB_GROUPS)
    print(f"canvas {x1 - x0}x{y1 - y0}, origin at ({-x0}, {-y0})")
    print(f"swing club layers: {groups}   putt: club {PUTTER_CLUB}")

    animations = (
        [False, True] if args.animation == "both" else [args.animation == "putt"]
    )
    for golfer in golfers:
        for putt in animations:
            path, meta = export_golfer(
                rom, sprites, golfer, putt, bounds, args.out_dir, args.club
            )
            linked = sum(1 for f in meta["frames"] if f["body_linked_to"] is not None)
            print(
                f"  {os.path.basename(path):22} {len(meta['frames'])} frames"
                f" ({linked} linked), {len(meta['clubs'])} club layer(s),"
                f" build {sprites.body_type(golfer)}"
            )


if __name__ == "__main__":
    main()
