"""Rebuild the pre-hole signpost screen straight out of the ROM.

Replays `LC_AC2F_DrawSignpostCard` (bank 12 `$AC2F`): loads the signpost CHR +
blank nametable, picks one of the 5 course/contest banner blobs, and draws the
hole number / par / distance with the big 2x2-tile digit font.  The replay
itself lives in `golf/core/signpost.py`, which the importer shares; this script
is just the picture-making front end.  See docs/prehole_signpost.md.
"""

import os
import sys

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from golf.core.palettes import NES_SYSTEM_PALETTE
from golf.core.rom_reader import RomReader
from golf.core.signpost import build_screen, render_screen

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HERE = os.path.dirname(os.path.abspath(__file__))


def render(vram, pal, out_path):
    img = Image.new("RGB", (256, 240))
    px = img.load()
    for y, row in enumerate(render_screen(vram, pal)):
        for x, value in enumerate(row):
            px[x, y] = NES_SYSTEM_PALETTE[value & 0x3F]
    img.resize((512, 480), Image.NEAREST).save(out_path)
    print("wrote", out_path)


def main():
    rom = RomReader(os.path.join(ROOT, "nes_open_us.nes"))

    for name, course in (("japan", 0), ("us", 1), ("uk", 2)):
        for hole in (1, 9, 10, 18):
            vram, pal = build_screen(rom, course, hole)
            render(vram, pal, os.path.join(HERE, f"signpost_{name}_hole{hole:02d}.png"))

    # Contest banners are course-independent (CurrCourse is discarded when
    # HoleMatchStatus != 0) - render both, using course 0's hole data for the
    # numbers since the banner itself doesn't depend on course.
    vram, pal = build_screen(rom, 0, 5, hole_match_status=1, contest_palette_patch=True)
    render(vram, pal, os.path.join(HERE, "signpost_longdrive_contest.png"))
    vram, pal = build_screen(rom, 1, 12, hole_match_status=2, contest_palette_patch=True)
    render(vram, pal, os.path.join(HERE, "signpost_nearestpin_contest.png"))


if __name__ == "__main__":
    main()
