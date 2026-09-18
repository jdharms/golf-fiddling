"""Rounds: the only code that writes `rounds`, `round_holes` and `voided_rounds`.

A round is a scan that `server/submissions.py` accepted: its 36-byte payload (which carries
every hole), recorded against (entry, slot), one round per pair. Each round is drawn a
`public_id` when it is recorded, the base62 id its `/r/<id>` permalink names it by
(`server/ids.py`). No other round is ever given it, so a permalink always means one
scorecard. See docs/randomizer_devplan.md, "Data model".

An admin can flag a round, which leaves it counted and marked, or void it. A voided round
moves to `voided_rounds` with its public id, freeing its slot for a different round, and a
scan of its payload is refused until an admin restores it. Each admin action writes its
audit row through `server/audit.py` in the same transaction.
"""

import json
import sqlite3
from dataclasses import dataclass

from golf.qr import payload
from golf.randomizer.manifest import Manifest

from . import audit
from .db import Database
from .ids import is_id, new_id
from .seeds import utc_now

#: draws before recording a round gives up on finding an unused public id
ID_ATTEMPTS = 10


class SlotTakenError(ValueError):
    """A voided round cannot be restored while its entry's slot holds another round."""


class RoundIdExhaustedError(RuntimeError):
    """Every draw collided with an existing round, which only a broken generator makes likely."""


@dataclass(frozen=True)
class RoundHole:
    position: int
    strokes: int
    putts: int


@dataclass(frozen=True)
class Round:
    """A recorded round and its holes."""

    #: the base62 id every page names the round by, its `/r/<id>` permalink and its admin page
    public_id: str
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
    holes: tuple[RoundHole, ...]


@dataclass(frozen=True)
class VoidedRound:
    """What the permalink of a voided round shows: that there was one, and no scores."""

    public_id: str
    seed_id: str
    user_id: int
    slot: int
    received_at: str
    voided_at: str


_ROUND_SELECT = """
    SELECT rounds.id, rounds.public_id, rounds.entry_id, entries.seed_id, entries.user_id, rounds.slot,
           rounds.total_strokes, rounds.total_putts, rounds.received_at, rounds.flagged, rounds.flag_note
    FROM rounds JOIN entries ON entries.id = rounds.entry_id
"""


def _load_round(conn: sqlite3.Connection, where: str, params: tuple) -> Round | None:
    row = conn.execute(f"{_ROUND_SELECT} WHERE {where}", params).fetchone()
    if row is None:
        return None
    holes = conn.execute(
        "SELECT position, strokes, putts FROM round_holes WHERE round_id = ? ORDER BY position",
        (row["id"],),
    ).fetchall()
    return Round(
        public_id=row["public_id"],
        entry_id=row["entry_id"],
        seed_id=row["seed_id"],
        user_id=row["user_id"],
        slot=row["slot"],
        total_strokes=row["total_strokes"],
        total_putts=row["total_putts"],
        received_at=row["received_at"],
        flagged=bool(row["flagged"]),
        flag_note=row["flag_note"],
        holes=tuple(
            RoundHole(hole["position"], hole["strokes"], hole["putts"])
            for hole in holes
        ),
    )


def _draw_public_id(conn: sqlite3.Connection) -> str:
    """A public id no recorded or voided round holds.

    One connection under a lock serves the site, so an id free inside this transaction is
    still free at the insert.
    """
    for _ in range(ID_ATTEMPTS):
        public_id = new_id()
        taken = conn.execute(
            """
            SELECT 1 FROM rounds WHERE public_id = ?
            UNION ALL
            SELECT 1 FROM voided_rounds WHERE public_id = ?
            """,
            (public_id, public_id),
        ).fetchone()
        if taken is None:
            return public_id
    raise RoundIdExhaustedError(f"no unused round id in {ID_ATTEMPTS} draws")


