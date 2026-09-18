"""Integration tests for the scorecard course name patch against the real ROM."""

from pathlib import Path

import pytest

from golf.core.graphics_codec import load_graphics_table
from golf.core.patches import (
    COURSE_MIRRORS_PATCH,
    PatchStack,
    scorecard_course_name_patch,
)
from golf.core.patches.scorecard_course_name import (
    _VANILLA_ATTRIBUTES,
    _VANILLA_DESCRIPTOR_REGION,
    _VANILLA_DISPATCH_POINTERS,
    _VANILLA_TITLE_POINTER,
    _VANILLA_TITLE_REGION,
    ATTRIBUTES_ADDR,
    BANK,
    DESCRIPTOR_ADDR,
    DISPATCH_POINTERS_ADDR,
    TITLE_DESCRIPTOR_ADDR,
    TITLE_POINTER_ADDR,
    title_descriptor_bytes,
)
from golf.core.rom_reader import RomReader

ROM_PATH = "nes_open_us.nes"
CARD_TABLE = 0xB90B  # the blank card and its attributes

pytestmark = pytest.mark.skipif(
    not Path(ROM_PATH).exists(), reason=f"{ROM_PATH} not present"
)


@pytest.fixture(scope="module")
def vanilla() -> bytes:
    return Path(ROM_PATH).read_bytes()


def test_vanilla_bytes_match_the_rom(vanilla):
    rom = RomReader.from_bytes(vanilla)
    assert (
        rom.read_switched(DISPATCH_POINTERS_ADDR, BANK, 5) == _VANILLA_DISPATCH_POINTERS
    )
    assert rom.read_switched(
        DESCRIPTOR_ADDR, BANK, len(_VANILLA_DESCRIPTOR_REGION)
    ) == (_VANILLA_DESCRIPTOR_REGION)
    assert (
        rom.read_switched(ATTRIBUTES_ADDR, BANK, len(_VANILLA_ATTRIBUTES))
        == _VANILLA_ATTRIBUTES
    )
    assert rom.read_switched(TITLE_POINTER_ADDR, BANK, 2) == _VANILLA_TITLE_POINTER
    assert rom.read_switched(
        TITLE_DESCRIPTOR_ADDR, BANK, len(_VANILLA_TITLE_REGION)
    ) == (_VANILLA_TITLE_REGION)


def test_the_stroke_play_encoder_matches_the_rom(vanilla):
    rom = RomReader.from_bytes(vanilla)
    assert rom.read_switched(0xB00D, BANK, 19) == title_descriptor_bytes(
        "18H STROKE PLAY"
    )
    assert rom.read_switched(0xB02C, BANK, 30) == title_descriptor_bytes(
        "18H STROKE PLAY TOURNAMENT"
    )


def test_the_attribute_bytes_are_all_of_attribute_row_0(vanilla):
    """The literal really is what the card decodes to at PPU $23C0-$23C7."""
    rom = RomReader.from_bytes(vanilla)
    _, vram = load_graphics_table(rom, BANK, CARD_TABLE)
    assert bytes(vram.read(0x23C0 + i) for i in range(8)) == _VANILLA_ATTRIBUTES


def test_random_course_on_the_rom(vanilla):
    rom = RomReader.from_bytes(
        PatchStack([COURSE_MIRRORS_PATCH, scorecard_course_name_patch()])
        .build(vanilla)
        .rom
    )

    # Every course slot's handler is $AFC2, which draws the rewritten descriptor
    assert rom.read_switched(0xAEAA, BANK, 10) == bytes(
        [0x00, 0xC2, 0xAF, 0x01, 0xC2, 0xAF, 0x02, 0xC2, 0xAF, 0xFF]
    )
    assert rom.read_switched(0xAFC5, BANK, 2) == bytes([0xC8, 0xAF])
    assert rom.read_switched(DESCRIPTOR_ADDR, BANK, 17) == bytes(
        [
            0x69,
            0x20,
            0x0D,
            0x01,
            0x1B,
            0x0A,
            0x17,
            0x0D,
            0x18,
            0x16,
            0x24,
            0x0C,
            0x18,
            0x1E,
            0x1B,
            0x1C,
            0x0E,
        ]
    )
    assert rom.read_switched(ATTRIBUTES_ADDR, BANK, 8) == bytes(
        [0x00, 0x00, 0xF0, 0xF0, 0xF0, 0x30, 0x00, 0x00]
    )
    # No title given: the stroke play title is untouched
    assert rom.read_switched(TITLE_POINTER_ADDR, BANK, 2) == _VANILLA_TITLE_POINTER


def test_title_on_the_rom(vanilla):
    title = "RANDOMIZER SEED 0123456789"
    patch = scorecard_course_name_patch("ABCDEFGHIJKLM", title)
    rom = RomReader.from_bytes(
        PatchStack([COURSE_MIRRORS_PATCH, patch]).build(vanilla).rom
    )

    assert rom.read_switched(TITLE_POINTER_ADDR, BANK, 2) == bytes([0xE0, 0xAF])
    assert rom.read_switched(TITLE_DESCRIPTOR_ADDR, BANK, 30) == title_descriptor_bytes(
        title
    )
    # The 20-tile name is red across columns 6-25, as the card decodes
    _, vram = load_graphics_table(rom, BANK, CARD_TABLE)
    assert bytes(vram.read(0x23C0 + i) for i in range(8)) == bytes(
        [0x00, 0xC0, 0xF0, 0xF0, 0xF0, 0xF0, 0x30, 0x00]
    )
    # The mode $01 handler after the vanilla descriptor is untouched
    assert rom.read_switched(0xB020, BANK, 3) == bytes([0x20, 0x62, 0xB1])
