#!/usr/bin/env python3
"""
NES Open Tournament Golf - Randomizer site

Runs the randomizer website (the server package) under uvicorn. Configuration comes from
GOLF_-prefixed environment variables; see docs/randomizer_devplan.md.
"""

import argparse
import sys


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

    import uvicorn

    # --reload also restarts on content that the app reads once at startup.
    extra = {"reload_includes": ["*.toml", "*.md"]} if args.reload else {}
    uvicorn.run(
        "server.app:create_app",
        factory=True,
        host=args.host,
        port=args.port,
        reload=args.reload,
        **extra,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
