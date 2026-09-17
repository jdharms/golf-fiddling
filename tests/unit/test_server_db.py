"""The site database: migrations and the seed tables' constraints."""

import sqlite3

import pytest

from server.db import Database, DatabaseError
from server.migrations import MIGRATIONS


@pytest.fixture
def db():
    database = Database(":memory:")
    yield database
    database.close()


def tables(db: Database) -> set[str]:
    with db.transaction() as conn:
        return {row["name"] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}


def seed_row(**overrides):
    row = {
        "id": "0000000001",
        "qr_seed_id": 1,
        "manifest": "{}",
        "generator_version": 1,
        "catalog_version": 1,
        "curation_stamp": "stamp",
        "unfinished_ips": b"PATCHEOF",
        "creator_id": None,
        "created_at": "2026-09-15T00:00:00Z",
    }
    row.update(overrides)
    return row


def insert_seed(db: Database, **overrides) -> None:
    row = seed_row(**overrides)
    columns = ", ".join(row)
    marks = ", ".join(f":{name}" for name in row)
    with db.transaction() as conn:
        conn.execute(f"INSERT INTO seeds ({columns}) VALUES ({marks})", row)


def test_a_fresh_database_migrates_to_the_latest_version(db):
    assert db.version() == 0
    assert db.migrate() == len(MIGRATIONS)
    assert db.version() == len(MIGRATIONS)
    assert {"seeds", "seed_holes", "users"} <= tables(db)


def test_migrating_again_changes_nothing(db):
    db.migrate()
    before = tables(db)
    assert db.migrate() == len(MIGRATIONS)
    assert tables(db) == before


def test_a_failing_script_leaves_the_version_and_schema_as_they_were(db):
    migrations = [
        "CREATE TABLE first (x INTEGER);",
        "CREATE TABLE second (x INTEGER); CREATE TABLE broken (;",
    ]
    with pytest.raises(sqlite3.OperationalError):
        db.migrate(migrations)
    assert db.version() == 1
    assert tables(db) == {"first"}


def test_a_database_newer_than_the_code_is_refused(db):
    db.migrate(["CREATE TABLE a (x);", "CREATE TABLE b (x);"])
    with pytest.raises(DatabaseError, match="newer"):
        db.migrate(["CREATE TABLE a (x);"])


def test_a_transaction_rolls_back_on_error(db):
    db.migrate()
    with pytest.raises(RuntimeError), db.transaction() as conn:
        conn.execute("INSERT INTO seeds (id, qr_seed_id, manifest, generator_version, catalog_version, curation_stamp, unfinished_ips, created_at) VALUES ('0000000001', 1, '{}', 1, 1, 's', x'00', 'now')")
        raise RuntimeError("abandon")
    with db.transaction() as conn:
        assert conn.execute("SELECT count(*) FROM seeds").fetchone()[0] == 0


def test_a_valid_seed_inserts(db):
    db.migrate()
    insert_seed(db)
    insert_seed(db, id="zzzzzzzzzz", qr_seed_id=839299365868340223)


@pytest.mark.parametrize(
    "overrides",
    [
        {"qr_seed_id": 0},
        {"qr_seed_id": 839299365868340224},
        {"id": "short"},
        {"id": "elevenchars"},
    ],
)
def test_seed_constraints(db, overrides):
    db.migrate()
    with pytest.raises(sqlite3.IntegrityError):
        insert_seed(db, **overrides)


def test_seed_ids_are_unique(db):
    db.migrate()
    insert_seed(db)
    with pytest.raises(sqlite3.IntegrityError):
        insert_seed(db, id="0000000002")


def test_seed_holes_need_their_seed(db):
    db.migrate()
    with pytest.raises(sqlite3.IntegrityError), db.transaction() as conn:
        conn.execute(
            "INSERT INTO seed_holes VALUES ('0000000001', 1, 'nes_us/01', '[]', 4, 1, 0, 0, 0)"
        )


def test_seed_hole_positions_run_1_to_18(db):
    db.migrate()
    insert_seed(db)
    with db.transaction() as conn:
        conn.execute("INSERT INTO seed_holes VALUES ('0000000001', 18, 'nes_us/18', '[]', 4, 1, 0, 0, 0)")
    with pytest.raises(sqlite3.IntegrityError), db.transaction() as conn:
        conn.execute("INSERT INTO seed_holes VALUES ('0000000001', 19, 'nes_us/01', '[]', 4, 1, 0, 0, 0)")


def test_a_file_database_uses_wal(tmp_path):
    database = Database(str(tmp_path / "site.db"))
    try:
        database.migrate()
        with database.transaction() as conn:
            pass
        assert conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    finally:
        database.close()
    reopened = Database(str(tmp_path / "site.db"))
    try:
        assert reopened.version() == len(MIGRATIONS)
    finally:
        reopened.close()


def user_row(**overrides):
    row = {
        "discord_id": "80351110224678912",
        "username": "nelly",
        "global_name": "Nelly",
        "avatar": None,
        "player_id": 1,
        "created_at": "2026-09-16T00:00:00Z",
        "last_login": "2026-09-16T00:00:00Z",
    }
    row.update(overrides)
    return row


def insert_user(db: Database, **overrides) -> None:
    row = user_row(**overrides)
    columns = ", ".join(row)
    marks = ", ".join(f":{name}" for name in row)
    with db.transaction() as conn:
        conn.execute(f"INSERT INTO users ({columns}) VALUES ({marks})", row)