def _insert_round(
    conn: sqlite3.Connection,
    public_id: str,
    entry_id: int,
    slot: int,
    data: bytes,
    received_at: str,
    flagged: bool = False,
    flag_note: str | None = None,
) -> int:
    """Insert a round and its holes, the totals and holes read from the payload. Returns its row id."""
    round_payload, _mac = payload.RoundPayload.from_bytes(data)
    round_id = conn.execute(
        """
        INSERT INTO rounds (public_id, entry_id, slot, payload, total_strokes, total_putts, received_at,
                            flagged, flag_note)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            public_id,
            entry_id,
            slot,
            data,
            round_payload.total_strokes,
            round_payload.total_putts,
            received_at,
            flagged,
            flag_note,
        ),
    ).lastrowid
    assert round_id is not None
    conn.executemany(
        "INSERT INTO round_holes (round_id, position, strokes, putts) VALUES (?, ?, ?, ?)",
        [
            (round_id, position, hole.strokes, hole.putts)
            for position, hole in enumerate(round_payload.holes, start=1)
        ],
    )
    return round_id


# -- Recording, inside a scan's transaction ------------------------------------------------


def round_in_slot(conn: sqlite3.Connection, entry_id: int, slot: int) -> Round | None:
    """The round recorded for an entry's slot, if any."""
    return _load_round(
        conn, "rounds.entry_id = ? AND rounds.slot = ?", (entry_id, slot)
    )


def is_voided(conn: sqlite3.Connection, data: bytes) -> bool:
    """Whether this payload is a voided round's, which a scan may not record again."""
    return (
        conn.execute(
            "SELECT 1 FROM voided_rounds WHERE payload = ?", (data,)
        ).fetchone()
        is not None
    )


def record_round(
    conn: sqlite3.Connection, entry_id: int, slot: int, data: bytes, received_at: str
) -> Round:
    """Record a verified payload as the entry's round for its slot, drawing its public id.

    The caller holds the transaction and has checked that the slot is free and the payload
    not voided.
    """
    round_id = _insert_round(
        conn, _draw_public_id(conn), entry_id, slot, data, received_at
    )
    recorded = _load_round(conn, "rounds.id = ?", (round_id,))
    assert recorded is not None
    return recorded


# -- Reads --------------------------------------------------------------------------------


def find_round(db: Database, public_id: str) -> Round | VoidedRound | None:
    """The round with this permalink id, recorded or voided, or None for a missing or malformed one.

    A voided round never carries the admin's void note, which the public page must not show.
    """
    if not is_id(public_id):
        return None
    with db.transaction() as conn:
        recorded = _load_round(conn, "rounds.public_id = ?", (public_id,))
        if recorded is not None:
            return recorded
        row = conn.execute(
            """
            SELECT voided_rounds.public_id, entries.seed_id, entries.user_id, voided_rounds.slot,
                   voided_rounds.received_at, voided_rounds.voided_at
            FROM voided_rounds JOIN entries ON entries.id = voided_rounds.entry_id
            WHERE voided_rounds.public_id = ?
            """,
            (public_id,),
        ).fetchone()
    if row is None:
        return None
    return VoidedRound(
        public_id=row["public_id"],
        seed_id=row["seed_id"],
        user_id=row["user_id"],
        slot=row["slot"],
        received_at=row["received_at"],
        voided_at=row["voided_at"],
    )


@dataclass(frozen=True)
class SeedRound:
    """A round as the seed page lists it."""

    public_id: str
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
            SELECT rounds.public_id, coalesce(users.global_name, users.username) AS player_name, rounds.slot,
                   rounds.total_strokes, rounds.total_putts, rounds.received_at, rounds.flagged
            FROM rounds
            JOIN entries ON entries.id = rounds.entry_id
            JOIN users ON users.id = entries.user_id
            WHERE entries.seed_id = ?
            ORDER BY rounds.total_strokes, rounds.received_at, rounds.id
            """,
            (seed_id,),
        ).fetchall()
    return [
        SeedRound(
            public_id=row["public_id"],
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
class UserRound:
    """A round as a player's own page lists it, with what it shows of the seed."""

    public_id: str
    seed_id: str
    magic_words: tuple[str, ...]
    par: int
    slot: int
    total_strokes: int
    total_putts: int
    received_at: str
    flagged: bool


def rounds_for_user(db: Database, user_id: int) -> list[UserRound]:
    """The rounds recorded against the user's entries, newest first."""
    with db.transaction() as conn:
        rows = conn.execute(
            """
            SELECT rounds.public_id, entries.seed_id, seeds.manifest, rounds.slot, rounds.total_strokes,
                   rounds.total_putts, rounds.received_at, rounds.flagged
            FROM rounds
            JOIN entries ON entries.id = rounds.entry_id
            JOIN seeds ON seeds.id = entries.seed_id
            WHERE entries.user_id = ?
            ORDER BY rounds.received_at DESC, rounds.id DESC
            """,
            (user_id,),
        ).fetchall()
    listings = []
    for row in rows:
        course = Manifest.from_json(json.loads(row["manifest"])).course
        listings.append(
            UserRound(
                public_id=row["public_id"],
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


def _require_round(conn: sqlite3.Connection, public_id: str) -> None:
    """Raise KeyError unless a recorded round has this public id."""
    if (
        conn.execute(
            "SELECT 1 FROM rounds WHERE public_id = ?", (public_id,)
        ).fetchone()
        is None
    ):
        raise KeyError(public_id)


def flag_round(
    db: Database,
    public_id: str,
    admin_id: int,
    note: str | None = None,
    now: str | None = None,
) -> None:
    """Flag a round, or replace a flagged round's note, and log it. Raises KeyError for a missing round."""
    note = _note(note)
    with db.transaction() as conn:
        _require_round(conn, public_id)
        conn.execute(
            "UPDATE rounds SET flagged = 1, flag_note = ? WHERE public_id = ?",
            (note, public_id),
        )
        audit.record(
            conn,
            admin_id,
            audit.FLAG,
            audit.ROUND,
            public_id,
            now or utc_now(),
            note=note,
        )


def unflag_round(
    db: Database, public_id: str, admin_id: int, now: str | None = None
) -> None:
    """Clear a round's flag and its note, and log it. Raises KeyError for a missing round."""
    with db.transaction() as conn:
        _require_round(conn, public_id)
        conn.execute(
            "UPDATE rounds SET flagged = 0, flag_note = NULL WHERE public_id = ?",
            (public_id,),
        )
        audit.record(
            conn, admin_id, audit.UNFLAG, audit.ROUND, public_id, now or utc_now()
        )


def void_round(
    db: Database,
    public_id: str,
    admin_id: int,
    note: str | None = None,
    now: str | None = None,
) -> None:
    """Move a round to the voided archive, freeing its slot, and log it. Raises KeyError for a missing round."""
    voided_at = now if now is not None else utc_now()
    note = _note(note)
    with db.transaction() as conn:
        row = conn.execute(
            "SELECT id, entry_id, slot, payload, received_at, flagged, flag_note FROM rounds WHERE public_id = ?",
            (public_id,),
        ).fetchone()
        if row is None:
            raise KeyError(public_id)
        conn.execute(
            """
            INSERT INTO voided_rounds (public_id, entry_id, slot, payload, received_at, flagged, flag_note,
                                       voided_at, void_note)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (public_id, *tuple(row)[1:], voided_at, note),
        )
        conn.execute("DELETE FROM round_holes WHERE round_id = ?", (row["id"],))
        conn.execute("DELETE FROM rounds WHERE id = ?", (row["id"],))
        audit.record(
            conn, admin_id, audit.VOID, audit.ROUND, public_id, voided_at, note=note
        )


def restore_round(
    db: Database, public_id: str, admin_id: int, now: str | None = None
) -> None:
    """Put a voided round back as its entry's round for its slot, and log it.

    The holes and totals come from the payload again, and the round keeps its received_at,
    flag and public id. Raises KeyError for a missing voided round, and SlotTakenError when
    the slot already holds a round.
    """
    with db.transaction() as conn:
        row = conn.execute(
            "SELECT entry_id, slot, payload, received_at, flagged, flag_note FROM voided_rounds WHERE public_id = ?",
            (public_id,),
        ).fetchone()
        if row is None:
            raise KeyError(public_id)
        if round_in_slot(conn, row["entry_id"], row["slot"]) is not None:
            raise SlotTakenError(
                f"entry {row['entry_id']} already has a round for slot {row['slot']}"
            )
        _insert_round(
            conn,
            public_id,
            row["entry_id"],
            row["slot"],
            bytes(row["payload"]),
            row["received_at"],
            flagged=bool(row["flagged"]),
            flag_note=row["flag_note"],
        )
        conn.execute("DELETE FROM voided_rounds WHERE public_id = ?", (public_id,))
        audit.record(
            conn, admin_id, audit.RESTORE, audit.ROUND, public_id, now or utc_now()
        )
