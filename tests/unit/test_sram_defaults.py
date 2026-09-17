"""Unit tests for the SRAM defaults patch."""

import pytest

from golf.core import rom_utils
from golf.core.patches import Club, sram_defaults_patch, sram_defaults_patches
from golf.core.patches.sram_defaults import (
    VANILLA_CLUBS,
    VANILLA_MAGIC,
    club_bag_bytes,
    club_labels,
    magic_bytes,
    parse_club,
    player_name_bytes,
)


def prg(cpu_addr: int) -> int:
    return rom_utils.cpu_to_prg_switched(cpu_addr, 9)


class MockRomWriter:
    """A bare PRG image with every sub-patch's original bytes."""

    def __init__(self, patch):
        self.data = bytearray(0x40000)
        for leaf in patch.patches:
            self.write_prg(leaf.prg_offset, leaf.original)

    def read_prg(self, prg_offset: int, length: int) -> bytes:
        return bytes(self.data[prg_offset : prg_offset + length])

    def write_prg(self, prg_offset: int, data: bytes):
        self.data[prg_offset : prg_offset + len(data)] = data


class TestClubs:
    def test_labels_follow_the_screen(self):
        assert [club.label for club in Club] == [
            "1W", "2W", "3W", "4W", "1I", "2I", "3I", "4I", "5I", "6I", "7I", "8I", "9I", "PW", "SW", "PT",
        ]

    def test_parse_is_case_insensitive(self):
        assert parse_club(" pw ") is Club.PW
        assert parse_club("5i") is Club.I5

    def test_parse_rejects_unknown_clubs(self):
        with pytest.raises(ValueError, match="unknown club '5W'"):
            parse_club("5W")

    def test_vanilla_bag_is_the_rom_table(self):
        assert club_bag_bytes(VANILLA_CLUBS) == bytes(
            [0x00, 0x01, 0x02, 0x05, 0x06, 0x07, 0x08, 0x09, 0x0A, 0x0B, 0x0C, 0x0D, 0x0E, 0x0F]
        )

    def test_bag_is_sorted_with_the_putter_added_and_padded(self):
        assert club_bag_bytes(["SW", Club.W1, "7i"]) == bytes([0x00, 0x0A, 0x0E, 0x0F] + [0xFF] * 10)

    def test_an_empty_bag_holds_the_putter(self):
        assert club_bag_bytes([]) == bytes([0x0F] + [0xFF] * 13)

    def test_fourteen_clubs_with_the_putter_fit(self):
        assert club_bag_bytes([club for club in Club if club not in (Club.W4, Club.I1)])[-1] == 0x0F

    def test_fourteen_clubs_without_the_putter_do_not(self):
        with pytest.raises(ValueError, match="at most 14 clubs including the putter, got 15"):
            club_bag_bytes([club for club in Club if club not in (Club.PT, Club.W4)])

    def test_rejects_repeated_clubs(self):
        with pytest.raises(ValueError, match="more than once: 1W, PW"):
            club_bag_bytes(["PW", "1W", "pw", Club.W1])

    def test_labels_of_a_bag(self):
        assert club_labels(club_bag_bytes(["3W", "PT"])) == ["3W", "PT"]


class TestPlayerName:
    def test_is_upper_cased_and_padded(self):
        assert player_name_bytes("mario") == b"MARIO     "

    def test_takes_dots_and_spaces(self):
        assert player_name_bytes("J.D. SMITH") == b"J.D. SMITH"

    @pytest.mark.parametrize(("name", "message"), [
        ("", "1-10 characters"),
        ("ABCDEFGHIJK", "1-10 characters"),
        ("MARIO1", "cannot store: '1'"),
        ("MARIO!", "cannot store: '!'"),
    ])
    def test_rejects_names_that_cannot_be_stored(self, name, message):
        with pytest.raises(ValueError, match=message):
            player_name_bytes(name)


class TestMagic:
    def test_vanilla_is_5s(self):
        assert magic_bytes(VANILLA_MAGIC) == b"5S"

    @pytest.mark.parametrize("magic", [0x0053, 0x3500, 0xFF53, 0x35FF, 0x0000, 0xFFFF])
    def test_rejects_blank_sram_bytes(self, magic):
        with pytest.raises(ValueError, match=r"may not be \$00 or \$FF"):
            magic_bytes(magic)

    @pytest.mark.parametrize("magic", [-1, 0x10000])
    def test_rejects_values_outside_16_bits(self, magic):
        with pytest.raises(ValueError, match="16-bit"):
            magic_bytes(magic)


class TestPatch:
    def test_vanilla_defaults_write_nothing(self):
        assert sram_defaults_patches() == []

    def test_player_name(self):
        (leaf,) = sram_defaults_patches(player_name="luigi")
        assert (leaf.prg_offset, leaf.original, leaf.patched) == (prg(0xAD5B), b"MARIO     ", b"LUIGI     ")

    def test_clubs(self):
        (leaf,) = sram_defaults_patches(clubs=["1W", "PW"])
        assert leaf.prg_offset == prg(0xAE23)
        assert leaf.patched == bytes([0x00, 0x0D, 0x0F] + [0xFF] * 11)

    def test_bgm_off_turns_the_fill_loop_bpl_into_bne(self):
        (leaf,) = sram_defaults_patches(bgm=False)
        assert (leaf.prg_offset, leaf.original, leaf.patched) == (prg(0xAD4E), b"\x10", b"\xd0")

    def test_magic_rewrites_the_check_and_the_writes(self):
        leaves = sram_defaults_patches(sram_magic=0x1234)
        assert [(leaf.prg_offset, leaf.original, leaf.patched) for leaf in leaves] == [
            (prg(0xACC0), b"\x35", b"\x12"),
            (prg(0xACC7), b"\x53", b"\x34"),
            (prg(0xAD51), b"\x35", b"\x12"),
            (prg(0xAD56), b"\x53", b"\x34"),
        ]

    def test_an_invalid_magic_is_rejected_even_alone(self):
        with pytest.raises(ValueError, match="sram_magic"):
            sram_defaults_patch(sram_magic=0x00FF)

    def test_apply_then_is_applied(self):
        patch = sram_defaults_patch("RANDO", ["3W", "5I"], bgm=False, sram_magic=0x5244)
        rom = MockRomWriter(patch)

        assert patch.can_apply(rom)
        assert not patch.is_applied(rom)
        patch.apply(rom)
        assert patch.is_applied(rom)
