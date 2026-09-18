"""Integration: read a signpost banner back off an edited screen, against the real ROM.

`renders/prehole_signpost/signpost_us_hole01_course_only.aseprite` is the export
that went to the artist: the US card with the country name painted out and
nothing else touched.  Because it was *rendered from the ROM*, every tile in it
must resolve to a pattern the ROM already has - which makes it a round-trip
check on the whole chain at once (aseprite -> screen -> attribute lookup ->
2bpp -> pattern match -> nametable bytes).  A regression anywhere in that chain
shows up here as art the tool suddenly thinks is new.
"""

from pathlib import Path

import pytest

from golf.core.rom_reader import RomReader
from golf.core.signpost import (
    BANNER_US,
    build_screen,
    changed_tiles,
    convert_banner,
    read_banner_body,
    read_banner_descriptor,
    screen_from_aseprite,
)

ROM_PATH = "nes_open_us.nes"
EXPORT = Path("renders/prehole_signpost/signpost_us_hole01_course_only.aseprite")

pytestmark = pytest.mark.skipif(
    not Path(ROM_PATH).exists() or not EXPORT.exists(),
    reason=f"{ROM_PATH} or {EXPORT} not present",
)

# The country name sits on the banner's first two rows, columns 6-9.
NAME_CELLS = {(col, row) for row in (5, 6) for col in range(14, 18)}
FILLER = 0x5F  # the sign's own "blank plank" tile


@pytest.fixture(scope="module")
def imported():
    rom = RomReader(ROM_PATH)
    reference, palette = build_screen(rom, course=1, hole_1based=1)
    descriptor = read_banner_descriptor(rom, BANNER_US)
    edited = screen_from_aseprite(EXPORT)
    result = convert_banner(edited.pixels, reference, palette, descriptor)
    return rom, reference, palette, descriptor, edited, result


def test_the_export_is_the_screen_at_an_exact_zoom(imported):
    _, _, _, _, edited, _ = imported
    assert edited.scale == 2
    assert edited.ragged == [], "the render itself cannot contain sub-pixel detail"


def test_every_tile_resolves_to_a_pattern_the_rom_already_has(imported):
    """Nothing was drawn here that the ROM cannot already display."""
    _, _, _, _, _, result = imported
    assert result.new_patterns == {}
    assert result.errors == []


def test_untouched_cells_come_back_as_the_rom_s_own_bytes(imported):
    rom, _, _, descriptor, _, result = imported
    original = read_banner_body(rom, descriptor)
    body = result.nametable()
    assert len(body) == descriptor.length

    for offset, (was, now) in enumerate(zip(original, body)):
        col = descriptor.col + offset % descriptor.width
        row = descriptor.row + offset // descriptor.width
        if (col, row) in NAME_CELLS:
            continue
        assert now == was, f"cell ({col}, {row}) drifted from ${was:02X} to ${now:02X}"


def test_the_painted_out_country_name_becomes_the_sign_s_filler_tile(imported):
    _, _, _, descriptor, _, result = imported
    painted = [tile for tile in result.tiles if (tile.col, tile.row) in NAME_CELLS]
    assert len(painted) == len(NAME_CELLS)
    assert all(tile.tile == FILLER for tile in painted)
    assert all(not tile.unchanged for tile in painted)


def test_edits_outside_the_banner_are_detected(imported):
    """The export's placeholder yardage differs from the real hole's."""
    _, reference, palette, descriptor, edited, _ = imported
    inside = {
        (descriptor.col + col, descriptor.row + row)
        for row in range(descriptor.rows)
        for col in range(descriptor.width)
    }
    outside = [
        c for c in changed_tiles(edited.pixels, reference, palette) if c not in inside
    ]
    assert outside, "the placeholder distance digits should be reported"
    assert all(row in (17, 18) for _, row in outside)


def test_the_banner_descriptor_matches_the_documented_layout(imported):
    _, _, _, descriptor, _, _ = imported
    assert (descriptor.dest, descriptor.width, descriptor.rows) == (0x20A8, 16, 6)
    assert (descriptor.col, descriptor.row) == (8, 5)
    assert descriptor.pointer == 0xAE44
