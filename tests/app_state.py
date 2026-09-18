"""The site's app state, reached through a TestClient."""

from fastapi.testclient import TestClient
from starlette.applications import Starlette
from starlette.datastructures import State


def app_state(client: TestClient) -> State:
    """`client.app.state`, which TestClient types only as a bare ASGI app."""
    assert isinstance(client.app, Starlette)
    return client.app.state
