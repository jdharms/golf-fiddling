"""Rebuild the pre-hole signpost screen straight out of the ROM.

Replays `LC_AC2F_DrawSignpostCard` (bank 12 `$AC2F`): loads the signpost CHR +
blank nametable, picks one of the 5 course/contest banner blobs, and draws the
hole number / par / distance with the big 2x2-tile digit font. See
docs/prehole_signpost.md.
"""

import os
import sys

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from golf.core.graphics_codec import VideoMemory, load_graphics_table
from golf.core.palettes import NES_SYSTEM_PALETTE
from golf.core.rom_reader import RomReader

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HERE = os.path.dirname(os.path.abspath(__file__))

CHR_BANK = 5
CHR_TABLES = (0xA69F, 0xA6DD, 0xB3B3)   # -> $0000, $1000 (font/texture), $2000 (blank card+attrs)

BANK = 12
BANNER_TABLE = 0xAD86        # 5 x 6-byte WriteNametableTiles descriptors
PALETTE = 0xADC4             # JapanSignpostData - shared by all 5 banners
DIGIT_PTR_TABLE = 0xB01C     # 11 entries (digits 0-9, then the narrow "1" prefix)

COURSE_HOLE_OFFSET = 0xDBBB
PAR = 0xDD05
DISTANCE = (0xDD3B, 0xDD71, 0xDDA7)      # hundreds, tens, ones


def write_rect(vram, ppu, width, rows, data):
    for row in range(rows):
        for col in range(width):
            vram.write(ppu + row * 0x20 + col, data[row * width + col])


def banner_index(course, hole_match_status):
    """LC_AC5D-LC_AC69: HoleMatchStatus!=0 overrides X with (status+2) entirely -
    CurrCourse is discarded, so the contest banners are course-independent."""
    if hole_match_status:
        return hole_match_status + 2
    return course


def write_banner(rom, vram, index):
    dest_lo, dest_hi, header, rows, ptr_lo, ptr_hi = rom.read_switched(
        BANNER_TABLE + index * 6, BANK, 6
    )
    width = header & 0x3F
    ptr = ptr_lo | (ptr_hi << 8)
    body = rom.read_switched(ptr, BANK, width * rows)
    write_rect(vram, dest_lo | (dest_hi << 8), width, rows, body)


def digit_tiles(rom, digit):
    """LC_AD0D_BufferBigDigit: digit -> (TL, TR, BL, BR)."""
    ptr_lo, ptr_hi = rom.read_switched(DIGIT_PTR_TABLE + digit * 2, BANK, 2)
    ptr = ptr_lo | (ptr_hi << 8)
    return rom.read_switched(ptr, BANK, 4)


def write_big_digits(rom, vram, dest, digits):
    """LC_AD31_FlushBigDigitBuffer: lay out N digits' 2x2 blocks side by side."""
    blocks = [digit_tiles(rom, d) for d in digits]
    top = [t for tl, tr, bl, br in blocks for t in (tl, tr)]
    bottom = [t for tl, tr, bl, br in blocks for t in (bl, br)]
    write_rect(vram, dest, len(digits) * 2, 2, top + bottom)


def hole_number_digits(hole_number_0based):
    """$AC84-$ACAF: HoleNumber ($94) is 0-based; 10 is the narrow '1' glyph."""
    if hole_number_0based < 9:
        dest = 0x2174
        digits = [hole_number_0based + 1]
    else:
        dest = 0x2172
        digits = [10, hole_number_0based - 9]
    return dest, digits


def build(rom, course, hole_1based, hole_match_status=0, contest_palette_patch=False):
    vram = VideoMemory()
    for addr in CHR_TABLES:
        load_graphics_table(rom, CHR_BANK, addr, vram)

    write_banner(rom, vram, banner_index(course, hole_match_status))

    hole0 = hole_1based - 1
    dest, digits = hole_number_digits(hole0)
    write_big_digits(rom, vram, dest, digits)

    base = rom.read_fixed(COURSE_HOLE_OFFSET, 3)[course]
    hole_idx = base + hole0
    par = rom.read_fixed(PAR, 54)[hole_idx]
    write_big_digits(rom, vram, 0x21D4, [par])

    hundreds, tens, ones = (rom.read_fixed(a, 54)[hole_idx] for a in DISTANCE)
    write_big_digits(rom, vram, 0x222A, [hundreds, tens, ones])

    pal = bytearray(rom.read_switched(PALETTE, BANK, 32))
    if contest_palette_patch:
        pal[0x047D - 0x0476] = 0x12
    return vram, pal


def render(vram, pal, out_path):
    img = Image.new("RGB", (256, 240))
    px = img.load()
    for ty in range(30):
        for tx in range(32):
            tile = vram.data[0x2000 + ty * 32 + tx]
            attr = vram.data[0x23C0 + (ty // 4) * 8 + (tx // 4)]
            shift = ((ty % 4) // 2) * 4 + ((tx % 4) // 2) * 2
            palette_index = (attr >> shift) & 3
            rows = vram.tile(tile, 0x1000)
            for y in range(8):
                for x in range(8):
                    value = rows[y][x]
                    nes = pal[0] if value == 0 else pal[palette_index * 4 + value]
                    px[tx * 8 + x, ty * 8 + y] = NES_SYSTEM_PALETTE[nes & 0x3F]
    img.resize((512, 480), Image.NEAREST).save(out_path)
    print("wrote", out_path)


def main():
    rom = RomReader(os.path.join(ROOT, "nes_open_us.nes"))

    for name, course in (("japan", 0), ("us", 1), ("uk", 2)):
        for hole in (1, 9, 10, 18):
            vram, pal = build(rom, course, hole)
            render(vram, pal, os.path.join(HERE, f"signpost_{name}_hole{hole:02d}.png"))

    # Contest banners are course-independent (CurrCourse is discarded when
    # HoleMatchStatus != 0) - render both, using course 0's hole data for the
    # numbers since the banner itself doesn't depend on course.
    vram, pal = build(rom, 0, 5, hole_match_status=1, contest_palette_patch=True)
    render(vram, pal, os.path.join(HERE, "signpost_longdrive_contest.png"))
    vram, pal = build(rom, 1, 12, hole_match_status=2, contest_palette_patch=True)
    render(vram, pal, os.path.join(HERE, "signpost_nearestpin_contest.png"))


if __name__ == "__main__":
    main()
