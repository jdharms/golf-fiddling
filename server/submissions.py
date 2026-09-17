"""Submissions: the only code that writes `submissions` and `submission_holes`.

A scan of a finished ROM's scorecard QR code carries the round's 36-byte payload
(`golf/qr/payload.py`). `submit_scan` resolves it to the entry it belongs to: the seed ID
names the seed, the player ID the user, the pair their entry, and the payload's slot the
MAC key. A payload that verifies is recorded against (entry, slot), and the first one
recorded stays: a later scan for the same entry and slot that also verifies, identical or
not, stores nothing and answers with the round already recorded. Both ROM slots carry the
downloader's player ID, so a player 2 round (slot 1) counts toward the same entry as slot 0. See
docs/randomizer_devplan.md, "Data model", and docs/scorecard_qr.md, "Server contract".

An admin can flag a round, which leaves it counted and marked, or void it. A voided round moves
to `voided_submissions`, freeing its slot for a different round, and a scan of its payload is
refused until an admin restores it. Each admin action writes its audit row through
`server/audit.py` in the same transaction. A rejected scan logs its exact cause, which the
page never shows.
"""

import json
import logging
from dataclasses import dataclass

from golf.qr import payload
from golf.randomizer.manifest import Manifest

from . import audit
from .db import Database
from .seeds import MAX_QR_SEED_ID, encode_seed_id, utc_now

log = logging.getLogger(__name__)

#: ScanError reasons, each shown by its own strings key in submission.html
#: not a payload this protocol version sends: length, alphabet, version, flags or slot
MALFORMED = "malformed"
#: an unfinished ROM's all-zero seed or player ID
UNFINISHED = "unfinished"
#: no entry for the seed and player, or a MAC that does not verify with its key
UNRECOGNIZED = "unrecognized"

#: the ROM slots a payload can name: player 1 and player 2
SLOTS = (0, 1)


#: how much of a malformed scan's text a log line quotes
LOGGED_TEXT_LENGTH = 64


class ScanError(ValueError):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class SlotTakenError(ValueError):
    """A voided round cannot be restored while its entry's slot holds another round."""


def _rejected(reason: str, cause: str, **details: object) -> ScanError:
    """Log a rejection's exact cause, and the error that shows the player only its reason."""
    fields = "".join(f" {name}={value}" for name, value in details.items())
    log.warning("scan rejected as %s: %s%s", reason, cause, fields)
    return ScanError(reason)


@dataclass(frozen=True)
class HoleResult:
    position: int
    strokes: int
    putts: int


@dataclass(frozen=True)
class Round:
    """A recorded submission and its holes."""

    id: int
    entry_id: int
    seed_id: str
    user_id: int
    slot: int
    total_strokes: int
    total_putts: int
    received_at: str
    flagged: bool
    #: an admin's note on the flag; never shown outside the admin pages
    flag_note: str | None
    holes: tuple[HoleResult, ...]


@dataclass(frozen=True)
class ScanResult:
    round: Round
    #: whether this scan recorded the round, rather than finding it recorded
    new: bool


def _parse(text: str) -> tuple[bytes, payload.RoundPayload]:
    quoted = repr(text[:LOGGED_TEXT_LENGTH])
    if len(text) != payload.BASE64_LEN:
        raise _rejected(MALFORMED, "length", length=len(text), text=quoted)
    try:
        data = payload.base64url_decode(text)
    except ValueError:
        raise _rejected(MALFORMED, "alphabet", text=quoted) from None
    round_payload, _mac = payload.RoundPayload.from_bytes(data)
    if round_payload.protocol_version != payload.PROTOCOL_VERSION:
        raise _rejected(MALFORMED, "protocol version", version=round_payload.protocol_version, text=quoted)
    if round_payload.reserved_flags != 0:
        raise _rejected(MALFORMED, "reserved flags", flags=round_payload.reserved_flags, text=quoted)
    if round_payload.player_slot not in SLOTS:
        raise _rejected(MALFORMED, "slot", slot=round_payload.player_slot, text=quoted)
    if not any(round_payload.seed_id):
        raise _rejected(UNFINISHED, "zero seed id")
    if not any(round_payload.player_id):
        raise _rejected(UNFINISHED, "zero player id")
    return data, round_payload


