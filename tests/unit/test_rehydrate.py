"""The rehydration checks that need no ROM: what the site refuses to start without."""

import json

import pytest

from golf.randomizer.catalog import Catalog
from golf.randomizer.rehydrate import RehydrateError, check_site_data
from golf.rendering.rangefinder import METADATA
from tests.synthetic_holes import write_courses


@pytest.fixture
def site(tmp_path):
    """A ROM directory holding a US ROM file, an empty hole store and no rangefinder."""
    roms, holes, rangefinder = (tmp_path / name for name in ("roms", "holes", "rf"))
    roms.mkdir()
    (roms / "nes_open_us.nes").write_bytes(b"")
    holes.mkdir()
    rangefinder.mkdir()
    return roms, holes, rangefinder


def render_metadata(rangefinder, courses: dict[str, int]) -> None:
    metadata = {"courses": {c: {"holes": [{}] * n} for c, n in courses.items()}}
    (rangefinder / METADATA).write_text(json.dumps(metadata))


def test_refuses_without_a_us_rom(site):
    roms, holes, rangefinder = site
    (roms / "nes_open_us.nes").unlink()
    with pytest.raises(RehydrateError, match="required ROM missing"):
        check_site_data(Catalog(0), roms, holes, rangefinder)


def test_refuses_holes_the_catalog_expects_but_the_store_lacks(site):
    roms, holes, rangefinder = site
    catalog = Catalog.load()
    with pytest.raises(RehydrateError, match=r"(?s)54 of 54 holes.*and 44 more"):
        check_site_data(catalog, roms, holes, rangefinder)


def test_refuses_a_missing_or_stale_rangefinder(site):
    roms, holes, rangefinder = site
    with pytest.raises(RehydrateError, match="metadata not found"):
        check_site_data(Catalog(0), roms, holes, rangefinder)
    write_courses(holes, "us")
    render_metadata(rangefinder, {"japan": 18})
    with pytest.raises(RehydrateError, match="rendered from other courses"):
        check_site_data(Catalog(0), roms, holes, rangefinder)


def test_accepts_a_store_and_rangefinder_that_agree(site):
    roms, holes, rangefinder = site
    write_courses(holes, "us")
    render_metadata(rangefinder, {"us": 18})
    assert check_site_data(Catalog(0), roms, holes, rangefinder) == 0
