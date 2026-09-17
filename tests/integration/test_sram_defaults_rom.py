"""Integration tests for the SRAM defaults patch against the real ROM."""

from pathlib import Path

import pytest

from golf.core.patches import PatchStack, sram_defaults_patch
from golf.core.patches.sram_defaults import (
    BANK,
    BGM_BRANCH_ADDR,
    CLUB_BAG_ADDR,
    NAME_ADDR,
    VANILLA_CLUBS,
    VANILLA_NAME,
    club_bag_bytes,
    player_name_bytes,
)
from golf.core.rom_reader import RomReader

ROM_PATH = "nes_open_us.nes"

pytestmark = pytest.mark.skipif(not Path(ROM_PATH).exists(), reason=f"{ROM_PATH} not present")


@pytest.fixture(scope="module")
def vanilla() -> bytes:
    return Path(ROM_PATH).read_bytes()


def test_vanilla_bytes_match_the_rom(vanilla):
    rom = RomReader.from_bytes(vanilla)
    assert rom.read_switched(NAME_ADDR, BANK, 10) == player_name_bytes(VANILLA_NAME)
    assert rom.read_switched(CLUB_BAG_ADDR, BANK, 14) == club_bag_bytes(VANILLA_CLUBS)
    # LDX #$17 / LDA #$FF / STA BGMOnFlag,X / DEX / BPL
    assert rom.read_switched(0xAD46, BANK, 10) == bytes([0xA2, 0x17, 0xA9, 0xFF, 0x9D, 0x98, 0x6F, 0xCA, 0x10, 0xF8])
    # LDA $6001 / CMP #$35 / BNE / LDA $6002 / CMP #$53
    assert rom.read_switched(0xACBC, BANK, 12) == bytes(
        [0xAD, 0x01, 0x60, 0xC9, 0x35, 0xD0, 0x08, 0xAD, 0x02, 0x60, 0xC9, 0x53]
    )
    # LDA #$35 / STA $6001 / LDA #$53 / STA $6002 / RTS
    assert rom.read_switched(0xAD50, BANK, 11) == bytes(
        [0xA9, 0x35, 0x8D, 0x01, 0x60, 0xA9, 0x53, 0x8D, 0x02, 0x60, 0x60]
    )


def test_every_default_on_the_rom(vanilla):
    patch = sram_defaults_patch("RANDO", ["1W", "3W", "5I", "PW", "SW"], bgm=False, sram_magic=0x5244)
    rom = RomReader.from_bytes(PatchStack([patch]).build(vanilla).rom)

    assert rom.read_switched(NAME_ADDR, BANK, 10) == b"RANDO     "
    assert rom.read_switched(CLUB_BAG_ADDR, BANK, 14) == bytes([0x00, 0x02, 0x08, 0x0D, 0x0E, 0x0F] + [0xFF] * 8)
    assert rom.read_switched(BGM_BRANCH_ADDR, BANK, 2) == bytes([0xD0, 0xF8])
    assert rom.read_switched(0xACBC, BANK, 12) == bytes(
        [0xAD, 0x01, 0x60, 0xC9, 0x52, 0xD0, 0x08, 0xAD, 0x02, 0x60, 0xC9, 0x44]
    )
    assert rom.read_switched(0xAD50, BANK, 11) == bytes(
        [0xA9, 0x52, 0x8D, 0x01, 0x60, 0xA9, 0x44, 0x8D, 0x02, 0x60, 0x60]
    )
