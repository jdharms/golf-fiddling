"""
The NES side of the QR display: CHR tiles, nametable, screen placement.

At 4 pixels per module an 8x8 tile holds exactly 2x2 modules, so with the code
placed on a tile boundary the whole thing is drawn from 16 tiles — every
combination of four 4x4 quadrants. That is the reason the display code on cart
is trivial: 361 nametable bytes out of a 1,369-byte matrix, and 256 bytes of
CHR that never changes.

`render_modules` reconstructs the module grid back out of the CHR and
nametable, which is what lets the renderer and the validation harness work from
the same bytes the PPU will see rather than from an idealised matrix.
"""

import numpy as np

from golf.qr.encoder import SIZE

#: Pixels per QR module.
MODULE_PX = 4

#: Modules per tile, each axis.
MODULES_PER_TILE = 2

#: Tiles needed to cover 37 modules (18.5, rounded up).
TILE_COUNT = (SIZE + MODULES_PER_TILE - 1) // MODULES_PER_TILE  # 19

#: Distinct tile patterns: one per combination of four dark/light quadrants.
QR_TILE_COUNT = 16

CHR_TILE_BYTES = 16
CHR_BYTES = QR_TILE_COUNT * CHR_TILE_BYTES

#: Where the code sits on screen, in tiles (column, row). Chosen so the code is
#: tile-aligned and roughly centred, with well over the 4-module quiet zone on
#: every side and room for a caption above and below.
SCREEN_TILE_ORIGIN = (7, 5)

SCREEN_WIDTH_PX = 256
SCREEN_HEIGHT_PX = 240
TILE_PX = 8

#: Quiet zone the spec asks for, in modules.
QUIET_MODULES = 4

#: NES system palette entries used: white ground, black modules.
COLOR_LIGHT = 0x30
COLOR_DARK = 0x0F


def tile_index(matrix_rows: list[list[int]], tile_row: int, tile_col: int) -> int:
    """
    The tile covering a 2x2 block of modules.

    Bit 3 is the top-left module, bit 2 top-right, bit 1 bottom-left, bit 0
    bottom-right; set means dark. Modules past the edge of the code are light,
    which is what makes the last row and column of tiles half quiet zone.
    """

    def module(row: int, col: int) -> int:
        if 0 <= row < SIZE and 0 <= col < SIZE:
            return matrix_rows[row][col]
        return 0

    row = tile_row * MODULES_PER_TILE
    col = tile_col * MODULES_PER_TILE
    return (
        (module(row, col) << 3)
        | (module(row, col + 1) << 2)
        | (module(row + 1, col) << 1)
        | module(row + 1, col + 1)
    )


def build_chr() -> bytes:
    """
    The 16 QR tiles in NES CHR format, 256 bytes, tile n holding pattern n.

    Plane 0 carries the pattern and plane 1 is zero, so every dark pixel is
    colour 1 of whatever palette the screen uses.
    """
    out = bytearray()
    for index in range(QR_TILE_COUNT):
        top_left = (index >> 3) & 1
        top_right = (index >> 2) & 1
        bottom_left = (index >> 1) & 1
        bottom_right = index & 1
        top = (0xF0 if top_left else 0x00) | (0x0F if top_right else 0x00)
        bottom = (0xF0 if bottom_left else 0x00) | (0x0F if bottom_right else 0x00)
        out += bytes([top] * 4 + [bottom] * 4)  # plane 0
        out += bytes(8)  # plane 1
    assert len(out) == CHR_BYTES, len(out)
    return bytes(out)


def build_nametable(matrix_rows: list[list[int]], base_tile: int = 0) -> bytes:
    """
    The 19x19 block of tile indices, row-major.

    `base_tile` is the CHR tile number the 16 QR tiles start at, so the caller
    can place them anywhere in the pattern table.
    """
    out = bytearray()
    for tile_row in range(TILE_COUNT):
        for tile_col in range(TILE_COUNT):
            out.append(base_tile + tile_index(matrix_rows, tile_row, tile_col))
    assert len(out) == TILE_COUNT * TILE_COUNT, len(out)
    return bytes(out)


