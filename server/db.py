"""The site's SQLite database: one connection, one lock, explicit transactions.

One uvicorn worker serves the site, so a single connection shared under a lock is enough,
and it lets tests run on ":memory:". The connection is in autocommit mode and every write
goes through `transaction()`, so a migration script and its version bump commit together
or not at all.
"""

import sqlite3
import threading
from collections.abc import Iterator, Sequence
from contextlib import contextmanager

from .migrations import MIGRATIONS

MEMORY = ":memory:"


class DatabaseError(Exception):
    """A database this code cannot use, such as one migrated by a newer version."""


class Database:
    def __init__(self, path: str):
        self.path = path
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(path, check_same_thread=False, autocommit=True)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA foreign_keys = ON")
        if path != MEMORY:
            self._conn.execute("PRAGMA journal_mode = WAL")

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """Hold the lock and a write transaction; commit on success, roll back on error."""
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                yield self._conn
            except BaseException:
                self._conn.execute("ROLLBACK")
                raise
            self._conn.execute("COMMIT")

    def version(self) -> int:
        with self._lock:
            return self._conn.execute("PRAGMA user_version").fetchone()[0]

    def migrate(self, migrations: Sequence[str] = MIGRATIONS) -> int:
        """Apply every script past the database's version, each atomically. Returns the version."""
        with self._lock:
            current = self.version()
            if current > len(migrations):
                raise DatabaseError(
                    f"the database is at schema version {current}, newer than this code's {len(migrations)}"
                )
            for number, script in enumerate(migrations[current:], start=current + 1):
                try:
                    # executescript runs statements as given, so BEGIN and COMMIT wrap the
                    # script and its version bump in one transaction
                    self._conn.executescript(
                        f"BEGIN IMMEDIATE;\n{script}\n;PRAGMA user_version = {number};\nCOMMIT;"
                    )
                except BaseException:
                    if self._conn.in_transaction:
                        self._conn.execute("ROLLBACK")
                    raise
            return self.version()
