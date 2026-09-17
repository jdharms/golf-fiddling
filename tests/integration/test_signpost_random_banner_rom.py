"""Integration: put edited banner art into the real ROM and read it back out.

The test that matters is the last one: it replays the patched card the way the
CPU would - walking the `JSR`/inline-pointer pairs the patch wrote, following
each descriptor to its body, running the transfers - and checks the pixels that
come out are the artist's.  Nothing in that path is told what the art should
be, so it fails if any link is wrong: the pattern allocation, the descriptor
geometry, the nametable indices, or the code.
"""

from pathlib import Path

import pytest

from golf.core.patches.signpost_random_banner import (
    BODY_REGION_END,
    BODY_REGION_START,
    PATTERN_BASE,
    ROW_WIDTH,
    SELECT_END,
    SELECT_START,
    WRITE_NAMETABLE_TILES,
    build_layout,
    data_region,
    random_banner_patches,
)
from golf.core.rom_reader import RomReader
from golf.core.rom_writer import RomWriter
from golf.core.signpost import (
    BANK,
    BANNER_US,
    DIGIT_COUNT,
    allocate_patterns,
    apply_descriptor,
    build_screen,
    convert_banner,
    digit_tiles,
    free_pattern_slots,
    load_scene_chr,
    read_banner_descriptor,
    read_descriptor,
    screen_from_aseprite,
)

ROM_PATH = "nes_open_us.nes"
EXPORT = Path("renders/prehole_signpost/signpost_us_hole01_course_only.aseprite")

pytestmark = pytest.mark.skipif(
    not Path(ROM_PATH).exists() or not EXPORT.exists(),
    reason=f"{ROM_PATH} or {EXPORT} not present",
)


def make_art(result, palette_shift=1):
    """Invent new art by recolouring the banner, so the fixture needs no
    second .aseprite and the expected pixels are known exactly."""
    patterns = []
    for tile in result.tiles[: 22]:
        rotated = bytes(b ^ 0xFF for b in tile.chr_bytes[:8]) + tile.chr_bytes[8:]
        patterns.append(rotated)
    return patterns


@pytest.fixture(scope="module")
def prepared():
    rom = RomReader(ROM_PATH)
    reference, palette = build_screen(rom, course=1, hole_1based=1)
    descriptor = read_banner_descriptor(rom, BANNER_US)
    edited = screen_from_aseprite(EXPORT)
    result = convert_banner(edited.pixels, reference, palette, descriptor)

    # The export needs no new art, so invent some: give the first 22 cells
    # patterns that are certainly not in CHR.
    patterns = make_art(result)
    kept = [tile.tile for index, tile in enumerate(result.tiles) if index >= 22]
    chunks = allocate_patterns(free_pattern_slots(rom, reference, kept), len(patterns))

    placement = {}
    supply = list(patterns)
    for first_tile, count in chunks:
        for offset in range(min(count, len(supply))):
            placement[supply[offset]] = first_tile + offset
        supply = supply[count:]
    for index, tile in enumerate(result.tiles[:22]):
        tile.tile = None
        tile.chr_bytes = patterns[index]

    body = result.nametable(placement)
    return rom, reference, palette, descriptor, result, patterns, chunks, body


def test_allocation_uses_even_aligned_even_length_runs(prepared):
    """A descriptor row is two tiles, so an odd start or count would smear."""
    *_, chunks, _ = prepared
    for first_tile, count in chunks:
        assert first_tile % 2 == 0, f"${first_tile:02X} is not an even tile index"
        assert count % 2 == 0
        assert count // 2 <= ROW_WIDTH, "$CEE8 abandons a transfer when width < rows"


def test_allocation_never_reuses_a_tile_the_screen_still_needs(prepared):
    rom, reference, _, _, result, patterns, chunks, _ = prepared
    kept = {tile.tile for tile in result.tiles if tile.tile is not None}
    free = set(free_pattern_slots(rom, reference, kept))
    for first_tile, count in chunks:
        assert set(range(first_tile, first_tile + count)) <= free


