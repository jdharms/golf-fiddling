"""Seed ids and the seed tables: base62 ids, inserting a seed with its holes, loading it back."""

import json

import pytest

from golf.core.patches.seeded_wind import predict_hole
from golf.randomizer.catalog import Catalog
from golf.randomizer.curation import CurationSnapshot
from golf.randomizer.generate import generate
from golf.randomizer.manifest import Manifest, Settings
from server.db import Database
from server.seeds import (
    ID_LENGTH,
    INSERT_ATTEMPTS,
    MAX_QR_SEED_ID,
    SeedIdError,
    SeedIdExhaustedError,
    SeedRow,
    decode_seed_id,
    encode_seed_id,
    insert_seed,
    load_seed,
    load_unfinished_ips,
    manifest_text,
    new_qr_seed_id,
)

IPS = b"PATCH\x00\x00\x10\x00\x01\xeaEOF"


def seed_row(db: Database, seed_id: str) -> SeedRow:
    """The stored seed with this id, which must exist."""
    row = load_seed(db, seed_id)
    assert row is not None
    return row


@pytest.fixture(scope="module")
def manifest() -> Manifest:
    return generate(
        Catalog.load(), CurationSnapshot.load(), Settings(prng_seed="server-seeds")
    )


@pytest.fixture
def db():
    database = Database(":memory:")
    database.migrate()
    yield database
    database.close()


def counts(db: Database) -> tuple[int, int]:
    with db.transaction() as conn:
        seeds = conn.execute("SELECT count(*) FROM seeds").fetchone()[0]
        holes = conn.execute("SELECT count(*) FROM seed_holes").fetchone()[0]
    return seeds, holes


# -- Ids --------------------------------------------------------------------------------------


def test_the_max_id_is_the_migrations_bound():
    assert MAX_QR_SEED_ID == 62**10 - 1 == 839299365868340223
    assert MAX_QR_SEED_ID < 2**60


@pytest.mark.parametrize(
    "value, text",
    [
        (1, "0000000001"),
        (61, "000000000z"),
        (62, "0000000010"),
        (MAX_QR_SEED_ID, "zzzzzzzzzz"),
    ],
)
def test_ids_encode_most_significant_digit_first_padded_to_ten(value, text):
    assert encode_seed_id(value) == text
    assert decode_seed_id(text) == value


def test_ids_round_trip():
    for value in (new_qr_seed_id() for _ in range(200)):
        text = encode_seed_id(value)
        assert len(text) == ID_LENGTH
        assert decode_seed_id(text) == value


@pytest.mark.parametrize("value", [0, -1, MAX_QR_SEED_ID + 1, True, "1"])
def test_encoding_refuses_values_outside_the_range(value):
    with pytest.raises(SeedIdError):
        encode_seed_id(value)


@pytest.mark.parametrize(
    "text",
    [
        "",
        "000000001",
        "00000000001",
        "0000000000",
        "abc-def-gh",
        "00000000é1",
        "nope.json",
    ],
)
def test_decoding_refuses_anything_but_an_id(text):
    with pytest.raises(SeedIdError):
        decode_seed_id(text)


def test_drawn_ids_are_in_range():
    assert all(1 <= new_qr_seed_id() <= MAX_QR_SEED_ID for _ in range(1000))


# -- Inserting and loading ------------------------------------------------------------------


def test_a_seed_is_stored_with_its_eighteen_holes(db, manifest):
    seed_id = insert_seed(
        db, manifest, IPS, now="2026-09-15T12:00:00Z", draw=lambda: 12345
    )
    assert seed_id == encode_seed_id(12345)
    assert counts(db) == (1, 18)
    with db.transaction() as conn:
        seed = conn.execute("SELECT * FROM seeds").fetchone()
        holes = conn.execute("SELECT * FROM seed_holes ORDER BY position").fetchall()
    assert seed["qr_seed_id"] == 12345
    assert seed["unfinished_ips"] == IPS
    assert seed["generator_version"] == manifest.generator_version
    assert seed["catalog_version"] == manifest.catalog_version
    assert seed["curation_stamp"] == manifest.curation_stamp
    assert seed["creator_id"] is None
    assert seed["created_at"] == "2026-09-15T12:00:00Z"
    assert Manifest.from_json(json.loads(seed["manifest"])) == manifest

    for hole, slot in zip(holes, manifest.course.holes, strict=True):
        forecast = predict_hole(slot.wind_seed)
        assert hole["seed_id"] == seed_id
        assert hole["hole_id"] == str(slot.id)
        assert json.loads(hole["transforms"]) == []
        assert hole["par"] == slot.par
        assert hole["wind_seed"] == slot.wind_seed
        assert hole["pin_index"] == forecast.pin_index
        assert hole["wind_direction"] == forecast.direction_anchor
        assert hole["wind_speed"] == forecast.speed_anchor
    assert [hole["position"] for hole in holes] == list(range(1, 19))


def test_created_at_defaults_to_utc_now(db, manifest):
    seed_id = insert_seed(db, manifest, IPS)
    assert seed_row(db, seed_id).created_at.endswith("Z")


def test_a_taken_id_is_drawn_again(db, manifest):
    insert_seed(db, manifest, IPS, draw=lambda: 7)
    draws = iter([7, 7, 8])
    assert insert_seed(db, manifest, IPS, draw=lambda: next(draws)) == encode_seed_id(8)
    assert counts(db) == (2, 36)


def test_insert_gives_up_after_its_attempts(db, manifest):
    insert_seed(db, manifest, IPS, draw=lambda: 7)
    calls = []

    def draw():
        calls.append(1)
        return 7

    with pytest.raises(SeedIdExhaustedError):
        insert_seed(db, manifest, IPS, draw=draw)
    assert len(calls) == INSERT_ATTEMPTS
    assert counts(db) == (1, 18)


def test_load_seed_returns_the_stored_manifest(db, manifest):
    seed_id = insert_seed(db, manifest, IPS, creator_id=None, draw=lambda: 99)
    row = seed_row(db, seed_id)
    assert row.id == seed_id
    assert row.qr_seed_id == 99
    assert row.manifest == manifest
    assert row.manifest_json == manifest_text(manifest)


@pytest.mark.parametrize("text", ["0000000001", "not-an-id", "nope.json"])
def test_load_seed_is_none_for_a_missing_or_malformed_id(db, text):
    assert load_seed(db, text) is None


def test_load_unfinished_ips_returns_the_stored_blob(db, manifest):
    seed_id = insert_seed(db, manifest, IPS)
    assert load_unfinished_ips(db, seed_id) == IPS


@pytest.mark.parametrize("text", ["0000000001", "not-an-id"])
def test_load_unfinished_ips_is_none_for_a_missing_or_malformed_id(db, text):
    assert load_unfinished_ips(db, text) is None
