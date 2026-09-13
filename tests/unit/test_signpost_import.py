"""Unit tests for reading banner art back off an edited screen.

The conversion is a chain of small, exact steps - downscale, attribute lookup,
colour to 2-bit value, planar pack, pattern match - and every one of them has a
silent failure mode: a colour resolved to the wrong bit pair still produces a
valid tile, just the wrong picture.  So each step is pinned on its own.
"""

import pytest

from golf.core.graphics_codec import VideoMemory
from golf.core.palettes import NES_SYSTEM_PALETTE
from golf.core.signpost import (
    ATTRIBUTES,
    NAMETABLE,
    PATTERN_BASE,
    BannerDescriptor,
    _colour_lookup,
    convert_banner,
    subpalette_at,
    tile_to_chr,
)

# Four colours on subpalette 0, and a second subpalette that shares none of
# them, so a mix-up between the two cannot pass unnoticed.
PALETTE = bytes(
    [0x0F, 0x30, 0x21, 0x15]      # 0: black bg, white, blue, magenta
    + [0x0F, 0x37, 0x1C, 0x2A]    # 1: tan, teal, green
    + [0x0F, 0x00, 0x00, 0x00]
    + [0x0F, 0x00, 0x00, 0x00]
)


def rgb(value):
    return NES_SYSTEM_PALETTE[value & 0x3F]


def test_tile_to_chr_packs_planes_the_way_the_ppu_reads_them():
    values = [[0] * 8 for _ in range(8)]
    values[0] = [1, 0, 0, 0, 0, 0, 0, 0]      # low plane bit 7
    values[1] = [2, 0, 0, 0, 0, 0, 0, 0]      # high plane bit 7
    values[2] = [3, 0, 0, 0, 0, 0, 0, 0]      # both
    values[3] = [0, 0, 0, 0, 0, 0, 0, 1]      # low plane bit 0

    chr_bytes = tile_to_chr(values)
    assert chr_bytes[0] == 0x80 and chr_bytes[8] == 0x00
    assert chr_bytes[1] == 0x00 and chr_bytes[9] == 0x80
    assert chr_bytes[2] == 0x80 and chr_bytes[10] == 0x80
    assert chr_bytes[3] == 0x01 and chr_bytes[11] == 0x00


def test_tile_to_chr_round_trips_through_video_memory():
    values = [[(x + y) % 4 for x in range(8)] for y in range(8)]
    vram = VideoMemory()
    for offset, byte in enumerate(tile_to_chr(values)):
        vram.write(PATTERN_BASE + offset, byte)
    assert vram.tile(0, PATTERN_BASE) == values


def test_colour_lookup_treats_the_two_whites_as_one_colour():
    """`$20` and `$30` are the same white; an artist may pick either swatch."""
    lookup = _colour_lookup(PALETTE)
    assert rgb(0x20) == rgb(0x30)
    assert lookup[0][rgb(0x20)] == 1
    assert lookup[0][rgb(0x30)] == 1


def test_colour_lookup_is_per_subpalette():
    lookup = _colour_lookup(PALETTE)
    assert lookup[0][rgb(0x15)] == 3
    assert rgb(0x15) not in lookup[1]
    assert lookup[1][rgb(0x2A)] == 3


def test_colour_lookup_maps_the_universal_background_to_zero():
    lookup = _colour_lookup(PALETTE)
    for sub in range(4):
        assert lookup[sub][rgb(0x0F)] == 0


def screen_from_tiles(vram, palette):
    """Render just enough of a screen for convert_banner to read back."""
    from golf.core.signpost import render_screen

    return [[rgb(value) for value in row] for row in render_screen(vram, palette)]


def make_reference(patterns, tiles, attribute=0x00):
    """A video memory with `patterns` in CHR and `tiles` on the nametable."""
    vram = VideoMemory()
    for index, pattern in enumerate(patterns):
        for offset, byte in enumerate(pattern):
            vram.write(PATTERN_BASE + index * 16 + offset, byte)
    for (col, row), tile in tiles.items():
        vram.write(NAMETABLE + row * 32 + col, tile)
    for slot in range(64):
        vram.write(ATTRIBUTES + slot, attribute)
    return vram


