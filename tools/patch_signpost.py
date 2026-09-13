"""
Put an edited signpost banner into a ROM, art and all.

    golf-patch-signpost nes_open_us.nes after.aseprite -o random.nes

Reads the banner back off the edited screen (`golf-signpost-import` prints the
same analysis), finds pattern-table slots for whatever art the ROM does not
already have, and writes the pixels, the descriptors that load them, the new
banner body and the code that draws it.  See docs/prehole_signpost.md.

The replacement banner is drawn for every hole: the course/contest selection is
what gets overwritten, so the other four banners stop being reachable.
"""

import argparse
import os
import sys

from golf.core.patches import PatchError
from golf.core.patches.signpost_random_banner import random_banner_patches
from golf.core.rom_reader import RomReader
from golf.core.rom_writer import RomWriter
from golf.core.signpost import (
    allocate_patterns,
    build_screen,
    convert_banner,
    free_pattern_slots,
    read_banner_descriptor,
    screen_from_aseprite,
)

BANNERS = {"japan": 0, "us": 1, "uk": 2, "long-drive": 3, "nearest-pin": 4}


def main():
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument("rom")
    parser.add_argument("aseprite", help="the edited screen")
    parser.add_argument("-o", "--output", help="default: <rom>.signpost.nes")
    parser.add_argument(
        "--banner", default="us", help="which banner the export was drawn over"
    )
    parser.add_argument("--hole", type=int, default=1)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()

    index = BANNERS.get(args.banner, None)
    if index is None:
        index = int(args.banner, 0)

    rom = RomReader(args.rom)
    reference, palette = build_screen(rom, course=min(index, 2), hole_1based=args.hole)
    descriptor = read_banner_descriptor(rom, index)

    try:
        edited = screen_from_aseprite(args.aseprite)
    except ValueError as problem:
        raise SystemExit(f"{os.path.basename(args.aseprite)}: {problem}")
    result = convert_banner(edited.pixels, reference, palette, descriptor)

    if result.errors:
        for error in result.errors:
            print(f"PALETTE ERROR: {error}")
        raise SystemExit("the art uses colours the attribute table does not allow")
    if edited.ragged:
        print(
            f"note: {len(edited.ragged)} NES pixel(s) were drawn finer than the "
            f"{edited.scale}x grid; each resolved to its lower palette index "
            "(run golf-signpost-import --grid to see them)"
        )

    patterns = list(result.new_patterns)
    kept = [tile.tile for tile in result.tiles]
    chunks = allocate_patterns(free_pattern_slots(rom, reference, kept), len(patterns))

    placement = {}
    supply = list(patterns)
    for first_tile, count in chunks:
        for offset in range(min(count, len(supply))):
            placement[supply[offset]] = first_tile + offset
        supply = supply[count:]

    body = result.nametable(placement)
    patch = random_banner_patches(rom, patterns, chunks, index, body)

    print(f"{len(patterns)} new tile(s) -> " + ", ".join(
        f"${first:02X}-${first + count - 1:02X}" for first, count in chunks
    ))
    for sub in patch.patches:
        print(f"  {sub.name}: {len(sub.patched)} bytes at PRG 0x{sub.prg_offset:05X}")

    output = args.output or os.path.splitext(args.rom)[0] + ".signpost.nes"
    writer = RomWriter(args.rom, output)
    if not patch.can_apply(writer):
        blocked = [
            sub.name
            for sub in patch.patches
            if not (sub.can_apply(writer) or sub.is_applied(writer))
        ]
        raise SystemExit(f"ROM is not in the expected state: {', '.join(blocked)}")

    if args.validate_only:
        print("\nvalidated; nothing written")
        return 0

    try:
        patch.apply(writer)
    except PatchError as problem:
        raise SystemExit(str(problem))
    writer.save()
    print(f"\nwrote {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
