"""The site's app skeleton: health check, home page, ROM setup page and static files."""

import pytest
from fastapi.testclient import TestClient

from golf.randomizer.roms import VANILLA_ROMS
from server.app import create_app
from server.config import Config
from server.migrations import MIGRATIONS


@pytest.fixture
def client():
    app = create_app(Config(database=":memory:"))
    with TestClient(app) as test_client:
        yield test_client


def test_health_check(client):
    response = client.get("/healthz")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_startup_migrates_the_database(client):
    assert client.app.state.db.version() == len(MIGRATIONS)


def test_home_links_to_rom_setup_and_generate(client):
    response = client.get("/")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert 'href="/rom"' in response.text
    assert 'href="/generate"' in response.text


def test_rom_setup_lists_every_vanilla_rom_with_its_hash(client):
    response = client.get("/rom")
    assert response.status_code == 200
    for rom in VANILLA_ROMS:
        assert f'data-rom-id="{rom.id}"' in response.text
        assert f'data-sha1="{rom.sha1}"' in response.text
        assert rom.title in response.text
    assert response.text.count('data-state="checking"') == len(VANILLA_ROMS)
    assert 'src="/static/rom.js"' in response.text


@pytest.mark.parametrize("path", ["/static/pico.green.min.css", "/static/site.css", "/static/rom.js"])
def test_static_files_are_served(client, path):
    response = client.get(path)
    assert response.status_code == 200
    assert response.content


def test_pages_use_the_vendored_and_site_stylesheets(client):
    page = client.get("/").text
    assert 'href="/static/pico.green.min.css"' in page
    assert 'href="/static/site.css"' in page


def test_api_docs_are_not_exposed(client):
    assert client.get("/docs").status_code == 404
    assert client.get("/openapi.json").status_code == 404
