#!/usr/bin/env python3
"""
NES Open Tournament Golf - Randomizer Spike

Proof of concept: draws 18 holes from the checked-in US and Mario Open courses to
fit a fixed par layout, and builds a full randomized ROM from a PatchStack
assembled in Python. Throwaway code on the way to the randomizer (docs/randomizer.md).
"""

import argparse
import json
import random
import sys
from pathlib import Path

from golf.core.patches import (
    ATTR_STREAMING_PATCH,
    COURSE_MIRRORS_PATCH,
    MULTI_BANK_CODE_PATCH,
    WRAM_EXPANSION_PATCH,
    CompositePatch,
    CoursePatch,
    PatchError,
    PatchStack,
    SCORECARD_QR_PATCH,
    QrCredentials,
    menu_trim_patch,
    mercy_tap_in_patches,
    music_import_patch,
    practice_swing_patch,
    qr_credentials_patch,
    scorecard_course_name_patch,
    sram_defaults_patch,
    seeded_wind_patch,
)
from golf.core.patches.signpost_random_banner import signpost_banner_patch
from golf.core.rom_reader import RomReader
from golf.formats.hole_data import HoleData

LAYOUT = [4, 5, 4, 3, 4, 3, 4, 5, 4, 4, 4, 3, 5, 4, 5, 3, 4, 4]

# Hardcoded for the spike: the US release's courses and Mario Open's.
POOL_DIRS = [
    "courses/us",
    "courses/uk",
    "courses/japan",
    "courses/jp/jp_australia",
    "courses/jp/jp_france",
    "courses/jp/jp_hawaii",
    "courses/jp/jp_japan",
    "courses/jp/jp_uk",
]

JP_MUSIC_DUMP = Path("data/music/music_jp_courses.json")
SIGNPOST_ART = Path("golf/core/patches/data/signpost_random.aseprite")
WORDS = "HOOK MARIO HAZARD"
MERCY_POINT = 9


def draw_holes(rng: random.Random) -> list[Path]:
    by_par: dict[int, list[Path]] = {}
    for course_dir in POOL_DIRS:
        for path in sorted(Path(course_dir).glob("hole_*.json")):
            par = json.loads(path.read_text())["par"]
            by_par.setdefault(par, []).append(path)
    for pool in by_par.values():
        rng.shuffle(pool)
    return [by_par[par].pop() for par in LAYOUT]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[2])
    parser.add_argument("rom", type=Path, help="vanilla US ROM")
    parser.add_argument("-o", "--output", type=Path, default=Path("randomized.nes"))
    parser.add_argument("--seed", default=None, help="drives the hole draw, wind and music choice")
    args = parser.parse_args()

    seed = args.seed if args.seed is not None else f"{random.SystemRandom().randrange(1 << 32):08x}"
    rng = random.Random(seed)
    vanilla = args.rom.read_bytes()

    hole_paths = draw_holes(rng)
    holes = []
    for path in hole_paths:
        hole = HoleData()
        hole.load(str(path))
        holes.append(hole)

    dump = json.loads(JP_MUSIC_DUMP.read_text())
    music_id = rng.choice(dump["course_bgm"]["unique_music_ids"])
    credentials = QrCredentials.random()

    try:
        course = CoursePatch(holes)
        stack = PatchStack(
            [
                WRAM_EXPANSION_PATCH,
                MULTI_BANK_CODE_PATCH,
                COURSE_MIRRORS_PATCH,
                ATTR_STREAMING_PATCH,
                course,
                seeded_wind_patch(seed),
                music_import_patch(dump, track=music_id),
                # practice_swing_patch(), -- Removed on purpose while I'm rethinking it.
                CompositePatch(
                    "mercy_tap_in",
                    f"End a hole at stroke {MERCY_POINT} with a tap-in",
                    mercy_tap_in_patches(MERCY_POINT),
                ),
                SCORECARD_QR_PATCH,
                qr_credentials_patch(credentials),
                signpost_banner_patch(RomReader.from_bytes(vanilla), SIGNPOST_ART),
                scorecard_course_name_patch(title=WORDS),
                menu_trim_patch(WORDS),
                sram_defaults_patch(),
            ]
        )
        build = stack.build(vanilla)
    except PatchError as problem:
        print(f"error: {problem}", file=sys.stderr)
        return 1

    args.output.write_bytes(build.rom)
    keys_path = args.output.with_suffix(".keys.json")
    keys_path.write_text(json.dumps(credentials.manifest(), indent=2) + "\n")

    print(f"seed {seed}")
    for number, (par, path) in enumerate(zip(LAYOUT, hole_paths), start=1):
        print(f"  {number:>2}  par {par}  {path}")
    print(f"music: Mario Open ${music_id:02X}")
    stats = course.stats
    for bank, capacity in stats.bank_capacity.items():
        print(f"bank {bank}: {stats.bank_usage[bank]:,} / {capacity:,} bytes")
    print(f"scorecard: {stats.total_yards:,} yards, par {stats.total_par}")
    print(f"wrote {args.output} and {keys_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
