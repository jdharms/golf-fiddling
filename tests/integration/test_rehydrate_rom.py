"""golf-rehydrate against the real ROMs: dump, verify against the catalog, install, render."""

import dataclasses
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from golf.randomizer.catalog import JP_ROM, US_ROM, Catalog, HoleId
from golf.randomizer.rehydrate import (
    RehydrateError,
    check_rangefinder,
    check_rehydrated,
    rehydrate,
)
from golf.rendering.rangefinder import METADATA

ROOT = Path(__file__).resolve().parents[2]
US_PATH = ROOT / "nes_open_us.nes"
JP_PATH = ROOT / "mario_open_jp.nes"

pytestmark = pytest.mark.skipif(
    not US_PATH.exists(), reason=f"{US_PATH.name} not present"
)


@pytest.fixture(scope="module")
def us_only(tmp_path_factory) -> tuple[Path, Path]:
    """A hole store and rangefinder rehydrated from the US ROM, with a marker kept."""
    root = tmp_path_factory.mktemp("rehydrated")
    holes, rangefinder = root / "courses", root / "rangefinder"
    (holes / "us").mkdir(parents=True)
    (holes / "us" / ".gitkeep").touch()
    report = rehydrate(Catalog.load(), holes, {US_ROM: US_PATH}, rangefinder)
    assert report.dumped == (US_ROM,)
    assert report.skipped == (JP_ROM,)
    assert report.holes == 54
    return holes, rangefinder


def test_installs_every_nes_open_hole_and_keeps_the_markers(us_only):
    holes, _ = us_only
    for course in ("japan", "us", "uk"):
        assert len(list((holes / course).glob("hole_*.json"))) == 18
    assert (holes / "us" / ".gitkeep").exists()
    assert not list(holes.glob(".rehydrate-*"))
    assert check_rehydrated(Catalog.load(), holes, [US_ROM]) == 54


def test_renders_the_rangefinder_from_what_it_installed(us_only):
    holes, rangefinder = us_only
    check_rangefinder(holes, rangefinder)
    assert sorted(p.name for p in (rangefinder / "images").iterdir()) == [
        "japan",
        "uk",
        "us",
    ]


def test_a_rangefinder_rendered_from_other_courses_is_stale(us_only, tmp_path):
    holes, rangefinder = us_only
    other = tmp_path / "other"
    (other / "japan").mkdir(parents=True)
    shutil.copy(holes / "japan" / "hole_01.json", other / "japan" / "hole_01.json")
    with pytest.raises(RehydrateError, match="rendered from other courses"):
        check_rangefinder(other, rangefinder)
    with pytest.raises(RehydrateError, match="not found"):
        check_rangefinder(holes, tmp_path / "unrendered")


def test_a_hole_that_does_not_match_the_catalog_installs_nothing(tmp_path):
    catalog = Catalog.load()
    hole_id = HoleId.parse("nes_uk/07")
    entries = dict(catalog.entries)
    entries[hole_id] = dataclasses.replace(entries[hole_id], content_hash="0" * 64)
    with pytest.raises(RehydrateError, match="nes_uk/07"):
        rehydrate(Catalog(catalog.version, entries), tmp_path, {US_ROM: US_PATH})
    assert not list(tmp_path.rglob("*.json"))


def test_a_wrong_rom_is_refused_before_anything_is_written(tmp_path):
    wrong = tmp_path / "wrong.nes"
    data = bytearray(US_PATH.read_bytes())
    data[0x100] ^= 0xFF
    wrong.write_bytes(bytes(data))
    holes = tmp_path / "courses"
    with pytest.raises(RehydrateError, match="is not NES Open"):
        rehydrate(Catalog.load(), holes, {US_ROM: wrong})
    assert not holes.exists()


def test_the_us_rom_is_required(tmp_path):
    with pytest.raises(RehydrateError, match="required ROM missing"):
        rehydrate(Catalog.load(), tmp_path, {JP_ROM: JP_PATH})


@pytest.mark.skipif(not JP_PATH.exists(), reason=f"{JP_PATH.name} not present")
def test_the_cli_rehydrates_both_roms_and_checks_the_result(tmp_path):
    holes, rangefinder = tmp_path / "courses", tmp_path / "rangefinder"
    args = ["--rom-dir", str(ROOT), "--holes", str(holes)]
    args += ["--rangefinder", str(rangefinder)]

    def run(*extra: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-m", "tools.rehydrate", *args, *extra],
            cwd=ROOT,
            capture_output=True,
            text=True,
        )

    assert run("--check").returncode == 1
    installed = run()
    assert installed.returncode == 0, installed.stderr
    assert "installed 144 holes" in installed.stdout
    assert (rangefinder / METADATA).exists()
    assert run("--check").returncode == 0

    (holes / "jp" / "jp_hawaii" / "hole_05.json").write_text("{}")
    assert run("--check").returncode == 1
