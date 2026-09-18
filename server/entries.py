"""Entries: the only code that writes `entries`.

An entry is the record that a signed-in player has entered a seed. A signed-in download
creates it, or updates its choices when it exists and has no recorded round; once a round is
recorded, downloads leave the entry as it is. Its two MAC keys, one per ROM slot, are drawn
when it is created and never change, so every ROM a player downloads for a seed submits
under the same keys. The name and clubs are the new-save defaults of the latest download
before the first round, not a record of the bag a round was played with. See
docs/randomizer_devplan.md, "Data model".
"""

import json
import secrets
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass, field

from golf.core.patches.sram_defaults import Club
from golf.qr import payload
from golf.randomizer.build import PlayerOptions
from golf.randomizer.manifest import Manifest

from .db import Database
from .seeds import utc_now

COLUMNS = "id, seed_id, user_id, player_name, clubs, key_slot0, key_slot1, created_at, updated_at"


def new_key() -> bytes:
    return secrets.token_bytes(payload.KEY_LEN)


def clubs_text(clubs: frozenset[Club]) -> str:
    """A bag as the `clubs` column stores it: labels in ascending club order, space-separated."""
    return " ".join(club.label for club in sorted(clubs))


@dataclass(frozen=True)
class Entry:
    id: int
    seed_id: str
    user_id: int
    player_name: str
    #: club labels in ascending club order, putter included
    clubs: tuple[str, ...]
    #: the MAC keys for slots 0 and 1; kept out of repr so they never reach a log
    keys: tuple[bytes, bytes] = field(repr=False)
    created_at: str
    updated_at: str


def _entry(row: sqlite3.Row) -> Entry:
    return Entry(
        id=row["id"],
        seed_id=row["seed_id"],
        user_id=row["user_id"],
        player_name=row["player_name"],
        clubs=tuple(row["clubs"].split()),
        keys=(bytes(row["key_slot0"]), bytes(row["key_slot1"])),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def upsert_entry(
    db: Database,
    seed_id: str,
    user_id: int,
    options: PlayerOptions,
    now: str | None = None,
    draw_key: Callable[[], bytes] = new_key,
) -> Entry:
    """Create the player's entry for a seed, or update its choices, and return it.

    One statement, so two first downloads at once still make one entry. The keys drawn here
    are only stored when the entry is new. An entry with a recorded round is not updated, and
    comes back as it is.
    """
    at = now if now is not None else utc_now()
    with db.transaction() as conn:
        rows = conn.execute(
            f"""
            INSERT INTO entries (seed_id, user_id, player_name, clubs, key_slot0, key_slot1,
                                 created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT (seed_id, user_id) DO UPDATE
                SET player_name = excluded.player_name, clubs = excluded.clubs, updated_at = excluded.updated_at
                WHERE NOT EXISTS (SELECT 1 FROM rounds WHERE rounds.entry_id = entries.id)
            RETURNING {COLUMNS}
            """,
            (seed_id, user_id, options.player_name, clubs_text(options.clubs), draw_key(), draw_key(), at, at),
        ).fetchall()
        # RETURNING rows are read in full inside the transaction, or COMMIT finds the statement open
        if not rows:  # the entry has a round, so the update was skipped
            rows = conn.execute(
                f"SELECT {COLUMNS} FROM entries WHERE seed_id = ? AND user_id = ?", (seed_id, user_id)
            ).fetchall()
    return _entry(rows[0])


def load_entry(db: Database, seed_id: str, user_id: int) -> Entry | None:
    with db.transaction() as conn:
        row = conn.execute(
            f"SELECT {COLUMNS} FROM entries WHERE seed_id = ? AND user_id = ?", (seed_id, user_id)
        ).fetchone()
    return None if row is None else _entry(row)


@dataclass(frozen=True)
class EntryListing:
    """An entry as a player's own page lists it, with what it shows of the seed."""

    seed_id: str
    magic_words: tuple[str, ...]
    par: int
    player_name: str
    clubs: tuple[str, ...]
    created_at: str


def entries_for_user(db: Database, user_id: int) -> list[EntryListing]:
    """The user's entries, newest first."""
    with db.transaction() as conn:
        rows = conn.execute(
            """
            SELECT entries.seed_id, seeds.manifest, entries.player_name, entries.clubs, entries.created_at
            FROM entries JOIN seeds ON seeds.id = entries.seed_id
            WHERE entries.user_id = ?
            ORDER BY entries.created_at DESC, entries.id DESC
            """,
            (user_id,),
        ).fetchall()
    listings = []
    for row in rows:
        course = Manifest.from_json(json.loads(row["manifest"])).course
        listings.append(
            EntryListing(
                seed_id=row["seed_id"],
                magic_words=course.magic_words,
                par=course.par,
                player_name=row["player_name"],
                clubs=tuple(row["clubs"].split()),
                created_at=row["created_at"],
            )
        )
    return listings
