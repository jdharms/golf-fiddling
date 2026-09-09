"""Contact sheets of every golfer animation frame, decoded from the ROM.

Uses golf.core.golfer_sprites, so the sheets and the Aseprite exporter agree by
construction.  See docs/golfer_sprites.md.
"""

import os
import sys

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from golf.core.golfer_sprites import BODY_IN_FRONT_FRAMES, GOLFER_NAMES, GolferSprites
from golf.core.palettes import NES_SYSTEM_PALETTE
from golf.core.rom_reader import RomReader

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
HERE = os.path.dirname(os.path.abspath(__file__))
BG = (24, 26, 22)
CLUB = 0  # driver


def paint(px, vram, meta, palette, ox, oy, size, dx=0, dy=0):
    w, h = size
    for sprite in meta.sprites:
        rows = vram.tile(sprite.tile)
        for y in range(8):
            for x in range(8):
                value = rows[y][x]
                if value == 0:
                    continue
                px_x, px_y = ox + sprite.dx + dx + x, oy + sprite.dy + dy + y
                if 0 <= px_x < w and 0 <= px_y < h:
                    px[px_x, px_y] = NES_SYSTEM_PALETTE[palette[value] & 0x3F]


def sheet(sprites, out, putt=False, with_club=False, scale=3):
    rows = [sprites.body_frames(g, putt) for g in range(6)]
    clubs = [sprites.club_frames(g, CLUB, putt) for g in range(6)]
    n = len(rows[0])

    xs, ys = [], []
    for g in range(6):
        for f in range(n):
            for meta, nudge in ((rows[g][f], (0, 0)), (clubs[g][f], sprites.club_nudge(g, CLUB, f))):
                x0, y0, x1, y1 = meta.bounds()
                xs += [x0 + nudge[0], x1 + nudge[0]]
                ys += [y0 + nudge[1], y1 + nudge[1]]
    x0, y0, x1, y1 = min(xs), min(ys), max(xs), max(ys)
    cw, ch = x1 - x0 + 6, y1 - y0 + 6
    label, header = 84, 26
    size = (label + n * cw, header + 6 * ch)

    img = Image.new("RGB", size, BG)
    px = img.load()
    draw = ImageDraw.Draw(img)
    for f in range(n):
        draw.text((label + f * cw + 4, 8), str(f), fill=(150, 160, 145))

    for g in range(6):
        vram = sprites.load_chr(g, CLUB)
        body_pal = [c or 0 for c in sprites.body_palette(g)]
        club_pal = [c or 0 for c in sprites.club_palette()]
        draw.text((6, header + g * ch + ch // 2 - 4), f"{g} {GOLFER_NAMES[g]}", fill=(210, 218, 205))
        for f in range(n):
            ox, oy = label + f * cw + 3 - x0, header + g * ch + 3 - y0
            if with_club:
                ndx, ndy = sprites.club_nudge(g, CLUB, f)
                # Lower OAM index wins, so paint the loser first: the body draws
                # in front only on frames $05 and $0B ($8060).
                order = [(clubs[g][f], club_pal, ndx, ndy), (rows[g][f], body_pal, 0, 0)]
                if putt or f not in BODY_IN_FRONT_FRAMES:
                    order.reverse()
                for meta, pal, dx, dy in order:
                    paint(px, vram, meta, pal, ox, oy, size, dx, dy)
            else:
                paint(px, vram, rows[g][f], body_pal, ox, oy, size)
            draw.line([(label + f * cw, header), (label + f * cw, size[1])], fill=(48, 52, 46))
        draw.line([(0, header + g * ch), (size[0], header + g * ch)], fill=(48, 52, 46))

    img.resize((size[0] * scale, size[1] * scale), Image.NEAREST).save(out)
    print("wrote", out)


def main():
    sprites = GolferSprites(RomReader(os.path.join(ROOT, "nes_open_us.nes")))
    sheet(sprites, os.path.join(HERE, "swing_frames.png"))
    sheet(sprites, os.path.join(HERE, "putt_frames.png"), putt=True)
    sheet(sprites, os.path.join(HERE, "swing_with_club.png"), with_club=True)


if __name__ == "__main__":
    main()
