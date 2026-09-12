"""
The NES side: 16 CHR tiles, the 19x19 nametable, and screen placement.

The round-trip test is the important one — recovering the module matrix from
the CHR and nametable proves the tile pipeline is lossless, which is what lets
the renderer and the validation sweep work from the bytes the PPU will see
rather than from the matrix.
"""

import random

import numpy as np
import pytest

from golf.qr import encoder, nes, sample
from golf.qr.render import render_code, render_screen


@pytest.fixture(scope="module")
def matrices() -> list[encoder.QrMatrix]:
    rng = random.Random(99)
    key = sample.random_key(rng)
    return [
        encoder.encode(sample.random_round(rng).to_url(key), mask) for mask in range(8)
    ]


# --------------------------------------------------------------------------
# Geometry
# --------------------------------------------------------------------------


def test_four_pixel_modules_give_two_modules_per_tile() -> None:
    assert nes.MODULE_PX * nes.MODULES_PER_TILE == nes.TILE_PX


def test_sixteen_tiles_cover_every_quadrant_combination() -> None:
    assert nes.QR_TILE_COUNT == 2 ** (nes.MODULES_PER_TILE**2)


def test_tile_count_covers_the_code() -> None:
    assert nes.TILE_COUNT == 19
    assert nes.TILE_COUNT * nes.MODULES_PER_TILE >= encoder.SIZE


def test_code_fits_the_screen() -> None:
    code_px = encoder.SIZE * nes.MODULE_PX
    assert code_px == 148
    assert code_px < nes.SCREEN_WIDTH_PX
    assert code_px < nes.SCREEN_HEIGHT_PX


def test_placement_is_tile_aligned() -> None:
    """
    Modules only pair up into 16 tiles if the origin sits on a tile boundary.
    `SCREEN_TILE_ORIGIN` is in tiles, so this is really a check that the code
    is placed in whole tiles and the block fits on screen.
    """
    col, row = nes.SCREEN_TILE_ORIGIN
    assert (col + nes.TILE_COUNT) * nes.TILE_PX <= nes.SCREEN_WIDTH_PX
    assert (row + nes.TILE_COUNT) * nes.TILE_PX <= nes.SCREEN_HEIGHT_PX


def test_quiet_zone_exceeds_the_spec_minimum() -> None:
    required = nes.QUIET_MODULES * nes.MODULE_PX
    margins = nes.quiet_zone_margins()
    assert min(margins.values()) >= required, margins


def test_quiet_zone_leaves_room_for_a_caption() -> None:
    """
    Two tile rows above and below the code, beyond the quiet zone, for text.
    """
    required = nes.QUIET_MODULES * nes.MODULE_PX
    margins = nes.quiet_zone_margins()
    assert margins["top"] - required >= 2 * nes.TILE_PX
    assert margins["bottom"] - required >= 2 * nes.TILE_PX


# --------------------------------------------------------------------------
# CHR
# --------------------------------------------------------------------------


def test_chr_is_the_documented_size() -> None:
    assert len(nes.build_chr()) == nes.CHR_BYTES == 256


def test_chr_uses_only_colour_zero_and_one() -> None:
    """Plane 1 is empty, so every dark pixel is colour 1 of whatever palette."""
    tiles = nes.decode_chr(nes.build_chr())
    assert set(np.unique(tiles).tolist()) <= {0, 1}


def test_chr_tile_quadrants_match_their_index() -> None:
    tiles = nes.decode_chr(nes.build_chr())
    for index in range(nes.QR_TILE_COUNT):
        tile = tiles[index]
        quadrants = {
            "top_left": tile[0:4, 0:4],
            "top_right": tile[0:4, 4:8],
            "bottom_left": tile[4:8, 0:4],
            "bottom_right": tile[4:8, 4:8],
        }
        expected = {
            "top_left": (index >> 3) & 1,
            "top_right": (index >> 2) & 1,
            "bottom_left": (index >> 1) & 1,
            "bottom_right": index & 1,
        }
        for name, block in quadrants.items():
            assert (block == expected[name]).all(), f"tile {index} {name}"


def test_tile_zero_is_blank_so_the_quiet_zone_is_free() -> None:
    tiles = nes.decode_chr(nes.build_chr())
    assert not tiles[0].any()


