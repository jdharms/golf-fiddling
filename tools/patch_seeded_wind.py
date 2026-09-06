#!/usr/bin/env python3
"""
NES Open Tournament Golf - Seeded Wind Patch Tool

Applies (or validates) the seeded wind patch defined in
golf/core/patches/seeded_wind.py, and can print the expected pin index,
wind anchors and per-swing wind for each hole so a Mesen session can be
checked against the seed.

The patch requires course3_mirror (applied by every golf-write); apply it
to a ROM that has already been through golf-write, or apply course3_mirror
first.
"""

import argparse
import sys
from pathlib import Path

from golf.core.patches import (
    COURSE3_MIRROR_PATCH,
    PatchError,
    derive_hole_seeds,
    predict_hole,
    seeded_wind_patch,
)
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


def _print_forecast(seeds: list[int], swings: int) -> None:
    print(f"{'hole':>4}  {'seed':>4}  pin  dir   spd  winds (dir/spd per swing)")
    for hole, seed in enumerate(seeds):
        f = predict_hole(seed, swings)
        winds = " ".join(f"{d:02X}/{s}" for d, s in f.winds)
        print(
            f"{hole + 1:>4}  {seed:04X}   {f.pin_index}   ${f.direction_anchor:02X}   {f.speed_anchor:>2}   {winds}"
        )


def main():
    parser = argparse.ArgumentParser(description="Apply or validate the seeded wind patch")
    parser.add_argument("rom_file", help="Source ROM file")
    parser.add_argument("--seed", required=True, help="Meta-seed string; expands to one RNG seed per hole")
    parser.add_argument(
        "--holes", type=int, default=18, help="Number of holes to seed (18 for 1-course, 36 for 2-course)"
    )
    parser.add_argument("-o", "--output", help="Output ROM file (default: <rom>.seeded.nes)")
    parser.add_argument(
        "--validate-only", action="store_true", help="Report sub-patch status without writing a ROM"
    )
    parser.add_argument(
        "--forecast",
        type=int,
        metavar="SWINGS",
        help="Print the expected pin index, anchors and first SWINGS wind values per hole",
    )
    args = parser.parse_args()

    seeds = derive_hole_seeds(args.seed, args.holes)
    if args.forecast:
        _print_forecast(seeds, args.forecast)
        print()

    output_path = args.output
    if output_path is None:
        output_path = str(Path(args.rom_file).with_suffix("")) + ".seeded.nes"

    rom_writer = RomWriter(args.rom_file, output_path)
    patch = seeded_wind_patch(seeds=seeds)

    print(f"{patch.name}: {patch.description}")
    can_apply = _report_status(patch, rom_writer)

    if not COURSE3_MIRROR_PATCH.is_applied(rom_writer):
        print(
            "  WARNING: course3_mirror is not applied; the seed table overwrites the "
            "UK flag X offsets, which are live without it"
        )

    if args.validate_only:
        sys.exit(0 if can_apply else 1)

    try:
        patch.apply(rom_writer)
    except PatchError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)

    rom_writer.save()
    print(f"Wrote {output_path}")


if __name__ == "__main__":
    main()
