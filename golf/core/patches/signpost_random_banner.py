"""
Put new wording on the pre-hole signpost, art and all.

The banner bodies are raw nametable bytes, so new *wording* is a byte swap
(`docs/prehole_signpost.md`).  New *pixels* need pattern-table space, and this
patch gets them there without a `$D4C3` encoder: `WriteNametableTiles`
(`$CE84`) copies literal bytes to whatever PPU address its descriptor names,
and nothing says that address has to be a nametable.  Pointed at
`$1000 + tile * 16` with a width of 32 it writes two tiles per row, straight
into the pattern table.

Everything lives in the space the five banner bodies already occupy
(`$ADE4`-`$B01B`, 568 bytes, ending exactly where the digit pointer table
begins).  The banner being replaced keeps its own body where it is; the tile
pixels and their descriptors go in the largest run left on either side of it.
The other four banners are not repointed - they simply stop being reachable,
because the selection logic that chose between them is what this patch
replaces.

**This placement is provisional.**  Nothing outside this module knows the
addresses.  Moving the pixels somewhere roomier means changing where
`build_layout` starts, and - if they land in a different bank - swapping the
pattern-table `WriteNametableTiles` calls for `LoadCompressedGraphics`, which
takes a bank number as an inline argument and restores the caller's bank on the
way out.  The tile bytes would need running through the `$D4C3` codec first,
which on letter art gives back about one byte in 352.

The code goes in the 39 bytes the banner-selection logic occupies at `$AC5D`
- the same span `remove_course_banner_patches` jumps over - because a single
fixed banner has nothing to select.
"""

from golf.core.asm6502 import assemble
from golf.core.signpost import (
    BANNER_TABLE,
    BANK,
    read_banner_descriptor,
)

from .byte_patch import BytePatch
from .composite import CompositePatch

WRITE_NAMETABLE_TILES = 0xCE84

# The banner-selection block: `LDX CurrCourse` through the last byte before the
# hole-number section at $AC84.
SELECT_START = 0xAC5D
SELECT_END = 0xAC84

# The five banner bodies, and where new data may start once they are reclaimed.
BODY_REGION_START = 0xADE4
BODY_REGION_END = 0xB01C        # the digit pointer table
PATTERN_BASE = 0x1000
ROW_WIDTH = 32                  # bytes per WriteNametableTiles row = 2 tiles

_BANK12_PRG_BASE = BANK * 0x4000


def _prg(cpu_addr: int) -> int:
    return _BANK12_PRG_BASE + (cpu_addr - 0x8000)


def _descriptor(dest: int, width: int, rows: int, pointer: int) -> bytes:
    """A `WriteNametableTiles` descriptor: dest, header, rows, then a pointer.

    Bit 7 of the header says the body lives elsewhere rather than following
    inline; the low six bits are the width.
    """
    if not 1 <= width <= 0x3F:
        raise ValueError(f"width {width} does not fit the header's six bits")
    if rows > width:
        raise ValueError(
            f"{rows} rows at width {width}: $CEE8 abandons a transfer when "
            "width < rows"
        )
    return bytes(
        [dest & 0xFF, dest >> 8, 0x80 | width, rows, pointer & 0xFF, pointer >> 8]
    )


def data_region(keep_start: int, keep_length: int) -> tuple:
    """The largest run of reclaimed banner body left beside the kept one."""
    before = (BODY_REGION_START, keep_start - BODY_REGION_START)
    after = (keep_start + keep_length, BODY_REGION_END - (keep_start + keep_length))
    return max(before, after, key=lambda run: run[1])


