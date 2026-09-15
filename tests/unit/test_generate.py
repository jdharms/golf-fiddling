"""Unit tests for generating a manifest from a catalog, curation and settings."""

import json
import re

import pytest

from golf.core.patches.seeded_wind import derive_hole_seeds
from golf.core.patches.sram_defaults import Club
from golf.randomizer.catalog import JP_ROM, US_ROM, Catalog, CatalogEntry, HoleId, RomSource
from golf.randomizer.curation import CurationSnapshot
from golf.core.patches.sram_defaults import magic_bytes
from golf.randomizer.generate import GENERATOR_VERSION, GenerationError, generate
from golf.randomizer.layout import COUNTS, satisfies
from golf.randomizer.manifest import ClubRules, Manifest, Settings, required_roms


@pytest.fixture(scope="module")
def real_catalog() -> Catalog:
    return Catalog.load()


@pytest.fixture(scope="module")
def real_curation() -> CurationSnapshot:
    return CurationSnapshot.load()


def entry(hole_id: str, par: int, rom: str = US_ROM) -> CatalogEntry:
    return CatalogEntry(HoleId.parse(hole_id), RomSource(rom, "course", 1), "0" * 64, par, 400, "Test")


def minimal_catalog(par3: int = 4, par4: int = 10, par5: int = 4, extra=()) -> Catalog:
    entries = [
        *(entry(f"t/three_{n}", 3) for n in range(par3)),
        *(entry(f"t/four_{n}", 4) for n in range(par4)),
        *(entry(f"t/five_{n}", 5) for n in range(par5)),
        *extra,
    ]
    return Catalog(1, {item.id: item for item in entries})


def test_same_inputs_give_the_same_manifest(real_catalog, real_curation):
    settings = Settings(prng_seed="league-week-1")
    first = generate(real_catalog, real_curation, settings)
    assert generate(real_catalog, real_curation, settings) == first
    assert generate(real_catalog, real_curation, Settings(prng_seed="league-week-2")) != first


def test_draws_a_prng_seed_when_the_settings_have_none(real_catalog, real_curation):
    drawn = generate(real_catalog, real_curation, Settings())
    assert re.fullmatch(r"[0-9a-f]{16}", drawn.settings.prng_seed)
    assert generate(real_catalog, real_curation, drawn.settings) == drawn


def test_records_versions_and_round_trips(real_catalog, real_curation):
    manifest = generate(real_catalog, real_curation, Settings(prng_seed="abc"))
    assert manifest.generator_version == GENERATOR_VERSION
    assert manifest.catalog_version == real_catalog.version
    assert manifest.curation_stamp == real_curation.stamp
    assert Manifest.from_json(json.loads(json.dumps(manifest.to_json()))) == manifest


@pytest.mark.parametrize("par", sorted(COUNTS))
def test_course_follows_a_valid_layout_of_real_holes(real_catalog, real_curation, par):
    for seed in range(10):
        course = generate(real_catalog, real_curation, Settings(prng_seed=str(seed), par=par)).course
        assert satisfies(course.layout, COUNTS[par])
        assert all(real_catalog[slot.id].par == slot.par for slot in course.holes)


def test_copies_settings_into_the_course(real_catalog, real_curation):
    clubs = ClubRules(max=12, banned={Club.W1})
    settings = Settings(prng_seed="abc", mercy_point=None, clubs=clubs, music="jp_uk")
    course = generate(real_catalog, real_curation, settings).course
    assert (course.mercy_point, course.clubs, course.music) == (None, clubs, "jp_uk")


def test_wind_seeds_come_from_the_prng_seed(real_catalog, real_curation):
    course = generate(real_catalog, real_curation, Settings(prng_seed="abc")).course
    assert [slot.wind_seed for slot in course.holes] == derive_hole_seeds("abc")


