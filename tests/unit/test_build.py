"""Unit tests for the two-stage build's pieces that need no ROM."""

import pytest

from golf.core import rom_utils
from golf.core.patches import QrCredentials, course_theme_patch
from golf.core.patches.course_theme import VANILLA_COURSE_BGM
from golf.core.patches.music_import import MusicImportPatch
from golf.core.patches.sram_defaults import Club, magic_bytes
from golf.qr import payload
from golf.randomizer.build import (
    BuildError,
    PlayerOptions,
    clubs_from_labels,
    credentials_for,
    finishing_steps,
    music_step,
    player_id_bytes,
    seed_id_bytes,
)
from golf.randomizer.catalog import JP_ROM, US_ROM
from golf.randomizer.manifest import ClubRules
from golf.randomizer.music import TRACKS

KEYS = (bytes(range(1, 9)), bytes(range(9, 17)))


def options(**overrides) -> PlayerOptions:
    return PlayerOptions(**({"player_name": "LUIGI", "clubs": {Club.W1, Club.PW}} | overrides))


class TestPlayerOptions:
    def test_the_putter_is_added(self):
        assert options().clubs == {Club.W1, Club.PW, Club.PT}

    def test_valid_options_pass_open_rules(self):
        options().check(ClubRules())

    def test_over_the_max(self):
        with pytest.raises(BuildError, match="at most 2 clubs"):
            options().check(ClubRules(max=2))

    def test_a_banned_club(self):
        with pytest.raises(BuildError, match="bans 1W"):
            options().check(ClubRules(banned={Club.W1, Club.SW}))

    def test_a_required_bag_must_match(self):
        options().check(ClubRules(required_bag={Club.W1, Club.PW}))
        with pytest.raises(BuildError, match="requires the bag"):
            options().check(ClubRules(required_bag={Club.W1}))

    @pytest.mark.parametrize(
        "overrides, message",
        [
            (dict(player_name="LUIGI!"), "cannot store"),
            (dict(player_name=""), "1-10 characters"),
            (dict(player_name="ABCDEFGHIJK"), "1-10 characters"),
            (dict(bgm="on"), "bgm"),
        ],
    )
    def test_rejects_options_no_rom_can_hold(self, overrides, message):
        with pytest.raises(BuildError, match=message):
            options(**overrides)

    def test_clubs_from_labels(self):
        assert clubs_from_labels(["1w", "PW"]) == {Club.W1, Club.PW}
        with pytest.raises(BuildError, match="unknown club"):
            clubs_from_labels(["5W"])


class TestCredentials:
    def test_integers_become_big_endian_fields(self):
        credentials = credentials_for(0x0102030405060708, 0x0A0B0C0D, KEYS)
        assert credentials.seed_id == bytes.fromhex("0102030405060708")
        assert credentials.player_ids == (bytes.fromhex("0a0b0c0d"),) * 2
        assert credentials.keys == KEYS
        assert int.from_bytes(credentials.seed_id, "big") == 0x0102030405060708

    def test_field_lengths(self):
        assert len(seed_id_bytes(1)) == payload.SEED_ID_LEN
        assert len(player_id_bytes(1)) == payload.PLAYER_ID_LEN
        assert seed_id_bytes(62**10 - 1) == (62**10 - 1).to_bytes(8, "big")

    @pytest.mark.parametrize("value", [0, -1, 1 << 64, True, "1"])
    def test_rejects_seed_ids_the_server_rejects_or_the_field_cannot_hold(self, value):
        with pytest.raises(BuildError, match="qr_seed_id"):
            seed_id_bytes(value)

    @pytest.mark.parametrize("value", [0, -1, 1 << 32, False])
    def test_rejects_bad_player_ids(self, value):
        with pytest.raises(BuildError, match="player_id"):
            player_id_bytes(value)

    def test_rejects_bad_keys(self):
        with pytest.raises(BuildError, match="key"):
            credentials_for(1, 1, (b"short", KEYS[1]))


class TestMusicStep:
    @pytest.mark.parametrize("slug", [slug for slug, theme in TRACKS.items() if theme.rom == US_ROM])
    def test_nes_open_themes_only_repoint_the_course_bgm_table(self, slug):
        step = music_step(slug)
        assert step.name == "course_theme"
        assert step.patched == bytes([TRACKS[slug].music_id]) * 3

    @pytest.mark.parametrize("slug", [slug for slug, theme in TRACKS.items() if theme.rom == JP_ROM])
    def test_mario_open_themes_are_imported(self, slug):
        step = music_step(slug)
        assert isinstance(step, MusicImportPatch)
        assert step.track == TRACKS[slug].music_id


class TestCourseTheme:
    def test_writes_every_course_bgm_entry(self):
        patch = course_theme_patch(0x04)
        assert patch.prg_offset == rom_utils.cpu_to_prg_fixed(0xDA14)
        assert patch.original == VANILLA_COURSE_BGM
        assert patch.patched == b"\x04\x04\x04"

    @pytest.mark.parametrize("music_id", [0x01, 0x05, 0x0B])
    def test_only_us_course_themes(self, music_id):
        with pytest.raises(ValueError, match="not a US ROM course theme"):
            course_theme_patch(music_id)


class TestFinishingSteps:
    def test_signed_in(self):
        credentials = credentials_for(1, 2, KEYS)
        steps = finishing_steps(options(), 0x5247, credentials)
        assert [step.name for step in steps] == ["sram_defaults", "qr_credentials"]

    def test_guest(self):
        assert [step.name for step in finishing_steps(options(), 0x5247, None)] == ["sram_defaults", "qr_disable"]

    def test_the_seed_magic_is_written(self):
        (defaults, _) = finishing_steps(options(bgm=False), 0x5247, None)
        writes = {sub.name: sub.patched for sub in defaults.patches}
        assert writes["sram_defaults_magic_write_6001"] + writes["sram_defaults_magic_write_6002"] == magic_bytes(0x5247)
        assert writes["sram_defaults_magic_check_6001"] + writes["sram_defaults_magic_check_6002"] == magic_bytes(0x5247)
        assert "sram_defaults_bgm_off" in writes
        assert writes["sram_defaults_player_name"] == b"LUIGI     "

    def test_credentials_type(self):
        assert isinstance(credentials_for(1, 1, KEYS), QrCredentials)
