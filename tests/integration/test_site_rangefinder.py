"""The rangefinder's browser interactions against the real site."""

from urllib.parse import parse_qs, urlsplit

import pytest

from server.app import create_app
from server.config import Config
from server.live import LiveServer
from server.strings import Entry, Strings

TIMEOUT_MS = 15_000


def _unwritten() -> Strings:
    """The real catalog with no text, so every string renders as the placeholder naming its key."""
    real = Strings.load()
    return Strings({key: Entry(real.entry(key).note, "") for key in real.keys()})  # noqa: SIM118 (Strings, not a dict)


def _chromium_launches() -> bool:
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            playwright.chromium.launch().close()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(
    not _chromium_launches(), reason="no Playwright Chromium"
)


def test_rangefinder_measures_zooms_switches_holes_and_opens_green():
    from playwright.sync_api import sync_playwright

    app = create_app(Config(database=":memory:"), strings=_unwritten())
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
            assert (
                page.locator("#distance-display").inner_text()
                == "⟦rangefinder.script.distance distance=100.0⟧"
            )

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
            assert (
                page.locator("#distance-display").inner_text()
                == "⟦rangefinder.script.distance_empty⟧"
            )

            page.click("#green-view")
            page.wait_for_selector("#green-modal[open]")
            assert (
                page.locator("#flag-indicator").inner_text()
                == "⟦rangefinder.script.flag current=1 total=4⟧"
            )
            page.keyboard.press("ArrowRight")
            assert (
                page.locator("#flag-indicator").inner_text()
                == "⟦rangefinder.script.flag current=2 total=4⟧"
            )
            page.keyboard.press("Escape")
            assert not page.locator("#green-modal").evaluate("dialog => dialog.open")
        finally:
            browser.close()

    assert not errors


def test_rangefinder_permalink_tracks_location_copies_and_does_not_add_history():
    from playwright.sync_api import sync_playwright

    app = create_app(Config(database=":memory:"), strings=_unwritten())
    errors: list[str] = []
    with LiveServer(app) as base, sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        try:
            context = browser.new_context(
                permissions=["clipboard-read", "clipboard-write"]
            )
            page = context.new_page()
            page.set_default_timeout(TIMEOUT_MS)
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(base + "/")
            page.goto(base + "/rangefinder?course=us&hole=3")
            page.wait_for_selector('.rangefinder[data-state="ready"]')

            assert page.locator("#course-select").input_value() == "us"
            assert page.locator("#hole-select").input_value() == "3"
            history_length = page.evaluate("history.length")

            page.select_option("#hole-select", "4")
            assert parse_qs(urlsplit(page.url).query) == {
                "course": ["us"],
                "hole": ["4"],
            }
            assert page.evaluate("history.length") == history_length

            page.click("#copy-permalink")
            assert await_text(page, "navigator.clipboard.readText()") == page.url
            assert (
                page.locator("#permalink-status").inner_text()
                == "⟦rangefinder.script.permalink_copied⟧"
            )

            page.go_back()
            assert page.url == base + "/"

            page.goto(base + "/rangefinder?course=not-a-course&hole=999")
            page.wait_for_selector('.rangefinder[data-state="ready"]')
            assert parse_qs(urlsplit(page.url).query) == {
                "course": ["japan"],
                "hole": ["1"],
            }
        finally:
            browser.close()

    assert not errors


def await_text(page, expression: str) -> str:
    page.wait_for_function(f"async () => Boolean(await {expression})")
    return page.evaluate(f"async () => await {expression}")
