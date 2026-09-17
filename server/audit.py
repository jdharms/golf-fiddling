"""The admin audit log: the only code that writes `admin_actions`.

Every admin action records one row: who, what, to which seed or round, when, the admin's
note and a small JSON detail. The modules that own the tables an action changes call
`record` with their own connection, inside the transaction that makes the change, so the
log and the change commit together or not at all. The admin pages read the log for "who did
this" and a target's history (`server/admin.py`). See docs/randomizer_devplan.md, "Data model".

A new admin action adds its name below and records a row; the table needs no migration.
"""

import json
import sqlite3

from golf.qr import payload

#: actions
REBUILD = "rebuild"
FLAG = "flag"
UNFLAG = "unflag"
VOID = "void"
RESTORE = "restore"

#: target types, and what target_id holds for each
#: a seed's URL id
SEED = "seed"
#: a round's payload as base64url, the text of its `/s/` URL (`round_target`). Not its
#: `submissions.id`, which changes when a round is voided and restored and can be reused by a
#: later round; the payload names one round for good, recorded or voided.
ROUND = "round"


def round_target(data: bytes) -> str:
    """The target_id naming the round with this 36-byte payload."""
    return payload.base64url_encode(bytes(data))


def record(
    conn: sqlite3.Connection,
    admin_id: int,
    action: str,
    target_type: str,
    target_id: str | int,
    created_at: str,
    note: str | None = None,
    detail: dict | None = None,
) -> int:
    """Log an admin action on the caller's connection, inside its transaction. Returns the row id.

    `detail` is what the action needs remembered beyond its target, such as whether a rebuild
    changed anything.
    """
    row_id = conn.execute(
        """
        INSERT INTO admin_actions (admin_id, action, target_type, target_id, note, detail, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (admin_id, action, target_type, str(target_id), note, json.dumps(detail or {}, sort_keys=True), created_at),
    ).lastrowid
    assert row_id is not None
    return row_id
