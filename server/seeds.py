"""Seed identity and the seed tables: the only code that writes `seeds` and `seed_holes`.

A seed's `qr_seed_id` is drawn uniformly from 1 to 62**10 - 1, and its URL id is that
integer in base62 (`server/ids.py`), so either converts to the other. See
docs/randomizer_devplan.md, "Generating seed ids".
"""

import json
import secrets
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime

from golf.core.patches.seeded_wind import predict_hole
from golf.randomizer.manifest import Manifest

from . import audit
from .db import Database
from .ids import ALPHABET, ID_LENGTH, MAX_VALUE, decode_base62, encode_base62, is_id

__all__ = ["ALPHABET", "ID_LENGTH"]  # re-exported: a seed id is a base62 id

#: the largest qr_seed_id, and the bound migration 1's CHECK holds the column to
MAX_QR_SEED_ID = MAX_VALUE
#: draws before an insert gives up on finding an unused id
INSERT_ATTEMPTS = 10


class SeedIdError(ValueError):
    """Text that is not a seed's URL id, or an integer outside the qr_seed_id range."""


class SeedIdExhaustedError(RuntimeError):
    """Every draw collided with an existing seed, which only a broken generator makes likely."""


def encode_seed_id(value: int) -> str:
    """A qr_seed_id as its 10-character base62 URL id."""
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or not 1 <= value <= MAX_QR_SEED_ID
    ):
        raise SeedIdError(f"a qr_seed_id is 1-{MAX_QR_SEED_ID}, got {value!r}")
    return encode_base62(value)


def decode_seed_id(text: str) -> int:
    """A URL id as its qr_seed_id. Raises SeedIdError for anything else."""
    if not is_id(text):
        raise SeedIdError(
            f"a seed id is {ID_LENGTH} characters of 0-9, A-Z and a-z, got {text!r}"
        )
    value = decode_base62(text)
    if value == 0:
        raise SeedIdError("no seed has the id 0000000000")
    return value


def new_qr_seed_id() -> int:
    return secrets.randbelow(MAX_QR_SEED_ID) + 1


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def manifest_text(manifest: Manifest) -> str:
    """The manifest as stored on the seed row, and as `/h/<id>.json` serves it."""
    return json.dumps(manifest.to_json(), indent=2) + "\n"


def hole_rows(seed_id: str, manifest: Manifest) -> list[tuple]:
    """The seed's `seed_holes` rows: each slot with the pin and wind anchors its wind seed gives."""
    rows = []
    for position, slot in enumerate(manifest.course.holes, start=1):
        forecast = predict_hole(slot.wind_seed, swings=0)
        rows.append(
            (
                seed_id,
                position,
                str(slot.id),
                json.dumps(list(slot.transforms)),
                slot.par,
                slot.wind_seed,
                forecast.pin_index,
                forecast.direction_anchor,
                forecast.speed_anchor,
            )
        )
    return rows


def _is_id_collision(problem: sqlite3.IntegrityError) -> bool:
    message = str(problem)
    return "UNIQUE" in message and (
        "seeds.id" in message or "seeds.qr_seed_id" in message
    )


def insert_seed(
    db: Database,
    manifest: Manifest,
    unfinished_ips: bytes,
    creator_id: int | None = None,
    now: str | None = None,
    draw: Callable[[], int] = new_qr_seed_id,
) -> str:
    """Store a seed and its holes in one transaction, and return its URL id.

    A drawn id that is already taken is drawn again, up to INSERT_ATTEMPTS times.
    """
    created_at = now if now is not None else utc_now()
    text = manifest_text(manifest)
    for _ in range(INSERT_ATTEMPTS):
        qr_seed_id = draw()
        seed_id = encode_seed_id(qr_seed_id)
        try:
            with db.transaction() as conn:
                conn.execute(
                    """
                    INSERT INTO seeds (id, qr_seed_id, manifest, generator_version, catalog_version,
                                       curation_stamp, unfinished_ips, creator_id, created_at)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        seed_id,
                        qr_seed_id,
                        text,
                        manifest.generator_version,
                        manifest.catalog_version,
                        manifest.curation_stamp,
                        unfinished_ips,
                        creator_id,
                        created_at,
                    ),
                )
                conn.executemany(
                    "INSERT INTO seed_holes VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    hole_rows(seed_id, manifest),
                )
        except sqlite3.IntegrityError as problem:
            if _is_id_collision(problem):
                continue
            raise
        return seed_id
    raise SeedIdExhaustedError(f"no unused seed id in {INSERT_ATTEMPTS} draws")


@dataclass(frozen=True)
class SeedRow:
    id: str
    qr_seed_id: int
    #: the manifest exactly as stored
    manifest_json: str
    manifest: Manifest
    creator_id: int | None
    created_at: str
    #: when an admin's rebuild last changed the stored unfinished IPS, or None
    rebuilt_at: str | None = None


def load_seed(db: Database, seed_id: str) -> SeedRow | None:
    """The seed with this URL id, or None when there is none or the text is not a seed id."""
    try:
        decode_seed_id(seed_id)
    except SeedIdError:
        return None
    with db.transaction() as conn:
        row = conn.execute(
            "SELECT id, qr_seed_id, manifest, creator_id, created_at, rebuilt_at FROM seeds WHERE id = ?",
            (seed_id,),
        ).fetchone()
    if row is None:
        return None
    return SeedRow(
        id=row["id"],
        qr_seed_id=row["qr_seed_id"],
        manifest_json=row["manifest"],
        manifest=Manifest.from_json(json.loads(row["manifest"])),
        creator_id=row["creator_id"],
        created_at=row["created_at"],
        rebuilt_at=row["rebuilt_at"],
    )


def load_unfinished_ips(db: Database, seed_id: str) -> bytes | None:
    """The seed's stored unfinished IPS, or None when there is no such seed.

    A query of its own, so pages that only show a seed never read the blob.
    """
    try:
        decode_seed_id(seed_id)
    except SeedIdError:
        return None
    with db.transaction() as conn:
        row = conn.execute(
            "SELECT unfinished_ips FROM seeds WHERE id = ?", (seed_id,)
        ).fetchone()
    return None if row is None else bytes(row["unfinished_ips"])


def rebuild_seed(
    db: Database,
    seed_id: str,
    unfinished_ips: bytes,
    admin_id: int,
    now: str | None = None,
) -> bool:
    """Store a rebuilt unfinished IPS, log the rebuild, and return whether the IPS changed.

    Only a changed IPS is written and stamps `rebuilt_at`, so the seed page never announces a
    rebuild that changed nothing; the audit log records both. Raises KeyError for a missing seed.
    """
    rebuilt_at = now if now is not None else utc_now()
    with db.transaction() as conn:
        row = conn.execute(
            "SELECT unfinished_ips FROM seeds WHERE id = ?", (seed_id,)
        ).fetchone()
        if row is None:
            raise KeyError(seed_id)
        changed = bytes(row["unfinished_ips"]) != unfinished_ips
        if changed:
            conn.execute(
                "UPDATE seeds SET unfinished_ips = ?, rebuilt_at = ? WHERE id = ?",
                (unfinished_ips, rebuilt_at, seed_id),
            )
        audit.record(
            conn,
            admin_id,
            audit.REBUILD,
            audit.SEED,
            seed_id,
            rebuilt_at,
            detail={"changed": changed},
        )
    return changed
