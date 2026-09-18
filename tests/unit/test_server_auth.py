"""Sign-in helpers: the Discord OAuth2 client against a mock transport, and safe return paths."""

import asyncio
import base64
from urllib.parse import parse_qs, urlsplit

import httpx2
import pytest

from server.auth import (
    API_BASE,
    AUTHORIZE_URL,
    DiscordClient,
    DiscordError,
    DiscordIdentity,
    safe_next,
)

REDIRECT = "http://127.0.0.1:8000/auth/callback"
ME = {
    "id": "80351110224678912",
    "username": "nelly",
    "global_name": "Nelly",
    "avatar": "8342729096ea3675442027381ff50dfe",
}


def discord(token=None, me=None, token_status=200, me_status=200, seen=None):
    """A DiscordClient whose calls reach a fake Discord that records the requests it gets."""
    seen = seen if seen is not None else []

    def handle(request: httpx2.Request) -> httpx2.Response:
        seen.append(request)
        if request.url.path == "/api/v10/oauth2/token":
            body = (
                token
                if token is not None
                else {"access_token": "token-abc", "token_type": "Bearer"}
            )
            return httpx2.Response(token_status, json=body)
        if request.url.path == "/api/v10/users/@me":
            return httpx2.Response(me_status, json=me if me is not None else ME)
        return httpx2.Response(404)

    return DiscordClient(
        "client-id", "client-secret", transport=httpx2.MockTransport(handle)
    )


def identify(client: DiscordClient) -> DiscordIdentity:
    return asyncio.run(client.identify("code-xyz", REDIRECT))


def test_the_authorize_url_asks_for_identify_with_the_state_and_redirect():
    url = urlsplit(
        DiscordClient("client-id", "secret").authorize_url("state-123", REDIRECT)
    )
    assert f"{url.scheme}://{url.netloc}{url.path}" == AUTHORIZE_URL
    assert parse_qs(url.query) == {
        "response_type": ["code"],
        "client_id": ["client-id"],
        "scope": ["identify"],
        "state": ["state-123"],
        "redirect_uri": [REDIRECT],
        "prompt": ["none"],
    }


def test_identify_exchanges_the_code_and_reads_the_user():
    seen = []
    assert identify(discord(seen=seen)) == DiscordIdentity(
        "80351110224678912", "nelly", "Nelly", "8342729096ea3675442027381ff50dfe"
    )
    token_request, me_request = seen
    assert str(token_request.url) == f"{API_BASE}/oauth2/token"
    assert token_request.method == "POST"
    assert parse_qs(token_request.content.decode()) == {
        "grant_type": ["authorization_code"],
        "code": ["code-xyz"],
        "redirect_uri": [REDIRECT],
    }
    assert (
        token_request.headers["authorization"]
        == "Basic " + base64.b64encode(b"client-id:client-secret").decode()
    )
    assert str(me_request.url) == f"{API_BASE}/users/@me"
    assert me_request.headers["authorization"] == "Bearer token-abc"


def test_a_user_without_a_display_name_or_avatar_is_accepted():
    identity = identify(
        discord(
            me={"id": "1", "username": "nelly", "global_name": None, "avatar": None}
        )
    )
    assert identity == DiscordIdentity("1", "nelly", None, None)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"token_status": 400},
        {"me_status": 401},
        {"token": {"error": "invalid_grant"}},
        {"token": {"access_token": 5}},
        {"token": ["not", "an", "object"]},
        {"me": ["not", "an", "object"]},
        {"me": {"username": "nelly"}},
        {"me": {"id": "1", "username": ""}},
        {"me": {"id": 1, "username": "nelly"}},
        {"me": {"id": "1", "username": "nelly", "global_name": 7}},
    ],
)
def test_a_failed_or_unexpected_answer_is_a_discord_error(kwargs):
    with pytest.raises(DiscordError):
        identify(discord(**kwargs))


def test_a_body_that_is_not_json_is_a_discord_error():
    def handle(request):
        return httpx2.Response(200, content=b"<html>")

    with pytest.raises(DiscordError):
        identify(DiscordClient("id", "secret", transport=httpx2.MockTransport(handle)))


def test_a_network_failure_is_a_discord_error():
    def handle(request):
        raise httpx2.ConnectError("down", request=request)

    with pytest.raises(DiscordError):
        identify(DiscordClient("id", "secret", transport=httpx2.MockTransport(handle)))


@pytest.mark.parametrize("value", ["/", "/h/0000000001", "/generate?par=71"])
def test_a_local_path_is_a_safe_return(value):
    assert safe_next(value) == value


@pytest.mark.parametrize(
    "value",
    [
        None,
        "",
        "h/1",
        "//evil.example/",
        "/\\evil.example",
        "https://evil.example/",
        "javascript:alert(1)",
    ],
)
def test_anything_else_returns_home(value):
    assert safe_next(value) == "/"
