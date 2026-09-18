"""The admin pages: who they admit, what they list, and flag, void and restore actions."""

import re

import pytest
from fastapi.testclient import TestClient

from golf.randomizer.catalog import Catalog, HoleStore
from golf.randomizer.curation import CurationSnapshot
from server.app import create_app
from server.config import Config
from tests.unit.test_server_app import (
    IPS,
    UNWRITTEN,
    FakeBuilder,
    entered_seed,
    scan_path,
)

ROUND_LINK = re.compile(r'href="/admin/rounds/([0-9A-Za-z]{10})"')

#: every admin page that needs no id
LISTS = (
    "/admin",
    "/admin/seeds",
    "/admin/rounds",
    "/admin/rounds?flagged=true",
    "/admin/users",
    "/admin/voided",
    "/admin/activity",
)


@pytest.fixture
def fake_builder(tmp_path):
    return FakeBuilder(
        Catalog.load(), CurationSnapshot.load(), HoleStore(), tmp_path / "unused.nes"
    )


def admin_client(builder, admins=("dev:admin",), **kwargs) -> TestClient:
    config = Config(database=":memory:", dev_login=True, admin_users=frozenset(admins))
    return TestClient(create_app(config, builder=builder, **kwargs))


def sign_in(client: TestClient, name: str) -> None:
    client.get("/auth/login", params={"as": name})


def post(client: TestClient, path: str, **data):
    return client.post(path, data=data, follow_redirects=False)


def played_seed(client: TestClient) -> tuple[str, str]:
    """A seed alice entered and recorded a round of 5s on, and that round's public id; signed in as admin."""
    seed_id = entered_seed(client, "alice")
    assert client.get(scan_path(client, seed_id, "alice", strokes=5)).status_code == 200
    sign_in(client, "admin")
    [round_id] = ROUND_LINK.findall(client.get("/admin/rounds").text)
    return seed_id, round_id


# -- Access -------------------------------------------------------------------------------


@pytest.mark.parametrize("who", [None, "alice"])
def test_admin_pages_are_not_found_for_anyone_else(fake_builder, who):
    with admin_client(fake_builder, strings=UNWRITTEN) as client:
        seed_id, round_id = played_seed(client)
        client.post("/auth/logout", data={"next": "/"})
        if who:
            sign_in(client, who)
        for path in (
            *LISTS,
            f"/admin/seeds/{seed_id}",
            f"/admin/rounds/{round_id}",
            "/admin/users/1",
        ):
            response = client.get(path)
            assert response.status_code == 404, path
            assert "not_found.heading" in response.text, path
        for path in (
            f"/admin/seeds/{seed_id}/rebuild",
            f"/admin/rounds/{round_id}/void",
        ):
            assert post(client, path).status_code == 404, path
        sign_in(client, "admin")
        assert client.get(f"/admin/rounds/{round_id}").status_code == 200
        assert post(client, f"/admin/seeds/{seed_id}/rebuild").status_code == 404


def test_no_admins_are_configured_by_default(fake_builder):
    with TestClient(
        create_app(Config(database=":memory:", dev_login=True), builder=fake_builder)
    ) as client:
        sign_in(client, "admin")
        assert client.get("/admin").status_code == 404


def test_every_list_renders_empty_and_full(fake_builder):
    with admin_client(fake_builder) as client:
        sign_in(client, "admin")
        for path in LISTS:
            assert client.get(path).status_code == 200, path
        seed_id, round_id = played_seed(client)
        post(client, f"/admin/rounds/{round_id}/flag")
        for path in LISTS:
            page = client.get(path)
            assert page.status_code == 200, path
        assert f'href="/admin/seeds/{seed_id}"' in client.get("/admin/seeds").text
        assert (
            f'href="/admin/rounds/{round_id}"'
            in client.get("/admin/rounds?flagged=true").text
        )
        assert "alice" in client.get("/admin/users").text


def test_admin_pages_write_their_own_text(fake_builder):
    with admin_client(fake_builder, strings=UNWRITTEN) as client:
        sign_in(client, "admin")
        page = client.get("/admin").text
    main = page[page.index("<main") :]
    assert "⟦" not in main


