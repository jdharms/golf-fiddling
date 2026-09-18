"""
Course music: the eight course themes a manifest can name, under stable slugs.

A slug names the course a theme belongs to, with the catalog's lineage prefixes: `nes_us`
for the US ROM's US course, `jp_france` for Mario Open's France course. Music ids collide
between the two ROMs (both have a $03), so a theme is always a ROM and an id together.
"""

import random
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from .catalog import JP_ROM, REPO_ROOT, US_ROM

RANDOM = "random"

MUSIC_DUMPS: Mapping[str, Path] = {
    US_ROM: REPO_ROOT / "data" / "music" / "music_us_courses.json",
    JP_ROM: REPO_ROOT / "data" / "music" / "music_jp_courses.json",
}


class MusicError(ValueError):
    """A slug that names no course theme."""


@dataclass(frozen=True)
class Track:
    slug: str
    rom: str
    #: the music id in its ROM, and in that ROM's `golf-export-music --dump` document
    music_id: int


TRACKS: Mapping[str, Track] = {
    track.slug: track
    for track in [
        Track("nes_japan", US_ROM, 0x03),
        Track("nes_us", US_ROM, 0x02),
        Track("nes_uk", US_ROM, 0x04),
        Track("jp_japan", JP_ROM, 0x04),
        Track("jp_australia", JP_ROM, 0x03),
        Track("jp_france", JP_ROM, 0x0B),
        Track("jp_hawaii", JP_ROM, 0x02),
        Track("jp_uk", JP_ROM, 0x0C),
    ]
}


def track(slug: str) -> Track:
    try:
        return TRACKS[slug]
    except KeyError:
        raise MusicError(
            f"unknown music {slug!r}: expected one of {', '.join(TRACKS)}"
        ) from None


def choose_music(rng: random.Random, include_mario_open: bool) -> str:
    """A uniform draw of a slug, from the NES Open themes alone unless told otherwise."""
    candidates = sorted(
        slug
        for slug, theme in TRACKS.items()
        if include_mario_open or theme.rom == US_ROM
    )
    return rng.choice(candidates)
