"""golf-site-screenshot against the real app in headless Chromium. Skipped without a Playwright browser."""

import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
US_ROM_PATH = ROOT / "nes_open_us.nes"
JP_ROM_PATH = ROOT / "mario_open_jp.nes"
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _chromium_launches() -> bool:
    try:
        from playwright.sync_api import sync_playwright

        with sync_playwright() as playwright:
            playwright.chromium.launch().close()
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _chromium_launches(), reason="no Playwright Chromium")


def run(*args) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "tools.site_screenshot", *map(str, args)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_captures_each_page_viewport_and_scheme(tmp_path):
    completed = run("/", "--viewports", "phone", "--schemes", "light,dark", "-o", tmp_path)
    assert completed.returncode == 0, completed.stderr
    for scheme in ("light", "dark"):
        shot = tmp_path / f"home-phone-{scheme}.png"
        assert shot.read_bytes().startswith(PNG_SIGNATURE)


def test_a_missing_page_is_a_problem(tmp_path):
    completed = run("/no-such-page", "--viewports", "phone", "--schemes", "light", "-o", tmp_path)
    assert completed.returncode == 1
    assert "HTTP 404" in completed.stderr


def test_login_signs_each_browser_in_before_capturing(tmp_path):
    completed = run("/", "--login", "alice", "--viewports", "phone", "--schemes", "light", "-o", tmp_path)
    assert completed.returncode == 0, completed.stderr
    assert (tmp_path / "home-phone-light.png").read_bytes().startswith(PNG_SIGNATURE)


@pytest.mark.skipif(not US_ROM_PATH.exists(), reason=f"{US_ROM_PATH.name} not present")
def test_rom_cards_verify_a_vanilla_rom_and_refuse_another_file(tmp_path):
    not_a_rom = tmp_path / "not_a_rom.nes"
    not_a_rom.write_bytes(b"not a rom")
    completed = run(
        "/rom", "--viewports", "desktop", "--schemes", "light", "-o", tmp_path / "shots",
        "--rom", f"nes_open_us={US_ROM_PATH}",
        "--rom", f"mario_open_jp={not_a_rom}",
    )
    assert completed.returncode == 0, completed.stderr
    assert "cards nes_open_us=stored mario_open_jp=error" in completed.stdout
    assert (tmp_path / "shots" / "rom-desktop-light-roms.png").read_bytes().startswith(PNG_SIGNATURE)


@pytest.mark.skipif(not US_ROM_PATH.exists(), reason=f"{US_ROM_PATH.name} not present")
def test_generate_submits_the_form_and_captures_the_seed_page(tmp_path):
    completed = run("/generate", "--generate", "--viewports", "phone", "--schemes", "light", "-o", tmp_path)
    assert completed.returncode == 0, completed.stderr
    assert re.search(r"seed /h/[0-9A-Za-z]{10} download missing$", completed.stdout, re.M)
    for name in ("generate-phone-light.png", "generate-phone-light-seed.png"):
        assert (tmp_path / name).read_bytes().startswith(PNG_SIGNATURE)


@pytest.mark.skipif(not US_ROM_PATH.exists() or not JP_ROM_PATH.exists(), reason="the vanilla ROMs are not present")
def test_generate_with_roms_captures_the_download_form_ready(tmp_path):
    completed = run(
        "/generate", "--generate", "--viewports", "phone", "--schemes", "dark", "-o", tmp_path,
        "--rom", f"nes_open_us={US_ROM_PATH}",
        "--rom", f"mario_open_jp={JP_ROM_PATH}",
    )
    assert completed.returncode == 0, completed.stderr
    assert re.search(r"seed /h/[0-9A-Za-z]{10} download ready$", completed.stdout, re.M)
