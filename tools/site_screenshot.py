#!/usr/bin/env python3
"""
NES Open Tournament Golf - Randomizer site screenshots

Serves the site in-process on a free localhost port with an in-memory database, and
captures full-page PNGs of its pages with Playwright's headless Chromium, at each viewport
in each color scheme. On the ROM setup page, --rom loads files into the cards and the
final card states are printed. With --generate, the generate form is submitted with its
defaults and the seed page it lands on is captured too; that builds a real seed, so it
needs the vanilla US ROM in GOLF_ROM_DIR (the repository root by default). Browser console
errors and page errors are printed and make the command exit 1.

Needs the dev dependencies and a Playwright browser (uv run playwright install chromium).
"""

import argparse
import re
import socket
import sys
import threading
import time
from dataclasses import replace
from pathlib import Path

VIEWPORTS = {"desktop": (1280, 800), "phone": (390, 844)}
SCHEMES = ("light", "dark")
SETTLE_MS = 10_000
GENERATE_MS = 60_000

EXAMPLES = """
examples:
  golf-site-screenshot -o shots
  golf-site-screenshot / --viewports phone --schemes dark -o shots
  golf-site-screenshot /rom --rom nes_open_us=nes_open_us.nes --rom mario_open_jp=guest.nes -o shots
  golf-site-screenshot /generate --generate -o shots
"""


def comma_choices(choices):
    def parse(text: str) -> list[str]:
        items = [item.strip() for item in text.split(",") if item.strip()]
        unknown = [item for item in items if item not in choices]
        if not items or unknown:
            raise argparse.ArgumentTypeError(f"expected a comma-separated selection of {', '.join(choices)}")
        return items

    return parse


def rom_file(text: str) -> tuple[str, Path]:
    rom_id, sep, path = text.partition("=")
    if not sep or not rom_id or not path:
        raise argparse.ArgumentTypeError(f"expected ID=PATH, got {text!r}")
    if not Path(path).is_file():
        raise argparse.ArgumentTypeError(f"no such file: {path}")
    return rom_id, Path(path)


def slug(path: str) -> str:
    name = re.sub(r"[^A-Za-z0-9_.-]", "-", path.strip("/").replace("/", "_"))
    return name or "home"


class LiveServer:
    """The app under uvicorn in a background thread, on a free port of 127.0.0.1."""

    def __init__(self, app):
        import uvicorn

        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.bind(("127.0.0.1", 0))
        self.server = uvicorn.Server(uvicorn.Config(app, log_level="warning"))
        self.thread = threading.Thread(target=self.server.run, kwargs={"sockets": [self.sock]}, daemon=True)

    def __enter__(self) -> str:
        self.thread.start()
        deadline = time.monotonic() + 15
        while not self.server.started:
            if not self.thread.is_alive() or time.monotonic() > deadline:
                raise RuntimeError("the site did not start")
            time.sleep(0.05)
        return f"http://127.0.0.1:{self.sock.getsockname()[1]}"

    def __exit__(self, *exc) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=10)
        self.sock.close()


def settle(page) -> None:
    """Wait until no ROM card is still checking."""
    page.wait_for_function("() => !document.querySelector('[data-state=checking]')", timeout=SETTLE_MS)


def card_states(page) -> str:
    states = page.eval_on_selector_all("article.rom", "cards => cards.map(c => `${c.dataset.romId}=${c.dataset.state}`)")
    return " ".join(states)


