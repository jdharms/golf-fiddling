"""The rangefinder's browser interactions against the real site."""

import pytest

from server.app import create_app
from server.config import Config
from server.live import LiveServer

TIMEOUT_MS = 15_000


def _chromium_launches() -> bool:
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            playwright.chromium.launch().close()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _chromium_launches(), reason="no Playwright Chromium")


def test_rangefinder_measures_zooms_switches_holes_and_opens_green():
    from playwright.sync_api import sync_playwright

    app = create_app(Config(database=":memory:"))
    errors: list[str] = []
    with LiveServer(app) as base, sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            page = browser.new_page(viewport={"width": 1280, "height": 800})
            page.set_default_timeout(TIMEOUT_MS)
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(base + "/rangefinder")
            page.wait_for_selector('.rangefinder[data-state="ready"]')

            image = page.locator("#hole-image")
            viewer = page.locator(".rangefinder-viewer")
            viewer_height = viewer.evaluate("element => element.clientHeight")
            assert image.evaluate("image => image.clientWidth") == 352
            image.click(position={"x": 40, "y": 40})
            image.click(position={"x": 40, "y": 140})
            assert "distance=100.0" in page.locator("#distance-display").inner_text()

            page.click("#zoom-in")
            assert image.evaluate("image => image.clientWidth") == 528

            page.click("#zoom-reset")
            page.select_option("#hole-select", "7")
            page.wait_for_function(
                "element => element.scrollTop > 0 && element.scrollTop + element.clientHeight === element.scrollHeight",
                arg=viewer.element_handle(),
            )
            assert viewer.evaluate("element => element.clientHeight") == viewer_height

            page.select_option("#hole-select", "2")
            assert "/images/japan/hole_02.png" in image.get_attribute("src")
            assert viewer.evaluate("element => element.clientHeight") == viewer_height
            assert "distance_empty" in page.locator("#distance-display").inner_text()

            page.click("#green-view")
            page.wait_for_selector("#green-modal[open]")
            assert "current=1 total=4" in page.locator("#flag-indicator").inner_text()
            page.keyboard.press("ArrowRight")
            assert "current=2 total=4" in page.locator("#flag-indicator").inner_text()
            page.keyboard.press("Escape")
            assert not page.locator("#green-modal").evaluate("dialog => dialog.open")
        finally:
            browser.close()

    assert not errors
