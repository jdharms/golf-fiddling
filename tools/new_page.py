#!/usr/bin/env python3
"""Create a Markdown page for the randomizer website."""

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

from server.pages import (
    DEFAULT_ENABLED,
    DEFAULT_LISTED,
    DEFAULT_ORDER,
    PAGES_DIR,
    SLUG,
)


def slug_from_title(title: str) -> str:
    """Turn a human-written page title into a valid page slug."""
    ascii_title = (
        unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode("ascii")
    )
    return re.sub(r"[^a-z0-9]+", "-", ascii_title.lower()).strip("-")


def toml_string(value: str) -> str:
    """Quote a string using escapes shared by JSON and TOML basic strings."""
    return json.dumps(value, ensure_ascii=False)


def page_source(title: str) -> str:
    """A new page with every optional frontmatter value written explicitly."""
    quoted = toml_string(title)
    return (
        "+++\n"
        f"title = {quoted}\n"
        f"nav_title = {quoted}\n"
        f"order = {DEFAULT_ORDER}\n"
        f"enabled = {str(DEFAULT_ENABLED).lower()}\n"
        f"listed = {str(DEFAULT_LISTED).lower()}\n"
        "+++\n\n"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Create a Markdown page in the randomizer site's pages directory."
    )
    parser.add_argument("name", metavar="TITLE", help="human-written page title")
    parser.add_argument(
        "--slug",
        help="URL and filename stem (default: derived from TITLE)",
    )
    parser.add_argument(
        "--dir",
        type=Path,
        default=PAGES_DIR,
        help="page directory (default: server/content/pages)",
    )
    args = parser.parse_args(argv)

    title = args.name.strip()
    if not title:
        print("error: TITLE must not be empty", file=sys.stderr)
        return 2
    slug = args.slug if args.slug is not None else slug_from_title(title)
    if not SLUG.fullmatch(slug):
        print(
            "error: slug must contain only lowercase letters, digits, and single hyphens",
            file=sys.stderr,
        )
        return 2
    if not args.dir.is_dir():
        print(f"error: page directory does not exist: {args.dir}", file=sys.stderr)
        return 2

    path = args.dir / f"{slug}.md"
    try:
        with path.open("x", encoding="utf-8") as handle:
            handle.write(page_source(title))
    except FileExistsError:
        print(f"error: page already exists: {path}", file=sys.stderr)
        return 2

    print(f"created {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