def capture(base: str, args: argparse.Namespace) -> tuple[list[Path], list[str]]:
    from playwright.sync_api import sync_playwright

    written: list[Path] = []
    problems: list[str] = []
    args.out_dir.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            for path in args.pages:
                for viewport in args.viewports:
                    for scheme in args.schemes:
                        width, height = VIEWPORTS[viewport]
                        label = f"{path} {viewport} {scheme}"
                        context = browser.new_context(viewport={"width": width, "height": height}, color_scheme=scheme)
                        page = context.new_page()
                        page.on(
                            "console",
                            lambda message, label=label: problems.append(f"{label}: console {message.type}: {message.text}")
                            if message.type == "error"
                            else None,
                        )
                        page.on("pageerror", lambda error, label=label: problems.append(f"{label}: page error: {error}"))
                        try:
                            response = page.goto(base + path, wait_until="networkidle")
                            if response is None or not response.ok:
                                status = response.status if response is not None else "no response"
                                problems.append(f"{label}: HTTP {status}")
                            settle(page)
                            name = f"{slug(path)}-{viewport}-{scheme}"
                            shot = args.out_dir / f"{name}.png"
                            page.screenshot(path=shot, full_page=True)
                            written.append(shot)

                            if args.rom and page.locator("article.rom").count():
                                for rom_id, file in args.rom:
                                    card = f'article.rom[data-rom-id="{rom_id}"]'
                                    if not page.locator(card).count():
                                        problems.append(f"{label}: no ROM card {rom_id!r}")
                                        continue
                                    page.set_input_files(f"{card} input[type=file]", str(file))
                                    settle(page)
                                shot = args.out_dir / f"{name}-roms.png"
                                page.screenshot(path=shot, full_page=True)
                                written.append(shot)
                                print(f"{label}: cards {card_states(page)}")

                            if args.generate and page.locator("#generate-form").count():
                                with page.expect_navigation(timeout=GENERATE_MS) as navigation:
                                    page.click("#generate-form button[type=submit]")
                                response = navigation.value
                                if response is None or not response.ok or "/h/" not in page.url:
                                    status = response.status if response is not None else "no response"
                                    problems.append(f"{label}: generating landed on {page.url} (HTTP {status})")
                                shot = args.out_dir / f"{name}-seed.png"
                                page.screenshot(path=shot, full_page=True)
                                written.append(shot)
                                print(f"{label}: seed {page.url.removeprefix(base)}")
                        finally:
                            context.close()
        finally:
            browser.close()
    return written, problems


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Render randomizer site pages to PNG in headless Chromium.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=EXAMPLES,
    )
    parser.add_argument("pages", nargs="*", default=["/", "/rom"], help="paths to capture (default: / /rom)")
    parser.add_argument("-o", "--out-dir", type=Path, default=Path("site-screenshots"), help="where PNGs go (default: %(default)s)")
    parser.add_argument(
        "--viewports",
        type=comma_choices(VIEWPORTS),
        default=list(VIEWPORTS),
        help=f"comma-separated: {', '.join(f'{name} {w}x{h}' for name, (w, h) in VIEWPORTS.items())} (default: all)",
    )
    parser.add_argument("--schemes", type=comma_choices(SCHEMES), default=list(SCHEMES), help="comma-separated: light, dark (default: both)")
    parser.add_argument(
        "--rom",
        type=rom_file,
        action="append",
        metavar="ID=PATH",
        help="on pages with ROM cards, load this file into the card for this ROM id, then capture again as <name>-roms.png",
    )
    parser.add_argument(
        "--generate",
        action="store_true",
        help="on the generate page, submit the form and capture the seed page as <name>-seed.png (needs the vanilla US ROM)",
    )
    args = parser.parse_args()

    try:
        from playwright.sync_api import Error as PlaywrightError
    except ImportError:
        print("error: playwright is not installed; run uv sync to install the dev dependencies", file=sys.stderr)
        return 1

    from server.app import create_app
    from server.config import Config
    from server.ratelimit import RateLimiter

    # The environment's ROM and hole directories, so --generate can build; never its database.
    config = replace(Config.from_env(), database=":memory:")
    # Every viewport and scheme may generate a seed, more than a player's bucket holds.
    limiter = RateLimiter(capacity=1000, refill_seconds=1)
    try:
        with LiveServer(create_app(config, rate_limiter=limiter)) as base:
            written, problems = capture(base, args)
    except PlaywrightError as problem:
        print(f"error: {problem}", file=sys.stderr)
        print("if the browser is missing: uv run playwright install chromium", file=sys.stderr)
        return 1

    for shot in written:
        print(f"wrote {shot}")
    for problem in problems:
        print(f"problem: {problem}", file=sys.stderr)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
