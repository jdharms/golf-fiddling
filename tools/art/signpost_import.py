"""
Read an edited pre-hole signpost screen back out of an `.aseprite` file.

The artist works on a flat picture of the whole 256x240 screen, drawn at an
integer zoom.  This turns their banner back into the two things the ROM needs:
the raw nametable bytes of the `$AD86` descriptor's body, and the CHR patterns
that do not exist in the signpost's pattern table yet.

    golf-signpost-import after.aseprite --banner us --json banner.json

Nothing is written to the ROM here - the output is the input to a patch, and
what the patch has to do depends entirely on whether any new CHR is needed.
See docs/prehole_signpost.md.
"""

import argparse
import json
import os
import sys

from golf.core.palettes import NES_SYSTEM_PALETTE
from golf.core.rom_reader import RomReader
from golf.core.signpost import (
    SCREEN_COLS,
    SCREEN_ROWS,
    build_screen,
    changed_tiles,
    chr_rows,
    convert_banner,
    freeable_patterns,
    parse_banner,
    read_banner_descriptor,
    screen_from_aseprite,
)


def grid_report(ase, ragged, path, margin=1, zoom=12):
    """Show the artist which marks the NES cannot hold.

    Their canvas is the screen at an integer zoom, so one NES pixel is a
    `zoom x zoom` block on an aligned grid.  A stroke drawn thinner than that,
    or starting half a block over, has no hardware pixel to live in - the
    overlay draws the real pixel boundaries and rings every block that ended up
    holding more than one colour.
    """
    from PIL import Image, ImageDraw

    if not ragged:
        return
    scale = ase.width // (SCREEN_COLS * 8)
    xs = [x for x, _ in ragged]
    ys = [y for _, y in ragged]
    x0, x1 = max(0, min(xs) - margin), min(SCREEN_COLS * 8, max(xs) + margin + 1)
    y0, y1 = max(0, min(ys) - margin), min(SCREEN_ROWS * 8, max(ys) + margin + 1)

    flat = ase.composite()
    colours = [(entry[0], entry[1], entry[2]) for entry in ase.palette]
    image = Image.new("RGB", ((x1 - x0) * scale, (y1 - y0) * scale))
    pixels = image.load()
    for j in range((y1 - y0) * scale):
        for i in range((x1 - x0) * scale):
            pixels[i, j] = colours[flat[(y0 * scale + j) * ase.width + x0 * scale + i]]

    big = image.resize((image.width * zoom, image.height * zoom), Image.NEAREST)
    draw = ImageDraw.Draw(big)
    step = scale * zoom
    for i in range(0, big.width + 1, step):
        draw.line([(i, 0), (i, big.height)], fill=(0, 255, 0))
    for j in range(0, big.height + 1, step):
        draw.line([(0, j), (big.width, j)], fill=(0, 255, 0))
    for x, y in ragged:
        left, top = (x - x0) * step, (y - y0) * step
        draw.rectangle(
            [left, top, left + step, top + step], outline=(255, 0, 0), width=3
        )

    big.save(path)
    print(
        f"\nwrote {path}: green = NES pixel boundaries, red = a pixel drawn "
        f"finer than {scale}x{scale} or off the grid"
    )


def preview(result, reference, palette, path, scale=2):
    """The card as the PPU would draw it once the imported tiles are in CHR.

    Rendering from the converted patterns rather than from the artist's canvas
    is the point: anything their drawing asked for that the hardware cannot do -
    a fourth colour, detail finer than a pixel - disappears here, which is the
    only honest preview.
    """
    from PIL import Image

    from golf.core.signpost import render_screen

    rendered = render_screen(reference, palette)
    image = Image.new("RGB", (SCREEN_COLS * 8, SCREEN_ROWS * 8))
    pixels = image.load()
    for y, line in enumerate(rendered):
        for x, value in enumerate(line):
            pixels[x, y] = NES_SYSTEM_PALETTE[value & 0x3F]

    for tile in result.tiles:
        for y, row in enumerate(chr_rows(tile.chr_bytes)):
            for x, value in enumerate(row):
                colour = (
                    palette[0] if value == 0 else palette[tile.subpalette * 4 + value]
                )
                pixels[tile.col * 8 + x, tile.row * 8 + y] = NES_SYSTEM_PALETTE[
                    colour & 0x3F
                ]

    image.resize((image.width * scale, image.height * scale), Image.NEAREST).save(path)
    print(f"\nwrote {path}")


