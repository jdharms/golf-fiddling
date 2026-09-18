"""Integration: generating a seed on the site builds and stores its real unfinished IPS, and rebuilds it."""

import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from golf.core import ips
from golf.randomizer.build import build_unfinished
from golf.randomizer.catalog import Catalog, HoleStore
from golf.randomizer.manifest import Manifest, required_roms
from golf.randomizer.roms import vanilla_rom
from server.app import create_app
from server.config import Config
from server.forms import FormState

ROOT = Path(__file__).resolve().parents[2]
ROM_PATH = ROOT / "nes_open_us.nes"

pytestmark = pytest.mark.skipif(
    not ROM_PATH.exists(), reason=f"{ROM_PATH.name} not present"
)


def form_data() -> dict[str, list[str]]:
    data: dict[str, list[str]] = {}
    for name, value in FormState.default().to_pairs():
        data.setdefault(name, []).append(value)
    return data


def test_a_generated_seed_stores_the_unfinished_build_of_its_manifest():
    vanilla = ROM_PATH.read_bytes()
    catalog = Catalog.load()
    with TestClient(create_app(Config(database=":memory:", rom_dir=ROOT))) as client:
        response = client.post("/generate", data=form_data(), follow_redirects=False)
        assert response.status_code == 303, response.text
        seed_id = re.fullmatch(
            r"/h/([0-9A-Za-z]{10})", response.headers["location"]
        ).group(1)

        with client.app.state.db.transaction() as conn:
            row = conn.execute(
                "SELECT manifest, unfinished_ips FROM seeds WHERE id = ?", (seed_id,)
            ).fetchone()
        manifest = Manifest.from_json(json.loads(row["manifest"]))
        page = client.get(f"/h/{seed_id}").text

    stored = row["unfinished_ips"]
    expected = build_unfinished(manifest, catalog, HoleStore(), vanilla)
    assert stored == expected.ips
    assert ips.apply(vanilla, stored) == expected.rom

    details = page[page.index('class="seed-details"') :]
    required = details[details.rindex("<tr>") :]
    for rom_id in required_roms(manifest, catalog):
        assert vanilla_rom(rom_id).title in required


def test_rebuilding_a_fresh_seed_with_the_real_builder_is_unchanged():
    config = Config(
        database=":memory:",
        rom_dir=ROOT,
        dev_login=True,
        admin_users=frozenset({"dev:admin"}),
    )
    with TestClient(create_app(config)) as client:
        client.get("/auth/login", params={"as": "admin"})
        response = client.post("/generate", data=form_data(), follow_redirects=False)
        seed_id = re.fullmatch(
            r"/h/([0-9A-Za-z]{10})", response.headers["location"]
        ).group(1)
        rebuilt = client.post(f"/admin/seeds/{seed_id}/rebuild", follow_redirects=False)
    assert rebuilt.status_code == 303, rebuilt.text
    assert rebuilt.headers["location"] == f"/admin/seeds/{seed_id}?result=unchanged"
