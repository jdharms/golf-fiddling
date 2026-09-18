"""The download form in headless Chromium: the ROM it saves is the library's finished ROM.

This is the only test of download.js's IPS applier. Skipped without a Playwright browser or
the vanilla ROMs.
"""

import json
from pathlib import Path

import pytest

from golf.core.patches.sram_defaults import VANILLA_CLUBS, Club
from golf.randomizer.build import PlayerOptions, finish
from golf.randomizer.manifest import Manifest
from server.app import create_app
from server.config import Config
from server.live import LiveServer
from server.ratelimit import RateLimiter

ROOT = Path(__file__).resolve().parents[2]
US_ROM_PATH = ROOT / "nes_open_us.nes"
JP_ROM_PATH = ROOT / "mario_open_jp.nes"
TIMEOUT_MS = 60_000


def _chromium_launches() -> bool:
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            playwright.chromium.launch().close()
        return True
    except Exception:
        return False


pytestmark = [
    pytest.mark.skipif(
        not US_ROM_PATH.exists() or not JP_ROM_PATH.exists(),
        reason="the vanilla ROMs are not present",
    ),
    pytest.mark.skipif(not _chromium_launches(), reason="no Playwright Chromium"),
]


def test_the_downloaded_rom_is_the_finished_rom(tmp_path):
    from playwright.sync_api import sync_playwright

    app = create_app(
        Config(database=":memory:", rom_dir=ROOT), rate_limiter=RateLimiter(100, 1)
    )
    errors: list[str] = []
    with LiveServer(app) as base, sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_context(accept_downloads=True).new_page()
            page.set_default_timeout(TIMEOUT_MS)
            page.on("pageerror", lambda error: errors.append(str(error)))

            page.goto(base + "/rom")
            for rom_id, path in (
                ("nes_open_us", US_ROM_PATH),
                ("mario_open_jp", JP_ROM_PATH),
            ):
                page.set_input_files(
                    f'article.rom[data-rom-id="{rom_id}"] input[type=file]', str(path)
                )
                page.wait_for_selector(
                    f'article.rom[data-rom-id="{rom_id}"][data-state="stored"]'
                )

            page.goto(base + "/generate")
            with page.expect_navigation():
                page.click("#generate-form button[type=submit]")
            seed_id = page.url.rsplit("/", 1)[1]
            page.wait_for_selector('article.download[data-state="ready"]')

            page.fill("#download-name", "yoshi")
            page.uncheck('input[name="clubs"][value="2W"]')
            with page.expect_download() as caught:
                page.click("#download-form button[type=submit]")
            saved = tmp_path / "download.nes"
            caught.value.save_as(saved)
            page.wait_for_selector('article.download[data-state="done"]')
            suggested = caught.value.suggested_filename
        finally:
            browser.close()

        with app.state.db.transaction() as conn:
            row = conn.execute(
                "SELECT manifest, unfinished_ips FROM seeds WHERE id = ?", (seed_id,)
            ).fetchone()

    assert not errors
    manifest = Manifest.from_json(json.loads(row["manifest"]))
    assert suggested == f"notgr_par{manifest.course.par}_{seed_id}.nes"
    options = PlayerOptions("YOSHI", frozenset(VANILLA_CLUBS) - {Club.W2})
    expected = finish(
        manifest, US_ROM_PATH.read_bytes(), row["unfinished_ips"], options
    )
    assert saved.read_bytes() == expected.rom
