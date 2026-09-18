"""What the admin pages show: lists and details across every seed, round and player.

Reads only; the admin actions write through the owning modules (`server/seeds.py`,
`server/rounds.py`), which log them through `server/audit.py`. Who did something, and
a seed's or round's history, come from that log. Nothing here is a web type. Lists come a
page at a time, newest first. See docs/randomizer_devplan.md, "Users and access".

This module holds every admin page's reads in one file. When adding to it, consider
splitting it into a `server/admin/` package by area (seeds, rounds, users, the audit log)
first; nothing outside imports more than the names `server/admin_routes.py` uses.
"""

import json
import sqlite3
from dataclasses import dataclass

from golf.qr import payload
from golf.randomizer.catalog import Catalog, CatalogError

from . import audit
from .db import Database
from .rounds import Round, find_round
from .seeds import SeedRow, load_seed
from .users import User, load_user

#: rows on one page of an admin list
PAGE_SIZE = 100

#: a user's name as the pages show it, for a query joining `users`
_USER_NAME = "coalesce(users.global_name, users.username)"


@dataclass(frozen=True)
class Page[T]:
    items: list[T]
    number: int
    has_next: bool


def _page[T](items: list[T], number: int) -> Page[T]:
    """A page from a query that asked for one row past PAGE_SIZE, to know whether another follows."""
    return Page(items[:PAGE_SIZE], number, len(items) > PAGE_SIZE)


def _limit(number: int) -> tuple[int, int]:
    return PAGE_SIZE + 1, (max(number, 1) - 1) * PAGE_SIZE


def _magic_words(manifest_text: str) -> tuple[str, ...]:
    return tuple(json.loads(manifest_text)["course"]["magic_words"])


@dataclass(frozen=True)
class Counts:
    seeds: int
    users: int
    entries: int
    rounds: int
    flagged: int
    voided: int
    actions: int


def counts(db: Database) -> Counts:
    with db.transaction() as conn:
        row = conn.execute(
            """
            SELECT (SELECT count(*) FROM seeds) AS seeds, (SELECT count(*) FROM users) AS users,
                   (SELECT count(*) FROM entries) AS entries, (SELECT count(*) FROM rounds) AS rounds,
                   (SELECT count(*) FROM rounds WHERE flagged) AS flagged,
                   (SELECT count(*) FROM voided_rounds) AS voided,
                   (SELECT count(*) FROM admin_actions) AS actions
            """
        ).fetchone()
    return Counts(**{name: row[name] for name in row.keys()})  # noqa: SIM118 (sqlite3.Row)


# -- The audit log ------------------------------------------------------------------------


@dataclass(frozen=True)
class AdminAction:
    id: int
    admin_id: int
    admin_name: str
    action: str
    target_type: str
    target_id: str
    note: str | None
    detail: dict
    created_at: str


@dataclass(frozen=True)
class ActionTarget:
    """Where an action's target is now, for a link: None when it is nowhere to link to."""

    path: str | None
    label: str


@dataclass(frozen=True)
class ActionListing:
    action: AdminAction
    target: ActionTarget


_ACTION_SELECT = f"""
    SELECT admin_actions.id, admin_actions.admin_id, {_USER_NAME} AS admin_name, admin_actions.action,
           admin_actions.target_type, admin_actions.target_id, admin_actions.note, admin_actions.detail,
           admin_actions.created_at
    FROM admin_actions JOIN users ON users.id = admin_actions.admin_id
"""


def _action(row: sqlite3.Row) -> AdminAction:
    return AdminAction(
        id=row["id"],
        admin_id=row["admin_id"],
        admin_name=row["admin_name"],
        action=row["action"],
        target_type=row["target_type"],
        target_id=row["target_id"],
        note=row["note"],
        detail=json.loads(row["detail"]),
        created_at=row["created_at"],
    )


def _history(
    conn: sqlite3.Connection, target_type: str, target_id: str
) -> list[AdminAction]:
    """Every action on one target, oldest first."""
    rows = conn.execute(
        f"{_ACTION_SELECT} WHERE admin_actions.target_type = ? AND admin_actions.target_id = ? ORDER BY admin_actions.id",
        (target_type, target_id),
    ).fetchall()
    return [_action(row) for row in rows]