DESCRIPTOR = BannerDescriptor(index=0, dest=NAMETABLE, header=0x82, rows=1, pointer=0x1234)


def test_unchanged_art_keeps_the_rom_s_own_tile_bytes():
    """Two slots can hold identical art; an untouched cell must not drift."""
    blank = tile_to_chr([[0] * 8 for _ in range(8)])
    solid = tile_to_chr([[1] * 8 for _ in range(8)])
    # $00 and $05 are the same picture - a naive "first match wins" lookup
    # would rewrite the cell from $05 to $00.
    patterns = [blank] + [solid] * 4 + [blank] + [blank] * 250
    vram = make_reference(patterns, {(0, 0): 0x05, (1, 0): 0x01})

    result = convert_banner(screen_from_tiles(vram, PALETTE), vram, PALETTE, DESCRIPTOR)

    assert [tile.tile for tile in result.tiles] == [0x05, 0x01]
    assert all(tile.unchanged for tile in result.tiles)
    assert result.nametable() == bytes([0x05, 0x01])
    assert result.new_patterns == {}


def test_redrawn_cell_resolves_to_an_existing_pattern():
    blank = tile_to_chr([[0] * 8 for _ in range(8)])
    solid = tile_to_chr([[1] * 8 for _ in range(8)])
    patterns = [blank, solid] + [blank] * 254
    vram = make_reference(patterns, {(0, 0): 0x00, (1, 0): 0x00})

    screen = screen_from_tiles(vram, PALETTE)
    for y in range(8):                    # paint cell 0 solid: that is tile $01
        for x in range(8):
            screen[y][x] = rgb(PALETTE[1])

    result = convert_banner(screen, vram, PALETTE, DESCRIPTOR)
    assert [tile.tile for tile in result.tiles] == [0x01, 0x00]
    assert not result.tiles[0].unchanged
    assert result.new_patterns == {}


def test_art_with_no_matching_pattern_is_reported_as_new():
    blank = tile_to_chr([[0] * 8 for _ in range(8)])
    vram = make_reference([blank] * 256, {(0, 0): 0x00, (1, 0): 0x00})

    screen = screen_from_tiles(vram, PALETTE)
    screen[0][0] = rgb(PALETTE[2])        # one pixel nothing in CHR has

    result = convert_banner(screen, vram, PALETTE, DESCRIPTOR)
    assert result.tiles[0].is_new
    assert result.tiles[1].tile == 0x00
    assert len(result.new_patterns) == 1

    with pytest.raises(ValueError, match="needs new CHR"):
        result.nametable()
    assert result.nametable({result.tiles[0].chr_bytes: 0x42}) == bytes([0x42, 0x00])


def test_a_colour_outside_the_cell_s_subpalette_is_an_error():
    blank = tile_to_chr([[0] * 8 for _ in range(8)])
    vram = make_reference([blank] * 256, {(0, 0): 0x00, (1, 0): 0x00})

    screen = screen_from_tiles(vram, PALETTE)
    screen[0][0] = rgb(0x2A)              # legal on subpalette 1, not on 0

    result = convert_banner(screen, vram, PALETTE, DESCRIPTOR)
    assert len(result.errors) == 1
    assert "outside palette 0" in result.errors[0]
    assert "(0, 0)" in result.errors[0]


def test_the_attribute_table_decides_which_colours_a_cell_may_use():
    """The same pixel is legal or not depending on the attribute byte."""
    blank = tile_to_chr([[0] * 8 for _ in range(8)])
    vram = make_reference([blank] * 256, {(0, 0): 0x00, (1, 0): 0x00}, attribute=0x55)
    assert subpalette_at(vram, 0, 0) == 1

    screen = screen_from_tiles(vram, PALETTE)
    screen[0][0] = rgb(0x2A)              # now legal

    result = convert_banner(screen, vram, PALETTE, DESCRIPTOR)
    assert result.errors == []
    assert result.tiles[0].subpalette == 1
