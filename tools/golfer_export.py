"""
Export a golfer's animation as a layered Aseprite file for redrawing.

Each file holds one golfer and one animation.  Layers, bottom to top:

``body``
    The golfer, and the only layer meant to be repainted.
``club``
    The real club metasprite for every frame, positioned exactly as the game
    draws it.  Move it to reposition the club; do not redraw it.  The offset is
    read back into the club nudge tables.
``guides``
    The 8x8 cell grid, the 40x64 body box, the drawing origin, the shared foot
    line, and a marker on the two frames where the body draws in front.

Frames that share a metasprite pointer in the ROM - swing frames 6 and 7 reuse
4 and 3 - are written as linked cels, so editing one edits both, exactly as the
game behaves.

A JSON sidecar beside each file records the canvas origin, the canonical club
position per frame, and which nudge slot each frame writes to.
"""

import argparse
import json
import os

from golf.core.golfer_sprites import (
    BODY_IN_FRONT_FRAMES,
    GOLFER_NAMES,
    PUTTER_CLUB,
    SWING_CLUB_GROUPS,
    GolferSprites,
)
from golf.core.aseprite import (
    LAYER_EDITABLE,
    LAYER_LOCK_MOVEMENT,
    LAYER_VISIBLE,
    AsepriteFile,
    Cel,
    Frame,
    Layer,
    LinkedCel,
)
from golf.core.palettes import (
    NES_CANONICAL_BLACK,
    NES_SYSTEM_PALETTE,
    canonical_nes,
    distinct_nes_entries,
)
from golf.core.rom_reader import RomReader

# Palette layout.  Index 0 is transparent, then every NES colour worth offering -
# all 64 less the nine redundant blacks, which fold onto $0F - then the guide
# colours.  The artist can reach for any of them; the importer is what enforces
# "at most three on the body".
NES_ENTRIES = distinct_nes_entries()
NES_TO_INDEX = {value: 1 + slot for slot, value in enumerate(NES_ENTRIES)}

IDX_TRANSPARENT = 0
NES_BASE = 1
IDX_GRID = NES_BASE + len(NES_ENTRIES)
IDX_BOX = IDX_GRID + 1
IDX_ORIGIN = IDX_BOX + 1
IDX_PRIORITY = IDX_ORIGIN + 1
PALETTE_SIZE = IDX_PRIORITY + 1

GUIDE_COLOURS = {
    IDX_GRID: (0x3A, 0x3A, 0x46, 0xFF, "guide: cell grid"),
    IDX_BOX: (0x2E, 0x8B, 0xA8, 0xFF, "guide: body box"),
    IDX_ORIGIN: (0xD6, 0x3C, 0x8A, 0xFF, "guide: origin and foot line"),
    IDX_PRIORITY: (0xE0, 0x8A, 0x28, 0xFF, "guide: body draws in front"),
}


def nes_index(value: int) -> int:
    """Palette index for a NES colour; the spare blacks resolve to $0F's slot."""
    return NES_TO_INDEX[canonical_nes(value)]


def build_palette(body_nes, club_nes):
    """Index 0 transparent, 1-64 the NES system palette, then the guide colours.

    Entries are named so hovering a swatch in Aseprite shows its NES value, with
    the golfer's own three colours and the unsafe blacks called out.
    """
    palette = [(0, 0, 0, 0, "transparent")] * PALETTE_SIZE
    roles = {}
    for slot, value in enumerate(body_nes, start=1):
        roles.setdefault(canonical_nes(value), []).append(f"body {slot}")
    for slot, value in enumerate(club_nes, start=1):
        roles.setdefault(canonical_nes(value), []).append(f"club {slot}")
    for value in NES_ENTRIES:
        name = f"${value:02X}"
        if value == NES_CANONICAL_BLACK:
            name += " - black"
        if value in roles:
            name += " - " + ", ".join(roles[value])
        palette[nes_index(value)] = NES_SYSTEM_PALETTE[value] + (255, name)
    for slot, rgba in GUIDE_COLOURS.items():
        palette[slot] = rgba
    return palette


def nes_by_index() -> list:
    """Palette index -> NES colour, with None for transparent and the guides.

    The authoritative map for an importer, since the collapsed blacks mean the
    relationship is no longer arithmetic.
    """
    table = [None] * PALETTE_SIZE
    for value in NES_ENTRIES:
        table[nes_index(value)] = value
    return table