def test_a_valid_user_inserts(db):
    db.migrate()
    insert_user(db)
    insert_user(db, discord_id="dev:alice", global_name=None, player_id=4294967295)


@pytest.mark.parametrize(
    "overrides",
    [
        {"player_id": 0},
        {"player_id": 4294967296},
        {"player_id": None},
        {"username": None},
        {"discord_id": None},
    ],
)
def test_user_constraints(db, overrides):
    db.migrate()
    with pytest.raises(sqlite3.IntegrityError):
        insert_user(db, **overrides)


def test_discord_ids_are_unique(db):
    db.migrate()
    insert_user(db)
    with pytest.raises(sqlite3.IntegrityError):
        insert_user(db, player_id=2)


def test_player_ids_are_unique(db):
    db.migrate()
    insert_user(db)
    with pytest.raises(sqlite3.IntegrityError):
        insert_user(db, discord_id="dev:other")


# -- entries ------------------------------------------------------------------------------


def entry_row(**overrides):
    row = {
        "seed_id": "0000000001",
        "user_id": 1,
        "player_name": "LUIGI",
        "clubs": "1W PW PT",
        "key_slot0": bytes(8),
        "key_slot1": bytes([1] * 8),
        "created_at": "2026-09-16T00:00:00Z",
        "updated_at": "2026-09-16T00:00:00Z",
    }
    row.update(overrides)
    return row


def insert_entry(db: Database, **overrides) -> None:
    row = entry_row(**overrides)
    columns = ", ".join(row)
    marks = ", ".join(f":{name}" for name in row)
    with db.transaction() as conn:
        conn.execute(f"INSERT INTO entries ({columns}) VALUES ({marks})", row)


@pytest.fixture
def entrant_db(db):
    db.migrate()
    insert_seed(db)
    insert_user(db)
    return db


def test_a_valid_entry_inserts(entrant_db):
    insert_entry(entrant_db)
    assert "entries" in tables(entrant_db)


@pytest.mark.parametrize(
    "overrides",
    [
        {"key_slot0": bytes(7)},
        {"key_slot1": bytes(9)},
        {"key_slot0": None},
        {"player_name": None},
        {"clubs": None},
        {"seed_id": "0000000002"},
        {"user_id": 2},
    ],
)
def test_entry_constraints(entrant_db, overrides):
    with pytest.raises(sqlite3.IntegrityError):
        insert_entry(entrant_db, **overrides)


def test_one_entry_per_seed_and_user(entrant_db):
    insert_entry(entrant_db)
    with pytest.raises(sqlite3.IntegrityError):
        insert_entry(entrant_db, player_name="TOAD")


# -- submissions --------------------------------------------------------------------------


def submission_row(**overrides):
    row = {
        "entry_id": 1,
        "slot": 0,
        "payload": bytes(36),
        "total_strokes": 72,
        "total_putts": 36,
        "received_at": "2026-09-17T00:00:00Z",
    }
    row.update(overrides)
    return row


def insert_submission(db: Database, **overrides) -> None:
    row = submission_row(**overrides)
    columns = ", ".join(row)
    marks = ", ".join(f":{name}" for name in row)
    with db.transaction() as conn:
        conn.execute(f"INSERT INTO submissions ({columns}) VALUES ({marks})", row)


def insert_submission_hole(db: Database, **overrides) -> None:
    row = {"submission_id": 1, "position": 1, "strokes": 4, "putts": 2, **overrides}
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO submission_holes (submission_id, position, strokes, putts) "
            "VALUES (:submission_id, :position, :strokes, :putts)",
            row,
        )


@pytest.fixture
def submitter_db(entrant_db):
    insert_entry(entrant_db)
    return entrant_db


def test_a_valid_submission_and_its_holes_insert_unflagged(submitter_db):
    insert_submission(submitter_db)
    insert_submission_hole(submitter_db)
    with submitter_db.transaction() as conn:
        assert conn.execute("SELECT flagged FROM submissions").fetchone()[0] == 0
    assert {"submissions", "submission_holes"} <= tables(submitter_db)


@pytest.mark.parametrize(
    "overrides",
    [
        {"slot": 2},
        {"slot": -1},
        {"payload": bytes(35)},
        {"payload": None},
        {"total_strokes": None},
        {"received_at": None},
        {"entry_id": 2},
        {"flagged": 2},
    ],
)
def test_submission_constraints(submitter_db, overrides):
    with pytest.raises(sqlite3.IntegrityError):
        insert_submission(submitter_db, **overrides)


def test_one_submission_per_entry_and_slot(submitter_db):
    insert_submission(submitter_db)
    insert_submission(submitter_db, slot=1)
    with pytest.raises(sqlite3.IntegrityError):
        insert_submission(submitter_db, total_strokes=70)


@pytest.mark.parametrize("overrides", [{"position": 0}, {"position": 19}, {"submission_id": 2}, {"strokes": None}])
def test_submission_hole_constraints(submitter_db, overrides):
    insert_submission(submitter_db)
    with pytest.raises(sqlite3.IntegrityError):
        insert_submission_hole(submitter_db, **overrides)


def test_one_row_per_submission_hole(submitter_db):
    insert_submission(submitter_db)
    insert_submission_hole(submitter_db)
    with pytest.raises(sqlite3.IntegrityError):
        insert_submission_hole(submitter_db, strokes=5)
