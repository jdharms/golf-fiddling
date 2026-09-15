"""The site's app skeleton: health check, home page, ROM setup page and static files."""

import pytest
from fastapi.testclient import TestClient

from golf.randomizer.roms import VANILLA_ROMS
from server.app import create_app
from server.config import Config
from server.migrations import MIGRATIONS
from server.strings import Entry, Strings


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
    assert 'id="rom-strings"' in response.text
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


def _catalog_with_text(text_for) -> Strings:
    real = Strings.load()
    return Strings({key: Entry(real.entry(key).note, text_for(key)) for key in real.keys()})  # noqa: SIM118 (Strings, not a dict)


def test_written_strings_render_without_placeholders():
    written = _catalog_with_text(lambda key: f"TEXT:{key}")
    with TestClient(create_app(Config(database=":memory:"), strings=written)) as test_client:
        home, rom = test_client.get("/").text, test_client.get("/rom").text
    for page in (home, rom):
        assert "⟦" not in page
        assert 'class="unwritten"' not in page
    assert "TEXT:home.heading" in home
    assert "<title>TEXT:rom.page_title</title>" in rom
    assert '"TEXT:rom.status.stored"' in rom


def test_unwritten_strings_render_as_placeholders_with_their_notes():
    unwritten = _catalog_with_text(lambda key: "")
    with TestClient(create_app(Config(database=":memory:"), strings=unwritten)) as test_client:
        rom = test_client.get("/rom").text
    assert "<title>⟦rom.page_title⟧</title>" in rom
    assert '<span class="unwritten" title="ROM setup page h1">⟦rom.heading⟧</span>' in rom
    assert f"⟦rom.expected_hash sha1={VANILLA_ROMS[0].sha1}⟧" in rom
    assert '"rom.status.stored": null' in rom
