"""Unit tests for the hole catalog: ids, the content hash, the index, the store and sync."""

import copy
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from golf.randomizer.catalog import (
    DEFAULT_COURSES,
    DEFAULT_INDEX,
    REPO_ROOT,
    US_ROM,
    Catalog,
    CatalogEntry,
    CatalogError,
    HoleId,
    HoleStore,
    RomSource,
    content_hash,
    sync_vanilla,
)


def entry(text: str, withdrawn: bool = False) -> CatalogEntry:
    return CatalogEntry(
        HoleId.parse(text),
        RomSource(US_ROM, "us", 1),
        "0" * 64,
        4,
        400,
        "someone",
        withdrawn,
    )


def catalog_of(*entries: CatalogEntry) -> Catalog:
    return Catalog(1, {e.id: e for e in entries})


class TestHoleId:
    def test_version_one_spellings_are_the_same_id(self):
        assert (
            HoleId.parse("nes_uk/01")
            == HoleId.parse("nes_uk/01@1")
            == HoleId("nes_uk/01", 1)
        )

    def test_canonical_form_omits_version_one(self):
        assert str(HoleId.parse("nes_uk/01@1")) == "nes_uk/01"
        assert str(HoleId.parse("dharms/cliffside@2")) == "dharms/cliffside@2"

    @pytest.mark.parametrize(
        "text",
        [
            "nes_uk",
            "nes_uk/01/02",
            "NES_UK/01",
            "nes-uk/01",
            "nes_uk/01@0",
            "nes_uk/01@",
            "nes_uk/01@02",
            "",
        ],
    )
    def test_rejects_malformed_ids(self, text):
        with pytest.raises(CatalogError):
            HoleId.parse(text)

    def test_orders_versions_numerically(self):
        assert HoleId.parse("a/b@2") < HoleId.parse("a/b@10")


class TestCatalog:
    def test_newest_picks_the_highest_version_of_each_lineage(self):
        catalog = catalog_of(
            entry("a/b"), entry("a/b@2"), entry("a/b@10"), entry("c/d")
        )
        newest = catalog.newest()
        assert {lineage: str(e.id) for lineage, e in newest.items()} == {
            "a/b": "a/b@10",
            "c/d": "c/d",
        }

    def test_a_withdrawn_newest_version_does_not_roll_back(self):
        catalog = catalog_of(
            entry("a/b"), entry("a/b@2", withdrawn=True), entry("c/d", withdrawn=True)
        )
        assert catalog.newest() == {}

    def test_json_round_trip(self):
        catalog = catalog_of(entry("a/b"), entry("a/b@2", withdrawn=True))
        assert Catalog.from_json(catalog.to_json()) == catalog

    def test_rejects_non_canonical_keys(self):
        data = catalog_of(entry("a/b")).to_json()
        data["holes"]["a/b@1"] = data["holes"].pop("a/b")
        with pytest.raises(CatalogError, match="canonical"):
            Catalog.from_json(data)

    def test_rejects_unknown_fields(self):
        data = catalog_of(entry("a/b")).to_json()
        data["holes"]["a/b"]["tags"] = ["hard"]
        with pytest.raises(CatalogError, match="unknown"):
            Catalog.from_json(data)

    def test_lookup_accepts_either_spelling(self):
        catalog = catalog_of(entry("a/b"))
        assert catalog["a/b@1"] is catalog["a/b"]
        with pytest.raises(CatalogError):
            catalog["a/b@2"]


class TestContentHash:
    def test_ignores_what_never_reaches_the_rom(self, hole_01_data):
        before = content_hash(hole_01_data)
        hole = copy.deepcopy(hole_01_data)
        hole.metadata["hole"] = 99
        hole.metadata["_debug"] = {"anything": 1}
        hole.terrain.append(
            [0xDF] * len(hole.terrain[0])
        )  # a hidden row past terrain_height
        assert content_hash(hole) == before

    @pytest.mark.parametrize(
        "change",
        [
            lambda h: h.terrain[0].__setitem__(0, h.terrain[0][0] ^ 1),
            lambda h: h.greens[5].__setitem__(5, h.greens[5][5] ^ 1),
            lambda h: h.metadata["flag_positions"][0].__setitem__("x_offset", 0),
            lambda h: h.metadata.__setitem__("distance", h.metadata["distance"] + 1),
            lambda h: h.metadata.__setitem__(
                "scroll_limit", h.metadata["scroll_limit"] + 1
            ),
            lambda h: setattr(h, "terrain_height", h.terrain_height - 2),
        ],
    )
    def test_changes_with_rom_bound_content(self, hole_01_data, change):
        hole = copy.deepcopy(hole_01_data)
        change(hole)
        assert content_hash(hole) != content_hash(hole_01_data)


