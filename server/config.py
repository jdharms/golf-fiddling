"""Site configuration, read from `GOLF_`-prefixed environment variables.

Every setting the devplan names is declared here, including those later items read, so
their names are fixed from the start. See docs/randomizer_devplan.md.
"""

import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

from golf.randomizer.catalog import DEFAULT_COURSES, REPO_ROOT

PREFIX = "GOLF_"
TRUE_WORDS = frozenset({"1", "true", "yes", "on"})
#: the only hosts the development login bypass may run on
LOCAL_HOSTS = frozenset({"127.0.0.1", "localhost", "::1"})


class ConfigError(ValueError):
    """Settings the site refuses to start with."""


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
    #: the Discord ids (`dev:<name>` under the bypass) of the users the admin pages admit
    admin_users: frozenset[str] = frozenset()
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
            holes_dir=Path(get("holes_dir"))
            if get("holes_dir")
            else defaults.holes_dir,
            base_url=get("base_url") or defaults.base_url,
            discord_client_id=get("discord_client_id"),
            discord_client_secret=get("discord_client_secret"),
            session_secret=get("session_secret"),
            admin_users=frozenset((get("admin_users") or "").replace(",", " ").split()),
            dev_login=(get("dev_login") or "").strip().lower() in TRUE_WORDS,
        )

    @property
    def discord_enabled(self) -> bool:
        return bool(self.discord_client_id and self.discord_client_secret)

    @property
    def sign_in_enabled(self) -> bool:
        """Discord sign-in is configured, or the development bypass stands in for it."""
        return self.dev_login or self.discord_enabled

    def is_admin(self, discord_id: str) -> bool:
        return discord_id in self.admin_users

    def validate(self) -> None:
        """Refuse settings that would be unsafe to serve. Raises ConfigError."""
        if self.dev_login and urlsplit(self.base_url).hostname not in LOCAL_HOSTS:
            raise ConfigError(
                f"the development login bypass only runs on localhost, not {self.base_url}"
            )
        if self.discord_enabled and not self.session_secret:
            raise ConfigError(
                "Discord sign-in needs a session secret (GOLF_SESSION_SECRET)"
            )
        dev_admins = sorted(
            user for user in self.admin_users if user.startswith("dev:")
        )
        if dev_admins and not self.dev_login:
            raise ConfigError(
                f"development users can only be admins with the login bypass on: {dev_admins}"
            )
