"""Unit tests for the course music slugs."""

import json
import random

import pytest

from golf.core import jp_rom_utils, rom_utils
from golf.randomizer.catalog import JP_ROM, US_ROM
from golf.randomizer.music import MUSIC_DUMPS, TRACKS, MusicError, choose_music, track


def test_slugs_match_the_music_dumps():
    us = json.loads(MUSIC_DUMPS[US_ROM].read_text())["course_bgm"]["music_ids"]
    jp = json.loads(MUSIC_DUMPS[JP_ROM].read_text())["course_bgm"]["music_ids"]
    expected = {
        f"nes_{course['name']}": (US_ROM, us[course["name"]])
        for course in rom_utils.COURSES
    }
    expected |= {
        course["name"]: (JP_ROM, jp[f"course_{slot}"])
        for slot, course in enumerate(jp_rom_utils.COURSES, start=1)
    }
    assert {
        slug: (theme.rom, theme.music_id) for slug, theme in TRACKS.items()
    } == expected


def test_nes_open_draws_never_pick_mario_open_themes():
    rng = random.Random(1)
    drawn = {choose_music(rng, include_mario_open=False) for _ in range(200)}
    assert drawn == {"nes_japan", "nes_us", "nes_uk"}


def test_mario_open_draws_cover_every_theme():
    rng = random.Random(1)
    assert {choose_music(rng, include_mario_open=True) for _ in range(500)} == set(
        TRACKS
    )


def test_unknown_slug():
    with pytest.raises(MusicError, match="unknown music"):
        track("nes_mars")
