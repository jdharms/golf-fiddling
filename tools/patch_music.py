#!/usr/bin/env python3
"""
NES Open Tournament Golf - Music Import Patch Tool

Replaces the US ROM's three course themes with tracks from a
`golf-export-music --dump` JSON document, using only the space the originals
occupied. Proof of concept - see golf/core/patches/music_import.py.

    golf-export-music mario_open_jp.nes --dump --reference nes_open_us.nes \\
        -o data/music/music_jp_courses.json
    golf-patch-music nes_open_us.nes data/music/music_jp_courses.json -o jp_music.nes

The dump must contain music $02, $03 and $04. Their transpose bytes are shifted
by the dump's recorded tuning difference so the tracks play at their original
pitch; --transpose-adjust overrides that.
"""

import argparse
import json
import sys
from pathlib import Path

from golf.core.patches import PatchError, music_import_patch
from golf.core.rom_writer import RomWriter


def main():
    parser = argparse.ArgumentParser(
        description="Import course themes from a music dump into the US ROM"
    )
    parser.add_argument("rom_file", help="Source ROM file (vanilla US ROM)")
    parser.add_argument("music_json", help="JSON written by golf-export-music --dump")
    parser.add_argument("-o", "--output", help="Output ROM file (default: <rom>.music.nes)")
    parser.add_argument(
        "--transpose-adjust",
        type=int,
        default=None,
        help="Semitones to add to each track's transpose byte (default: the "
        "dump's semitones_sharper_than_reference)",
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Report the layout and status without writing a ROM",
    )
    args = parser.parse_args()

    output_path = args.output or str(Path(args.rom_file).with_suffix("")) + ".music.nes"

    dump = json.loads(Path(args.music_json).read_text())
    try:
        patch = music_import_patch(dump, transpose_adjust=args.transpose_adjust)
    except PatchError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    rom_writer = RomWriter(args.rom_file, output_path)

    print(f"{patch.name}: {patch.description}")
    for track in patch.tracks:
        transpose = track["transpose"] + patch.transpose_adjust
        print(
            f"  music ${track['music_id']:02X}: {len(track['patterns'])} patterns, "
            f"{len(track['order'])} order entries, transpose "
            f"{track['transpose']:+d} -> {transpose:+d}"
        )
    for name, used, size in patch.usage():
        print(f"  {name:16} {used:5}/{size} bytes")
    print(
        f"  envelope table relocated to ${patch.envelope_addr:04X} "
        f"({len(patch.envelope_table)} bytes)"
    )

    if patch.is_applied(rom_writer):
        state = "already applied"
    elif patch.can_apply(rom_writer):
        state = "pending"
    else:
        state = "CONFLICT (ROM is not the vanilla US music data)"
    print(f"  status: {state}")

    if args.validate_only:
        sys.exit(1 if "CONFLICT" in state else 0)

    try:
        patch.apply(rom_writer)
    except PatchError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    rom_writer.save()


if __name__ == "__main__":
    main()
