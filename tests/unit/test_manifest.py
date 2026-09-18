"""Unit tests for the manifest model and its JSON form."""

import json

import pytest

from golf.core.patches.sram_defaults import Club
from golf.randomizer.catalog import (
    JP_ROM,
    US_ROM,
    Catalog,
    CatalogEntry,
    HoleId,
    RomSource,
)
from golf.randomizer.manifest import (
    ClubRules,
    Course,
    Manifest,
    ManifestError,
    Settings,
    Slot,
    required_roms,
)

PARS = (4, 5, 4, 3, 4, 3, 4, 5, 4, 4, 4, 3, 5, 4, 5, 3, 4, 4)


def slots(prefix: str = "nes_us") -> tuple[Slot, ...]:
    return tuple(
        Slot(HoleId(f"{prefix}/{number:02d}"), par, number)
        for number, par in enumerate(PARS, start=1)
    )


def course(**overrides) -> Course:
    fields = dict(
        holes=slots(),
        music="nes_uk",
        mercy_point=9,
        clubs=ClubRules(),
        magic_words=("DIVOT", "CADDY", "BOGEY"),
        sram_magic=0x5247,
    )
    return Course(**(fields | overrides))


def manifest(**overrides) -> Manifest:
    fields = dict(
        schema=1,
        generator_version=1,
        catalog_version=1,
        curation_stamp="stamp",
        settings=Settings(prng_seed="abc"),
        course=course(),
    )
    return Manifest(**(fields | overrides))


def round_trip(value: Manifest) -> Manifest:
    return Manifest.from_json(json.loads(json.dumps(value.to_json())))


def test_round_trips_through_json():
    value = manifest(
        settings=Settings(
            prng_seed="abc",
            par=70,
            sources={JP_ROM},
            exclude_tags={"expert"},
            allow_family_repeats=True,
            music="jp_hawaii",
            mercy_point=None,
            clubs=ClubRules(max=10, banned={Club.W1}, required_bag={Club.I7, Club.W3}),
        ),
        course=course(
            mercy_point=None, clubs=ClubRules(max=12, banned={Club.SW, Club.W2})
        ),
    )
    assert round_trip(value) == value


def test_json_shape():
    data = manifest().to_json()
    assert list(data) == [
        "schema",
        "generator_version",
        "catalog_version",
        "curation_stamp",
        "settings",
        "course",
    ]
    assert data["course"]["holes"][0] == {
        "id": "nes_us/01",
        "par": 4,
        "transforms": [],
        "wind_seed": 1,
    }
    assert data["settings"]["clubs"] == {"max": 14, "banned": [], "required_bag": None}
    assert data["settings"]["sources"] == [US_ROM, JP_ROM]


def test_course_json_carries_the_sram_magic():
    assert manifest().to_json()["course"]["sram_magic"] == 0x5247
    data = manifest().to_json()
    del data["course"]["sram_magic"]
    with pytest.raises(ManifestError, match="missing fields \\['sram_magic'\\]"):
        Manifest.from_json(data)


@pytest.mark.parametrize(
    "sram_magic", [0x0047, 0xFF47, 0x5200, 0x52FF, -1, 0x10000, "0x5247", True, None]
)
def test_rejects_a_bad_sram_magic(sram_magic):
    with pytest.raises(ManifestError, match="sram_magic"):
        course(sram_magic=sram_magic)
    data = manifest().to_json()
    data["course"]["sram_magic"] = sram_magic
    with pytest.raises(ManifestError, match="sram_magic"):
        Manifest.from_json(data)


def test_course_par_and_layout():
    assert course().layout == PARS
    assert course().par == 72


def test_club_labels_are_written_in_club_order():
    rules = ClubRules(banned={Club.SW, Club.W1, Club.I5})
    assert rules.to_json()["banned"] == ["1W", "5I", "SW"]


def test_required_bag_gains_the_putter():
    assert ClubRules(required_bag={Club.W1}).required_bag == {Club.W1, Club.PT}


