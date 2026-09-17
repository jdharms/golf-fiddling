#!/usr/bin/env python3
"""
NES Open Tournament Golf - Randomizer site strings

Lists the site's unwritten strings: entries in server/strings/ whose text is still empty,
grouped by catalog file. See server/CLAUDE.md, "Player-facing text".
"""

import argparse
import sys
from pathlib import Path

from server.strings import CATALOG_DIR, Strings, StringsError


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="List the randomizer site's strings with empty text, by file.")
    parser.add_argument("--dir", type=Path, default=CATALOG_DIR, help="catalog directory (default: server/strings)")
    parser.add_argument("--notes", action="store_true", help="print each entry's note under its key")
    args = parser.parse_args(argv)

    try:
        catalogs = Strings.load_files(args.dir)
    except StringsError as problem:
        print(f"error: {problem}", file=sys.stderr)
        return 2

    unwritten = {file: strings.unwritten() for file, strings in catalogs.items()}
    unwritten = {file: keys for file, keys in unwritten.items() if keys}
    if not unwritten:
        print("every string is written")
        return 0

    for index, (file, keys) in enumerate(unwritten.items()):
        if index:
            print()
        print(f"{file.relative_to(args.dir)} ({len(keys)})")
        for key in keys:
            print(f"  {key}")
            if args.notes:
                print(f"      {catalogs[file].entry(key).note}")
    total = sum(len(keys) for keys in unwritten.values())
    print(f"\n{total} unwritten in {len(unwritten)} of {len(catalogs)} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