def build_layout(patterns, chunks, banner_index: int, banner_body: bytes, keep: tuple):
    """Where every byte goes, without reading or writing a ROM.

    `chunks` is `[(first_tile, count), ...]` from `signpost.allocate_patterns`;
    the patterns are handed out in that order.  `keep` is the kept banner body's
    `(address, length)`, which the new data has to stay clear of.
    """
    if sum(count for _, count in chunks) < len(patterns):
        raise ValueError("chunks do not cover every new pattern")

    origin, available = data_region(*keep)
    blobs = []
    descriptors = []
    supply = list(patterns)
    cursor = origin

    for first_tile, count in chunks:
        taken, supply = supply[:count], supply[count:]
        # A short chunk still writes whole rows, so pad with what is already in
        # the unused slots - blank tiles the screen never references.
        body = b"".join(taken) + bytes(16 * (count - len(taken)))
        blobs.append((cursor, body))
        descriptors.append(
            _descriptor(
                dest=PATTERN_BASE + first_tile * 16,
                width=ROW_WIDTH,
                rows=count // 2,
                pointer=cursor,
            )
        )
        cursor += len(body)

    descriptor_origin = cursor
    cursor += 6 * len(descriptors)
    if cursor - origin > available:
        raise ValueError(
            f"tile data and descriptors need {cursor - origin} bytes; the "
            f"reclaimed banner bodies beside ${keep[0]:04X} hold {available}"
        )

    return {
        "blobs": blobs,
        "descriptors": descriptors,
        "descriptor_origin": descriptor_origin,
        "banner_descriptor": BANNER_TABLE + banner_index * 6,
        "banner_body": banner_body,
        "origin": origin,
        "end": cursor,
    }


def build_code(layout) -> bytes:
    """The replacement for the banner-selection block.

    One `WriteNametableTiles` call per pattern chunk, then the banner itself,
    then back into the hole-number section.  The banner call reuses the
    descriptor already in the `$AD86` table rather than writing a sixth one.
    """
    calls = "\n".join(
        f"        jsr ${WRITE_NAMETABLE_TILES:04X}\n"
        f"        .word ${layout['descriptor_origin'] + 6 * index:04X}"
        for index in range(len(layout["descriptors"]))
    )
    source = f"""
{calls}
        jsr ${WRITE_NAMETABLE_TILES:04X}
        .word ${layout["banner_descriptor"]:04X}
        jmp ${SELECT_END:04X}
    """
    code = assemble(source, SELECT_START).code
    if len(code) > SELECT_END - SELECT_START:
        raise ValueError(
            f"{len(code)} bytes of code do not fit the "
            f"{SELECT_END - SELECT_START} the banner selection occupies"
        )
    return code


def random_banner_patches(rom, patterns, chunks, banner_index: int, banner_body: bytes):
    """The whole change, as one composite patch against a vanilla ROM.

    `rom` is only read, to record the bytes each sub-patch expects to replace.
    """
    target = read_banner_descriptor(rom, banner_index)
    layout = build_layout(
        patterns, chunks, banner_index, banner_body, (target.pointer, target.length)
    )
    patches = []

    for origin, body in layout["blobs"]:
        patches.append(
            BytePatch(
                name=f"signpost_random_tiles_{origin:04X}",
                description=f"{len(body) // 16} new signpost tiles at ${origin:04X}",
                prg_offset=_prg(origin),
                original=bytes(rom.read_switched(origin, BANK, len(body))),
                patched=body,
            )
        )

    descriptors = b"".join(layout["descriptors"])
    patches.append(
        BytePatch(
            name="signpost_random_tile_descriptors",
            description=(
                f"{len(layout['descriptors'])} WriteNametableTiles descriptors "
                f"aimed at the pattern table"
            ),
            prg_offset=_prg(layout["descriptor_origin"]),
            original=bytes(
                rom.read_switched(layout["descriptor_origin"], BANK, len(descriptors))
            ),
            patched=descriptors,
        )
    )

    patches.append(
        BytePatch(
            name="signpost_random_banner_body",
            description=f"the new banner's {len(banner_body)} nametable bytes",
            prg_offset=_prg(target.pointer),
            original=bytes(rom.read_switched(target.pointer, BANK, len(banner_body))),
            patched=banner_body,
        )
    )

    code = build_code(layout)
    patches.append(
        BytePatch(
            name="signpost_random_banner_draw",
            description=(
                "replace the course/contest banner selection with the fixed "
                "banner plus its pattern-table loads"
            ),
            prg_offset=_prg(SELECT_START),
            original=bytes(rom.read_switched(SELECT_START, BANK, len(code))),
            patched=code,
        )
    )

    return CompositePatch(
        name="signpost_random_banner",
        description="draw one fixed signpost banner, with new tile art",
        patches=patches,
    )
