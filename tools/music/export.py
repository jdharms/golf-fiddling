"""Export NES Open Tournament Golf music.

Three outputs, all driven by the game's own audio engine:

* an NSF containing every track, played by the original 6502 code;
* an NSF of the ten DPCM drum samples, one song each;
* a JSON dump of tracks as relocatable data, for inserting them into another ROM.

Works on the US ROM and on the Japanese release (Mario Open Golf), whose engine is the
same code at shifted addresses. See docs/music_format.md.
"""

import argparse
import json
import sys
from pathlib import Path

from golf.core.audio import (
    DMC_SAMPLE_COUNT,
    FIRST_MUSIC_ID,
    LAST_MUSIC_ID,
    TRACK_COUNT,
    build_drum_nsf,
    build_nsf,
)
from golf.core.music_data import discover_course_bgm, export


def _tracks(spec: str | None, rom: bytes) -> list[int]:
    if spec in (None, "courses"):
        return discover_course_bgm(rom)["unique_music_ids"]
    if spec == "all":
        return list(range(FIRST_MUSIC_ID, LAST_MUSIC_ID + 1))
    out = []
    for part in spec.split(","):
        n = int(part, 0)
        if not FIRST_MUSIC_ID <= n <= LAST_MUSIC_ID:
            raise SystemExit(f"track {n} out of range "
                             f"(${FIRST_MUSIC_ID:02X}-${LAST_MUSIC_ID:02X})")
        out.append(n)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rom", type=Path)
    ap.add_argument("-o", "--output", type=Path, help="output file")
    ap.add_argument("--drums", action="store_true",
                    help="export the 10 DPCM drum samples as an NSF, one song each")
    ap.add_argument("--dump", action="store_true",
                    help="write tracks as relocatable JSON instead of an NSF")
    ap.add_argument("--tracks", metavar="N[,N...]|courses|all", default="courses",
                    help="which tracks to dump (default: the three course themes)")
    ap.add_argument("--reference", type=Path,
                    help="ROM to compare note tuning against, recorded in the dump")
    args = ap.parse_args(argv)

    rom = args.rom.read_bytes()

    if args.drums:
        out = args.output or args.rom.with_name("drum_kit.nsf")
        out.write_bytes(build_drum_nsf(rom))
        print(f"wrote {out}  ({DMC_SAMPLE_COUNT} songs, one per slot x1-x{DMC_SAMPLE_COUNT})")
        return 0

    if args.dump:
        ids = _tracks(args.tracks, rom)
        ref = args.reference.read_bytes() if args.reference else None
        data = export(rom, ids, source=args.rom.name, reference=ref)
        out = args.output or args.rom.with_suffix(".music.json")
        out.write_text(json.dumps(data, indent=2) + "\n")
        cb = data["course_bgm"]
        print(f"wrote {out}")
        print(f"  {len(cb['slots'])} course slots, {len(cb['unique_music_ids'])} distinct themes: "
              + ", ".join(f"{s['name']}=${s['music_id']:02X}" for s in cb["slots"]))
        for t in data["tracks"]:
            print(f"  track ${t['music_id']:02X}: {len(t['patterns'])} patterns, "
                  f"{len(t['order'])} order entries, transpose {t['transpose']:+d}, "
                  f"{t['bytes']} bytes")
        if ref is not None:
            n = data["engine"]["semitones_sharper_than_reference"]
            print(f"  tuning: {n:+d} semitones vs {args.reference.name} "
                  f"(add {n:+d} to each track's transpose when inserting there)")
        return 0

    out = args.output or args.rom.with_suffix(".nsf")
    out.write_bytes(build_nsf(rom))
    print(f"wrote {out}  ({TRACK_COUNT} tracks, "
          f"${FIRST_MUSIC_ID:02X}-${LAST_MUSIC_ID:02X})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
