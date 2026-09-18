#!/usr/bin/env python3
"""
NES Open Tournament Golf - Randomizer

Generates a seed manifest from settings, and builds a ROM or IPS patch from a manifest,
with the same library the randomizer site uses (golf.randomizer). See docs/manifest.md
and docs/randomizer_devplan.md.

  generate  settings in, manifest out
  build     manifest in, ROM or IPS out: a finished guest ROM by default, an unfinished
            one with --unfinished, or a signed-in one with --credentials
  show      print a manifest's course
"""

import argparse
import json
import sys
from pathlib import Path

from golf.core.patches import PatchError, load_credentials
from golf.core.patches.sram_defaults import VANILLA_CLUBS, VANILLA_NAME
from golf.randomizer.build import (
    PlayerOptions,
    build_unfinished,
    clubs_from_labels,
    finish,
)
from golf.randomizer.catalog import (
    DEFAULT_COURSES,
    DEFAULT_INDEX,
    Catalog,
    CatalogError,
    HoleStore,
)
from golf.randomizer.curation import DEFAULT_CURATION, CurationSnapshot
from golf.randomizer.generate import GenerationError, generate
from golf.randomizer.layout import COUNTS
from golf.randomizer.manifest import (
    SOURCES,
    ClubRules,
    Manifest,
    Settings,
    required_roms,
)
from golf.randomizer.music import RANDOM, TRACKS

EXAMPLES = """
examples:
  golf-randomize generate --seed demo -o demo.json
  golf-randomize generate --par 71 --sources nes_open_us --music nes_uk --mercy-point none
  golf-randomize build nes_open_us.nes demo.json -o demo.nes
  golf-randomize build nes_open_us.nes demo.json --unfinished --ips demo.unfinished.ips
  golf-qr-credentials -o keys.json
  golf-randomize build nes_open_us.nes demo.json --credentials keys.json --name LUIGI --clubs 1W,3W,5I,PW
  golf-randomize show demo.json
"""


def comma_list(text: str) -> list[str]:
    return [item.strip() for item in text.split(",") if item.strip()]


def mercy_point(text: str) -> int | None:
    if text.lower() == "none":
        return None
    try:
        return int(text, 0)
    except ValueError:
        raise argparse.ArgumentTypeError(
            f"expected a stroke number or 'none', got {text!r}"
        ) from None


def settings_from_args(args: argparse.Namespace) -> Settings:
    defaults = Settings()
    rules = ClubRules(
        max=args.clubs_max if args.clubs_max is not None else defaults.clubs.max,
        banned=clubs_from_labels(comma_list(args.banned))
        if args.banned
        else frozenset(),
        required_bag=clubs_from_labels(comma_list(args.required_bag))
        if args.required_bag
        else None,
    )
    return Settings(
        prng_seed=args.seed,
        par=args.par,
        sources=frozenset(comma_list(args.sources))
        if args.sources
        else defaults.sources,
        exclude_tags=frozenset(comma_list(args.exclude_tags))
        if args.exclude_tags
        else frozenset(),
        allow_family_repeats=args.allow_family_repeats,
        music=args.music,
        mercy_point=args.mercy_point,
        clubs=rules,
    )


def describe_clubs(rules: ClubRules) -> str:
    parts = [f"at most {rules.max}"]
    if rules.banned:
        parts.append("banned " + " ".join(club.label for club in sorted(rules.banned)))
    if rules.required_bag is not None:
        parts.append(
            "required bag "
            + " ".join(club.label for club in sorted(rules.required_bag))
        )
    return ", ".join(parts)


