"""Submissions: a scan records a verified round once per entry and slot, and rejects anything else."""

import pytest

from golf.core.patches.sram_defaults import Club
from golf.qr.payload import HoleRecord, RoundPayload, base64url_encode
from golf.randomizer.build import PlayerOptions
from golf.randomizer.catalog import Catalog
from golf.randomizer.curation import CurationSnapshot
from golf.randomizer.generate import generate
from golf.randomizer.manifest import Settings
from server.db import Database
from server.entries import load_entry, upsert_entry
from server.seeds import MAX_QR_SEED_ID, insert_seed, load_seed
from server.submissions import (
    MALFORMED,
    UNFINISHED,
    UNRECOGNIZED,
    HoleResult,
    ScanError,
    rounds_for_seed,
    rounds_for_user,
    submit_scan,
)
from server.users import sign_in

LUIGI = PlayerOptions("LUIGI", frozenset({Club.W1, Club.PW}))
TOAD = PlayerOptions("TOAD", frozenset({Club.W3, Club.SW}))

#: a round of 4s with 2 putts, but a 6 with 3 putts on hole 18
HOLES = (HoleRecord(4, 2),) * 17 + (HoleRecord(6, 3),)


@pytest.fixture(scope="module")
def manifest():
    return generate(Catalog.load(), CurationSnapshot.load(), Settings(prng_seed="submissions"))


@pytest.fixture
def db():
    database = Database(":memory:")
    database.migrate()
    yield database
    database.close()


class Player:
    """A signed-in player entered in a seed: what their ROM's QR code is built from."""

    def __init__(self, db: Database, seed_id: str, name: str, global_name: str | None = None):
        self.user = sign_in(db, f"dev:{name}", name, global_name, None)
        self.entry = upsert_entry(db, seed_id, self.user.id, LUIGI)
        self.qr_seed_id = load_seed(db, seed_id).qr_seed_id

    def payload(self, slot: int = 0, holes=HOLES, key: bytes | None = None, **changes) -> bytes:
        fields = {
            "seed_id": self.qr_seed_id.to_bytes(8, "big"),
            "player_id": self.user.player_id.to_bytes(4, "big"),
            "holes": holes,
            "player_slot": slot,
            **changes,
        }
        return RoundPayload(**fields).to_bytes(key if key is not None else self.entry.keys[slot])

    def scan(self, slot: int = 0, **changes) -> str:
        return base64url_encode(self.payload(slot, **changes))


@pytest.fixture
def seed_id(db, manifest):
    return insert_seed(db, manifest, b"PATCHEOF")


@pytest.fixture
def alice(db, seed_id):
    return Player(db, seed_id, "alice", "Alice")


def submission_rows(db: Database) -> list[dict]:
    with db.transaction() as conn:
        return [dict(row) for row in conn.execute("SELECT * FROM submissions ORDER BY id")]


def test_a_verified_scan_records_the_round(db, seed_id, alice):
    result = submit_scan(db, alice.scan(), now="2026-09-17T12:00:00Z")
    assert result.new
    recorded = result.round
    assert (recorded.entry_id, recorded.seed_id, recorded.user_id, recorded.slot) == (
        alice.entry.id,
        seed_id,
        alice.user.id,
        0,
    )
    assert (recorded.total_strokes, recorded.total_putts) == (4 * 17 + 6, 2 * 17 + 3)
    assert recorded.received_at == "2026-09-17T12:00:00Z"
    assert not recorded.flagged
    assert recorded.holes[0] == HoleResult(1, 4, 2)
    assert recorded.holes[-1] == HoleResult(18, 6, 3)
    assert len(recorded.holes) == 18
    [row] = submission_rows(db)
    assert row["payload"] == alice.payload()


def test_scanning_the_same_round_again_finds_it_recorded(db, alice):
    first = submit_scan(db, alice.scan(), now="2026-09-17T12:00:00Z")
    again = submit_scan(db, alice.scan(), now="2026-09-17T13:00:00Z")
    assert not again.new
    assert again.round == first.round
    assert len(submission_rows(db)) == 1


def test_a_different_round_for_a_recorded_slot_keeps_the_first(db, alice):
    first = submit_scan(db, alice.scan())
    later = submit_scan(db, alice.scan(holes=(HoleRecord(3, 1),) * 18))
    assert not later.new
    assert later.round == first.round
    [row] = submission_rows(db)
    assert row["payload"] == alice.payload()


def test_player_two_records_against_the_same_entry_under_its_own_key(db, alice):
    player_one = submit_scan(db, alice.scan(slot=0))
    player_two = submit_scan(db, alice.scan(slot=1, holes=(HoleRecord(5, 2),) * 18))
    assert player_two.new
    assert player_two.round.entry_id == player_one.round.entry_id
    assert player_two.round.slot == 1
    assert player_two.round.total_strokes == 90
    assert len(submission_rows(db)) == 2


def test_a_slot_signed_with_the_other_slots_key_is_not_recognized(db, alice):
    with pytest.raises(ScanError) as rejected:
        submit_scan(db, alice.scan(slot=1, key=alice.entry.keys[0]))
    assert rejected.value.reason == UNRECOGNIZED