def _latest(history: list[AdminAction], action: str) -> AdminAction | None:
    return next((entry for entry in reversed(history) if entry.action == action), None)


def _resolve(conn: sqlite3.Connection, entry: AdminAction) -> ActionTarget:
    if entry.target_type == audit.SEED:
        row = conn.execute(
            "SELECT manifest FROM seeds WHERE id = ?", (entry.target_id,)
        ).fetchone()
        if row is None:  # pragma: no cover - seeds are never deleted
            return ActionTarget(None, entry.target_id)
        return ActionTarget(
            f"/admin/seeds/{entry.target_id}", " ".join(_magic_words(row["manifest"]))
        )
    if entry.target_type == audit.ROUND:
        for table, path in (
            ("rounds", f"/admin/rounds/{entry.target_id}"),
            ("voided_rounds", "/admin/voided"),
        ):
            row = conn.execute(
                f"""
                SELECT {_USER_NAME} AS user_name, {table}.slot, seeds.manifest
                FROM {table}
                JOIN entries ON entries.id = {table}.entry_id
                JOIN users ON users.id = entries.user_id
                JOIN seeds ON seeds.id = entries.seed_id
                WHERE {table}.public_id = ?
                """,
                (entry.target_id,),
            ).fetchone()
            if row is not None:
                player = row["user_name"] + (" (P2)" if row["slot"] == 1 else "")
                label = f"{player} on {' '.join(_magic_words(row['manifest']))}"
                if table == "voided_rounds":
                    label += ", voided"
                return ActionTarget(path, label)
    return ActionTarget(
        None, entry.target_id
    )  # pragma: no cover - rounds are never deleted outright


def actions_page(db: Database, number: int = 1) -> Page[ActionListing]:
    with db.transaction() as conn:
        rows = conn.execute(
            f"{_ACTION_SELECT} ORDER BY admin_actions.id DESC LIMIT ? OFFSET ?",
            _limit(number),
        ).fetchall()
        listings = [
            ActionListing(entry, _resolve(conn, entry)) for entry in map(_action, rows)
        ]
    return _page(listings, number)


# -- Seeds --------------------------------------------------------------------------------


@dataclass(frozen=True)
class SeedListing:
    id: str
    magic_words: tuple[str, ...]
    par: int
    created_at: str
    rebuilt_at: str | None
    creator_id: int | None
    creator_name: str | None
    entries: int
    rounds: int


_SEED_SELECT = f"""
    SELECT seeds.id, seeds.manifest, seeds.created_at, seeds.rebuilt_at, seeds.creator_id,
           {_USER_NAME} AS creator_name,
           (SELECT count(*) FROM entries WHERE entries.seed_id = seeds.id) AS entries,
           (SELECT count(*) FROM rounds JOIN entries ON entries.id = rounds.entry_id
            WHERE entries.seed_id = seeds.id) AS rounds
    FROM seeds LEFT JOIN users ON users.id = seeds.creator_id
"""


def _seed_listing(row: sqlite3.Row) -> SeedListing:
    course = json.loads(row["manifest"])["course"]
    return SeedListing(
        id=row["id"],
        magic_words=tuple(course["magic_words"]),
        par=sum(hole["par"] for hole in course["holes"]),
        created_at=row["created_at"],
        rebuilt_at=row["rebuilt_at"],
        creator_id=row["creator_id"],
        creator_name=row["creator_name"],
        entries=row["entries"],
        rounds=row["rounds"],
    )


def seeds_page(db: Database, number: int = 1) -> Page[SeedListing]:
    with db.transaction() as conn:
        rows = conn.execute(
            f"{_SEED_SELECT} ORDER BY seeds.created_at DESC, seeds.rowid DESC LIMIT ? OFFSET ?",
            _limit(number),
        ).fetchall()
    return _page([_seed_listing(row) for row in rows], number)


