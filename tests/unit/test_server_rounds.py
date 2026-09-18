"""Rounds: the listings, the permalink lookup, and the admin flag, void and restore actions."""

import pytest

from golf.qr.payload import HoleRecord
from server.audit import FLAG, RESTORE, ROUND, UNFLAG, VOID
from server.db import Database
from server.ids import is_id
from server.rounds import (
    Round,
    SlotTakenError,
    VoidedRound,
    find_round,
    flag_round,
    restore_round,
    rounds_for_seed,
    rounds_for_user,
    unflag_round,
    void_round,
)
from server.seeds import insert_seed
from server.submissions import UNRECOGNIZED, ScanError, submit_scan
from server.users import sign_in
from tests.unit import test_server_submissions as scans

#: rounds are recorded the way a scan records them, from the submission tests' players
Player = scans.Player
round_rows = scans.round_rows
manifest = scans.manifest
db = scans.db
seed_id = scans.seed_id
alice = scans.alice


def live_round(db: Database, public_id: str) -> Round:
    """The round with this id, which must be recorded and not voided."""
    found = find_round(db, public_id)
    assert isinstance(found, Round)
    return found


def test_a_seeds_rounds_list_fewest_strokes_first_under_display_names(
    db, seed_id, alice
):
    bob = Player(db, seed_id, "bob")
    submit_scan(
        db, alice.scan(holes=(HoleRecord(5, 2),) * 18), now="2026-09-17T10:00:00Z"
    )
    submit_scan(
        db, bob.scan(holes=(HoleRecord(4, 2),) * 18), now="2026-09-17T11:00:00Z"
    )
    submit_scan(
        db,
        alice.scan(slot=1, holes=(HoleRecord(5, 2),) * 18),
        now="2026-09-17T12:00:00Z",
    )
    rounds = rounds_for_seed(db, seed_id)
    assert [(r.player_name, r.slot, r.total_strokes) for r in rounds] == [
        ("bob", 0, 72),
        ("Alice", 0, 90),
        ("Alice", 1, 90),
    ]
    assert rounds[0].total_putts == 36
    assert rounds[0].received_at == "2026-09-17T11:00:00Z"


def test_a_players_rounds_list_newest_first_with_their_seeds(
    db, manifest, seed_id, alice
):
    other_seed = insert_seed(db, manifest, b"PATCHEOF")
    alice_elsewhere = Player(db, other_seed, "alice", "Alice")
    bob = Player(db, seed_id, "bob")
    submit_scan(db, alice.scan(), now="2026-09-17T10:00:00Z")
    submit_scan(db, alice_elsewhere.scan(slot=1), now="2026-09-17T11:00:00Z")
    submit_scan(db, bob.scan(), now="2026-09-17T12:00:00Z")
    listings = rounds_for_user(db, alice.user.id)
    assert [(listing.seed_id, listing.slot) for listing in listings] == [
        (other_seed, 1),
        (seed_id, 0),
    ]
    assert listings[1].magic_words == manifest.course.magic_words
    assert listings[1].par == manifest.course.par
    assert listings[1].total_strokes == 74
    assert rounds_for_user(db, sign_in(db, "dev:carol", "carol", None, None).id) == []


# -- Admin actions ------------------------------------------------------------------------


def audit_rows(db: Database) -> list[dict]:
    with db.transaction() as conn:
        return [
            dict(row) for row in conn.execute("SELECT * FROM admin_actions ORDER BY id")
        ]


def test_flagging_marks_the_round_everywhere_it_is_listed(db, seed_id, alice):
    public_id = submit_scan(db, alice.scan()).round.public_id
    flag_round(db, public_id, admin_id=alice.user.id, note="  six on 18?  ")
    flagged = live_round(db, public_id)
    assert (flagged.flagged, flagged.flag_note) == (True, "six on 18?")
    assert rounds_for_seed(db, seed_id)[0].flagged
    assert rounds_for_user(db, alice.user.id)[0].flagged
    unflag_round(db, public_id, admin_id=alice.user.id)
    unflagged = live_round(db, public_id)
    assert (unflagged.flagged, unflagged.flag_note) == (False, None)
    assert not rounds_for_seed(db, seed_id)[0].flagged


def test_every_action_logs_itself_against_the_rounds_public_id(db, seed_id, alice):
    public_id = submit_scan(db, alice.scan()).round.public_id
    flag_round(
        db, public_id, admin_id=alice.user.id, note="why 6?", now="2026-09-18T00:00:00Z"
    )
    unflag_round(db, public_id, admin_id=alice.user.id, now="2026-09-18T01:00:00Z")
    void_round(
        db,
        public_id,
        admin_id=alice.user.id,
        note="warm-up",
        now="2026-09-18T02:00:00Z",
    )
    restore_round(db, public_id, admin_id=alice.user.id, now="2026-09-18T03:00:00Z")
    rows = audit_rows(db)
    assert [
        (
            row["action"],
            row["target_type"],
            row["target_id"],
            row["note"],
            row["created_at"],
        )
        for row in rows
    ] == [
        (FLAG, ROUND, public_id, "why 6?", "2026-09-18T00:00:00Z"),
        (UNFLAG, ROUND, public_id, None, "2026-09-18T01:00:00Z"),
        (VOID, ROUND, public_id, "warm-up", "2026-09-18T02:00:00Z"),
        (RESTORE, ROUND, public_id, None, "2026-09-18T03:00:00Z"),
    ]
    assert {row["admin_id"] for row in rows} == {alice.user.id}
    assert {row["detail"] for row in rows} == {"{}"}
    assert live_round(db, public_id).flagged is False


