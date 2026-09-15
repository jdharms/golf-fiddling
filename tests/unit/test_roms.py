"""The vanilla ROM list the site checks players' files against."""

import hashlib
from pathlib import Path

import pytest

from golf.randomizer.catalog import JP_ROM, US_ROM
from golf.randomizer.manifest import SOURCES
from golf.randomizer.roms import VANILLA_ROMS, vanilla_rom

ROOT = Path(__file__).resolve().parents[2]
LOCAL_FILES = {US_ROM: ROOT / "nes_open_us.nes", JP_ROM: ROOT / "mario_open_jp.nes"}


def test_the_roms_are_the_manifest_sources_in_order():
    assert tuple(rom.id for rom in VANILLA_ROMS) == SOURCES


def test_hashes_are_lowercase_sha1_hex():
    for rom in VANILLA_ROMS:
        assert len(rom.sha1) == 40
        assert rom.sha1 == rom.sha1.lower()
        int(rom.sha1, 16)


def test_lookup_by_id():
    assert vanilla_rom(JP_ROM).id == JP_ROM
    with pytest.raises(KeyError):
        vanilla_rom("nes_open_jp")


@pytest.mark.parametrize("rom", VANILLA_ROMS, ids=lambda rom: rom.id)
def test_the_hash_matches_a_local_rom(rom):
    path = LOCAL_FILES[rom.id]
    if not path.exists():
        pytest.skip(f"{path.name} not present")
    assert hashlib.sha1(path.read_bytes()).hexdigest() == rom.sha1
