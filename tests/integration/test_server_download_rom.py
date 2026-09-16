"""Integration: downloading from a seed page finishes the seed's real stored IPS."""

import json
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from golf.core import ips
from golf.core.patches.sram_defaults import Club
from golf.randomizer.build import PlayerOptions, finish
from golf.randomizer.catalog import JP_ROM, US_ROM
from golf.randomizer.manifest import Manifest
from golf.randomizer.roms import VANILLA_ROMS, vanilla_rom
from server.app import create_app
from server.config import Config
from server.forms import FormState

ROOT = Path(__file__).resolve().parents[2]
ROM_PATH = ROOT / "nes_open_us.nes"

pytestmark = pytest.mark.skipif(not ROM_PATH.exists(), reason=f"{ROM_PATH.name} not present")


@pytest.fixture(scope="module")
def client():
    with TestClient(create_app(Config(database=":memory:", rom_dir=ROOT))) as test_client:
        yield test_client


def generate(client: TestClient, **changes) -> str:
    form = FormState.default()
    for name, value in changes.items():
        setattr(form, name, value)
    data: dict[str, list[str]] = {}
    for name, value in form.to_pairs():
        data.setdefault(name, []).append(value)
    response = client.post("/generate", data=data, follow_redirects=False)
    assert response.status_code == 303, response.text
    return re.fullmatch(r"/h/([0-9A-Za-z]{10})", response.headers["location"]).group(1)


def test_a_download_is_the_finished_build_of_the_stored_seed(client):
    seed_id = generate(client, music="jp_france")
    response = client.post(
        f"/h/{seed_id}/patch.ips",
        data={"player_name": "toad", "clubs": ["1W", "3W", "5I", "PW"], **{f"rom_{rom.id}": rom.sha1 for rom in VANILLA_ROMS}},
    )
    assert response.status_code == 200, response.text

    with client.app.state.db.transaction() as conn:
        row = conn.execute("SELECT manifest, unfinished_ips FROM seeds WHERE id = ?", (seed_id,)).fetchone()
    manifest = Manifest.from_json(json.loads(row["manifest"]))
    vanilla = ROM_PATH.read_bytes()
    options = PlayerOptions("TOAD", frozenset({Club.W1, Club.W3, Club.I5, Club.PW}))
    expected = finish(manifest, vanilla, row["unfinished_ips"], options)
    assert response.content == expected.ips
    assert ips.apply(vanilla, response.content) == expected.rom
    assert response.headers["content-disposition"] == f'attachment; filename="notgr_par{manifest.course.par}_{seed_id}.ips"'


def test_a_seed_playing_a_mario_open_theme_needs_the_jp_rom(client):
    seed_id = generate(client, music="jp_france")
    response = client.post(
        f"/h/{seed_id}/patch.ips",
        data={"player_name": "toad", f"rom_{US_ROM}": vanilla_rom(US_ROM).sha1},
    )
    assert response.status_code == 403
    assert response.json() == {"error": "roms_missing", "values": {"roms": vanilla_rom(JP_ROM).title}}