def test_detail_pages_show_the_seed_the_round_and_the_player(fake_builder):
    with admin_client(fake_builder) as client:
        seed_id, round_id = played_seed(client)
        seed_page = client.get(f"/admin/seeds/{seed_id}").text
        round_page = client.get(f"/admin/rounds/{round_id}").text
        users = client.get("/admin/users").text
        alice_link = re.search(r'href="/admin/users/(\d+)">alice<', users)
        assert alice_link is not None
        alice_id = alice_link.group(1)
        user_page = client.get(f"/admin/users/{alice_id}").text
    assert f"{len(IPS)} bytes" in seed_page
    assert f'href="/admin/rounds/{round_id}"' in seed_page
    assert "<td>LUIGI</td>" in seed_page
    assert '<td class="num over-par">5</td>' in round_page
    assert f'href="/r/{round_id}"' in round_page
    assert f'href="/admin/seeds/{seed_id}"' in user_page
    assert f'href="/admin/rounds/{round_id}"' in user_page


@pytest.mark.parametrize(
    "path", ["/admin/seeds/0000000001", "/admin/rounds/0000000000", "/admin/users/99"]
)
def test_missing_details_are_not_found(fake_builder, path):
    with admin_client(fake_builder) as client:
        sign_in(client, "admin")
        assert client.get(path).status_code == 404


# -- Flag, void and restore ---------------------------------------------------------------


def test_the_activity_page_and_round_history_show_who_did_what(fake_builder):
    with admin_client(fake_builder) as client:
        _seed_id, round_id = played_seed(client)
        post(client, f"/admin/rounds/{round_id}/flag", note="five on every hole?")
        activity = client.get("/admin/activity").text
        round_page = client.get(f"/admin/rounds/{round_id}").text
        admin_link = re.search(r'href="/admin/users/(\d+)">admin<', activity)
        assert admin_link is not None
        admin_id = admin_link.group(1)
        admin_page = client.get(f"/admin/users/{admin_id}").text
    assert "flagged" in activity
    assert "five on every hole?" in activity
    assert f'href="/admin/rounds/{round_id}"' in activity
    assert "flagged" in round_page and "by <a" in round_page
    assert "flagged" in admin_page


def test_a_restored_rounds_history_reaches_back_past_the_void(fake_builder):
    with admin_client(fake_builder) as client:
        seed_id, round_id = played_seed(client)
        post(client, f"/admin/rounds/{round_id}/flag", note="five on every hole?")
        post(client, f"/admin/rounds/{round_id}/void", note="warm-up")
        [restore_path] = re.findall(
            r'action="(/admin/rounds/[0-9A-Za-z]{10}/restore)"',
            client.get("/admin/voided").text,
        )
        restored = post(client, restore_path).headers["location"]
        page = client.get(restored).text
    for phrase in ("flagged", "voided", "restored", "five on every hole?", "warm-up"):
        assert phrase in page, phrase


def test_a_voided_rounds_page_names_the_admin_who_voided_it(fake_builder):
    with admin_client(fake_builder) as client:
        _seed_id, round_id = played_seed(client)
        post(client, f"/admin/rounds/{round_id}/void")
        voided = client.get("/admin/voided").text
        activity = client.get("/admin/activity").text
    assert "by admin" in voided
    # the round is no longer recorded, so activity points at the voided page instead
    assert ", voided</a>" in activity
    assert 'href="/admin/voided"' in activity


def test_flagging_marks_the_round_publicly_and_keeps_the_note_private(fake_builder):
    with admin_client(fake_builder, strings=UNWRITTEN) as client:
        seed_id, round_id = played_seed(client)
        response = post(
            client, f"/admin/rounds/{round_id}/flag", note="five on every hole?"
        )
        assert response.status_code == 303
        assert (
            response.headers["location"] == f"/admin/rounds/{round_id}?result=flagged"
        )
        assert "five on every hole?" in client.get(f"/admin/rounds/{round_id}").text
        seed_page = client.get(f"/h/{seed_id}").text
        sign_in(client, "alice")
        my_page = client.get("/me").text
        sign_in(client, "admin")
        post(client, f"/admin/rounds/{round_id}/unflag")
        unflagged_seed_page = client.get(f"/h/{seed_id}").text
    assert "seed.rounds.flagged" in seed_page
    assert "me.rounds.flagged" in my_page
    assert "five on every hole?" not in seed_page + my_page
    assert "seed.rounds.flagged" not in unflagged_seed_page


