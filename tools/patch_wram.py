#!/usr/bin/env python3
"""
NES Open Tournament Golf - WRAM Expansion Patch Tool

Applies (or validates) the WRAM expansion composite patch defined in
golf/core/patches/wram_expansion.py. Sub-patches are added to that module
incrementally as the plan in docs/wram_expansion.md is worked through; this
tool exists to make re-testing the growing patch set against a real ROM
fast, without going through golf-write.
"""

import argparse
import sys
from pathlib import Path

from golf.core.patches import PatchError, WRAM_EXPANSION_PATCH
from golf.core.rom_writer import RomWriter


def _report_status(rom_writer: RomWriter) -> bool:
    """Print per-sub-patch status. Returns True if the whole group can apply."""
    patch = WRAM_EXPANSION_PATCH

    if not patch.patches:
        print(f"{patch.name}: no sub-patches defined yet")
        return True

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
    parser = argparse.ArgumentParser(
        description="Apply or validate the WRAM expansion composite patch"
    )
    parser.add_argument("rom_file", help="Source ROM file")
    parser.add_argument(
        "-o", "--output", help="Output ROM file (default: <rom>.wram.nes)"
    )
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Report sub-patch status without writing a ROM",
    )
    args = parser.parse_args()

    output_path = args.output
    if output_path is None:
        output_path = str(Path(args.rom_file).with_suffix("")) + ".wram.nes"

    rom_writer = RomWriter(args.rom_file, output_path)

    print(f"{WRAM_EXPANSION_PATCH.name}: {WRAM_EXPANSION_PATCH.description}")
    can_apply = _report_status(rom_writer)

    if args.validate_only:
        sys.exit(0 if can_apply else 1)

    try:
        WRAM_EXPANSION_PATCH.apply(rom_writer)
    except PatchError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    if not WRAM_EXPANSION_PATCH.patches:
        print("Nothing to apply yet (no sub-patches defined).")
        return

    rom_writer.save()


if __name__ == "__main__":
    main()