@dataclass(frozen=True)
class EntryListing:
    id: int
    seed_id: str
    magic_words: tuple[str, ...]
    user_id: int
    user_name: str
    player_name: str
    clubs: tuple[str, ...]
    created_at: str
    updated_at: str


_ENTRY_SELECT = f"""
    SELECT entries.id, entries.seed_id, seeds.manifest, entries.user_id, {_USER_NAME} AS user_name,
           entries.player_name, entries.clubs, entries.created_at, entries.updated_at
    FROM entries JOIN seeds ON seeds.id = entries.seed_id JOIN users ON users.id = entries.user_id
"""


def _entry_listing(row: sqlite3.Row) -> EntryListing:
    return EntryListing(
        id=row["id"],
        seed_id=row["seed_id"],
        magic_words=_magic_words(row["manifest"]),
        user_id=row["user_id"],
        user_name=row["user_name"],
        player_name=row["player_name"],
        clubs=tuple(row["clubs"].split()),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


@dataclass(frozen=True)
class RoundListing:
    public_id: str
    seed_id: str
    magic_words: tuple[str, ...]
    user_id: int
    user_name: str
    slot: int
    total_strokes: int
    total_putts: int
    received_at: str
    flagged: bool
    flag_note: str | None


_ROUND_SELECT = f"""
    SELECT rounds.public_id, entries.seed_id, seeds.manifest, entries.user_id, {_USER_NAME} AS user_name,
           rounds.slot, rounds.total_strokes, rounds.total_putts, rounds.received_at,
           rounds.flagged, rounds.flag_note
    FROM rounds
    JOIN entries ON entries.id = rounds.entry_id
    JOIN seeds ON seeds.id = entries.seed_id
    JOIN users ON users.id = entries.user_id
"""


def _round_listing(row: sqlite3.Row) -> RoundListing:
    return RoundListing(
        public_id=row["public_id"],
        seed_id=row["seed_id"],
        magic_words=_magic_words(row["manifest"]),
        user_id=row["user_id"],
        user_name=row["user_name"],
        slot=row["slot"],
        total_strokes=row["total_strokes"],
        total_putts=row["total_putts"],
        received_at=row["received_at"],
        flagged=bool(row["flagged"]),
        flag_note=row["flag_note"],
    )


@dataclass(frozen=True)
class HoleSlot:
    number: int
    id: str
    par: int
    withdrawn: bool


@dataclass(frozen=True)
class SeedDetail:
    seed: SeedRow
    generator_version: int
    catalog_version: int
    curation_stamp: str
    ips_size: int
    creator: User | None
    holes: tuple[HoleSlot, ...]
    entries: list[EntryListing]
    rounds: list[RoundListing]
    #: every admin action on the seed, oldest first
    history: list[AdminAction]

    @property
    def rebuilt_by(self) -> AdminAction | None:
        """The rebuild that last changed the IPS."""
        return next(
            (
                entry
                for entry in reversed(self.history)
                if entry.action == audit.REBUILD and entry.detail.get("changed")
            ),
            None,
        )

    @property
    def withdrawn(self) -> tuple[HoleSlot, ...]:
        """The holes a rebuild cannot load."""
        return tuple(hole for hole in self.holes if hole.withdrawn)


def seed_detail(db: Database, seed_id: str, catalog: Catalog) -> SeedDetail | None:
    seed = load_seed(db, seed_id)
    if seed is None:
        return None
    with db.transaction() as conn:
        row = conn.execute(
            "SELECT length(unfinished_ips) AS ips_size FROM seeds WHERE id = ?",
            (seed_id,),
        ).fetchone()
        history = _history(conn, audit.SEED, seed_id)
        entries = conn.execute(
            f"{_ENTRY_SELECT} WHERE entries.seed_id = ? ORDER BY entries.created_at, entries.id",
            (seed_id,),
        ).fetchall()
        rounds = conn.execute(
            f"{_ROUND_SELECT} WHERE entries.seed_id = ? ORDER BY rounds.received_at, rounds.id",
            (seed_id,),
        ).fetchall()
    holes = []
    for number, slot in enumerate(seed.manifest.course.holes, start=1):
        try:
            withdrawn = catalog[slot.id].withdrawn
        except CatalogError:  # pragma: no cover - the catalog never loses an id
            withdrawn = True
        holes.append(HoleSlot(number, str(slot.id), slot.par, withdrawn))
    return SeedDetail(
        seed=seed,
        generator_version=seed.manifest.generator_version,
        catalog_version=seed.manifest.catalog_version,
        curation_stamp=seed.manifest.curation_stamp,
        ips_size=row["ips_size"],
        creator=load_user(db, seed.creator_id) if seed.creator_id is not None else None,
        holes=tuple(holes),
        entries=[_entry_listing(entry) for entry in entries],
        rounds=[_round_listing(listing) for listing in rounds],
        history=history,
    )


# -- Rounds -------------------------------------------------------------------------------


def rounds_page(
    db: Database, number: int = 1, flagged_only: bool = False
) -> Page[RoundListing]:
    where = "WHERE rounds.flagged" if flagged_only else ""
    with db.transaction() as conn:
        rows = conn.execute(
            f"{_ROUND_SELECT} {where} ORDER BY rounds.received_at DESC, rounds.id DESC LIMIT ? OFFSET ?",
            _limit(number),
        ).fetchall()
    return _page([_round_listing(row) for row in rows], number)


@dataclass(frozen=True)
class HoleScore:
    number: int
    par: int
    strokes: int
    putts: int


@dataclass(frozen=True)
class RoundDetail:
    round: Round
    seed: SeedRow
    player: User
    holes: tuple[HoleScore, ...]
    #: every admin action on the round, across voids and restores, oldest first
    history: list[AdminAction]

    @property
    def flagged_by(self) -> AdminAction | None:
        """The flag that set the round's current flag and note."""
        return _latest(self.history, audit.FLAG) if self.round.flagged else None

    @property
    def total_par(self) -> int:
        return sum(hole.par for hole in self.holes)


def round_detail(db: Database, public_id: str) -> RoundDetail | None:
    """A recorded round's page, or None for a voided or missing one, which the voided list shows."""
    recorded = find_round(db, public_id)
    if not isinstance(recorded, Round):
        return None
    seed = load_seed(db, recorded.seed_id)
    player = load_user(db, recorded.user_id)
    with db.transaction() as conn:
        history = _history(conn, audit.ROUND, public_id)
    if (
        seed is None or player is None
    ):  # pragma: no cover - seeds and users are never deleted
        return None
    holes = tuple(
        HoleScore(hole.position, slot.par, hole.strokes, hole.putts)
        for hole, slot in zip(recorded.holes, seed.manifest.course.holes, strict=True)
    )
    return RoundDetail(
        round=recorded,
        seed=seed,
        player=player,
        holes=holes,
        history=history,
    )


# -- Users --------------------------------------------------------------------------------


@dataclass(frozen=True)
class UserListing:
    user: User
    entries: int
    rounds: int


def users_page(db: Database, number: int = 1) -> Page[UserListing]:
    with db.transaction() as conn:
        rows = conn.execute(
            """
            SELECT users.*,
                   (SELECT count(*) FROM entries WHERE entries.user_id = users.id) AS entry_count,
                   (SELECT count(*) FROM rounds JOIN entries ON entries.id = rounds.entry_id
                    WHERE entries.user_id = users.id) AS round_count
            FROM users ORDER BY users.last_login DESC, users.id DESC LIMIT ? OFFSET ?
            """,
            _limit(number),
        ).fetchall()
    listings = [
        UserListing(
            user=User(
                id=row["id"],
                discord_id=row["discord_id"],
                username=row["username"],
                global_name=row["global_name"],
                avatar=row["avatar"],
                player_id=row["player_id"],
                created_at=row["created_at"],
                last_login=row["last_login"],
            ),
            entries=row["entry_count"],
            rounds=row["round_count"],
        )
        for row in rows
    ]
    return _page(listings, number)


@dataclass(frozen=True)
class UserDetail:
    user: User
    entries: list[EntryListing]
    rounds: list[RoundListing]
    seeds_created: list[SeedListing]
    #: the admin actions the user took, newest first
    actions: list[ActionListing]


def user_detail(db: Database, user_id: int) -> UserDetail | None:
    user = load_user(db, user_id)
    if user is None:
        return None
    with db.transaction() as conn:
        entries = conn.execute(
            f"{_ENTRY_SELECT} WHERE entries.user_id = ? ORDER BY entries.created_at DESC, entries.id DESC",
            (user_id,),
        ).fetchall()
        rounds = conn.execute(
            f"{_ROUND_SELECT} WHERE entries.user_id = ? ORDER BY rounds.received_at DESC, rounds.id DESC",
            (user_id,),
        ).fetchall()
        seeds = conn.execute(
            f"{_SEED_SELECT} WHERE seeds.creator_id = ? ORDER BY seeds.created_at DESC, seeds.rowid DESC",
            (user_id,),
        ).fetchall()
        taken = conn.execute(
            f"{_ACTION_SELECT} WHERE admin_actions.admin_id = ? ORDER BY admin_actions.id DESC",
            (user_id,),
        ).fetchall()
        actions = [
            ActionListing(entry, _resolve(conn, entry)) for entry in map(_action, taken)
        ]
    return UserDetail(
        user=user,
        entries=[_entry_listing(row) for row in entries],
        rounds=[_round_listing(row) for row in rounds],
        seeds_created=[_seed_listing(row) for row in seeds],
        actions=actions,
    )


# -- Voided rounds ------------------------------------------------------------------------


@dataclass(frozen=True)
class VoidedListing:
    public_id: str
    seed_id: str
    magic_words: tuple[str, ...]
    user_id: int
    user_name: str
    slot: int
    total_strokes: int
    total_putts: int
    received_at: str
    flagged: bool
    flag_note: str | None
    voided_at: str
    voided_by_name: str | None
    void_note: str | None
    #: whether the entry's slot holds another round, which refuses a restore
    slot_taken: bool


def voided_page(db: Database, number: int = 1) -> Page[VoidedListing]:
    with db.transaction() as conn:
        rows = conn.execute(
            f"""
            SELECT voided.public_id, entries.seed_id, seeds.manifest, entries.user_id, {_USER_NAME} AS user_name,
                   voided.slot, voided.payload, voided.received_at, voided.flagged, voided.flag_note,
                   voided.voided_at, voided.void_note,
                   EXISTS (SELECT 1 FROM rounds
                           WHERE rounds.entry_id = voided.entry_id AND rounds.slot = voided.slot) AS slot_taken
            FROM voided_rounds AS voided
            JOIN entries ON entries.id = voided.entry_id
            JOIN seeds ON seeds.id = entries.seed_id
            JOIN users ON users.id = entries.user_id
            ORDER BY voided.voided_at DESC, voided.id DESC LIMIT ? OFFSET ?
            """,
            _limit(number),
        ).fetchall()
        voids = {
            row["public_id"]: _latest(
                _history(conn, audit.ROUND, row["public_id"]), audit.VOID
            )
            for row in rows
        }
    listings = []
    for row in rows:
        round_payload, _mac = payload.RoundPayload.from_bytes(bytes(row["payload"]))
        voided_by = voids[row["public_id"]]
        listings.append(
            VoidedListing(
                public_id=row["public_id"],
                seed_id=row["seed_id"],
                magic_words=_magic_words(row["manifest"]),
                user_id=row["user_id"],
                user_name=row["user_name"],
                slot=row["slot"],
                total_strokes=round_payload.total_strokes,
                total_putts=round_payload.total_putts,
                received_at=row["received_at"],
                flagged=bool(row["flagged"]),
                flag_note=row["flag_note"],
                voided_at=row["voided_at"],
                voided_by_name=voided_by.admin_name if voided_by is not None else None,
                void_note=row["void_note"],
                slot_taken=bool(row["slot_taken"]),
            )
        )
    return _page(listings, number)