def summary(
    manifest: Manifest, catalog: Catalog, curation: CurationSnapshot | None
) -> list[str]:
    course = manifest.course
    lines = [
        f"seed {manifest.settings.prng_seed}  (par {manifest.settings.par} target)"
    ]
    total_yards = 0
    for number, slot in enumerate(course.holes, start=1):
        entry = catalog[slot.id]
        total_yards += entry.distance
        name = curation.for_hole(slot.id).display_name if curation is not None else None
        suffix = f"  {name}" if name else ""
        lines.append(
            f"  {number:>2}  par {slot.par}  {entry.distance:>3} yd  {slot.id}{suffix}"
        )
    mercy = "off" if course.mercy_point is None else f"stroke {course.mercy_point}"
    lines += [
        f"total: par {course.par}, {total_yards:,} yards",
        f"music: {course.music}",
        f"mercy tap-in: {mercy}",
        f"clubs: {describe_clubs(course.clubs)}",
        f"magic words: {' '.join(course.magic_words)}",
        f"requires: {', '.join(required_roms(manifest, catalog))}",
    ]
    return lines


def load_manifest(path: Path) -> Manifest:
    return Manifest.from_json(json.loads(path.read_text()))


def curation_or_none(path: Path) -> CurationSnapshot | None:
    return CurationSnapshot.load(path) if path.exists() else None


def cmd_generate(args: argparse.Namespace) -> int:
    settings = settings_from_args(args)
    catalog = Catalog.load(args.catalog)
    curation = CurationSnapshot.load(args.curation)
    manifest = generate(catalog, curation, settings)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest.to_json(), indent=2) + "\n")
    for line in summary(manifest, catalog, curation):
        print(line)
    print(f"wrote {args.output}")
    return 0


def cmd_build(args: argparse.Namespace) -> int:
    manifest = load_manifest(args.manifest)
    catalog = Catalog.load(args.catalog)
    store = HoleStore(args.holes)
    vanilla = args.rom.read_bytes()

    options = None
    credentials = None
    if not args.unfinished:
        clubs = (
            clubs_from_labels(comma_list(args.clubs))
            if args.clubs
            else frozenset(VANILLA_CLUBS)
        )
        options = PlayerOptions(args.name, clubs, bgm=not args.no_bgm)
        if args.credentials:
            credentials = load_credentials(args.credentials)

    unfinished = build_unfinished(manifest, catalog, store, vanilla)
    if args.unfinished:
        stage, rom, patch = "unfinished", unfinished.rom, unfinished.ips
    else:
        assert options is not None
        finished = finish(manifest, vanilla, unfinished.ips, options, credentials)
        stage = "finished, signed in" if credentials is not None else "finished, guest"
        rom, patch = finished.rom, finished.ips

    for line in summary(manifest, catalog, curation_or_none(DEFAULT_CURATION)):
        print(line)
    stats = unfinished.course_stats
    for bank, capacity in stats.bank_capacity.items():
        print(f"bank {bank}: {stats.bank_usage[bank]:,} / {capacity:,} bytes")
    print(f"scorecard: {stats.total_yards:,} yards, par {stats.total_par}")
    if options is not None:
        bag = " ".join(club.label for club in sorted(options.clubs))
        music = "on" if options.bgm else "off"
        print(f"player: {options.player_name}, bag {bag}, music {music}")
    print(f"built: {stage}")

    if args.ips:
        args.ips.parent.mkdir(parents=True, exist_ok=True)
        args.ips.write_bytes(patch)
        print(f"wrote {args.ips}")
    if args.output or not args.ips:
        output = args.output or args.manifest.with_suffix(".nes")
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(rom)
        print(f"wrote {output}")
    return 0