@pytest.mark.parametrize(
    "rules, message",
    [
        (dict(max=0), "max must be"),
        (dict(max=15), "max must be"),
        (dict(banned={Club.PT}), "putter cannot be banned"),
        (dict(max=2, required_bag={Club.W1, Club.W2}), "over the max"),
        (dict(banned={Club.W1}, required_bag={Club.W1}), "includes banned"),
    ],
)
def test_rejects_bad_club_rules(rules, message):
    with pytest.raises(ManifestError, match=message):
        ClubRules(**rules)


@pytest.mark.parametrize(
    "data",
    [
        {"max": 14, "banned": ["1W", "1W"], "required_bag": None},
        {"max": 14, "banned": ["5W"], "required_bag": None},
        {"max": True, "banned": [], "required_bag": None},
        {"max": 14, "banned": []},
    ],
)
def test_rejects_bad_club_json(data):
    with pytest.raises(ManifestError):
        ClubRules.from_json(data)


@pytest.mark.parametrize(
    "settings",
    [
        dict(par=73),
        dict(sources=set()),
        dict(sources={"nes_open_eu"}),
        dict(music="nes_mars"),
        dict(mercy_point=0),
        dict(mercy_point=256),
        dict(prng_seed=""),
        dict(allow_family_repeats="yes"),
    ],
)
def test_rejects_bad_settings(settings):
    with pytest.raises(ManifestError):
        Settings(**settings)


def test_rejects_bad_courses():
    with pytest.raises(ManifestError, match="18 holes"):
        course(holes=slots()[:17])
    with pytest.raises(ManifestError, match="more than once"):
        course(holes=slots()[:17] + slots()[:1])
    with pytest.raises(ManifestError, match="course music"):
        course(music="random")
    with pytest.raises(ManifestError, match="uppercase"):
        course(magic_words=("divot", "CADDY", "BOGEY"))
    with pytest.raises(ManifestError, match="magic_words"):
        course(magic_words=("DIVOT", "DIVOT", "BOGEY"))


def test_rejects_bad_slots():
    with pytest.raises(ManifestError, match="wind_seed"):
        Slot(HoleId("nes_us/01"), 4, 0x10000)
    with pytest.raises(ManifestError, match="par"):
        Slot(HoleId("nes_us/01"), 6, 0)
    with pytest.raises(ManifestError, match="no transforms"):
        Slot(HoleId("nes_us/01"), 4, 0, ("mirror",))
    with pytest.raises(ManifestError, match="not canonical"):
        Slot.from_json(
            {"id": "nes_us/01@1", "par": 4, "transforms": [], "wind_seed": 0}
        )


def test_rejects_missing_and_unknown_fields():
    data = manifest().to_json()
    del data["course"]["music"]
    with pytest.raises(ManifestError, match="missing fields \\['music'\\]"):
        Manifest.from_json(data)
    data = manifest().to_json()
    data["settings"]["practice_swing"] = True
    with pytest.raises(ManifestError, match="unknown \\['practice_swing'\\]"):
        Manifest.from_json(data)


def test_rejects_other_schemas_before_reading_fields():
    data = manifest().to_json() | {"schema": 2, "something_new": 1}
    with pytest.raises(ManifestError, match="schema 2"):
        Manifest.from_json(data)


def test_a_manifest_records_its_prng_seed():
    with pytest.raises(ManifestError, match="prng_seed"):
        manifest(settings=Settings())


def test_required_roms_count_holes_and_music():
    entries = [
        CatalogEntry(
            slot.id,
            RomSource(US_ROM, "us", number),
            "0" * 64,
            slot.par,
            400,
            "Nintendo",
        )
        for number, slot in enumerate(slots(), start=1)
    ]
    holes = Catalog(1, {item.id: item for item in entries})
    assert required_roms(manifest(), holes) == (US_ROM,)
    assert required_roms(manifest(course=course(music="jp_france")), holes) == (
        US_ROM,
        JP_ROM,
    )
