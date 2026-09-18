"""The site's configuration from environment variables."""

from pathlib import Path

import pytest

from golf.randomizer.catalog import DEFAULT_COURSES, REPO_ROOT
from server.config import Config, ConfigError


def test_an_empty_environment_gives_the_defaults():
    config = Config.from_env({})
    assert config == Config()
    assert config.database == "golf_site.db"
    assert config.rom_dir == REPO_ROOT
    assert config.holes_dir == DEFAULT_COURSES
    assert config.rangefinder_dir == REPO_ROOT / "rangefinder"
    assert config.base_url == "http://127.0.0.1:8000"
    assert config.discord_client_id is None
    assert config.dev_login is False


def test_every_variable_overrides_its_field():
    config = Config.from_env(
        {
            "GOLF_DATABASE": "/srv/golf/site.db",
            "GOLF_ROM_DIR": "/srv/golf/roms",
            "GOLF_HOLES_DIR": "/srv/golf/holes",
            "GOLF_RANGEFINDER_DIR": "/srv/golf/rangefinder",
            "GOLF_BASE_URL": "https://golf.example",
            "GOLF_DISCORD_CLIENT_ID": "client",
            "GOLF_DISCORD_CLIENT_SECRET": "secret",
            "GOLF_SESSION_SECRET": "session",
            "GOLF_ADMIN_USERS": "1234, 5678",
            "GOLF_DEV_LOGIN": "1",
        }
    )
    assert config == Config(
        database="/srv/golf/site.db",
        rom_dir=Path("/srv/golf/roms"),
        holes_dir=Path("/srv/golf/holes"),
        rangefinder_dir=Path("/srv/golf/rangefinder"),
        base_url="https://golf.example",
        discord_client_id="client",
        discord_client_secret="secret",
        session_secret="session",
        admin_users=frozenset({"1234", "5678"}),
        dev_login=True,
    )


def test_empty_values_count_as_unset():
    assert Config.from_env({"GOLF_DATABASE": "", "GOLF_ADMIN_USERS": ""}) == Config()


@pytest.mark.parametrize("value", ["1", "true", "TRUE", "yes", "on", " Yes "])
def test_dev_login_true_words(value):
    assert Config.from_env({"GOLF_DEV_LOGIN": value}).dev_login is True


@pytest.mark.parametrize("value", ["0", "false", "no", "off", "enabled"])
def test_dev_login_anything_else_is_off(value):
    assert Config.from_env({"GOLF_DEV_LOGIN": value}).dev_login is False


def test_sign_in_needs_both_discord_credentials_or_the_bypass():
    assert Config().sign_in_enabled is False
    assert Config(discord_client_id="id").sign_in_enabled is False
    assert (
        Config(discord_client_id="id", discord_client_secret="secret").sign_in_enabled
        is True
    )
    assert Config(dev_login=True).sign_in_enabled is True


@pytest.mark.parametrize(
    "base_url", ["http://127.0.0.1:8000", "http://localhost:5000", "http://[::1]:8000"]
)
def test_the_bypass_runs_on_localhost(base_url):
    Config(dev_login=True, base_url=base_url).validate()


@pytest.mark.parametrize(
    "base_url",
    ["https://golf.example", "http://192.168.1.10:8000", "http://localhost.example"],
)
def test_the_bypass_is_refused_anywhere_else(base_url):
    with pytest.raises(ConfigError, match="localhost"):
        Config(dev_login=True, base_url=base_url).validate()


def test_discord_sign_in_needs_a_session_secret():
    with pytest.raises(ConfigError, match="GOLF_SESSION_SECRET"):
        Config(discord_client_id="id", discord_client_secret="secret").validate()
    Config(
        discord_client_id="id", discord_client_secret="secret", session_secret="s"
    ).validate()
    Config().validate()


@pytest.mark.parametrize("value", ["1234 5678", "1234,5678", " 1234 ,\t5678, "])
def test_admin_users_are_separated_by_commas_or_whitespace(value):
    assert Config.from_env({"GOLF_ADMIN_USERS": value}).admin_users == {"1234", "5678"}


def test_only_listed_discord_ids_are_admins():
    config = Config(admin_users=frozenset({"1234"}))
    assert config.is_admin("1234")
    assert not config.is_admin("5678")
    assert not Config().is_admin("1234")


def test_development_admins_need_the_bypass():
    with pytest.raises(ConfigError, match="dev:alice"):
        Config(admin_users=frozenset({"1234", "dev:alice"})).validate()
    Config(admin_users=frozenset({"dev:alice"}), dev_login=True).validate()
