"""Entries: a signed-in download creates one per seed and player, updates its choices, and never redraws its keys."""

import itertools

import pytest

from golf.core.patches.sram_defaults import Club
from golf.randomizer.build import PlayerOptions
from golf.randomizer.catalog import Catalog
from golf.randomizer.curation import CurationSnapshot
from golf.randomizer.generate import generate
from golf.randomizer.manifest import Settings
from server.db import Database
from server.entries import Entry, entries_for_user, load_entry, upsert_entry
from server.seeds import insert_seed
from server.users import sign_in


@pytest.fixture(scope="module")
def manifest():
    return generate(Catalog.load(), CurationSnapshot.load(), Settings(prng_seed="entries"))


@pytest.fixture
def db():
    database = Database(":memory:")
    database.migrate()
    yield database
    database.close()


def keys():
    """Distinct 8-byte keys: 00..00, 01..01, ..."""
    counter = itertools.count()
    return lambda: bytes([next(counter)] * 8)


def user(db, name: str) -> int:
    return sign_in(db, f"dev:{name}", name, None, None).id


LUIGI = PlayerOptions("LUIGI", frozenset({Club.W1, Club.PW}))
TOAD = PlayerOptions("TOAD", frozenset({Club.W3, Club.SW}))


def test_a_first_download_creates_the_entry_with_drawn_keys(db, manifest):
    seed_id = insert_seed(db, manifest, b"PATCHEOF")
    alice = user(db, "alice")
    entry = upsert_entry(db, seed_id, alice, LUIGI, now="2026-09-16T00:00:00Z", draw_key=keys())
    assert entry == Entry(
        id=entry.id,
        seed_id=seed_id,
        user_id=alice,
        player_name="LUIGI",
        clubs=("1W", "PW", "PT"),
        keys=(bytes(8), bytes([1] * 8)),
        created_at="2026-09-16T00:00:00Z",
        updated_at="2026-09-16T00:00:00Z",
    )
    assert load_entry(db, seed_id, alice) == entry


def test_downloading_again_updates_the_choices_and_keeps_the_keys(db, manifest):
    seed_id = insert_seed(db, manifest, b"PATCHEOF")
    alice = user(db, "alice")
    first = upsert_entry(db, seed_id, alice, LUIGI, now="2026-09-16T00:00:00Z")
    second = upsert_entry(db, seed_id, alice, TOAD, now="2026-09-17T00:00:00Z")
    assert second.id == first.id
    assert second.keys == first.keys
    assert (second.player_name, second.clubs) == ("TOAD", ("3W", "SW", "PT"))
    assert (second.created_at, second.updated_at) == ("2026-09-16T00:00:00Z", "2026-09-17T00:00:00Z")


def test_each_player_gets_their_own_entry_and_keys(db, manifest):
    seed_id = insert_seed(db, manifest, b"PATCHEOF")
    alice = upsert_entry(db, seed_id, user(db, "alice"), LUIGI)
    bob = upsert_entry(db, seed_id, user(db, "bob"), LUIGI)
    assert alice.id != bob.id
    assert set(alice.keys).isdisjoint(bob.keys)


def test_no_entry_loads_as_none(db, manifest):
    seed_id = insert_seed(db, manifest, b"PATCHEOF")
    assert load_entry(db, seed_id, user(db, "alice")) is None


def test_keys_stay_out_of_repr(db, manifest):
    seed_id = insert_seed(db, manifest, b"PATCHEOF")
    entry = upsert_entry(db, seed_id, user(db, "alice"), LUIGI, draw_key=lambda: b"\xab" * 8)
    assert "keys" not in repr(entry)
    assert "\\xab" not in repr(entry)


def test_a_players_entries_list_newest_first_with_their_seeds(db, manifest):
    first = insert_seed(db, manifest, b"PATCHEOF")
    second = insert_seed(db, manifest, b"PATCHEOF")
    alice, bob = user(db, "alice"), user(db, "bob")
    upsert_entry(db, first, alice, LUIGI, now="2026-09-16T00:00:00Z")
    upsert_entry(db, second, alice, TOAD, now="2026-09-17T00:00:00Z")
    upsert_entry(db, first, bob, TOAD)
    listings = entries_for_user(db, alice)
    assert [listing.seed_id for listing in listings] == [second, first]
    assert listings[0].magic_words == manifest.course.magic_words
    assert listings[0].par == manifest.course.par
    assert (listings[1].player_name, listings[1].clubs) == ("LUIGI", ("1W", "PW", "PT"))
    assert entries_for_user(db, user(db, "carol")) == []
