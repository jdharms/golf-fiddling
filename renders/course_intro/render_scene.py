"""Rebuild the course intro screens straight out of the ROM.

Decodes the scene's four graphics tables, replays the nametable writes the
scene's phase handlers make, and renders the result with the sprite-0 raster
split at tile row 8.  See docs/course_intro_scene.md.
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

FONT_CHR = (6, 0xA781)          # landscape tiles + dialogue font -> PPU $1000
PORTRAIT_CHR = (8, 0xA945)      # $071D = 0
PALETTE = (12, 0x9777)
SPLIT_ROW = 8                   # sprite-0 split: rows 0-7 use CHR $0000

COURSES = [
    ("japan", (8, 0x9BDB), (8, 0xB723)),
    ("us", (8, 0xA452), (8, 0xB91B)),
    ("uk", (8, 0xA452), (8, 0xBB04)),
]


def nametable_write(rom, bank, cpu_addr, vram, fill_mode):
    """One WriteNametableTiles ($CE84) or WriteNametableTilesMode1 ($CE75) descriptor."""
    data = rom.read_switched(0x8000, bank, 0x4000)
    o = cpu_addr - 0x8000
    dest = data[o] | (data[o + 1] << 8)
    width_byte, height = data[o + 2], data[o + 3]
    width = width_byte & 0x3F
    o += 4
    if width_byte & 0x80:
        o = (data[o] | (data[o + 1] << 8)) - 0x8000
    repeat = fill_mode or bool(width_byte & 0x40)
    for row in range(height):
        for col in range(width):
            vram.write(dest + row * 0x20 + col, data[o if repeat else o + row * width + col])


def rect_list(rom, bank, cpu_addr, vram, fill=0x02):
    """A $9615 step: 4-byte (dest_lo, dest_hi, w, h) rects, $00-terminated."""
    data = rom.read_switched(0x8000, bank, 0x4000)
    o = cpu_addr - 0x8000
    while data[o]:
        dest = data[o] | (data[o + 1] << 8)
        for row in range(data[o + 3]):
            for col in range(data[o + 2]):
                vram.write(dest + row * 0x20 + col, fill)
        o += 4


def build(rom, chr_table, nt_table):
    vram = VideoMemory()
    load_graphics_table(rom, *FONT_CHR, vram)
    load_graphics_table(rom, *chr_table, vram)
    load_graphics_table(rom, *PORTRAIT_CHR, vram)
    load_graphics_table(rom, *nt_table, vram)

    nametable_write(rom, 12, 0x9847, vram, False)   # $94CC
    nametable_write(rom, 12, 0x9610, vram, True)    # phase 0/1
    steps = rom.read_switched(0x96E3, 12, 24)
    for i in range(12):                             # phase 2, the box opening
        rect_list(rom, 12, steps[2 * i] | (steps[2 * i + 1] << 8), vram)
    nametable_write(rom, 12, 0x98CB, vram, False)   # phase 3
    nametable_write(rom, 12, 0x98DA, vram, False)
    nametable_write(rom, 12, 0x98E9, vram, True)    # phase 4
    nametable_write(rom, 12, 0x98EE, vram, True)
    return vram


def render(rom, vram, out_path):
    pal = rom.read_switched(PALETTE[1], PALETTE[0], 32)
    img = Image.new("RGB", (256, 240))
    px = img.load()
    for ty in range(30):
        base = 0x0000 if ty < SPLIT_ROW else 0x1000
        for tx in range(32):
            tile = vram.data[0x2000 + ty * 32 + tx]
            attr = vram.data[0x23C0 + (ty // 4) * 8 + (tx // 4)]
            shift = ((ty % 4) // 2) * 4 + ((tx % 4) // 2) * 2
            palette_index = (attr >> shift) & 3
            rows = vram.tile(tile, base)
            for y in range(8):
                for x in range(8):
                    value = rows[y][x]
                    nes = pal[0] if value == 0 else pal[palette_index * 4 + value]
                    px[tx * 8 + x, ty * 8 + y] = NES_SYSTEM_PALETTE[nes & 0x3F]
    img.resize((512, 480), Image.NEAREST).save(out_path)
    print("wrote", out_path)


def main():
    rom = RomReader(os.path.join(ROOT, "nes_open_us.nes"))
    for name, chr_table, nt_table in COURSES:
        render(rom, build(rom, chr_table, nt_table), os.path.join(HERE, f"scene_{name}.png"))


if __name__ == "__main__":
    main()