def copy_courses(root: Path, *courses: str) -> Path:
    for course in courses:
        shutil.copytree(DEFAULT_COURSES / course, root / course)
    return root


class TestHoleStore:
    def test_loads_a_matching_hole_and_refuses_a_changed_one(self, tmp_path):
        store = HoleStore(copy_courses(tmp_path, "us"))
        report = sync_vanilla(Catalog(0), store)
        hole_entry = report.catalog["nes_us/01"]
        assert store.load(hole_entry).metadata["par"] == hole_entry.par

        path = store.path_for(hole_entry)
        data = json.loads(path.read_text())
        data["distance"] += 1
        path.write_text(json.dumps(data))
        with pytest.raises(CatalogError, match="content hash"):
            store.load(hole_entry)

    def test_refuses_withdrawn_entries(self, tmp_path):
        store = HoleStore(copy_courses(tmp_path, "us"))
        withdrawn = CatalogEntry(
            **{
                **vars(sync_vanilla(Catalog(0), store).catalog["nes_us/01"]),
                "withdrawn": True,
            }
        )
        with pytest.raises(CatalogError, match="withdrawn"):
            store.load(withdrawn)


class TestSyncVanilla:
    def test_adds_then_verifies(self, tmp_path):
        store = HoleStore(copy_courses(tmp_path, "us", "uk"))
        first = sync_vanilla(Catalog(0), store)
        assert len(first.added) == 36 and first.ok
        assert first.catalog.version == 1
        assert {e.id.lineage.split("/")[0] for e in first.catalog} == {
            "nes_us",
            "nes_uk",
        }

        second = sync_vanilla(first.catalog, store)
        assert len(second.verified) == 36 and not second.added
        assert second.catalog is first.catalog

    def test_never_rewrites_a_changed_hole(self, tmp_path):
        store = HoleStore(copy_courses(tmp_path, "us"))
        catalog = sync_vanilla(Catalog(0), store).catalog
        path = tmp_path / "us" / "hole_07.json"
        data = json.loads(path.read_text())
        data["par"] = 4 if data["par"] == 3 else 3
        path.write_text(json.dumps(data))

        report = sync_vanilla(catalog, store)
        assert not report.ok
        assert report.mismatched[0].startswith("nes_us/07: content_hash, par differ")
        assert report.catalog is catalog

    def test_entries_without_data_are_absent_not_errors(self, tmp_path):
        store = HoleStore(copy_courses(tmp_path, "us"))
        report = sync_vanilla(Catalog.load(), store)
        assert report.ok and not report.added
        assert len(report.verified) == 18
        assert "nes_uk/01" in {str(hole_id) for hole_id in report.absent}


def run_sync(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "tools.data.catalog_sync", *args],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )


class TestSyncCli:
    def test_check_exit_codes_and_write(self, tmp_path):
        courses = copy_courses(tmp_path / "courses", "us")
        index = tmp_path / "holes.json"

        assert run_sync(str(courses), "--index", str(index), "--check").returncode == 1
        assert not index.exists()
        assert run_sync(str(courses), "--index", str(index)).returncode == 0
        assert len(Catalog.load(index)) == 18
        assert run_sync(str(courses), "--index", str(index), "--check").returncode == 0

        path = courses / "us" / "hole_03.json"
        data = json.loads(path.read_text())
        data["tee"]["x"] += 1
        path.write_text(json.dumps(data))
        written = index.read_text()
        result = run_sync(str(courses), "--index", str(index))
        assert result.returncode == 1
        assert "nes_us/03" in result.stderr
        assert index.read_text() == written


class TestCheckedInIndex:
    def test_is_in_canonical_form(self):
        assert (
            DEFAULT_INDEX.read_text()
            == json.dumps(Catalog.load().to_json(), indent=2) + "\n"
        )

    def test_every_vanilla_hole_matches_its_data(self):
        catalog = Catalog.load()
        store = HoleStore()
        checked = 0
        for hole_entry in catalog:
            path = store.path_for(hole_entry)
            if hole_entry.id.lineage.startswith("jp_") and not path.exists():
                continue  # Mario Open dumps are not checked in
            store.load(hole_entry)
            checked += 1
        assert checked >= 54