def test_voiding_removes_the_round_and_refuses_its_scan_until_restored(fake_builder):
    with admin_client(fake_builder, strings=UNWRITTEN) as client:
        seed_id, round_id = played_seed(client)
        response = post(client, f"/admin/rounds/{round_id}/void", note="warm-up")
        assert response.headers["location"] == "/admin/voided?result=voided"
        assert client.get(f"/admin/rounds/{round_id}").status_code == 404
        voided = client.get("/admin/voided").text
        assert "warm-up" in voided
        [restore_path] = re.findall(
            r'action="(/admin/rounds/[0-9A-Za-z]{10}/restore)"', voided
        )

        rescan = client.get(scan_path(client, seed_id, "alice", strokes=5))
        assert rescan.status_code == 404
        assert "scan_rejected.unrecognized" in rescan.text

        restored = post(client, restore_path)
        assert (
            restored.headers["location"] == f"/admin/rounds/{round_id}?result=restored"
        )
        assert client.get(restored.headers["location"]).status_code == 200
        assert (
            "round.heading"
            in client.get(scan_path(client, seed_id, "alice", strokes=5)).text
        )
        assert post(client, restore_path).status_code == 404


def test_a_voided_rounds_permalink_is_gone_and_comes_back_with_it(fake_builder):
    with admin_client(fake_builder, strings=UNWRITTEN) as client:
        seed_id, round_id = played_seed(client)
        permalink = f"/r/{round_id}"

        post(client, f"/admin/rounds/{round_id}/void", note="warm-up")
        gone = client.get(permalink)
        [restore_path] = re.findall(
            r'action="(/admin/rounds/[0-9A-Za-z]{10}/restore)"',
            client.get("/admin/voided").text,
        )

        post(client, restore_path)
        back = client.get(permalink)
        # the round keeps its public id through the void and the restore
        assert ROUND_LINK.findall(client.get("/admin/rounds").text) == [round_id]

    assert gone.status_code == 410
    assert "round_voided.heading" in gone.text
    assert "round_voided.player_one name=alice" in gone.text
    assert f'href="/h/{seed_id}"' in gone.text
    # the void note is the admin's alone, and no scores are shown
    assert "warm-up" not in gone.text
    assert "90" not in gone.text[gone.text.index("<main") :]
    assert back.status_code == 200
    assert "round.heading" in back.text


def test_a_round_replacing_a_voided_one_gets_its_own_permalink(fake_builder):
    with admin_client(fake_builder, strings=UNWRITTEN) as client:
        seed_id, round_id = played_seed(client)
        voided_permalink = f"/r/{round_id}"
        post(client, f"/admin/rounds/{round_id}/void")

        replacement = client.get(
            scan_path(client, seed_id, "alice", strokes=3), follow_redirects=False
        )

    assert replacement.status_code == 303
    assert replacement.headers["location"].removesuffix("?recorded") != voided_permalink


def test_restoring_into_a_slot_with_a_round_is_refused(fake_builder):
    with admin_client(fake_builder, strings=UNWRITTEN) as client:
        seed_id, round_id = played_seed(client)
        post(client, f"/admin/rounds/{round_id}/void")
        assert (
            client.get(scan_path(client, seed_id, "alice", strokes=3)).status_code
            == 200
        )
        voided = client.get("/admin/voided").text
        assert "slot has a round" in voided
        assert "/restore" not in voided
        response = post(client, f"/admin/rounds/{round_id}/restore")
        assert response.headers["location"] == "/admin/voided?result=slot_taken"
        assert (
            "slot already has a round" in client.get(response.headers["location"]).text
        )


@pytest.mark.parametrize("action", ["flag", "unflag", "void", "restore"])
def test_acting_on_a_missing_round_is_not_found(fake_builder, action):
    with admin_client(fake_builder) as client:
        sign_in(client, "admin")
        assert post(client, f"/admin/rounds/0000000000/{action}").status_code == 404
