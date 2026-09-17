#!/usr/bin/env python3
"""
Catalog Sync - add dumped vanilla holes to the randomizer catalog and verify the rest

Walks the vanilla course directories under a courses root, adds a version 1 entry to
data/catalog/holes.json for every hole the index lacks, and checks every hole the index
already has against its data. Never removes or rewrites an entry: a hole whose data has
changed needs a new version, added by hand. See docs/catalog.md.
"""

import argparse
import sys
from pathlib import Path

from golf.randomizer.catalog import DEFAULT_COURSES, DEFAULT_INDEX, Catalog, HoleStore, sync_vanilla


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.strip().splitlines()[0])
    parser.add_argument(
        "courses_root",
        nargs="?",
        type=Path,
        default=DEFAULT_COURSES,
        help="directory holding the dumped courses, with Mario Open under jp/ (default: courses/)",
    )
    parser.add_argument("--index", type=Path, default=DEFAULT_INDEX, help="catalog index to update")
    parser.add_argument(
        "--check", action="store_true", help="report without writing; exit 1 if anything would change"
    )
    args = parser.parse_args()

    catalog = Catalog.load(args.index) if args.index.exists() else Catalog(version=0)
    report = sync_vanilla(catalog, HoleStore(args.courses_root))

    for problem in report.mismatched:
        print(f"mismatch: {problem}", file=sys.stderr)
    verb = "missing" if args.check else "added"
    for hole_id in report.added:
        print(f"{verb}: {hole_id}")
    print(
        f"{len(report.verified)} verified, {len(report.added)} {verb}, "
        f"{len(report.absent)} without data under {args.courses_root}, "
        f"{len(report.mismatched)} mismatched"
    )

    if not report.ok:
        print("index not written: fix the mismatches first", file=sys.stderr)
        return 1
    if args.check:
        return 1 if report.added else 0
    if report.added:
        args.index.parent.mkdir(parents=True, exist_ok=True)
        report.catalog.save(args.index)
        print(f"wrote {args.index} (version {report.catalog.version})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
