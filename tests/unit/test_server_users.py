"""Site users: sign-in records a user once, refreshes them after, and draws player ids."""

import itertools

import pytest

from server.db import Database
from server.users import (
    MAX_PLAYER_ID,
    PlayerIdExhaustedError,
    User,
    load_user,
    new_player_id,
    sign_in,
)


@pytest.fixture
def db():
    database = Database(":memory:")
    database.migrate()
    yield database
    database.close()


def draws(*values):
    iterator = iter(values)
    return lambda: next(iterator)


def test_a_first_sign_in_inserts_the_user(db):
    user = sign_in(db, "80351110224678912", "nelly", "Nelly", "abc123", now="2026-09-16T00:00:00Z", draw=draws(77))
    assert user == User(
        id=user.id,
        discord_id="80351110224678912",
        username="nelly",
        global_name="Nelly",
        avatar="abc123",
        player_id=77,
        created_at="2026-09-16T00:00:00Z",
        last_login="2026-09-16T00:00:00Z",
    )
    assert load_user(db, user.id) == user


def test_a_later_sign_in_refreshes_names_and_last_login_only(db):
    first = sign_in(db, "1", "nelly", "Nelly", None, now="2026-09-16T00:00:00Z", draw=draws(77))
    again = sign_in(db, "1", "nelly2", None, "def456", now="2026-09-17T00:00:00Z", draw=draws(99))
    assert again == User(first.id, "1", "nelly2", None, "def456", 77, "2026-09-16T00:00:00Z", "2026-09-17T00:00:00Z")
    assert load_user(db, first.id) == again


def test_each_account_gets_its_own_user(db):
    first = sign_in(db, "1", "a", None, None, draw=draws(5))
    second = sign_in(db, "2", "b", None, None, draw=draws(6))
    assert first.id != second.id


def test_a_player_id_collision_draws_again(db):
    sign_in(db, "1", "a", None, None, draw=draws(5))
    second = sign_in(db, "2", "b", None, None, draw=draws(5, 5, 6))
    assert second.player_id == 6
    assert load_user(db, second.id) == second


def test_a_generator_that_only_collides_gives_up(db):
    sign_in(db, "1", "a", None, None, draw=draws(5))
    with pytest.raises(PlayerIdExhaustedError):
        sign_in(db, "2", "b", None, None, draw=lambda: 5)
    with db.transaction() as conn:
        assert conn.execute("SELECT count(*) FROM users").fetchone()[0] == 1


def test_new_player_ids_are_never_zero(monkeypatch):
    values = itertools.chain([0, 0], itertools.repeat(MAX_PLAYER_ID))
    monkeypatch.setattr("server.users.secrets.randbits", lambda bits: next(values))
    assert new_player_id() == MAX_PLAYER_ID


def test_new_player_ids_fit_the_column():
    assert all(1 <= new_player_id() <= MAX_PLAYER_ID for _ in range(1000))


def test_the_display_name_falls_back_to_the_username():
    user = User(1, "1", "nelly", "Nelly", None, 5, "t", "t")
    assert user.display_name == "Nelly"
    assert User(1, "1", "nelly", None, None, 5, "t", "t").display_name == "nelly"


def test_an_unknown_user_is_none(db):
    assert load_user(db, 12345) is None
