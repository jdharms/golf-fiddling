"""Integration: the QR code a signed-in download's ROM draws records its round on the site.

Downloads a finished ROM from the app, pulls the scorecard QR image back out of it, runs the
6502 routine under the simulator to build the URL the code carries, and opens that URL.
"""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from golf.core import ips
from golf.core.patches import SCORECARD_QR_PATCH
from golf.qr.payload import URL_LEN, URL_PREFIX
from golf.qr.port import layout
from golf.qr.port.sim import Machine
from golf.randomizer.catalog import US_ROM
from golf.randomizer.roms import vanilla_rom
from server.app import create_app
from server.config import Config
from server.forms import FormState

ROOT = Path(__file__).resolve().parents[2]
ROM_PATH = ROOT / "nes_open_us.nes"
HEADER = 0x10

pytestmark = pytest.mark.skipif(not ROM_PATH.exists(), reason=f"{ROM_PATH.name} not present")

#: (strokes, putts) for holes 1-18, per player slot
ROUNDS = {
    0: [(4, 2)] * 9 + [(5, 2)] * 9,
    1: [(3, 1)] * 18,
}


def rom_url(rom: bytes, slot: int) -> str:
    """The URL the ROM's QR screen shows for `slot` after ROUNDS has been played."""
    image = rom[HEADER + SCORECARD_QR_PATCH.image_offset :][: len(SCORECARD_QR_PATCH.image)]
    machine = Machine()
    machine.write(layout.TABLE_ORIGIN, image)
    for player, holes in ROUNDS.items():
        machine.set_round(holes, player=player, player_count=1)
    machine.call("QrBuildPayload", a=slot)
    machine.call("QrBuildUrl")
    return machine.read(layout.URL, URL_LEN).decode("ascii")


def test_a_downloaded_roms_codes_record_both_players_rounds():
    with TestClient(create_app(Config(database=":memory:", rom_dir=ROOT, dev_login=True))) as client:
        form = FormState.default()
        form.sources, form.music = {US_ROM}, "nes_us"
        data: dict[str, list[str]] = {}
        for name, value in form.to_pairs():
            data.setdefault(name, []).append(value)
        generated = client.post("/generate", data=data, follow_redirects=False)
        assert generated.status_code == 303, generated.text
        seed_path = generated.headers["location"]

        client.get("/auth/login", params={"as": "alice"})
        download = client.post(
            f"{seed_path}/patch.ips",
            data={"player_name": "toad", "clubs": ["1W", "PW"], f"rom_{US_ROM}": vanilla_rom(US_ROM).sha1},
        )
        assert download.status_code == 200, download.text
        rom = ips.apply(ROM_PATH.read_bytes(), download.content)
        client.post("/auth/logout", data={"next": "/"})

        for slot in ROUNDS:
            url = rom_url(rom, slot)
            assert url.startswith(URL_PREFIX)
            response = client.get("/s/" + url.removeprefix(URL_PREFIX))
            assert response.status_code == 200, response.text

        with client.app.state.db.transaction() as conn:
            recorded = conn.execute("SELECT slot, total_strokes, total_putts FROM submissions ORDER BY slot").fetchall()
    assert [tuple(row) for row in recorded] == [
        (slot, sum(s for s, _ in holes), sum(p for _, p in holes)) for slot, holes in ROUNDS.items()
    ]
