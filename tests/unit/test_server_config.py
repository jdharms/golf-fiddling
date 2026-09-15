"""The site's configuration from environment variables."""

from pathlib import Path

import pytest

from golf.randomizer.catalog import DEFAULT_COURSES, REPO_ROOT
from server.config import Config


def test_an_empty_environment_gives_the_defaults():
    config = Config.from_env({})
    assert config == Config()
    assert config.database == "golf_site.db"
    assert config.rom_dir == REPO_ROOT
    assert config.holes_dir == DEFAULT_COURSES
    assert config.base_url == "http://127.0.0.1:8000"
    assert config.discord_client_id is None
    assert config.dev_login is False


def test_every_variable_overrides_its_field():
    config = Config.from_env(
        {
            "GOLF_DATABASE": "/srv/golf/site.db",
            "GOLF_ROM_DIR": "/srv/golf/roms",
            "GOLF_HOLES_DIR": "/srv/golf/holes",
            "GOLF_BASE_URL": "https://golf.example",
            "GOLF_DISCORD_CLIENT_ID": "client",
            "GOLF_DISCORD_CLIENT_SECRET": "secret",
            "GOLF_SESSION_SECRET": "session",
            "GOLF_ADMIN_TOKEN": "admin",
            "GOLF_DEV_LOGIN": "1",
        }
    )
    assert config == Config(
        database="/srv/golf/site.db",
        rom_dir=Path("/srv/golf/roms"),
        holes_dir=Path("/srv/golf/holes"),
        base_url="https://golf.example",
        discord_client_id="client",
        discord_client_secret="secret",
        session_secret="session",
        admin_token="admin",
        dev_login=True,
    )


def test_empty_values_count_as_unset():
    assert Config.from_env({"GOLF_DATABASE": "", "GOLF_ADMIN_TOKEN": ""}) == Config()


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on", " Yes "])
def test_dev_login_true_words(value):
    assert Config.from_env({"GOLF_DEV_LOGIN": value}).dev_login is True


@pytest.mark.parametrize("value", ["0", "false", "no", "off", "enabled"])
def test_dev_login_anything_else_is_off(value):
    assert Config.from_env({"GOLF_DEV_LOGIN": value}).dev_login is False