# --------------------------------------------------------------------------
# Nametable
# --------------------------------------------------------------------------


def test_nametable_is_the_documented_size(matrices) -> None:
    nametable = nes.build_nametable(matrices[0].rows())
    assert len(nametable) == nes.TILE_COUNT**2 == 361


def test_nametable_only_references_the_sixteen_qr_tiles(matrices) -> None:
    for matrix in matrices:
        nametable = nes.build_nametable(matrix.rows())
        assert max(nametable) < nes.QR_TILE_COUNT


def test_nametable_honours_a_base_tile_offset(matrices) -> None:
    base = 0x40
    plain = nes.build_nametable(matrices[0].rows())
    offset = nes.build_nametable(matrices[0].rows(), base_tile=base)
    assert bytes(b + base for b in plain) == offset


def test_last_tile_row_and_column_are_half_quiet_zone(matrices) -> None:
    """
    37 modules is 18.5 tiles, so the final tiles carry only their top-left
    quadrant of code; the rest must read as light.
    """
    nametable = nes.build_nametable(matrices[0].rows())
    last = nes.TILE_COUNT - 1
    for tile_col in range(nes.TILE_COUNT):
        index = nametable[last * nes.TILE_COUNT + tile_col]
        assert index & 0b0011 == 0, f"bottom edge tile {tile_col} has dark lower half"
    for tile_row in range(nes.TILE_COUNT):
        index = nametable[tile_row * nes.TILE_COUNT + last]
        assert index & 0b0101 == 0, f"right edge tile {tile_row} has dark right half"


# --------------------------------------------------------------------------
# Round trip
# --------------------------------------------------------------------------


def test_modules_survive_the_tile_pipeline(matrices) -> None:
    chr_data = nes.build_chr()
    for matrix in matrices:
        nametable = nes.build_nametable(matrix.rows())
        assert nes.render_modules(chr_data, nametable) == matrix.rows()


def test_round_trip_with_a_base_tile_offset(matrices) -> None:
    chr_data = nes.build_chr()
    base = 0x80
    nametable = nes.build_nametable(matrices[0].rows(), base_tile=base)
    assert nes.render_modules(chr_data, nametable, base_tile=base) == matrices[0].rows()


def test_screen_pixels_place_the_code_where_documented(matrices) -> None:
    screen = nes.screen_pixels(matrices[0].rows())
    assert screen.shape == (nes.SCREEN_HEIGHT_PX, nes.SCREEN_WIDTH_PX)

    origin_x = nes.SCREEN_TILE_ORIGIN[0] * nes.TILE_PX
    origin_y = nes.SCREEN_TILE_ORIGIN[1] * nes.TILE_PX
    code_px = encoder.SIZE * nes.MODULE_PX

    # The finder pattern's dark core sits 2 modules in from the origin.
    assert screen[origin_y + 2 * nes.MODULE_PX, origin_x + 2 * nes.MODULE_PX] == 1

    # Everything outside the code block is light.
    outside = screen.copy()
    outside[origin_y : origin_y + code_px, origin_x : origin_x + code_px] = 0
    assert not outside.any()


# --------------------------------------------------------------------------
# Rendering
# --------------------------------------------------------------------------


def test_render_code_is_180_square(matrices) -> None:
    image = render_code(matrices[0])
    assert image.size == (180, 180)


def test_render_screen_is_nes_sized(matrices) -> None:
    image = render_screen(matrices[0])
    assert image.size == (nes.SCREEN_WIDTH_PX, nes.SCREEN_HEIGHT_PX)


def test_render_scales_by_whole_pixels(matrices) -> None:
    image = render_screen(matrices[0], scale=3)
    assert image.size == (nes.SCREEN_WIDTH_PX * 3, nes.SCREEN_HEIGHT_PX * 3)


def test_render_uses_only_two_colours(matrices) -> None:
    image = render_screen(matrices[0])
    colours = {tuple(px) for px in np.array(image).reshape(-1, 3).tolist()}
    assert len(colours) == 2


def test_render_code_rejects_too_large_a_quiet_zone(matrices) -> None:
    with pytest.raises(ValueError, match="too little quiet zone"):
        render_code(matrices[0], quiet_modules=20)
