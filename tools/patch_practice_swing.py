#!/usr/bin/env python3
"""
NES Open Tournament Golf - Practice Swing Patch Tool

Applies (or validates) the practice swing patch defined in
golf/core/patches/practice_swing.py.

The patch places its toggle routine in the fixed-bank free space at $CAE4,
which is the tail of the $CA40-$CAFF block wram_expansion carves its
relocated tables from, so apply it to a ROM that has already been through
golf-patch-wram.
"""

import argparse
import sys
from pathlib import Path

from golf.core.patches import DEFAULT_HOLD_FRAMES, PatchError, practice_swing_patch
from golf.core.rom_writer import RomWriter


def _report_status(patch, rom_writer: RomWriter) -> bool:
    """Print per-sub-patch status. Returns True if the whole group can apply."""
    all_ok = True
    for sub in patch.patches:
        if sub.is_applied(rom_writer):
            state = "already applied"
        elif sub.can_apply(rom_writer):
            state = "pending"
        else:
            state = "CONFLICT (unexpected bytes)"
            all_ok = False
        print(f"  [{state:24}] {sub.name}: {sub.description}")
    return all_ok


def main():
    parser = argparse.ArgumentParser(description="Apply or validate the practice swing patch")
    parser.add_argument("rom_file", help="Source ROM file")
    parser.add_argument("-o", "--output", help="Output ROM file (default: <rom>.practice.nes)")
    parser.add_argument(
        "--hold-frames",
        type=lambda v: int(v, 0),
        default=DEFAULT_HOLD_FRAMES,
        help=(
            "Value $0586 must reach before the ready state is restored "
            f"(default ${DEFAULT_HOLD_FRAMES:02X}, about 2 seconds)"
        ),
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Report sub-patch status without writing a ROM",
    )
    args = parser.parse_args()

    output_path = args.output
    if output_path is None:
        output_path = str(Path(args.rom_file).with_suffix("")) + ".practice.nes"

    try:
        patch = practice_swing_patch(args.hold_frames)
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    rom_writer = RomWriter(args.rom_file, output_path)

    print(f"{patch.name}: {patch.description}")
    can_apply = _report_status(patch, rom_writer)

    if args.validate_only:
        sys.exit(0 if can_apply else 1)

    try:
        patch.apply(rom_writer)
    except PatchError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    rom_writer.save()


if __name__ == "__main__":
    main()
