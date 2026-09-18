#!/usr/bin/env python3
"""Run every linter, formatter check and type checker the repo uses.

Checks: ruff (lint and format) and pyright over the Python, djLint over the Jinja
templates, and Biome over the site's JS and CSS. Each tool reads its configuration from
pyproject.toml or biome.json. With --fix, the formatters rewrite files and the linters
apply their safe fixes; pyright has nothing to fix and runs as a check.
"""

import argparse
import subprocess
import sys
from pathlib import Path

from tools.dev.biome import ensure_binary

REPO_ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = "server/templates"


def commands(fix: bool) -> list[tuple[str, list[str]]]:
    """(name, command) for each tool, in the order they run."""
    python = [sys.executable, "-m"]
    biome = [str(ensure_binary())]
    if fix:
        return [
            ("ruff lint", [*python, "ruff", "check", "--fix", "."]),
            ("ruff format", [*python, "ruff", "format", "."]),
            ("djlint format", [*python, "djlint", "--reformat", TEMPLATES]),
            ("djlint lint", [*python, "djlint", "--lint", TEMPLATES]),
            ("biome", [*biome, "check", "--write", "."]),
            ("pyright", [*python, "pyright"]),
        ]
    return [
        ("ruff lint", [*python, "ruff", "check", "."]),
        ("ruff format", [*python, "ruff", "format", "--check", "."]),
        ("djlint format", [*python, "djlint", "--check", TEMPLATES]),
        ("djlint lint", [*python, "djlint", "--lint", TEMPLATES]),
        ("biome", [*biome, "check", "."]),
        ("pyright", [*python, "pyright"]),
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--fix",
        action="store_true",
        help="format files and apply safe lint fixes instead of only checking",
    )
    args = parser.parse_args(argv)

    failed = []
    for name, command in commands(args.fix):
        print(f"==> {name}", flush=True)
        returncode = subprocess.run(command, cwd=REPO_ROOT).returncode
        # djlint --reformat exits 1 whenever it rewrote a file
        if returncode != 0 and not (args.fix and name == "djlint format"):
            failed.append(name)

    if failed:
        print(f"\nFailed: {', '.join(failed)}")
        return 1
    print("\nAll checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
