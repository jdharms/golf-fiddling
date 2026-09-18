"""Unit tests for the scorecard course name patch."""

from itertools import pairwise

import pytest

from golf.core import rom_utils
from golf.core.patches import (
    COURSE_MIRRORS_PATCH,
    PatchError,
    scorecard_course_name_patch,
)
from golf.core.patches.scorecard_course_name import (
    _VANILLA_ATTRIBUTES,
    _VANILLA_DESCRIPTOR_REGION,
    DESCRIPTOR_ADDR,
    MAX_TILES,
    TITLE_DESCRIPTOR_ADDR,
    attribute_bytes,
    course_name_text,
    descriptor_bytes,
    first_column,
    title_descriptor_bytes,
    title_font_tiles,
    title_text,
)

LONGEST_NAME = "ABCDEFGHIJKLM"
LONGEST_TITLE = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"


class MockRomWriter:
    """A bare PRG image with every sub-patch's and requirement's original bytes."""

    def __init__(self, patch):
        self.data = bytearray(0x40000)
        for leaf in [*COURSE_MIRRORS_PATCH.patches, *patch.patches]:
            self.write_prg(leaf.prg_offset, leaf.original)

    def read_prg(self, prg_offset: int, length: int) -> bytes:
        return bytes(self.data[prg_offset : prg_offset + length])

    def write_prg(self, prg_offset: int, data: bytes):
        self.data[prg_offset : prg_offset + len(data)] = data


class TestEncoding:
    def test_title_font_tiles(self):
        assert title_font_tiles("AZ 09") == bytes([0x0A, 0x23, 0x24, 0x00, 0x09])

    def test_text_is_upper_cased_with_the_suffix(self):
        assert course_name_text("random") == "RANDOM COURSE"

    def test_japan_reproduces_the_vanilla_descriptor_and_attributes(self):
        """Checks the tile mapping, centring, header and colour rule against the ROM."""
        assert descriptor_bytes("JAPAN COURSE") == _VANILLA_DESCRIPTOR_REGION[:16]
        assert attribute_bytes("JAPAN COURSE") == _VANILLA_ATTRIBUTES

    def test_us_reproduces_the_vanilla_descriptor(self):
        # The vanilla red band is sized for JAPAN COURSE, so only the descriptor matches
        us = bytes(
            [
                0x6B,
                0x20,
                0x09,
                0x01,
                0x1E,
                0x1C,
                0x24,
                0x0C,
                0x18,
                0x1E,
                0x1B,
                0x1C,
                0x0E,
            ]
        )
        assert descriptor_bytes("US COURSE") == us

    def test_random_course(self):
        text = course_name_text("RANDOM")
        assert first_column(text) == 9
        assert descriptor_bytes(text)[:4] == bytes([0x69, 0x20, 0x0D, 0x01])
        # Column 9 falls in the lower-left quadrant of the columns 8-11 byte, 21 in the columns 20-23 one's
        assert attribute_bytes(text) == bytes(
            [0x00, 0x00, 0xF0, 0xF0, 0xF0, 0x30, 0x00, 0x00]
        )

    @pytest.mark.parametrize("name", ["ABCDEFGHIJKL", "ABCDEFGHIJKLM"])
    def test_names_past_the_vanilla_band_fill_columns_6_to_25(self, name):
        # 19 tiles start at column 6 and end at 24, which shares a quadrant with 25
        text = course_name_text(name)
        assert first_column(text) == 6
        assert attribute_bytes(text) == bytes(
            [0x00, 0xC0, 0xF0, 0xF0, 0xF0, 0xF0, 0x30, 0x00]
        )

    def test_rejects_a_name_too_long_for_its_descriptor(self):
        with pytest.raises(ValueError, match="at most 13 characters"):
            course_name_text("ABCDEFGHIJKLMN")

    @pytest.mark.parametrize("name", ["RANDOM!", "CAFÉ", "A-B"])
    def test_rejects_characters_the_font_lacks(self, name):
        with pytest.raises(ValueError, match="title font cannot render"):
            course_name_text(name)


