"""Integration: golf-randomize build on the real vanilla ROM matches the library's two stages."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

from golf.core import ips
from golf.core.patches import load_credentials
from golf.core.patches.qr_credentials import PLACEHOLDERS, placeholder_offset
from golf.core.patches.sram_defaults import VANILLA_CLUBS, VANILLA_NAME, Club
from golf.qr import port
from golf.randomizer.build import (
    PlayerOptions,
    build_unfinished,
    clubs_from_labels,
    finish,
)
from golf.randomizer.catalog import Catalog, HoleStore
from golf.randomizer.curation import CurationSnapshot
from golf.randomizer.generate import generate
from golf.randomizer.manifest import ClubRules, Settings

ROOT = Path(__file__).resolve().parents[2]
ROM_PATH = ROOT / "nes_open_us.nes"
HEADER = 0x10

pytestmark = pytest.mark.skipif(
    not ROM_PATH.exists(), reason=f"{ROM_PATH.name} not present"
)


def run(module: str, *args) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", module, *map(str, args)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )


def build(*args) -> subprocess.CompletedProcess:
    return run("tools.randomize", "build", ROM_PATH, *args)


@pytest.fixture(scope="module")
def vanilla() -> bytes:
    return ROM_PATH.read_bytes()


@pytest.fixture(scope="module")
def catalog() -> Catalog:
    return Catalog.load()


@pytest.fixture(scope="module")
def manifest(catalog):
    return generate(catalog, CurationSnapshot.load(), Settings(prng_seed="cli-rom"))


@pytest.fixture(scope="module")
def unfinished(manifest, catalog, vanilla):
    return build_unfinished(manifest, catalog, HoleStore(), vanilla)


@pytest.fixture
def manifest_path(manifest, tmp_path) -> Path:
    path = tmp_path / "seed.json"
    path.write_text(json.dumps(manifest.to_json()))
    return path


def test_build_defaults_to_a_finished_guest_rom(
    manifest, manifest_path, unfinished, vanilla, tmp_path
):
    out, patch = tmp_path / "out.nes", tmp_path / "out.ips"
    completed = build(manifest_path, "-o", out, "--ips", patch)
    assert completed.returncode == 0, completed.stderr

    options = PlayerOptions(VANILLA_NAME, frozenset(VANILLA_CLUBS))
    expected = finish(manifest, vanilla, unfinished.ips, options)
    assert out.read_bytes() == expected.rom
    assert ips.apply(vanilla, patch.read_bytes()) == expected.rom
    assert "built: finished, guest" in completed.stdout
    assert "bank 0:" in completed.stdout


def test_build_unfinished_writes_the_first_stage_next_to_the_manifest(
    manifest_path, unfinished
):
    completed = build(manifest_path, "--unfinished")
    assert completed.returncode == 0, completed.stderr

    rom = manifest_path.with_suffix(".nes").read_bytes()
    assert rom == unfinished.rom
    for _, symbol, length in PLACEHOLDERS:
        start = HEADER + placeholder_offset(symbol)
        assert rom[start : start + length] == bytes([port.PATCH_FILL]) * length
    assert "built: unfinished" in completed.stdout


def test_build_with_credentials_finishes_signed_in(
    manifest, manifest_path, unfinished, vanilla, tmp_path
):
    keys, out = tmp_path / "keys.json", tmp_path / "out.nes"
    assert run("tools.qr.credentials", "-o", keys, "--rng-seed", "7").returncode == 0
    completed = build(manifest_path, "--credentials", keys, "-o", out)
    assert completed.returncode == 0, completed.stderr

    options = PlayerOptions(VANILLA_NAME, frozenset(VANILLA_CLUBS))
    expected = finish(
        manifest, vanilla, unfinished.ips, options, load_credentials(keys)
    )
    assert out.read_bytes() == expected.rom
    assert "built: finished, signed in" in completed.stdout
    assert load_credentials(keys).keys[0].hex() not in completed.stdout


def test_build_applies_the_player_options(
    manifest, manifest_path, unfinished, vanilla, tmp_path
):
    out = tmp_path / "out.nes"
    completed = build(
        manifest_path, "--name", "LUIGI", "--clubs", "1W,3W,5I", "--no-bgm", "-o", out
    )
    assert completed.returncode == 0, completed.stderr

    options = PlayerOptions("LUIGI", clubs_from_labels(["1W", "3W", "5I"]), bgm=False)
    assert out.read_bytes() == finish(manifest, vanilla, unfinished.ips, options).rom


def test_build_refuses_a_bag_the_seed_bans(catalog, tmp_path):
    strict = generate(
        catalog,
        CurationSnapshot.load(),
        Settings(prng_seed="cli-rom", clubs=ClubRules(banned=frozenset({Club.W1}))),
    )
    path = tmp_path / "strict.json"
    path.write_text(json.dumps(strict.to_json()))
    completed = build(path, "--clubs", "1W,PW", "-o", tmp_path / "out.nes")
    assert completed.returncode == 1
    assert "bans 1W" in completed.stderr
    assert not (tmp_path / "out.nes").exists()


def test_build_refuses_an_unknown_hole(manifest, tmp_path):
    data = manifest.to_json()
    data["course"]["holes"][0]["id"] = "nes_us/99"
    path = tmp_path / "unknown.json"
    path.write_text(json.dumps(data))
    completed = build(path, "-o", tmp_path / "out.nes")
    assert completed.returncode == 1
    assert completed.stderr.startswith("error:") and "nes_us/99" in completed.stderr


def test_build_refuses_player_options_with_unfinished(manifest_path):
    completed = build(manifest_path, "--unfinished", "--no-bgm")
    assert completed.returncode == 2
    assert "finishing options" in completed.stderr
