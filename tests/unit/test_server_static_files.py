"""Versioned static URLs and their cache headers."""

import os
import re

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from server.app import TEMPLATES_DIR, create_app
from server.config import Config
from server.static_files import (
    IMMUTABLE,
    REVALIDATE,
    CachedStaticFiles,
    StaticVersions,
)

VERSIONED = re.compile(r"^/static/site\.css\?v=([0-9a-f]{12})$")


def test_a_url_carries_a_hash_of_the_contents(tmp_path):
    (tmp_path / "site.css").write_text("body {}")
    versions = StaticVersions(tmp_path)
    first = versions.url("site.css")
    assert VERSIONED.match(first)
    assert versions.url("site.css") == first

    (tmp_path / "other.css").write_text("body {}")
    assert versions.version("other.css") == versions.version("site.css")


def test_an_edited_file_gets_a_new_version(tmp_path):
    path = tmp_path / "site.css"
    path.write_text("body {}")
    versions = StaticVersions(tmp_path)
    before = versions.version("site.css")
    path.write_text("body { color: red; }")
    os.utime(path, ns=(0, path.stat().st_mtime_ns + 1_000_000))
    assert versions.version("site.css") != before


def test_a_missing_file_is_an_error(tmp_path):
    with pytest.raises(FileNotFoundError):
        StaticVersions(tmp_path).url("missing.js")


@pytest.fixture
def static_client(tmp_path):
    (tmp_path / "app.js").write_text("export {};")
    app = FastAPI()
    app.mount("/static", CachedStaticFiles(directory=tmp_path))
    with TestClient(app) as client:
        yield client


def test_a_versioned_file_is_immutable(static_client):
    response = static_client.get("/static/app.js?v=0123456789ab")
    assert response.status_code == 200
    assert response.headers["cache-control"] == IMMUTABLE


def test_an_unversioned_file_is_revalidated(static_client):
    response = static_client.get("/static/app.js")
    assert response.status_code == 200
    assert response.headers["cache-control"] == REVALIDATE

    etag = response.headers["etag"]
    again = static_client.get("/static/app.js", headers={"if-none-match": etag})
    assert again.status_code == 304
    assert again.headers["cache-control"] == REVALIDATE


def test_a_missing_file_gets_no_cache_header(static_client):
    response = static_client.get("/static/missing.js?v=0123456789ab")
    assert response.status_code == 404
    assert "cache-control" not in response.headers


def test_pages_link_versioned_static_files():
    with TestClient(create_app(Config(database=":memory:"))) as client:
        page = client.get("/rom").text
        links = re.findall(r'(?:href|src)="(/static/[^"]+)"', page)
        assert len(links) == 4
        for link in links:
            assert re.search(r"\?v=[0-9a-f]{12}$", link), link
            response = client.get(link)
            assert response.status_code == 200
            assert response.headers["cache-control"] == IMMUTABLE


def test_templates_link_static_files_only_through_static_url():
    for template in TEMPLATES_DIR.rglob("*.html"):
        assert "/static/" not in template.read_text(), template
