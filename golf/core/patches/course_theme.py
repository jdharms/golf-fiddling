"""
Course theme: make one of the US ROM's own course themes play on every course.

`CourseBgmTable` (fixed bank `$DA14`) maps courses Japan/US/UK to music
`$03`/`$02`/`$04`. Writing one id into all three entries makes that theme play
whichever course slot is selected; under `menu_trim`, which pins `CurrCourse`
to 0, it is the theme a randomized ROM plays.

This is for themes already in the ROM. A theme from another ROM goes through
`music_import` with `track=`, which also writes `CourseBgmTable`, so a stack
holds one or the other.
"""

from golf.core import rom_utils

from .byte_patch import BytePatch
from .music_import import COURSE_TRACKS

COURSE_BGM_TABLE_ADDR = 0xDA14
VANILLA_COURSE_BGM = bytes([0x03, 0x02, 0x04])


def course_theme_patch(music_id: int) -> BytePatch:
    """Point every `CourseBgmTable` entry at `music_id`, one of the US ROM's course themes."""
    if music_id not in COURSE_TRACKS:
        themes = ", ".join(f"${track:02X}" for track in COURSE_TRACKS)
        raise ValueError(
            f"music ${music_id:02X} is not a US ROM course theme; expected one of {themes}"
        )
    return BytePatch(
        name="course_theme",
        description=f"Play music ${music_id:02X} on every course (CourseBgmTable)",
        prg_offset=rom_utils.cpu_to_prg_fixed(COURSE_BGM_TABLE_ADDR),
        original=VANILLA_COURSE_BGM,
        patched=bytes([music_id] * len(VANILLA_COURSE_BGM)),
    )