def test_each_draw_has_its_own_stream(real_catalog, real_curation):
    both = generate(real_catalog, real_curation, Settings(prng_seed="abc")).course
    us_only = generate(real_catalog, real_curation, Settings(prng_seed="abc", sources={US_ROM})).course
    assert both.layout == us_only.layout
    assert both.magic_words == us_only.magic_words
    assert both.sram_magic == us_only.sram_magic
    assert [s.wind_seed for s in both.holes] == [s.wind_seed for s in us_only.holes]


def test_sram_magic_is_drawn_per_seed_and_never_holds_a_blank_sram_byte(real_catalog, real_curation):
    magics = [
        generate(real_catalog, real_curation, Settings(prng_seed=str(seed))).course.sram_magic for seed in range(40)
    ]
    for magic in magics:
        assert all(byte not in (0x00, 0xFF) for byte in magic_bytes(magic))
    assert len(set(magics)) > 1


def test_nes_open_seeds_use_nes_open_music(real_catalog, real_curation):
    for seed in range(40):
        manifest = generate(real_catalog, real_curation, Settings(prng_seed=str(seed), sources={US_ROM}))
        assert manifest.course.music.startswith("nes_")
        assert required_roms(manifest, real_catalog) == (US_ROM,)


def test_mario_open_seeds_can_use_mario_open_music(real_catalog, real_curation):
    music = {
        generate(real_catalog, real_curation, Settings(prng_seed=str(seed))).course.music for seed in range(60)
    }
    assert any(slug.startswith("jp_") for slug in music)


def test_never_repeats_a_family():
    twins = [entry("t/twin_a", 4), entry("t/twin_b", 4, JP_ROM)]
    holes = minimal_catalog(par4=9, extra=twins)
    curation = CurationSnapshot.from_json({"t/twin_a": {"family": "twin"}, "t/twin_b": {"family": "twin"}})
    for seed in range(30):
        ids = {str(slot.id) for slot in generate(holes, curation, Settings(prng_seed=str(seed))).course.holes}
        assert len(ids & {"t/twin_a", "t/twin_b"}) == 1


def test_allowing_repeats_can_use_both_twins():
    twins = [entry("t/twin_a", 4), entry("t/twin_b", 4, JP_ROM)]
    holes = minimal_catalog(par4=8, extra=twins)
    curation = CurationSnapshot.from_json({"t/twin_a": {"family": "twin"}, "t/twin_b": {"family": "twin"}})
    course = generate(holes, curation, Settings(prng_seed="abc", allow_family_repeats=True)).course
    assert {"t/twin_a", "t/twin_b"} <= {str(slot.id) for slot in course.holes}


def test_spends_a_mixed_family_where_it_is_the_only_fit():
    # Three par 3 families and four par 5 families, plus one family with a par 3 and a
    # par 5 member: the course is only fillable if that family takes a par 3 slot.
    mixed = [entry("t/mixed_short", 3), entry("t/mixed_long", 5)]
    holes = minimal_catalog(par3=3, extra=mixed)
    curation = CurationSnapshot.from_json({"t/mixed_short": {"family": "m"}, "t/mixed_long": {"family": "m"}})
    for seed in range(30):
        ids = {str(slot.id) for slot in generate(holes, curation, Settings(prng_seed=str(seed))).course.holes}
        assert "t/mixed_short" in ids and "t/mixed_long" not in ids


def test_reports_a_pool_the_family_rule_leaves_too_small():
    twins = [entry("t/twin_a", 3), entry("t/twin_b", 3)]
    holes = minimal_catalog(par3=2, extra=twins)
    curation = CurationSnapshot.from_json({"t/twin_a": {"family": "twin"}, "t/twin_b": {"family": "twin"}})
    with pytest.raises(GenerationError, match="4 par 3.*par 3: 3"):
        generate(holes, curation, Settings(prng_seed="abc"))


def test_reports_filters_that_empty_the_pool(real_catalog, real_curation):
    with pytest.raises(GenerationError, match="par 5: 0"):
        generate(minimal_catalog(par5=0), real_curation, Settings(prng_seed="abc"))