def cmd_show(args: argparse.Namespace) -> int:
    manifest = load_manifest(args.manifest)
    catalog = Catalog.load(args.catalog)
    for line in summary(manifest, catalog, curation_or_none(args.curation)):
        print(line)
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(__doc__ or "").strip().splitlines()[2],
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=EXAMPLES,
    )
    commands = parser.add_subparsers(dest="command", required=True)

    gen = commands.add_parser("generate", help="settings in, manifest out")
    gen.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path("manifest.json"),
        help="manifest to write",
    )
    gen.add_argument(
        "--seed", help="the PRNG seed every random choice comes from (default: drawn)"
    )
    gen.add_argument(
        "--par", type=int, choices=sorted(COUNTS, reverse=True), default=Settings().par
    )
    gen.add_argument(
        "--sources", help=f"comma-separated source ROMs (default: {','.join(SOURCES)})"
    )
    gen.add_argument(
        "--exclude-tags", help="comma-separated curation tags to keep out of the pool"
    )
    gen.add_argument(
        "--allow-family-repeats",
        action="store_true",
        help="let two holes of one family share the course",
    )
    gen.add_argument(
        "--music", default=RANDOM, help=f"{RANDOM} or one of {', '.join(TRACKS)}"
    )
    gen.add_argument(
        "--mercy-point",
        type=mercy_point,
        default=Settings().mercy_point,
        metavar="N|none",
        help="the stroke a hole ends on with a tap-in; none leaves the patch out (default: %(default)s)",
    )
    gen.add_argument(
        "--clubs-max",
        type=int,
        help="the most clubs a bag may hold, putter included (default: 14)",
    )
    gen.add_argument(
        "--banned",
        metavar="CLUBS",
        help="comma-separated clubs no bag may hold, e.g. 1W,SW",
    )
    gen.add_argument(
        "--required-bag",
        metavar="CLUBS",
        help="comma-separated clubs every player carries",
    )
    gen.add_argument(
        "--catalog", type=Path, default=DEFAULT_INDEX, help="catalog index"
    )
    gen.add_argument(
        "--curation", type=Path, default=DEFAULT_CURATION, help="curation file"
    )
    gen.set_defaults(func=cmd_generate)

    build = commands.add_parser("build", help="manifest in, ROM or IPS out")
    build.add_argument("rom", type=Path, help="vanilla US ROM")
    build.add_argument("manifest", type=Path, help="manifest from generate or the site")
    build.add_argument(
        "-o",
        "--output",
        type=Path,
        help="write the ROM (default: <manifest>.nes unless --ips)",
    )
    build.add_argument(
        "--ips", type=Path, help="write an IPS patch from the vanilla ROM to the build"
    )
    stage = build.add_mutually_exclusive_group()
    stage.add_argument(
        "--unfinished", action="store_true", help="stop after the unfinished stage"
    )
    stage.add_argument(
        "--credentials",
        type=Path,
        metavar="KEYS",
        help="finish signed in with a golf-qr-credentials file",
    )
    build.add_argument(
        "--name",
        default=VANILLA_NAME,
        help="the new-save player name (default: %(default)s)",
    )
    build.add_argument(
        "--clubs",
        metavar="CLUBS",
        help="comma-separated new-save bag (default: the vanilla bag)",
    )
    build.add_argument(
        "--no-bgm", action="store_true", help="new saves start with music off"
    )
    build.add_argument(
        "--catalog", type=Path, default=DEFAULT_INDEX, help="catalog index"
    )
    build.add_argument(
        "--holes",
        type=Path,
        default=DEFAULT_COURSES,
        help="hole store root (default: courses/)",
    )
    build.set_defaults(func=cmd_build)

    show = commands.add_parser("show", help="print a manifest's course")
    show.add_argument("manifest", type=Path, help="manifest file")
    show.add_argument(
        "--catalog", type=Path, default=DEFAULT_INDEX, help="catalog index"
    )
    show.add_argument(
        "--curation",
        type=Path,
        default=DEFAULT_CURATION,
        help="curation file, for display names",
    )
    show.set_defaults(func=cmd_show)
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if (
        args.command == "build"
        and args.unfinished
        and (args.clubs or args.no_bgm or args.name != VANILLA_NAME)
    ):
        parser.error(
            "--name, --clubs and --no-bgm are finishing options; drop them with --unfinished"
        )
    try:
        return args.func(args)
    except (ValueError, CatalogError, GenerationError, PatchError, OSError) as problem:
        print(f"error: {problem}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
