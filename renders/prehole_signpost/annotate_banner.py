"""Annotate the course-name banner with tile indices, colour-coded by role.

Answers "what's actually reusable background vs. baked-in art" by rendering
the 16x6 banner blob at high zoom with each tile's hex index and a coloured
border: green = confirmed background filler (appears identically in letter-free
rows and as spacing beside letters), grey = the signpost's structural frame/
shadow, red = unique wordmark/letter art (not reusable for other text).
See docs/prehole_signpost.md "Is there a reusable background tile?".
"""

import os
import sys

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from render_signpost import BANK, CHR_BANK, CHR_TABLES, PALETTE, banner_index, write_banner
from golf.core.graphics_codec import VideoMemory, load_graphics_table
from golf.core.palettes import NES_SYSTEM_PALETTE
from golf.core.rom_reader import RomReader

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))

FRAME = {0x0E, 0x1E, 0xDF, 0xCE, 0x2E, 0xEE}
BACKGROUND = {0x3F, 0x4F, 0x5F, 0x6F, 0x7F}
# everything else in the banner is unique wordmark/letter art

ZOOM = 24
DEST = 0x20A8
WIDTH, ROWS = 16, 6


def main():
    rom = RomReader(os.path.join(ROOT, "nes_open_us.nes"))
    vram = VideoMemory()
    for addr in CHR_TABLES:
        load_graphics_table(rom, CHR_BANK, addr, vram)
    write_banner(rom, vram, banner_index(0, 0))  # Japan, for the widest label set
    pal = rom.read_switched(PALETTE, BANK, 32)

    img = Image.new("RGB", (WIDTH * ZOOM, ROWS * ZOOM))
    draw = ImageDraw.Draw(img)

    # attribute byte covering this region (constant across the block in practice)
    attr = vram.data[0x23C0 + (5 // 4) * 8 + (8 // 4)]
    palette_index = (attr >> (((5 % 4) // 2) * 4 + ((8 % 4) // 2) * 2)) & 3

    for ty in range(ROWS):
        for tx in range(WIDTH):
            tile = vram.data[DEST + ty * 0x20 + tx]
            rows = vram.tile(tile, 0x1000)
            for y in range(8):
                for x in range(8):
                    value = rows[y][x]
                    nes = pal[0] if value == 0 else pal[palette_index * 4 + value]
                    color = NES_SYSTEM_PALETTE[nes & 0x3F]
                    ox, oy = tx * ZOOM + x * (ZOOM // 8), ty * ZOOM + y * (ZOOM // 8)
                    draw.rectangle([ox, oy, ox + ZOOM // 8 - 1, oy + ZOOM // 8 - 1], fill=color)

            if tile in FRAME:
                border = (128, 128, 128)
            elif tile in BACKGROUND:
                border = (0, 220, 0)
            else:
                border = (255, 40, 40)
            x0, y0 = tx * ZOOM, ty * ZOOM
            draw.rectangle([x0, y0, x0 + ZOOM - 1, y0 + ZOOM - 1], outline=border, width=2)
            draw.text((x0 + 2, y0 + 1), f"{tile:02X}", fill=(255, 255, 0))

    out = os.path.join(HERE, "banner_annotated_japan.png")
    img.save(out)
    print("wrote", out)
    print("green border = confirmed background filler, grey = signpost frame/shadow,")
    print("red = unique wordmark/letter art (JAPAN + COURSE)")


if __name__ == "__main__":
    main()
