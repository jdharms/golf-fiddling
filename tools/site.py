#!/usr/bin/env python3
"""
NES Open Tournament Golf - Randomizer site

Runs the randomizer website (the server package) under uvicorn. Configuration comes from
GOLF_-prefixed environment variables; see docs/randomizer_devplan.md. Refuses to start
until golf-rehydrate has dumped the holes of every ROM in the ROM directory and rendered
the rangefinder from them.
"""

import argparse
import sys

from golf.randomizer.catalog import Catalog
from golf.randomizer.rehydrate import RehydrateError, check_site_data
from golf.rendering.rangefinder import DEFAULT_OUTPUT
from server.config import Config


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run the randomizer website under uvicorn."
    )
    parser.add_argument(
        "--host", default="127.0.0.1", help="interface to bind (default: %(default)s)"
    )
    parser.add_argument(
        "--port", type=int, default=8000, help="port to bind (default: %(default)s)"
    )
    parser.add_argument(
        "--reload", action="store_true", help="restart on code changes, for development"
    )
    args = parser.parse_args()

    config = Config.from_env()
    try:
        check_site_data(
            Catalog.load(), config.rom_dir, config.holes_dir, DEFAULT_OUTPUT
        )
    except RehydrateError as error:
        print(f"error: {error}\nrun `golf-rehydrate` first", file=sys.stderr)
        return 1

    import uvicorn

    # --reload also restarts on content that the app reads once at startup.
    uvicorn.run(
        "server.app:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        reload=args.reload,
        reload_includes=["*.toml", "*.md"] if args.reload else None,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
