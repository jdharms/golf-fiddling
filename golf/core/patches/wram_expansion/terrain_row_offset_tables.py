"""
Expand TerrainRowOffsetsLo/Hi from 48 to 60 entries, to support ball-lie
lookups on holes taller than 48 rows.

Found while chasing a bug where the 3 tallest JP UK holes (9, 14, 18 -
the only ones over 48 rows) showed the ball at the wrong position and a
bogus "Out of Bounds" lie check at rest. `LEE9F` (see "Terrain Buffer
Reference Sites" in docs/wram_expansion.md) converts ball Y to a row index
and looks up that row's byte offset into the terrain buffer via these two
tables. Both turned out to still be vanilla-sized (48 entries, rows 0-47)
with zero slack - immediately followed by real code, not $FF filler - so a
row index past 47 (e.g. ~54 for JP UK hole 14's tee) read straight past
the table into opcode bytes.

Rather than relocate both tables to free space (120 bytes needed - more
than the ~105 bytes left in $CA40-$CAFF after the stat-zero-source patch),
only `TerrainRowOffsetsHi` moves. `TerrainRowOffsetsLo` ($F66E, immediately
followed by `TerrainRowOffsetsHi` at $F69E, which is immediately followed
by real code at $F6CE) grows in place from 48 to 60 bytes, using the space
`TerrainRowOffsetsHi` vacates - `Lo`'s new tail ($F69E-$F6A9, 12 bytes)
lands entirely inside `Hi`'s old 48-byte span, nowhere near the code at
$F6CE. `Lo`'s own read site (`$EEB5: ADC TerrainRowOffsetsLo,Y`) doesn't
need patching at all, since its base address never changes. Only `Hi`'s
read site needs redirecting to its new home.

`Hi`'s new 60 bytes go into $CA97-$CAD2 (free space, part of the same
$CA40-$CAFF block documented in "Known Free Space" - $CA93-$CA96 is
already spoken for by the stat-zero-source patch).
"""

from ..byte_patch import BytePatch

# TerrainRowOffsetsLo grows from 48 to 60 entries (row * 22, low byte,
# mod 256) by claiming the first 12 bytes of TerrainRowOffsetsHi's old
# space - rows 48-59.
_LO_NEW_ROWS_48_TO_59 = bytes(
    [0x20, 0x36, 0x4C, 0x62, 0x78, 0x8E, 0xA4, 0xBA, 0xD0, 0xE6, 0xFC, 0x12]
)
assert len(_LO_NEW_ROWS_48_TO_59) == 12

TERRAIN_ROW_OFFSETS_LO_GROW_PATCH = BytePatch(
    name="wram_expansion_terrain_row_offsets_lo_grow",
    description=(
        "$F69E: grow TerrainRowOffsetsLo from 48 to 60 entries (rows "
        "48-59), reusing TerrainRowOffsetsHi's vacated space"
    ),
    prg_offset=0x3F69E,
    original=bytes(12),
    patched=_LO_NEW_ROWS_48_TO_59,
)

# Full 60-entry TerrainRowOffsetsHi (row * 22, high byte), relocated to
# free space at $CA97.
_HI_NEW_TABLE = bytes([0x00] * 12 + [0x01] * 12 + [0x02] * 11 + [0x03] * 12 + [0x04] * 12 + [0x05] * 1)
assert len(_HI_NEW_TABLE) == 60

TERRAIN_ROW_OFFSETS_HI_FREE_SPACE_PATCH = BytePatch(
    name="wram_expansion_terrain_row_offsets_hi_free_space",
    description=(
        "New 60-entry TerrainRowOffsetsHi table written into free space "
        "at $CA97 (expanded from vanilla's 48 entries to support 60-row "
        "terrain)"
    ),
    prg_offset=0x3CA97,
    original=bytes([0xFF] * 60),
    patched=_HI_NEW_TABLE,
)

# LEE9F: ADC TerrainRowOffsetsHi,Y -> new table at $CA97. (The matching
# TerrainRowOffsetsLo read at $EEB5 needs no change - Lo's base address
# never moves, only its length grows.)
TERRAIN_ROW_OFFSETS_HI_ADC_PATCH = BytePatch(
    name="wram_expansion_terrain_row_offsets_hi_adc",
    description="LEE9F ($EEBC): ADC TerrainRowOffsetsHi,Y -> ADC $CA97,Y",
    prg_offset=0x3EEBC,
    original=bytes([0x79, 0x9E, 0xF6]),
    patched=bytes([0x79, 0x97, 0xCA]),
)

TERRAIN_ROW_OFFSET_TABLE_PATCHES = [
    TERRAIN_ROW_OFFSETS_LO_GROW_PATCH,
    TERRAIN_ROW_OFFSETS_HI_FREE_SPACE_PATCH,
    TERRAIN_ROW_OFFSETS_HI_ADC_PATCH,
]
