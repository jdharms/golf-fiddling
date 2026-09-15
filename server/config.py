"""Site configuration, read from `GOLF_`-prefixed environment variables.

Every setting the devplan names is declared here, including those later items read, so
their names are fixed from the start. See docs/randomizer_devplan.md.
"""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from golf.randomizer.catalog import DEFAULT_COURSES, REPO_ROOT

PREFIX = "GOLF_"
TRUE_WORDS = frozenset({"1", "true", "yes", "on"})


@dataclass(frozen=True)
class Config:
    #: SQLite database path, or ":memory:"
    database: str = "golf_site.db"
    #: the directory holding the server's vanilla ROMs
    rom_dir: Path = REPO_ROOT
    #: the hole store root the catalog's ids resolve in
    holes_dir: Path = DEFAULT_COURSES
    #: the public base URL, also the OAuth redirect base
    base_url: str = "http://127.0.0.1:8000"
    discord_client_id: str | None = None
    discord_client_secret: str | None = None
    session_secret: str | None = None
    admin_token: str | None = None
    #: the development-only login bypass
    dev_login: bool = False

    @classmethod
    def from_env(cls, environ: Mapping[str, str] = os.environ) -> "Config":
        def get(name: str) -> str | None:
            value = environ.get(PREFIX + name.upper())
            return value if value else None

        defaults = cls()
        return cls(
            database=get("database") or defaults.database,
            rom_dir=Path(get("rom_dir")) if get("rom_dir") else defaults.rom_dir,
            holes_dir=Path(get("holes_dir")) if get("holes_dir") else defaults.holes_dir,
            base_url=get("base_url") or defaults.base_url,
            discord_client_id=get("discord_client_id"),
            discord_client_secret=get("discord_client_secret"),
            session_secret=get("session_secret"),
            admin_token=get("admin_token"),
            dev_login=(get("dev_login") or "").strip().lower() in TRUE_WORDS,
        )
