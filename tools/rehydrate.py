#!/usr/bin/env python3
"""
Rehydrate - rebuild the vanilla course data and the rangefinder from the vanilla ROMs

The repository holds no vanilla course data. This dumps the US ROM (required) and the
Mario Open ROM (optional) into the hole store, checks every hole against the catalog's
content hashes before installing any of them, and renders the rangefinder's images from
the result. The ROMs are found under their usual file names (nes_open_us.nes,
mario_open_jp.nes) in GOLF_ROM_DIR, or the repository root; the hole store is
GOLF_HOLES_DIR, or courses/. --check verifies an earlier run without writing anything.
"""

import argparse
import sys
from pathlib import Path

from golf.randomizer.catalog import DEFAULT_INDEX, JP_ROM, US_ROM, Catalog
from golf.randomizer.rehydrate import (
    RehydrateError,
    check_rehydrated,
    check_rom,
    find_roms,
    rehydrate,
)
from golf.randomizer.roms import vanilla_rom
from golf.rendering.rangefinder import DEFAULT_OUTPUT
from server.config import Config


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(__doc__ or "").strip().splitlines()[2],
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="\n".join((__doc__ or "").strip().splitlines()[4:]),
    )
    config = Config.from_env()
    parser.add_argument(
        "--us", type=Path, help="the US ROM (default: nes_open_us.nes in the ROM dir)"
    )
    parser.add_argument(
        "--jp", type=Path, help="the JP ROM (default: mario_open_jp.nes in the ROM dir)"
    )
    parser.add_argument(
        "--rom-dir",
        type=Path,
        default=config.rom_dir,
        help="where to look for the ROMs by name (default: %(default)s)",
    )
    parser.add_argument(
        "--holes",
        type=Path,
        default=config.holes_dir,
        help="hole store root to write (default: %(default)s)",
    )
    parser.add_argument(
        "--rangefinder",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="the rangefinder's static directory (default: %(default)s)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify an earlier run without dumping or writing; exit 1 on a mismatch",
    )
    args = parser.parse_args()

    roms = find_roms(args.rom_dir)
    for rom_id, path in ((US_ROM, args.us), (JP_ROM, args.jp)):
        if path is not None:
            roms[rom_id] = path
    for path in roms.values():
        if not path.is_file():
            print(f"error: {path} not found", file=sys.stderr)
            return 1

    catalog = Catalog.load(DEFAULT_INDEX)
    try:
        if args.check:
            for rom_id, path in roms.items():
                check_rom(vanilla_rom(rom_id), path)
            holes = check_rehydrated(catalog, args.holes, roms, args.rangefinder)
            print(f"{holes} holes under {args.holes} match the catalog")
        else:
            report = rehydrate(
                catalog, args.holes, roms, args.rangefinder, progress=print
            )
            for rom_id in report.skipped:
                print(f"skipped {vanilla_rom(rom_id).title}: no ROM found")
            print(f"installed {report.holes} holes under {args.holes}")
    except RehydrateError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
