"""The database schema as ordered SQL scripts.

Migration 1 is the frozen version 1.0 baseline. A committed migration is never edited:
later schema changes append scripts that advance ``PRAGMA user_version`` by one.
"""

# ``GOLF`` in ASCII. This distinguishes the 1.0 baseline from disposable databases made
# by the pre-release migration chain, including its otherwise-ambiguous user_version 1.
APPLICATION_ID = 0x474F4C46

MIGRATIONS: list[str] = [
    # 1: version 1.0 baseline (docs/randomizer_devplan.md, "Data model")
    f"""
    PRAGMA application_id = {APPLICATION_ID};

    CREATE TABLE users (
        id INTEGER PRIMARY KEY,
        discord_id TEXT NOT NULL UNIQUE,
        username TEXT NOT NULL,
        global_name TEXT,
        avatar TEXT,
        player_id INTEGER NOT NULL UNIQUE CHECK (player_id BETWEEN 1 AND 4294967295),
        created_at TEXT NOT NULL,
        last_login TEXT NOT NULL
    );

    CREATE TABLE seeds (
        id TEXT PRIMARY KEY CHECK (length(id) = 10),
        qr_seed_id INTEGER NOT NULL UNIQUE CHECK (qr_seed_id BETWEEN 1 AND 839299365868340223),
        manifest TEXT NOT NULL,
        generator_version INTEGER NOT NULL,
        catalog_version INTEGER NOT NULL,
        curation_stamp TEXT NOT NULL,
        unfinished_ips BLOB NOT NULL,
        creator_id INTEGER,
        created_at TEXT NOT NULL
    );

    CREATE TABLE seed_holes (
        seed_id TEXT NOT NULL REFERENCES seeds (id),
        position INTEGER NOT NULL CHECK (position BETWEEN 1 AND 18),
        hole_id TEXT NOT NULL,
        transforms TEXT NOT NULL,
        par INTEGER NOT NULL,
        wind_seed INTEGER NOT NULL,
        pin_index INTEGER NOT NULL,
        wind_direction INTEGER NOT NULL,
        wind_speed INTEGER NOT NULL,
        PRIMARY KEY (seed_id, position)
    );

    CREATE TABLE entries (
        id INTEGER PRIMARY KEY,
        seed_id TEXT NOT NULL REFERENCES seeds (id),
        user_id INTEGER NOT NULL REFERENCES users (id),
        player_name TEXT NOT NULL,
        clubs TEXT NOT NULL,
        key_slot0 BLOB NOT NULL CHECK (length(key_slot0) = 8),
        key_slot1 BLOB NOT NULL CHECK (length(key_slot1) = 8),
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        UNIQUE (seed_id, user_id)
    );

    CREATE INDEX entries_by_user ON entries (user_id, created_at);

    CREATE TABLE rounds (
        id INTEGER PRIMARY KEY,
        public_id TEXT NOT NULL UNIQUE CHECK (length(public_id) = 10),
        entry_id INTEGER NOT NULL REFERENCES entries (id),
        slot INTEGER NOT NULL CHECK (slot IN (0, 1)),
        payload BLOB NOT NULL CHECK (length(payload) = 36),
        total_strokes INTEGER NOT NULL,
        total_putts INTEGER NOT NULL,
        received_at TEXT NOT NULL,
        flagged INTEGER NOT NULL DEFAULT 0 CHECK (flagged IN (0, 1)),
        flag_note TEXT,
        UNIQUE (entry_id, slot)
    );

    CREATE TABLE round_holes (
        round_id INTEGER NOT NULL REFERENCES rounds (id),
        position INTEGER NOT NULL CHECK (position BETWEEN 1 AND 18),
        strokes INTEGER NOT NULL,
        putts INTEGER NOT NULL,
        PRIMARY KEY (round_id, position)
    );

    CREATE TABLE voided_rounds (
        id INTEGER PRIMARY KEY,
        public_id TEXT NOT NULL UNIQUE CHECK (length(public_id) = 10),
        entry_id INTEGER NOT NULL REFERENCES entries (id),
        slot INTEGER NOT NULL CHECK (slot IN (0, 1)),
        payload BLOB NOT NULL UNIQUE CHECK (length(payload) = 36),
        received_at TEXT NOT NULL,
        flagged INTEGER NOT NULL CHECK (flagged IN (0, 1)),
        flag_note TEXT,
        voided_at TEXT NOT NULL,
        void_note TEXT
    );

    CREATE INDEX voided_rounds_by_entry ON voided_rounds (entry_id, slot);

    CREATE TABLE admin_actions (
        id INTEGER PRIMARY KEY,
        admin_id INTEGER NOT NULL REFERENCES users (id),
        action TEXT NOT NULL,
        target_type TEXT NOT NULL,
        target_id TEXT NOT NULL,
        note TEXT,
        detail TEXT NOT NULL DEFAULT '{{}}' CHECK (json_valid(detail) AND json_type(detail) = 'object'),
        created_at TEXT NOT NULL
    );

    CREATE INDEX admin_actions_by_target ON admin_actions (target_type, target_id, id);
    CREATE INDEX admin_actions_by_admin ON admin_actions (admin_id, id);
    """,
]