def test_a_failed_action_logs_nothing(db, alice):
    public_id = submit_scan(db, alice.scan()).round.public_id
    void_round(db, public_id, admin_id=alice.user.id)
    submit_scan(db, alice.scan(holes=(HoleRecord(3, 1),) * 18))
    with pytest.raises(SlotTakenError):
        restore_round(db, public_id, admin_id=alice.user.id)
    with pytest.raises(KeyError):
        flag_round(db, "0000000000", admin_id=alice.user.id)
    assert [row["action"] for row in audit_rows(db)] == [VOID]


def test_a_blank_flag_note_is_no_note(db, alice):
    public_id = submit_scan(db, alice.scan()).round.public_id
    flag_round(db, public_id, admin_id=alice.user.id, note="   ")
    assert live_round(db, public_id).flag_note is None


@pytest.mark.parametrize(
    "action", [flag_round, unflag_round, void_round, restore_round]
)
def test_acting_on_a_missing_round_is_an_error(db, action):
    with pytest.raises(KeyError):
        action(db, "0000000000", admin_id=1)


@pytest.mark.parametrize("action", [flag_round, unflag_round, void_round])
def test_acting_on_a_voided_round_as_recorded_is_an_error(db, alice, action):
    public_id = submit_scan(db, alice.scan()).round.public_id
    void_round(db, public_id, admin_id=alice.user.id)
    with pytest.raises(KeyError):
        action(db, public_id, admin_id=alice.user.id)


def test_voiding_frees_the_slot_and_refuses_the_same_round(db, seed_id, alice):
    public_id = submit_scan(db, alice.scan()).round.public_id
    void_round(db, public_id, admin_id=alice.user.id, note="warm-up round")
    assert round_rows(db) == []
    assert isinstance(find_round(db, public_id), VoidedRound)
    assert rounds_for_seed(db, seed_id) == []
    with pytest.raises(ScanError) as rejected:
        submit_scan(db, alice.scan())
    assert rejected.value.reason == UNRECOGNIZED
    replacement = submit_scan(db, alice.scan(holes=(HoleRecord(3, 1),) * 18))
    assert replacement.new
    assert replacement.round.total_strokes == 54


def test_restoring_puts_the_round_back_as_it_was(db, seed_id, alice):
    recorded = submit_scan(db, alice.scan(), now="2026-09-17T12:00:00Z").round
    flag_round(db, recorded.public_id, admin_id=alice.user.id, note="check")
    void_round(db, recorded.public_id, admin_id=alice.user.id)
    restore_round(db, recorded.public_id, admin_id=alice.user.id)
    restored = live_round(db, recorded.public_id)
    assert restored.holes == recorded.holes
    assert (restored.total_strokes, restored.total_putts, restored.received_at) == (
        recorded.total_strokes,
        recorded.total_putts,
        "2026-09-17T12:00:00Z",
    )
    assert (restored.flagged, restored.flag_note) == (True, "check")
    again = submit_scan(db, alice.scan())
    assert not again.new
    assert again.round == restored
    with pytest.raises(KeyError):
        restore_round(db, recorded.public_id, admin_id=alice.user.id)


def test_restoring_into_a_taken_slot_is_refused(db, alice):
    public_id = submit_scan(db, alice.scan()).round.public_id
    void_round(db, public_id, admin_id=alice.user.id)
    replacement = submit_scan(db, alice.scan(holes=(HoleRecord(3, 1),) * 18)).round
    with pytest.raises(SlotTakenError):
        restore_round(db, public_id, admin_id=alice.user.id)
    assert [row["public_id"] for row in round_rows(db)] == [replacement.public_id]


# -- Permalinks --------------------------------------------------------------------------


def test_a_recorded_round_is_found_by_its_public_id(db, seed_id, alice):
    recorded = submit_scan(db, alice.scan()).round
    assert is_id(recorded.public_id)
    assert find_round(db, recorded.public_id) == recorded


@pytest.mark.parametrize(
    "public_id", ["0000000000", "not an id", "", "x" * 11, "!!!!!!!!!!"]
)
def test_a_public_id_naming_no_round_finds_nothing(db, public_id):
    assert find_round(db, public_id) is None


def test_the_public_id_survives_a_void_and_a_restore(db, seed_id, alice):
    recorded = submit_scan(db, alice.scan(), now="2026-09-17T12:00:00Z").round
    void_round(
        db, recorded.public_id, admin_id=alice.user.id, now="2026-09-17T13:00:00Z"
    )

    assert find_round(db, recorded.public_id) == VoidedRound(
        public_id=recorded.public_id,
        seed_id=seed_id,
        user_id=alice.user.id,
        slot=0,
        received_at="2026-09-17T12:00:00Z",
        voided_at="2026-09-17T13:00:00Z",
    )

    restore_round(db, recorded.public_id, admin_id=alice.user.id)
    assert find_round(db, recorded.public_id) == recorded


def test_a_round_replacing_a_voided_one_gets_its_own_public_id(db, alice):
    recorded = submit_scan(db, alice.scan()).round
    void_round(db, recorded.public_id, admin_id=alice.user.id)
    replacement = submit_scan(db, alice.scan(holes=(HoleRecord(3, 1),) * 18)).round
    assert replacement.public_id != recorded.public_id
    # the voided round keeps its own, so neither permalink comes to mean the other round
    assert isinstance(find_round(db, recorded.public_id), VoidedRound)
    assert find_round(db, replacement.public_id) == replacement


def test_the_listings_carry_each_rounds_public_id(db, seed_id, alice):
    recorded = submit_scan(db, alice.scan()).round
    assert [row.public_id for row in rounds_for_seed(db, seed_id)] == [
        recorded.public_id
    ]
    assert [row.public_id for row in rounds_for_user(db, alice.user.id)] == [
        recorded.public_id
    ]