def test_allocation_never_takes_a_digit_tile(prepared):
    """The reference card draws only some digits; the other holes draw the rest.

    Read straight from the `$B01C` records rather than through
    `free_pattern_slots`, so it cannot share that function's view of the screen.
    """
    rom, *_, chunks, _ = prepared
    digits = {tile for digit in range(DIGIT_COUNT) for tile in digit_tiles(rom, digit)}
    for first_tile, count in chunks:
        taken = digits & set(range(first_tile, first_tile + count))
        assert not taken, f"chunk ${first_tile:02X} overwrites digit tiles {sorted(taken)}"


def test_layout_stays_inside_the_reclaimed_banner_bodies(prepared):
    rom, _, _, descriptor, _, patterns, chunks, body = prepared
    layout = build_layout(
        patterns, chunks, BANNER_US, body, (descriptor.pointer, descriptor.length)
    )
    origin, available = data_region(descriptor.pointer, descriptor.length)
    assert BODY_REGION_START <= origin
    assert layout["end"] <= BODY_REGION_END
    assert layout["end"] - origin <= available
    # and never over the banner body that is being kept
    kept = range(descriptor.pointer, descriptor.pointer + descriptor.length)
    for blob_origin, blob in layout["blobs"]:
        assert not set(range(blob_origin, blob_origin + len(blob))) & set(kept)


def test_the_code_fits_the_space_the_selection_logic_occupied(prepared):
    rom, _, _, descriptor, _, patterns, chunks, body = prepared
    layout = build_layout(
        patterns, chunks, BANNER_US, body, (descriptor.pointer, descriptor.length)
    )
    from golf.core.patches.signpost_random_banner import build_code

    code = build_code(layout)
    assert len(code) <= SELECT_END - SELECT_START
    assert code[-3] == 0x4C, "must end by jumping to the hole-number section"
    assert code[-2] | (code[-1] << 8) == SELECT_END


def test_patch_applies_to_the_vanilla_rom_and_reloads(prepared, tmp_path):
    rom, _, _, _, _, patterns, chunks, body = prepared
    patch = random_banner_patches(rom, patterns, chunks, BANNER_US, body)

    out = tmp_path / "random.nes"
    writer = RomWriter(ROM_PATH, str(out))
    assert patch.can_apply(writer)
    patch.apply(writer)
    writer.save()

    assert patch.is_applied(RomWriter(str(out), str(tmp_path / "unused.nes")))


def test_the_patched_rom_really_draws_the_new_art(prepared, tmp_path):
    """Walk the patched code, follow its descriptors, compare the pixels."""
    rom, _, _, descriptor, result, patterns, chunks, body = prepared
    out = tmp_path / "random.nes"
    writer = RomWriter(ROM_PATH, str(out))
    random_banner_patches(rom, patterns, chunks, BANNER_US, body).apply(writer)
    writer.save()

    patched = RomReader(str(out))
    code = bytes(patched.read_switched(SELECT_START, BANK, SELECT_END - SELECT_START))

    pointers = []
    pos = 0
    while pos < len(code) and code[pos] == 0x20:
        assert code[pos + 1] | (code[pos + 2] << 8) == WRITE_NAMETABLE_TILES
        pointers.append(code[pos + 3] | (code[pos + 4] << 8))
        pos += 5
    assert code[pos] == 0x4C and code[pos + 1] | (code[pos + 2] << 8) == SELECT_END
    assert len(pointers) == len(chunks) + 1, "one call per chunk, plus the banner"

    vram = load_scene_chr(patched)
    for pointer in pointers:
        apply_descriptor(patched, vram, read_descriptor(patched, pointer))

    # The last call is the banner; every earlier one targets the pattern table.
    for pointer in pointers[:-1]:
        assert read_descriptor(patched, pointer).dest < 0x2000
    assert read_descriptor(patched, pointers[-1]).dest == descriptor.dest

    for tile in result.tiles:
        index = vram.data[0x2000 + tile.row * 32 + tile.col]
        drawn = bytes(vram.data[PATTERN_BASE + index * 16: PATTERN_BASE + index * 16 + 16])
        assert drawn == tile.chr_bytes, (
            f"cell ({tile.col}, {tile.row}) draws tile ${index:02X}, whose pattern "
            "is not the art that was imported"
        )