def _round_out(low: int, high: int) -> tuple[int, int]:
    return (low // 8) * 8, -((-high) // 8) * 8


def clubs_for(animation_is_putt: bool) -> list[int]:
    """The clubs a file needs a layer for.

    A swing needs one layer per animation group - clubs 0-3, 4-7, 8-11 and
    12-14 are four separate artworks.  Putting only ever uses club 15.
    """
    if animation_is_putt:
        return [PUTTER_CLUB]
    return [low for low, _ in SWING_CLUB_GROUPS]


def canvas_bounds(sprites: GolferSprites) -> tuple[int, int, int, int]:
    """One canvas that fits every golfer, frame, animation and club group."""
    xs: list[int] = []
    ys: list[int] = []
    for golfer in range(len(GOLFER_NAMES)):
        for putt in (False, True):
            body = sprites.body_frames(golfer, putt)
            for club in clubs_for(putt):
                clubs = sprites.club_frames(golfer, club, putt)
                for frame, (b, c) in enumerate(zip(body, clubs)):
                    bx0, by0, bx1, by1 = b.bounds()
                    cx0, cy0, cx1, cy1 = c.bounds()
                    ndx, ndy = sprites.club_nudge(golfer, club, frame)
                    xs += [bx0, bx1, cx0 + ndx, cx1 + ndx]
                    ys += [by0, by1, cy0 + ndy, cy1 + ndy]
    x0, x1 = _round_out(min(xs), max(xs))
    y0, y1 = _round_out(min(ys), max(ys))
    return x0, y0, x1, y1


def render_metasprite(meta, vram, colour_indices, ox, oy, w, h, dx=0, dy=0):
    """Paint a metasprite into a canvas-sized buffer of palette indices."""
    buf = bytearray(w * h)
    for sprite in meta.sprites:
        rows = vram.tile(sprite.tile)
        for y in range(8):
            py = oy + sprite.dy + dy + y
            if not 0 <= py < h:
                continue
            for x in range(8):
                value = rows[y][x]
                if value == 0:
                    continue
                px = ox + sprite.dx + dx + x
                if 0 <= px < w:
                    buf[py * w + px] = colour_indices[value - 1]
    return buf


def _tight(buf, w, h):
    """Crop a full-canvas buffer to its non-empty box; returns (x, y, w, h, pixels)."""
    xs = [x for y in range(h) for x in range(w) if buf[y * w + x]]
    ys = [y for y in range(h) for x in range(w) if buf[y * w + x]]
    if not xs:
        return 0, 0, 1, 1, bytes(1)
    x0, x1, y0, y1 = min(xs), max(xs) + 1, min(ys), max(ys) + 1
    cw, chh = x1 - x0, y1 - y0
    pixels = bytearray(cw * chh)
    for y in range(chh):
        row = (y0 + y) * w + x0
        pixels[y * cw : (y + 1) * cw] = buf[row : row + cw]
    return x0, y0, cw, chh, bytes(pixels)


def build_guides(w, h, ox, oy, body_box, frame_in_front):
    """The locked reference layer: grid, body box, origin, foot line.

    A bar across the top edge marks the frames where the body draws in front of
    the club; see `frame_in_front`.
    """
    buf = bytearray(w * h)
    bx0, by0, bx1, by1 = body_box

    def put(x, y, idx):
        if 0 <= x < w and 0 <= y < h:
            buf[y * w + x] = idx

    # 8x8 cell corners inside the body box
    for cy in range(by0, by1 + 1, 8):
        for cx in range(bx0, bx1 + 1, 8):
            put(ox + cx, oy + cy, IDX_GRID)
    # dashed body box outline
    for x in range(bx0, bx1):
        if x % 2 == 0:
            put(ox + x, oy + by0, IDX_BOX)
            put(ox + x, oy + by1, IDX_BOX)
    for y in range(by0, by1):
        if y % 2 == 0:
            put(ox + bx0, oy + y, IDX_BOX)
            put(ox + bx1, oy + y, IDX_BOX)
    # foot line, shared by all six golfers, across the whole canvas
    for x in range(0, w, 3):
        put(x, oy + by1, IDX_ORIGIN)
    # origin crosshair
    for d in range(-3, 4):
        put(ox + d, oy, IDX_ORIGIN)
        put(ox, oy + d, IDX_ORIGIN)
    if frame_in_front:
        # On frames $05 and $0B the body is written to OAM first and so draws in
        # front of the club.  Aseprite's layer order is fixed for the whole
        # file, so this bar is the only way the file can say "on this frame the
        # club is behind the golfer".
        for x in range(0, w, 2):
            put(x, 0, IDX_PRIORITY)
            put(x, 1, IDX_PRIORITY)
    return bytes(buf)


def export_golfer(rom, sprites, golfer, putt, bounds, out_dir, visible_club=0):
    x0, y0, x1, y1 = bounds
    w, h = x1 - x0, y1 - y0
    ox, oy = -x0, -y0
    club_list = clubs_for(putt)

    body = sprites.body_frames(golfer, putt)
    # CHR is per club group, so each group's tiles are decoded separately.
    vrams = {club: sprites.load_chr(golfer, club) for club in club_list}

    body_pal = sprites.body_palette(golfer)
    club_pal = sprites.club_palette()
    palette = build_palette(body_pal[1:], club_pal[1:])
    body_indices = tuple(nes_index(v) for v in body_pal[1:])
    club_indices = tuple(nes_index(v) for v in club_pal[1:])

    bx0 = min(f.bounds()[0] for f in body)
    by0 = min(f.bounds()[1] for f in body)
    bx1 = max(f.bounds()[2] for f in body)
    by1 = max(f.bounds()[3] for f in body)

    ase = AsepriteFile(width=w, height=h, palette=palette, grid=(ox % 8, oy % 8, 8, 8))
    ase.layers = [Layer("body - draw here", LAYER_VISIBLE | LAYER_EDITABLE)]
    club_layer_index = {}
    for club in club_list:
        low, high = SWING_CLUB_GROUPS[sprites.club_group(club)] if not putt else (15, 15)
        cls = sprites.nudge_class(club)
        span = f"club {low}" if low == high else f"clubs {low}-{high}"  # layer name
        suffix = "putter, no nudge" if cls is None else f"nudge class {cls}"
        club_layer_index[club] = len(ase.layers)
        visible = LAYER_VISIBLE if club == visible_club or putt else 0
        ase.layers.append(
            Layer(f"{span} - move only ({suffix})", visible | LAYER_EDITABLE)
        )
    guides_layer = len(ase.layers)
    ase.layers.append(Layer("guides - locked", LAYER_VISIBLE | LAYER_LOCK_MOVEMENT))

    # Groups sharing a nudge class cannot be positioned independently.
    shared: dict[int, list[str]] = {}
    for club in club_list:
        cls = sprites.nudge_class(club)
        if cls is not None:
            shared.setdefault(cls, []).append(ase.layers[club_layer_index[club]].name)

    meta = {
        "golfer": golfer,
        "name": GOLFER_NAMES[golfer],
        "animation": "putt" if putt else "swing",
        "clubs": club_list,
        "canvas": {"width": w, "height": h, "origin_x": ox, "origin_y": oy},
        "body_box": {"x0": bx0, "y0": by0, "x1": bx1, "y1": by1},
        "body_palette_nes": [None] + list(body_pal[1:]),
        "club_palette_nes": [None] + list(club_pal[1:]),
        "palette": {
            "transparent_index": IDX_TRANSPARENT,
            "nes_by_index": nes_by_index(),
            "note": (
                "nes_by_index maps a palette index to a NES colour; null means "
                "transparent or a guide colour. The nine redundant blacks are "
                f"collapsed onto ${NES_CANONICAL_BLACK:02X}."
            ),
            "body_indices": list(body_indices),
            "club_indices": list(club_indices),
            "max_body_colours": 3,
        },
        "body_in_front_frames": [
            f for f in range(len(body)) if not putt and f in BODY_IN_FRONT_FRAMES
        ],
        "layers": [layer.name for layer in ase.layers],
        "nudge_classes_shared_by": {
            str(cls): names for cls, names in shared.items() if len(names) > 1
        },
        "golfer_screen_x": {str(c): sprites.screen_x(c) for c in club_list},
        "frames": [],
    }

    seen_body: dict[int, int] = {}
    seen_club: dict[tuple, int] = {}
    for frame in range(len(body)):
        cels = []
        b = body[frame]

        if b.cpu_addr in seen_body:
            source, pos = seen_body[b.cpu_addr]
            cels.append(LinkedCel(0, source, pos[0], pos[1]))
        else:
            buf = render_metasprite(b, vrams[club_list[0]], body_indices, ox, oy, w, h)
            cx, cy, cw, chh, pixels = _tight(buf, w, h)
            seen_body[b.cpu_addr] = (frame, (cx, cy))
            cels.append(Cel(0, cx, cy, cw, chh, pixels))

        club_info = {}
        for club in club_list:
            layer = club_layer_index[club]
            c = sprites.club_frames(golfer, club, putt)[frame]
            ndx, ndy = sprites.club_nudge(golfer, club, frame)
            key = (layer, c.cpu_addr, ndx, ndy)
            if key in seen_club:
                source, (sx, sy) = seen_club[key]
                cels.append(LinkedCel(layer, source, sx, sy))
                pos = {"x": sx, "y": sy, "linked_to": source}
            else:
                buf = render_metasprite(c, vrams[club], club_indices, ox, oy, w, h, ndx, ndy)
                cx, cy, cw, chh, pixels = _tight(buf, w, h)
                seen_club[key] = (frame, (cx, cy))
                cels.append(Cel(layer, cx, cy, cw, chh, pixels))
                pos = {"x": cx, "y": cy}
            club_info[str(club)] = {
                "layer": layer,
                "metasprite": f"${c.cpu_addr:04X}",
                "canonical_pos": pos,
                "nudge": {"dx": ndx, "dy": ndy},
                "nudge_slot": sprites.nudge_slot(golfer, club, frame),
                "nudge_class": sprites.nudge_class(club),
            }

        cels.append(
            Cel(
                guides_layer, 0, 0, w, h,
                build_guides(
                    w, h, ox, oy, (bx0, by0, bx1, by1),
                    not putt and frame in BODY_IN_FRONT_FRAMES,
                ),
            )
        )
        ase.frames.append(Frame(duration_ms=120, cels=cels))

        meta["frames"].append(
            {
                "frame": frame,
                "body_metasprite": f"${b.cpu_addr:04X}",
                "body_sprites": len(b),
                "body_linked_to": seen_body[b.cpu_addr][0]
                if seen_body[b.cpu_addr][0] != frame
                else None,
                "peak_sprites_per_scanline": b.peak_per_scanline(),
                "body_in_front": not putt and frame in BODY_IN_FRONT_FRAMES,
                "clubs": club_info,
            }
        )

    stem = f"{GOLFER_NAMES[golfer].lower()}_{'putt' if putt else 'swing'}"
    ase_path = os.path.join(out_dir, f"{stem}.aseprite")
    ase.write(ase_path)
    with open(os.path.join(out_dir, f"{stem}.json"), "w") as handle:
        json.dump(meta, handle, indent=2)
    return ase_path, meta


def main():
    parser = argparse.ArgumentParser(
        description="Export golfer animations as layered Aseprite files"
    )
    parser.add_argument("rom")
    parser.add_argument("out_dir")
    parser.add_argument(
        "-g", "--golfer", default="all",
        help="name or index (default: all six)",
    )
    parser.add_argument(
        "-c", "--club", type=int, default=0,
        help="which club layer starts visible in the swing file (default: 0); "
             "every club group gets a layer regardless",
    )
    parser.add_argument(
        "-a", "--animation", choices=["swing", "putt", "both"], default="both"
    )
    args = parser.parse_args()

    if not 0 <= args.club < PUTTER_CLUB:
        parser.error(
            f"--club must be 0-{PUTTER_CLUB - 1}; putting always uses club {PUTTER_CLUB}"
        )

    rom = RomReader(args.rom)
    sprites = GolferSprites(rom)

    if args.golfer == "all":
        golfers = list(range(len(GOLFER_NAMES)))
    elif args.golfer.isdigit():
        golfers = [int(args.golfer)]
    else:
        lowered = [n.lower() for n in GOLFER_NAMES]
        if args.golfer.lower() not in lowered:
            parser.error(f"unknown golfer {args.golfer!r}; expected one of {GOLFER_NAMES}")
        golfers = [lowered.index(args.golfer.lower())]

    os.makedirs(args.out_dir, exist_ok=True)
    bounds = canvas_bounds(sprites)
    x0, y0, x1, y1 = bounds
    groups = ", ".join(f"{lo}-{hi}" for lo, hi in SWING_CLUB_GROUPS)
    print(f"canvas {x1 - x0}x{y1 - y0}, origin at ({-x0}, {-y0})")
    print(f"swing club layers: {groups}   putt: club {PUTTER_CLUB}")

    animations = (
        [False, True] if args.animation == "both" else [args.animation == "putt"]
    )
    for golfer in golfers:
        for putt in animations:
            path, meta = export_golfer(
                rom, sprites, golfer, putt, bounds, args.out_dir, args.club
            )
            linked = sum(1 for f in meta["frames"] if f["body_linked_to"] is not None)
            print(
                f"  {os.path.basename(path):22} {len(meta['frames'])} frames"
                f" ({linked} linked), {len(meta['clubs'])} club layer(s),"
                f" build {sprites.body_type(golfer)}"
            )


if __name__ == "__main__":
    main()