_ROUND_SELECT = """
    SELECT submissions.id, submissions.entry_id, entries.seed_id, entries.user_id, submissions.slot,
           submissions.total_strokes, submissions.total_putts, submissions.received_at, submissions.flagged,
           submissions.flag_note
    FROM submissions JOIN entries ON entries.id = submissions.entry_id
"""


def _load_round(conn, where: str, params: tuple) -> Round | None:
    row = conn.execute(f"{_ROUND_SELECT} WHERE {where}", params).fetchone()
    if row is None:
        return None
    holes = conn.execute(
        "SELECT position, strokes, putts FROM submission_holes WHERE submission_id = ? ORDER BY position",
        (row["id"],),
    ).fetchall()
    return Round(
        id=row["id"],
        entry_id=row["entry_id"],
        seed_id=row["seed_id"],
        user_id=row["user_id"],
        slot=row["slot"],
        total_strokes=row["total_strokes"],
        total_putts=row["total_putts"],
        received_at=row["received_at"],
        flagged=bool(row["flagged"]),
        flag_note=row["flag_note"],
        holes=tuple(HoleResult(hole["position"], hole["strokes"], hole["putts"]) for hole in holes),
    )


def _missing_entry_cause(conn, qr_seed_id: int, player_id: int) -> str:
    """Which lookup found nothing, for the log."""
    if conn.execute("SELECT 1 FROM seeds WHERE qr_seed_id = ?", (qr_seed_id,)).fetchone() is None:
        return "unknown seed"
    if conn.execute("SELECT 1 FROM users WHERE player_id = ?", (player_id,)).fetchone() is None:
        return "unknown player"
    return "no entry for the seed and player"