@pytest.mark.parametrize(
    "text",
    [
        "",
        "A" * 47,
        "A" * 52,
        "!" * 48,
        "A" * 47 + "=",
    ],
)
def test_text_that_is_not_a_payload_is_malformed(db, alice, text):
    with pytest.raises(ScanError) as rejected:
        submit_scan(db, text)
    assert rejected.value.reason == MALFORMED


@pytest.mark.parametrize(
    "changes",
    [
        {"protocol_version": 2},
        {"protocol_version": 0},
        {"reserved_flags": 1},
        {"slot": 2},
        {"slot": 3},
    ],
)
def test_a_signed_payload_this_protocol_does_not_send_is_malformed(db, alice, changes):
    slot = changes.pop("slot", 0)
    key = alice.entry.keys[0]
    with pytest.raises(ScanError) as rejected:
        submit_scan(db, alice.scan(slot=0, key=key, player_slot=slot, **changes))
    assert rejected.value.reason == MALFORMED


@pytest.mark.parametrize("field, width", [("seed_id", 8), ("player_id", 4)])
def test_an_unfinished_roms_zero_ids_are_rejected(db, alice, field, width):
    with pytest.raises(ScanError) as rejected:
        submit_scan(db, alice.scan(**{field: bytes(width)}))
    assert rejected.value.reason == UNFINISHED


def test_a_payload_matching_no_entry_is_not_recognized(db, manifest, seed_id, alice):
    other_seed = insert_seed(db, manifest, b"PATCHEOF")
    bob = sign_in(db, "dev:bob", "bob", None, None)
    cases = {
        "unknown seed": alice.scan(seed_id=(alice.qr_seed_id % MAX_QR_SEED_ID + 1).to_bytes(8, "big")),
        "seed id past the range": alice.scan(seed_id=b"\xff" * 8),
        "unknown player": alice.scan(player_id=(alice.user.player_id ^ 1 or 2).to_bytes(4, "big")),
        "player without an entry": alice.scan(player_id=bob.player_id.to_bytes(4, "big")),
        "entry on another seed": alice.scan(seed_id=load_seed(db, other_seed).qr_seed_id.to_bytes(8, "big")),
        "wrong key": alice.scan(key=b"\x00" * 8),
    }
    for case, text in cases.items():
        with pytest.raises(ScanError) as rejected:
            submit_scan(db, text)
        assert rejected.value.reason == UNRECOGNIZED, case
    assert submission_rows(db) == []


def test_a_rejected_different_round_does_not_reveal_the_recorded_one(db, alice):
    submit_scan(db, alice.scan())
    with pytest.raises(ScanError) as rejected:
        submit_scan(db, alice.scan(holes=(HoleRecord(3, 1),) * 18, key=b"\x01" * 8))
    assert rejected.value.reason == UNRECOGNIZED


def test_a_recorded_round_locks_the_entrys_choices(db, seed_id, alice):
    upsert_entry(db, seed_id, alice.user.id, TOAD, now="2026-09-17T10:00:00Z")
    submit_scan(db, alice.scan())
    after = upsert_entry(db, seed_id, alice.user.id, LUIGI, now="2026-09-18T10:00:00Z")
    assert (after.player_name, after.clubs, after.updated_at) == ("TOAD", ("3W", "SW", "PT"), "2026-09-17T10:00:00Z")
    assert after.keys == alice.entry.keys
    assert load_entry(db, seed_id, alice.user.id) == after


def test_a_seeds_rounds_list_fewest_strokes_first_under_display_names(db, seed_id, alice):
    bob = Player(db, seed_id, "bob")
    submit_scan(db, alice.scan(holes=(HoleRecord(5, 2),) * 18), now="2026-09-17T10:00:00Z")
    submit_scan(db, bob.scan(holes=(HoleRecord(4, 2),) * 18), now="2026-09-17T11:00:00Z")
    submit_scan(db, alice.scan(slot=1, holes=(HoleRecord(5, 2),) * 18), now="2026-09-17T12:00:00Z")
    rounds = rounds_for_seed(db, seed_id)
    assert [(r.player_name, r.slot, r.total_strokes) for r in rounds] == [
        ("bob", 0, 72),
        ("Alice", 0, 90),
        ("Alice", 1, 90),
    ]
    assert rounds[0].total_putts == 36
    assert rounds[0].received_at == "2026-09-17T11:00:00Z"


def test_a_players_rounds_list_newest_first_with_their_seeds(db, manifest, seed_id, alice):
    other_seed = insert_seed(db, manifest, b"PATCHEOF")
    alice_elsewhere = Player(db, other_seed, "alice", "Alice")
    bob = Player(db, seed_id, "bob")
    submit_scan(db, alice.scan(), now="2026-09-17T10:00:00Z")
    submit_scan(db, alice_elsewhere.scan(slot=1), now="2026-09-17T11:00:00Z")
    submit_scan(db, bob.scan(), now="2026-09-17T12:00:00Z")
    listings = rounds_for_user(db, alice.user.id)
    assert [(listing.seed_id, listing.slot) for listing in listings] == [(other_seed, 1), (seed_id, 0)]
    assert listings[1].magic_words == manifest.course.magic_words
    assert listings[1].par == manifest.course.par
    assert listings[1].total_strokes == 74
    assert rounds_for_user(db, sign_in(db, "dev:carol", "carol", None, None).id) == []
