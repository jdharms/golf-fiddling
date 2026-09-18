"""Submissions: decoding and verifying a scan, and handing the round it carries to `server/rounds.py`.

A scan of a finished ROM's scorecard QR code carries the round's 36-byte payload
(`golf/qr/payload.py`). `submit_scan` resolves it to the entry it belongs to: the seed ID
names the seed, the player ID the user, the pair their entry, and the payload's slot the
MAC key. A payload that verifies is recorded as the round for (entry, slot), and the first
one recorded stays: a later scan for the same entry and slot that also verifies, identical
or not, stores nothing and answers with the round already recorded. A voided round's
payload is refused. Both ROM slots carry the downloader's player ID, so a player 2 round
(slot 1) counts toward the same entry as slot 0. See docs/randomizer_devplan.md, "Data
model", and docs/scorecard_qr.md, "Server contract".

A rejected scan is stored nowhere. It logs its exact cause, which the page never shows.
"""

import logging
from dataclasses import dataclass

from golf.qr import payload

from .db import Database
from .rounds import Round, is_voided, record_round, round_in_slot
from .seeds import MAX_QR_SEED_ID, encode_seed_id, utc_now

log = logging.getLogger(__name__)

#: ScanError reasons, each shown by its own strings key in scan_rejected.html
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


def _rejected(reason: str, cause: str, **details: object) -> ScanError:
    """Log a rejection's exact cause, and the error that shows the player only its reason."""
    fields = "".join(f" {name}={value}" for name, value in details.items())
    log.warning("scan rejected as %s: %s%s", reason, cause, fields)
    return ScanError(reason)


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
        if is_voided(conn, data):
            raise _rejected(UNRECOGNIZED, "voided round", **ids)

        recorded = round_in_slot(conn, entry["id"], slot)
        if recorded is not None:
            return ScanResult(recorded, new=False)
        return ScanResult(record_round(conn, entry["id"], slot, data, received_at), new=True)
