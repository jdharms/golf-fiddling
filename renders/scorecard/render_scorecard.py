"""Rebuild the tournament scorecard screen straight out of the ROM.

Decodes the two graphics tables `DrawScorecardScreen` ($AE76, bank 2) loads,
then replays the nametable writes it makes for a given game mode and course.
The per-player score columns are left empty - those come from RAM, not ROM.
See docs/scorecard.md.
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

BANK = 2
CHR_TABLE = 0xB469              # -> PPU $1000
NAMETABLE_TABLE = 0xB90B        # -> PPU $2000
PALETTE = 0xB0EB

COURSE_NAME = {0: 0xAFC8, 1: 0xAFDE, 2: 0xAFF1}
TITLE = {0: 0xB00D, 1: 0xB02C, 2: 0xB05B, 4: 0xB085, 5: 0xB0A3, 7: 0xB0DA}

COURSE_HOLE_OFFSET = 0xDBBB     # per course, into the 54-hole metadata tables
PAR = 0xDD05
DISTANCE = (0xDD3B, 0xDD71, 0xDDA7)     # hundreds, tens, ones
HANDICAP = 0xDDDD

BLANK = 0x52                    # the tile leading-zero suppression uses
RULE = 0x51                     # thin vertical column rule


def two_digit_tiles(value):
    """$AF80: A -> (tens tile, ones tile), leading zero blanked."""
    tens = 0x3F
    while value >= 0:
        tens += 1
        value -= 10
    return (BLANK if tens == 0x40 else tens), (value + 10) | 0x40


def write_rect(vram, ppu, width, rows, data):
    for row in range(rows):
        for col in range(width):
            vram.write(ppu + row * 0x20 + col, data[row * width + col])


def write_descriptor(rom, vram, cpu_addr):
    """One WriteNametableTiles ($CE84) descriptor held in ROM."""
    dest_lo, dest_hi, header, rows = rom.read_switched(cpu_addr, BANK, 4)
    width = header & 0x3F
    body = rom.read_switched(cpu_addr + 4, BANK, width * rows)
    write_rect(vram, dest_lo | (dest_hi << 8), width, rows, body)


def build(rom, course, mode, holes_played):
    vram = VideoMemory()
    load_graphics_table(rom, BANK, CHR_TABLE, vram)
    load_graphics_table(rom, BANK, NAMETABLE_TABLE, vram)

    write_descriptor(rom, vram, COURSE_NAME[course])
    write_descriptor(rom, vram, TITLE[mode])

    # $AEB9-$AF2D: 18 rows of yardage / handicap / par, drawn bottom-up.
    base = rom.read_fixed(COURSE_HOLE_OFFSET, 3)[course]
    par = rom.read_fixed(PAR, 54)
    hundreds, tens, ones = (rom.read_fixed(a, 54) for a in DISTANCE)
    handicap = rom.read_fixed(HANDICAP, 54)

    ppu = 0x22E6
    hole = base + 0x11
    for _ in range(18):
        hcp_tens, hcp_ones = two_digit_tiles(handicap[hole])
        write_rect(vram, ppu, 9, 1, [
            hundreds[hole] | 0x40, tens[hole] | 0x40, ones[hole] | 0x40,
            BLANK, RULE, hcp_tens, hcp_ones, RULE, par[hole] | 0x40,
        ])
        ppu -= 0x20
        hole -= 1

    # $AF2F: total yardage, first digit hardcoded to $47.  $AF54: holes played.
    total = [0x47] + [
        rom.read_switched(table + course, BANK, 1)[0] | 0x40
        for table in (0xAF71, 0xAF74, 0xAF77)
    ]
    write_rect(vram, 0x2305, 4, 1, total)
    write_rect(vram, 0x2325, 2, 1, list(two_digit_tiles(holes_played)))
    return vram


def render(rom, vram, out_path):
    pal = rom.read_switched(PALETTE, BANK, 32)
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
        vram = build(rom, course, mode=1, holes_played=18)
        render(rom, vram, os.path.join(HERE, f"scorecard_{name}.png"))


if __name__ == "__main__":
    main()