def describe(result, reference, scale, ragged, free, args):
    descriptor = result.descriptor
    print(
        f"banner {descriptor.index} ({args.banner}): {descriptor.width}x{descriptor.rows} "
        f"tiles at ${descriptor.dest:04X} (column {descriptor.col}, row {descriptor.row}), "
        f"body at ${descriptor.pointer:04X} in bank 12, {descriptor.length} bytes"
    )
    print(f"canvas zoom: {scale}x")
    if ragged:
        print(
            f"  WARNING: {len(ragged)} NES pixel(s) contain sub-pixel detail the "
            f"NES cannot show, e.g. {ragged[:4]}"
        )

    inside = {(t.col, t.row) for t in result.tiles}
    edited = [t for t in result.tiles if not t.unchanged]
    reused = [t for t in edited if not t.is_new]
    new = result.new_patterns

    print(
        f"\n{len(result.tiles)} banner cells: {len(result.tiles) - len(edited)} unchanged, "
        f"{len(reused)} redrawn with tiles that already exist, "
        f"{len(edited) - len(reused)} needing art that does not"
    )
    if reused:
        print(
            "  reused: "
            + ", ".join(f"({t.col},{t.row})->${t.tile:02X}" for t in reused[:12])
            + (" ..." if len(reused) > 12 else "")
        )
    if new:
        print(f"  {len(new)} distinct new pattern(s), wanted by:")
        for pattern, cells in new.items():
            where = ", ".join(f"({t.col},{t.row})" for t in cells)
            print(f"    {pattern[:4].hex(' ')}... x{len(cells)}: {where}")

    if result.outside:
        print(
            f"\n{len(result.outside)} edited cell(s) outside the banner - not "
            "expressible as a banner swap, ignored:"
        )
        print("  " + ", ".join(f"({c},{r})" for c, r in result.outside))

    for error in result.errors:
        print(f"\nPALETTE ERROR: {error}")

    print(
        f"\npattern-table budget: {len(free['blank'])} blank, "
        f"{len(free['unreferenced_by_screen'])} unreferenced by this screen, "
        f"{len(free['only_other_banners'])} held only by the other four banners"
    )

    if not new and not result.errors:
        body = result.nametable()
        print(
            f"\nnametable body ({len(body)} bytes) - writes over ${descriptor.pointer:04X}:"
        )
        for row in range(descriptor.rows):
            line = body[row * descriptor.width : (row + 1) * descriptor.width]
            print("  " + " ".join(f"{b:02X}" for b in line))
    elif new:
        print(
            f"\nNo nametable body yet: {sum(len(v) for v in new.values())} cell(s) "
            "need pattern indices assigned first."
        )
    return inside


def main():
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("aseprite", help="the edited screen")
    parser.add_argument("--rom", default="nes_open_us.nes")
    parser.add_argument(
        "--banner", default="us", help="which banner the export was drawn over"
    )
    parser.add_argument("--course", type=int, default=None)
    parser.add_argument("--hole", type=int, default=1)
    parser.add_argument("--json", help="write the extracted tiles and bytes here")
    parser.add_argument("--preview", help="render the card as the PPU would draw it")
    parser.add_argument(
        "--grid",
        help="render the off-grid pixels for the artist, with a NES pixel grid",
    )
    args = parser.parse_args()

    index = parse_banner(args.banner)
    course = args.course if args.course is not None else min(index, 2)

    rom = RomReader(args.rom)
    reference, palette = build_screen(rom, course, args.hole)
    descriptor = read_banner_descriptor(rom, index)

    try:
        edited = screen_from_aseprite(args.aseprite)
    except ValueError as problem:
        raise SystemExit(f"{os.path.basename(args.aseprite)}: {problem}")
    screen, scale, ragged, ase = (
        edited.pixels,
        edited.scale,
        edited.ragged,
        edited.source,
    )
    result = convert_banner(screen, reference, palette, descriptor)

    inside = {
        (descriptor.col + c, descriptor.row + r)
        for r in range(descriptor.rows)
        for c in range(descriptor.width)
    }
    result.outside = [
        t for t in changed_tiles(screen, reference, palette) if t not in inside
    ]

    free = freeable_patterns(rom, reference, descriptor)
    describe(result, reference, scale, ragged, free, args)

    if args.preview:
        preview(result, reference, palette, args.preview)
    if args.grid:
        grid_report(ase, ragged, args.grid)

    if args.json:
        payload = {
            "source": os.path.basename(args.aseprite),
            "rom": os.path.basename(args.rom),
            "banner": {
                "index": descriptor.index,
                "dest": descriptor.dest,
                "width": descriptor.width,
                "rows": descriptor.rows,
                "pointer": descriptor.pointer,
            },
            "cells": [
                {
                    "col": t.col,
                    "row": t.row,
                    "subpalette": t.subpalette,
                    "tile": t.tile,
                    "unchanged": t.unchanged,
                    "chr": t.chr_bytes.hex(),
                }
                for t in result.tiles
            ],
            "new_patterns": [
                {"chr": pattern.hex(), "cells": [[t.col, t.row] for t in cells]}
                for pattern, cells in result.new_patterns.items()
            ],
            "free_patterns": free,
            "errors": result.errors,
            "outside": result.outside,
        }
        with open(args.json, "w") as handle:
            json.dump(payload, handle, indent=2)
        print(f"\nwrote {args.json}")

    return 1 if result.errors else 0


if __name__ == "__main__":
    sys.exit(main())
