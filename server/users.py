"""Site users: the only code that writes `users`.

A user is a Discord account, or a `dev:<name>` account from the development login bypass.
Each gets a random nonzero uint32 `player_id` on first sign-in, which scorecard QR
submissions carry and which never changes. See docs/randomizer_devplan.md, "Data model"
and "Generating player_id".
"""

import secrets
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass

from .db import Database
from .seeds import utc_now

#: draws before a first sign-in gives up on finding an unused player_id
INSERT_ATTEMPTS = 10
#: the largest player_id, and the version 1.0 baseline's CHECK holds the column to
MAX_PLAYER_ID = 2**32 - 1

COLUMNS = (
    "id, discord_id, username, global_name, avatar, player_id, created_at, last_login"
)


class PlayerIdExhaustedError(RuntimeError):
    """Every draw collided with an existing user, which only a broken generator makes likely."""


@dataclass(frozen=True)
class User:
    id: int
    discord_id: str
    #: the Discord handle
    username: str
    #: the Discord display name, which an account may not have
    global_name: str | None
    #: the Discord avatar hash
    avatar: str | None
    player_id: int
    created_at: str
    last_login: str

    @property
    def display_name(self) -> str:
        return self.global_name or self.username


def new_player_id() -> int:
    while True:
        value = secrets.randbits(32)
        if value != 0:
            return value


def _user(row: sqlite3.Row) -> User:
    return User(**{name: row[name] for name in row.keys()})  # noqa: SIM118 (sqlite3.Row, not a dict)


def _is_player_id_collision(problem: sqlite3.IntegrityError) -> bool:
    message = str(problem)
    return "UNIQUE" in message and "users.player_id" in message


def sign_in(
    db: Database,
    discord_id: str,
    username: str,
    global_name: str | None,
    avatar: str | None,
    now: str | None = None,
    draw: Callable[[], int] = new_player_id,
) -> User:
    """Record a sign-in and return the user.

    An existing user gets their names, avatar and last_login refreshed; a new one is
    inserted with a drawn player_id, drawn again on a collision up to INSERT_ATTEMPTS times.
    """
    signed_in_at = now if now is not None else utc_now()
    for _ in range(INSERT_ATTEMPTS):
        try:
            with db.transaction() as conn:
                rows = conn.execute(
                    """
                    UPDATE users SET username = ?, global_name = ?, avatar = ?, last_login = ?
                    WHERE discord_id = ?
                    RETURNING """
                    + COLUMNS,
                    (username, global_name, avatar, signed_in_at, discord_id),
                ).fetchall()
                if not rows:
                    rows = conn.execute(
                        """
                        INSERT INTO users (discord_id, username, global_name, avatar, player_id,
                                           created_at, last_login)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                        RETURNING """
                        + COLUMNS,
                        (
                            discord_id,
                            username,
                            global_name,
                            avatar,
                            draw(),
                            signed_in_at,
                            signed_in_at,
                        ),
                    ).fetchall()
        except sqlite3.IntegrityError as problem:
            if _is_player_id_collision(problem):
                continue
            raise
        # RETURNING rows are read in full inside the transaction, or COMMIT finds the statement open
        return _user(rows[0])
    raise PlayerIdExhaustedError(f"no unused player_id in {INSERT_ATTEMPTS} draws")


def load_user(db: Database, user_id: int) -> User | None:
    with db.transaction() as conn:
        row = conn.execute(
            f"SELECT {COLUMNS} FROM users WHERE id = ?", (user_id,)
        ).fetchone()
    return None if row is None else _user(row)