def decode_chr(chr_data: bytes) -> np.ndarray:
    """
    Decode a CHR blob into an (n, 8, 8) array of colour indices 0-3, the way
    the PPU combines the two bit planes.
    """
    raw = np.frombuffer(chr_data, dtype=np.uint8).reshape(-1, 2, TILE_PX)
    bits = np.unpackbits(raw, axis=-1).reshape(-1, 2, TILE_PX, TILE_PX)
    return (bits[:, 0] | (bits[:, 1] << 1)).astype(np.uint8)


def render_tiles(chr_data: bytes, nametable: bytes, base_tile: int = 0) -> np.ndarray:
    """
    Decode CHR + nametable back into a pixel array of colour indices (0 light,
    1 dark), 152 x 152 for the 19x19 block.

    This is the PPU's job done in software: everything downstream renders from
    here rather than from the module matrix, so the preview and the validation
    harness exercise the real tile pipeline.
    """
    tiles = decode_chr(chr_data)
    indices = (
        np.frombuffer(nametable, dtype=np.uint8).astype(int) - base_tile
    ).reshape(TILE_COUNT, TILE_COUNT)
    # (rows, cols, 8, 8) -> (rows, 8, cols, 8) -> one flat bitmap
    block = tiles[indices].transpose(0, 2, 1, 3)
    return np.ascontiguousarray(
        block.reshape(TILE_COUNT * TILE_PX, TILE_COUNT * TILE_PX)
    )


def render_modules(
    chr_data: bytes, nametable: bytes, base_tile: int = 0
) -> list[list[int]]:
    """
    Recover the module matrix from CHR + nametable, for round-trip checking.
    Each module must be a solid 4x4 block or this raises.
    """
    pixels = render_tiles(chr_data, nametable, base_tile)
    code_px = SIZE * MODULE_PX
    blocks = pixels[:code_px, :code_px].reshape(SIZE, MODULE_PX, SIZE, MODULE_PX)
    blocks = blocks.transpose(0, 2, 1, 3).reshape(SIZE, SIZE, MODULE_PX * MODULE_PX)
    if not (blocks == blocks[:, :, :1]).all():
        row, col = np.argwhere(~(blocks == blocks[:, :, :1]).all(axis=2))[0]
        raise ValueError(f"module ({row}, {col}) is not a solid block")
    return blocks[:, :, 0].tolist()


def screen_pixels(matrix_rows: list[list[int]], base_tile: int = 0) -> np.ndarray:
    """
    A full 256x240 screen of colour indices with the code placed at
    `SCREEN_TILE_ORIGIN`, built through the CHR and nametable.
    """
    chr_data = build_chr()
    nametable = build_nametable(matrix_rows, base_tile)
    block = render_tiles(chr_data, nametable, base_tile)

    screen = np.zeros((SCREEN_HEIGHT_PX, SCREEN_WIDTH_PX), dtype=np.uint8)
    origin_x = SCREEN_TILE_ORIGIN[0] * TILE_PX
    origin_y = SCREEN_TILE_ORIGIN[1] * TILE_PX
    screen[
        origin_y : origin_y + block.shape[0], origin_x : origin_x + block.shape[1]
    ] = block
    return screen


def quiet_zone_margins() -> dict[str, int]:
    """
    Clear pixels on each side of the code as placed, for checking against the
    spec's 4-module (16 px) quiet zone.
    """
    origin_x = SCREEN_TILE_ORIGIN[0] * TILE_PX
    origin_y = SCREEN_TILE_ORIGIN[1] * TILE_PX
    code_px = SIZE * MODULE_PX
    return {
        "left": origin_x,
        "right": SCREEN_WIDTH_PX - (origin_x + code_px),
        "top": origin_y,
        "bottom": SCREEN_HEIGHT_PX - (origin_y + code_px),
    }