class TestTitleEncoding:
    def test_stroke_play_reproduces_the_vanilla_descriptor(self):
        """The descriptor at $B00D, which the title replaces."""
        vanilla = bytes(
            [
                0x89,
                0x20,
                0x0F,
                0x01,
                0x01,
                0x08,
                0x11,
                0x24,
                0x1C,
                0x1D,
                0x1B,
                0x18,
                0x14,
                0x0E,
                0x24,
                0x19,
                0x15,
                0x0A,
                0x22,
            ]
        )
        assert title_descriptor_bytes("18H STROKE PLAY") == vanilla

    def test_match_play_is_centred_like_vanilla(self):
        # $B085: PPU $2089, width 14
        assert title_descriptor_bytes("18H MATCH PLAY")[:3] == bytes([0x89, 0x20, 0x0E])

    def test_the_longest_title_starts_at_column_3(self):
        # Where vanilla puts 18H STROKE PLAY TOURNAMENT ($B02C: PPU $2083, width 26)
        title = title_text("abcdefghijklmnopqrstuvwxyz")
        assert title_descriptor_bytes(title)[:3] == bytes([0x83, 0x20, 0x1A])

    @pytest.mark.parametrize(
        ("title", "message"),
        [
            ("ABCDEFGHIJKLMNOPQRSTUVWXYZ0", "1-26 characters"),
            ("", "1-26 characters"),
            ("SEED #1", "title font cannot render"),
        ],
    )
    def test_rejects_titles_that_cannot_be_drawn(self, title, message):
        with pytest.raises(ValueError, match=message):
            title_text(title)

    def test_title_descriptor_follows_the_longest_name_descriptor(self):
        assert TITLE_DESCRIPTOR_ADDR == DESCRIPTOR_ADDR + 4 + MAX_TILES


class TestPatch:
    def test_requires_course_mirrors(self):
        assert list(scorecard_course_name_patch().requires) == [COURSE_MIRRORS_PATCH]

    def test_writes_land_in_bank_2(self):
        offsets = {
            leaf.name: leaf.prg_offset for leaf in scorecard_course_name_patch().patches
        }
        assert offsets == {
            "scorecard_course_name_dispatch": rom_utils.cpu_to_prg_switched(0xAEAE, 2),
            "scorecard_course_name_descriptor": rom_utils.cpu_to_prg_switched(
                0xAFC8, 2
            ),
            "scorecard_course_name_attributes": rom_utils.cpu_to_prg_switched(
                0xB9F0, 2
            ),
        }

    def test_every_slot_uses_the_japan_handler(self):
        (dispatch, *_) = scorecard_course_name_patch().patches
        assert dispatch.patched == bytes([0xC2, 0xAF, 0x02, 0xC2, 0xAF])

    def test_title_writes(self):
        leaves = {
            leaf.name: leaf
            for leaf in scorecard_course_name_patch(title="SEED 1234").patches
        }
        descriptor = leaves["scorecard_course_name_title_descriptor"]
        pointer = leaves["scorecard_course_name_title_pointer"]
        assert descriptor.prg_offset == rom_utils.cpu_to_prg_switched(0xAFE0, 2)
        assert descriptor.patched == title_descriptor_bytes("SEED 1234")
        assert pointer.prg_offset == rom_utils.cpu_to_prg_switched(0xB00A, 2)
        assert (pointer.original, pointer.patched) == (
            bytes([0x0D, 0xB0]),
            bytes([0xE0, 0xAF]),
        )

    @pytest.mark.parametrize(
        ("name", "title"),
        [("RANDOM", None), ("X", "A"), (LONGEST_NAME, LONGEST_TITLE)],
    )
    def test_apply_then_is_applied(self, name, title):
        patch = scorecard_course_name_patch(name, title)
        rom = MockRomWriter(patch)
        COURSE_MIRRORS_PATCH.apply(rom)

        assert patch.can_apply(rom)
        assert not patch.is_applied(rom)
        patch.apply(rom)
        assert patch.is_applied(rom)

    def test_the_longest_name_and_title_do_not_overlap(self):
        leaves = scorecard_course_name_patch(LONGEST_NAME, LONGEST_TITLE).patches
        spans = sorted(
            (leaf.prg_offset, leaf.prg_offset + len(leaf.patched)) for leaf in leaves
        )
        assert all(end <= start for (_, end), (start, _) in pairwise(spans))

    def test_the_longest_title_ends_before_the_mode_0_handler(self):
        leaves = {
            leaf.name: leaf
            for leaf in scorecard_course_name_patch(LONGEST_NAME, LONGEST_TITLE).patches
        }
        descriptor = leaves["scorecard_course_name_title_descriptor"]
        assert descriptor.prg_offset + len(
            descriptor.patched
        ) == rom_utils.cpu_to_prg_switched(0xAFFE, 2)

    def test_refuses_rom_without_course_mirrors(self):
        patch = scorecard_course_name_patch()
        with pytest.raises(PatchError, match="requires course_mirrors"):
            patch.apply(MockRomWriter(patch))