def submit_scan(db: Database, text: str, now: str | None = None) -> ScanResult:
    """Record the round a scan's base64url text carries, or find it already recorded.

    Raises ScanError for a payload that is malformed, from an unfinished ROM, or matches
    no entry's key. Unknown seeds, unknown players, missing entries and bad MACs are one
    reason, so a rejection says nothing about which part failed.
    """
    data, round_payload = _parse(text)
    qr_seed_id = int.from_bytes(round_payload.seed_id, "big")
    player_id = int.from_bytes(round_payload.player_id, "big")
    slot = round_payload.player_slot
    if qr_seed_id > MAX_QR_SEED_ID:  # no seed has it, and SQLite could not bind it
        raise _rejected(UNRECOGNIZED, "seed id past the range", qr_seed_id=qr_seed_id, player_id=player_id, slot=slot)
    ids = {"seed": encode_seed_id(qr_seed_id), "player_id": player_id, "slot": slot}
    received_at = now if now is not None else utc_now()

    # One transaction from the key lookup to the insert, so two scans of one round at once
    # still record it once.
    with db.transaction() as conn:
        entry = conn.execute(
            """
            SELECT entries.id, entries.key_slot0, entries.key_slot1
            FROM entries
            JOIN seeds ON seeds.id = entries.seed_id
            JOIN users ON users.id = entries.user_id
            WHERE seeds.qr_seed_id = ? AND users.player_id = ?
            """,
            (qr_seed_id, player_id),
        ).fetchone()
        if entry is None:
            raise _rejected(UNRECOGNIZED, _missing_entry_cause(conn, qr_seed_id, player_id), **ids)
        key = bytes(entry["key_slot0"] if slot == 0 else entry["key_slot1"])
        if not payload.verify(data, key):
            raise _rejected(UNRECOGNIZED, "MAC does not verify", **ids)
        if conn.execute("SELECT 1 FROM voided_submissions WHERE payload = ?", (data,)).fetchone():
            raise _rejected(UNRECOGNIZED, "voided round", **ids)

        where = "submissions.entry_id = ? AND submissions.slot = ?"
        recorded = _load_round(conn, where, (entry["id"], slot))
        if recorded is not None:
            return ScanResult(recorded, new=False)

        submission_id = conn.execute(
            """
            INSERT INTO submissions (entry_id, slot, payload, total_strokes, total_putts, received_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (entry["id"], slot, data, round_payload.total_strokes, round_payload.total_putts, received_at),
        ).lastrowid
        conn.executemany(
            "INSERT INTO submission_holes (submission_id, position, strokes, putts) VALUES (?, ?, ?, ?)",
            [
                (submission_id, position, hole.strokes, hole.putts)
                for position, hole in enumerate(round_payload.holes, start=1)
            ],
        )
        created = _load_round(conn, where, (entry["id"], slot))
    assert created is not None
    return ScanResult(created, new=True)


@dataclass(frozen=True)
class SeedRound:
    """A round as the seed page lists it."""

    player_name: str
    slot: int
    total_strokes: int
    total_putts: int
    received_at: str
    flagged: bool


def rounds_for_seed(db: Database, seed_id: str) -> list[SeedRound]:
    """The seed's recorded rounds, fewest strokes first, earliest first on a tie."""
    with db.transaction() as conn:
        rows = conn.execute(
            """
            SELECT coalesce(users.global_name, users.username) AS player_name, submissions.slot,
                   submissions.total_strokes, submissions.total_putts, submissions.received_at,
                   submissions.flagged
            FROM submissions
            JOIN entries ON entries.id = submissions.entry_id
            JOIN users ON users.id = entries.user_id
            WHERE entries.seed_id = ?
            ORDER BY submissions.total_strokes, submissions.received_at, submissions.id
            """,
            (seed_id,),
        ).fetchall()
    return [
        SeedRound(
            player_name=row["player_name"],
            slot=row["slot"],
            total_strokes=row["total_strokes"],
            total_putts=row["total_putts"],
            received_at=row["received_at"],
            flagged=bool(row["flagged"]),
        )
        for row in rows
    ]


@dataclass(frozen=True)
class RoundListing:
    """A round as a player's own page lists it, with what it shows of the seed."""

    seed_id: str
    magic_words: tuple[str, ...]
    par: int
    slot: int
    total_strokes: int
    total_putts: int
    received_at: str
    flagged: bool


def rounds_for_user(db: Database, user_id: int) -> list[RoundListing]:
    """The rounds recorded against the user's entries, newest first."""
    with db.transaction() as conn:
        rows = conn.execute(
            """
            SELECT entries.seed_id, seeds.manifest, submissions.slot, submissions.total_strokes,
                   submissions.total_putts, submissions.received_at, submissions.flagged
            FROM submissions
            JOIN entries ON entries.id = submissions.entry_id
            JOIN seeds ON seeds.id = entries.seed_id
            WHERE entries.user_id = ?
            ORDER BY submissions.received_at DESC, submissions.id DESC
            """,
            (user_id,),
        ).fetchall()
    listings = []
    for row in rows:
        course = Manifest.from_json(json.loads(row["manifest"])).course
        listings.append(
            RoundListing(
                seed_id=row["seed_id"],
                magic_words=course.magic_words,
                par=course.par,
                slot=row["slot"],
                total_strokes=row["total_strokes"],
                total_putts=row["total_putts"],
                received_at=row["received_at"],
                flagged=bool(row["flagged"]),
            )
        )
    return listings


# -- Admin actions ------------------------------------------------------------------------


def _note(text: str | None) -> str | None:
    """An admin's note as stored: stripped, and None when there is nothing to it."""
    text = (text or "").strip()
    return text or None


def load_round(db: Database, submission_id: int) -> Round | None:
    with db.transaction() as conn:
        return _load_round(conn, "submissions.id = ?", (submission_id,))


def _payload_of(conn, submission_id: int) -> bytes:
    """A recorded round's payload. Raises KeyError for a missing round."""
    row = conn.execute("SELECT payload FROM submissions WHERE id = ?", (submission_id,)).fetchone()
    if row is None:
        raise KeyError(submission_id)
    return bytes(row["payload"])


def flag_round(
    db: Database, submission_id: int, admin_id: int, note: str | None = None, now: str | None = None
) -> None:
    """Flag a round, or replace a flagged round's note, and log it. Raises KeyError for a missing round."""
    note = _note(note)
    with db.transaction() as conn:
        data = _payload_of(conn, submission_id)
        conn.execute("UPDATE submissions SET flagged = 1, flag_note = ? WHERE id = ?", (note, submission_id))
        audit.record(conn, admin_id, audit.FLAG, audit.ROUND, audit.round_target(data), now or utc_now(), note=note)


def unflag_round(db: Database, submission_id: int, admin_id: int, now: str | None = None) -> None:
    """Clear a round's flag and its note, and log it. Raises KeyError for a missing round."""
    with db.transaction() as conn:
        data = _payload_of(conn, submission_id)
        conn.execute("UPDATE submissions SET flagged = 0, flag_note = NULL WHERE id = ?", (submission_id,))
        audit.record(conn, admin_id, audit.UNFLAG, audit.ROUND, audit.round_target(data), now or utc_now())


def void_round(
    db: Database, submission_id: int, admin_id: int, note: str | None = None, now: str | None = None
) -> int:
    """Move a round to the voided archive, freeing its slot, log it, and return its voided id.

    Raises KeyError for a missing round.
    """
    voided_at = now if now is not None else utc_now()
    note = _note(note)
    with db.transaction() as conn:
        row = conn.execute(
            "SELECT entry_id, slot, payload, received_at, flagged, flag_note FROM submissions WHERE id = ?",
            (submission_id,),
        ).fetchone()
        if row is None:
            raise KeyError(submission_id)
        voided_id = conn.execute(
            """
            INSERT INTO voided_submissions (entry_id, slot, payload, received_at, flagged, flag_note,
                                            voided_at, void_note)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (*tuple(row), voided_at, note),
        ).lastrowid
        assert voided_id is not None
        conn.execute("DELETE FROM submission_holes WHERE submission_id = ?", (submission_id,))
        conn.execute("DELETE FROM submissions WHERE id = ?", (submission_id,))
        audit.record(conn, admin_id, audit.VOID, audit.ROUND, audit.round_target(row["payload"]), voided_at, note=note)
    return voided_id


def restore_round(db: Database, voided_id: int, admin_id: int, now: str | None = None) -> int:
    """Put a voided round back as its entry's round for its slot, log it, and return its new submission id.

    The holes and totals come from the payload again, and the round keeps its received_at
    and flag. Raises KeyError for a missing voided round, and SlotTakenError when the slot
    already holds a round.
    """
    with db.transaction() as conn:
        row = conn.execute(
            "SELECT entry_id, slot, payload, received_at, flagged, flag_note FROM voided_submissions WHERE id = ?",
            (voided_id,),
        ).fetchone()
        if row is None:
            raise KeyError(voided_id)
        taken = conn.execute(
            "SELECT 1 FROM submissions WHERE entry_id = ? AND slot = ?", (row["entry_id"], row["slot"])
        ).fetchone()
        if taken:
            raise SlotTakenError(f"entry {row['entry_id']} already has a round for slot {row['slot']}")
        data = bytes(row["payload"])
        round_payload, _mac = payload.RoundPayload.from_bytes(data)
        submission_id = conn.execute(
            """
            INSERT INTO submissions (entry_id, slot, payload, total_strokes, total_putts, received_at,
                                     flagged, flag_note)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row["entry_id"],
                row["slot"],
                data,
                round_payload.total_strokes,
                round_payload.total_putts,
                row["received_at"],
                row["flagged"],
                row["flag_note"],
            ),
        ).lastrowid
        assert submission_id is not None
        conn.executemany(
            "INSERT INTO submission_holes (submission_id, position, strokes, putts) VALUES (?, ?, ?, ?)",
            [
                (submission_id, position, hole.strokes, hole.putts)
                for position, hole in enumerate(round_payload.holes, start=1)
            ],
        )
        conn.execute("DELETE FROM voided_submissions WHERE id = ?", (voided_id,))
        audit.record(conn, admin_id, audit.RESTORE, audit.ROUND, audit.round_target(data), now or utc_now())
    return submission_id
