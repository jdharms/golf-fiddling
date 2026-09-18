"""Unit tests for curation records and snapshots."""

import pytest

from golf.randomizer.catalog import Catalog
from golf.randomizer.curation import (
    DEFAULT_CURATION,
    CurationError,
    CurationSnapshot,
    HoleCuration,
)


def test_uncurated_holes_get_the_default_record():
    snapshot = CurationSnapshot.from_json({"nes_uk/01": {"tags": ["dogleg"]}})
    assert snapshot.for_hole("nes_us/07") == HoleCuration()
    assert HoleCuration().drawable


def test_records_apply_to_every_version_of_a_lineage():
    snapshot = CurationSnapshot.from_json(
        {"dharms/cliffside": {"family": "cliffs", "drawable": False}}
    )
    assert snapshot.for_hole("dharms/cliffside@3") == snapshot.for_hole(
        "dharms/cliffside"
    )
    assert snapshot.for_hole("dharms/cliffside@3").family == "cliffs"


def test_rejects_versioned_keys():
    with pytest.raises(CurationError, match="no @version"):
        CurationSnapshot.from_json({"nes_uk/01@2": {}})


@pytest.mark.parametrize(
    "record",
    [
        {"tag": ["dogleg"]},
        {"tags": "dogleg"},
        {"drawable": "no"},
        {"family": "Not A Slug"},
        {"display_name": 7},
        ["dogleg"],
    ],
)
def test_rejects_malformed_records(record):
    with pytest.raises(CurationError):
        CurationSnapshot.from_json({"nes_uk/01": record})


def test_stamp_depends_on_content_not_key_or_tag_order():
    a = CurationSnapshot.from_json(
        {"a/b": {"tags": ["x", "y"], "family": "f"}, "c/d": {}}
    )
    b = CurationSnapshot.from_json(
        {"c/d": {}, "a/b": {"family": "f", "tags": ["y", "x"]}}
    )
    c = CurationSnapshot.from_json({"a/b": {"tags": ["x"], "family": "f"}, "c/d": {}})
    assert a.stamp == b.stamp != c.stamp


def test_families_group_lineages_by_label():
    snapshot = CurationSnapshot.from_json(
        {
            "nes_uk/01": {"family": "nes_uk_01"},
            "jp_japan/01": {"family": "nes_uk_01"},
            "nes_us/02": {},
        }
    )
    assert snapshot.families() == {"nes_uk_01": ["jp_japan/01", "nes_uk/01"]}


def test_round_trip():
    data = {
        "a/b": {
            "tags": ["x"],
            "drawable": False,
            "family": "f",
            "display_name": "Cliffs",
        }
    }
    assert CurationSnapshot.from_json(data).to_json() == data


def test_checked_in_curation_names_only_catalog_lineages():
    snapshot = CurationSnapshot.load()
    assert DEFAULT_CURATION.exists()
    assert snapshot.unknown_lineages(Catalog.load()) == []
