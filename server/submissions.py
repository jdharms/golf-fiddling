"""Submissions: the only code that writes `submissions` and `submission_holes`.

A scan of a finished ROM's scorecard QR code carries the round's 36-byte payload
(`golf/qr/payload.py`). `submit_scan` resolves it to the entry it belongs to: the seed ID
names the seed, the player ID the user, the pair their entry, and the payload's slot the
MAC key. A payload that verifies is recorded against (entry, slot), and the first one
recorded stays: a later scan for the same entry and slot that also verifies, identical or
not, stores nothing and answers with the round already recorded. Both ROM slots carry the
downloader's player ID, so a player 2 round (slot 1) counts toward the same entry as slot 0. See
docs/randomizer_devplan.md, "Data model", and docs/scorecard_qr.md, "Server contract".
"""

import json
from dataclasses import dataclass

from golf.qr import payload
from golf.randomizer.manifest import Manifest

from .db import Database
from .seeds import MAX_QR_SEED_ID, utc_now

#: ScanError reasons, each shown by its own strings key in submission.html
#: not a payload this protocol version sends: length, alphabet, version, flags or slot
MALFORMED = "malformed"
#: an unfinished ROM's all-zero seed or player ID
UNFINISHED = "unfinished"
#: no entry for the seed and player, or a MAC that does not verify with its key
UNRECOGNIZED = "unrecognized"

#: the ROM slots a payload can name: player 1 and player 2
SLOTS = (0, 1)


class ScanError(ValueError):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


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
    holes: tuple[HoleResult, ...]


@dataclass(frozen=True)
class ScanResult:
    round: Round
    #: whether this scan recorded the round, rather than finding it recorded
    new: bool


def _parse(text: str) -> tuple[bytes, payload.RoundPayload]:
    if len(text) != payload.BASE64_LEN:
        raise ScanError(MALFORMED)
    try:
        data = payload.base64url_decode(text)
    except ValueError:
        raise ScanError(MALFORMED) from None
    round_payload, _mac = payload.RoundPayload.from_bytes(data)
    if (
        round_payload.protocol_version != payload.PROTOCOL_VERSION
        or round_payload.reserved_flags != 0
        or round_payload.player_slot not in SLOTS
    ):
        raise ScanError(MALFORMED)
    if not any(round_payload.seed_id) or not any(round_payload.player_id):
        raise ScanError(UNFINISHED)
    return data, round_payload


_ROUND_SELECT = """
    SELECT submissions.id, submissions.entry_id, entries.seed_id, entries.user_id, submissions.slot,
           submissions.total_strokes, submissions.total_putts, submissions.received_at, submissions.flagged
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
        holes=tuple(HoleResult(hole["position"], hole["strokes"], hole["putts"]) for hole in holes),
    )


def submit_scan(db: Database, text: str, now: str | None = None) -> ScanResult:
    """Record the round a scan's base64url text carries, or find it already recorded.

    Raises ScanError for a payload that is malformed, from an unfinished ROM, or matches
    no entry's key. Unknown seeds, unknown players, missing entries and bad MACs are one
    reason, so a rejection says nothing about which part failed.
    """
    data, round_payload = _parse(text)
    qr_seed_id = int.from_bytes(round_payload.seed_id, "big")
    player_id = int.from_bytes(round_payload.player_id, "big")
    if qr_seed_id > MAX_QR_SEED_ID:  # no seed has it, and SQLite could not bind it
        raise ScanError(UNRECOGNIZED)
    slot = round_payload.player_slot
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
            raise ScanError(UNRECOGNIZED)
        key = bytes(entry["key_slot0"] if slot == 0 else entry["key_slot1"])
        if not payload.verify(data, key):
            raise ScanError(UNRECOGNIZED)

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


def rounds_for_seed(db: Database, seed_id: str) -> list[SeedRound]:
    """The seed's recorded rounds, fewest strokes first, earliest first on a tie."""
    with db.transaction() as conn:
        rows = conn.execute(
            """
            SELECT coalesce(users.global_name, users.username) AS player_name, submissions.slot,
                   submissions.total_strokes, submissions.total_putts, submissions.received_at
            FROM submissions
            JOIN entries ON entries.id = submissions.entry_id
            JOIN users ON users.id = entries.user_id
            WHERE entries.seed_id = ?
            ORDER BY submissions.total_strokes, submissions.received_at, submissions.id
            """,
            (seed_id,),
        ).fetchall()
    return [SeedRound(**{name: row[name] for name in row.keys()}) for row in rows]  # noqa: SIM118 (sqlite3.Row)


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


def rounds_for_user(db: Database, user_id: int) -> list[RoundListing]:
    """The rounds recorded against the user's entries, newest first."""
    with db.transaction() as conn:
        rows = conn.execute(
            """
            SELECT entries.seed_id, seeds.manifest, submissions.slot, submissions.total_strokes,
                   submissions.total_putts, submissions.received_at
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
            )
        )
    return listings
