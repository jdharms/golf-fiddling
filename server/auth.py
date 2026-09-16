"""Sign-in: the Discord OAuth2 client, the session's user, and safe redirects.

Discord sign-in is the authorization code flow with the `identify` scope, two calls and
no library: exchange the code for a token, read `/users/@me` with it, and throw the token
away. The session cookie holds only the signed-in user's `users.id`, plus the OAuth
`state` and return path while a sign-in is under way. See docs/randomizer_devplan.md,
"Users and access".
"""

import re
from dataclasses import dataclass
from urllib.parse import urlencode

import httpx2
from starlette.requests import Request

from .db import Database
from .users import User, load_user

AUTHORIZE_URL = "https://discord.com/oauth2/authorize"
API_BASE = "https://discord.com/api/v10"
SCOPE = "identify"
#: seconds each Discord call may take
TIMEOUT_SECONDS = 10.0

#: the session key holding the signed-in user's users.id
SESSION_USER = "user_id"
#: session keys held between /auth/login and /auth/callback
SESSION_STATE = "oauth_state"
SESSION_NEXT = "next"

#: what `/auth/login?as=` accepts under the development login bypass
DEV_NAME = re.compile(r"[A-Za-z0-9_-]{1,32}")
DEV_DISCORD_PREFIX = "dev:"


class DiscordError(Exception):
    """Discord refused the code, failed, or answered with something unexpected."""


@dataclass(frozen=True)
class DiscordIdentity:
    id: str
    username: str
    global_name: str | None
    avatar: str | None


class DiscordClient:
    def __init__(self, client_id: str, client_secret: str, transport: httpx2.AsyncBaseTransport | None = None):
        self.client_id = client_id
        self.client_secret = client_secret
        self._transport = transport

    def authorize_url(self, state: str, redirect_uri: str) -> str:
        query = {
            "response_type": "code",
            "client_id": self.client_id,
            "scope": SCOPE,
            "state": state,
            "redirect_uri": redirect_uri,
            "prompt": "none",
        }
        return f"{AUTHORIZE_URL}?{urlencode(query)}"

    async def identify(self, code: str, redirect_uri: str) -> DiscordIdentity:
        """The Discord account that granted this authorization code."""
        try:
            async with httpx2.AsyncClient(transport=self._transport, timeout=TIMEOUT_SECONDS) as client:
                token = await client.post(
                    f"{API_BASE}/oauth2/token",
                    data={"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri},
                    auth=(self.client_id, self.client_secret),
                )
                token.raise_for_status()
                access_token = token.json()["access_token"]
                if not isinstance(access_token, str):
                    raise DiscordError("the token response has no access token")
                me = await client.get(f"{API_BASE}/users/@me", headers={"Authorization": f"Bearer {access_token}"})
                me.raise_for_status()
                body = me.json()
        except (httpx2.HTTPError, ValueError, KeyError, TypeError) as problem:
            raise DiscordError(str(problem)) from problem
        return _identity(body)


def _identity(body: object) -> DiscordIdentity:
    if not isinstance(body, dict):
        raise DiscordError("the user response is not an object")
    discord_id, username = body.get("id"), body.get("username")
    if not isinstance(discord_id, str) or not discord_id or not isinstance(username, str) or not username:
        raise DiscordError("the user response has no id or username")
    optional = {}
    for name in ("global_name", "avatar"):
        value = body.get(name)
        if value is not None and not isinstance(value, str):
            raise DiscordError(f"the user's {name} is not a string")
        optional[name] = value
    return DiscordIdentity(discord_id, username, **optional)


def safe_next(value: str | None) -> str:
    """A return path that stays on this site: a local path, or "/" for anything else."""
    if not value or not value.startswith("/") or value.startswith("//") or "\\" in value:
        return "/"
    return value


def current_user(request: Request) -> User | None:
    """The signed-in user, loaded once per request. A session naming a missing user is cleared."""
    if hasattr(request.state, "current_user"):
        return request.state.current_user
    user = None
    user_id = request.session.get(SESSION_USER)
    if isinstance(user_id, int):
        db: Database = request.app.state.db
        user = load_user(db, user_id)
        if user is None:
            request.session.clear()
    request.state.current_user = user
    return user


def start_session(request: Request, user: User) -> None:
    """Sign the browser in as `user`, dropping whatever the session held before."""
    request.session.clear()
    request.session[SESSION_USER] = user.id
