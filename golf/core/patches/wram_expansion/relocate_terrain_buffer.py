"""
Relocate the decompressed terrain buffer's base address to make room for
60-row terrain.

Greens is *not* moving - it stays fixed at WRAM $15A6 (CPU $75A6), see
docs/wram_expansion.md. Terrain needs to grow from 1,056 bytes (22 x 48)
to 1,320 bytes (22 x 60), so keeping its current *end* address fixed
(WRAM $1186 + 1,056 = $15A6, i.e. unchanged - right where greens begins)
and extending backward only, the new base works out to:

    $15A6 - 1,320 = $107E  (WRAM), i.e. CPU $707E

That lands inside the WRAM region reclaimed in steps 1-6 (`$0F9C`-`$1185`,
490 bytes) using 264 of its 490 bytes, leaving the 226-byte margin noted
in "What We Know". Nothing after the terrain buffer's end moves, so
`DecompressGreen` and everything downstream of it is untouched.

Every site that hardcodes the old base ($7186, i.e. lo=$86/hi=$71) - see
"Terrain Buffer Reference Sites" in docs/wram_expansion.md for how these
were found - gets its lo/hi bytes swapped to the new base (lo=$7E/hi=$70):

- `DecompressTerrain` main write pointer ($E107-$E10D): sets SramPtr to
  the terrain base directly.
- `DecompressTerrain` vertical-fill second pass ($E168-$E176): sets
  $20/$21 to the terrain base (current row) and $24/$25 to the terrain
  base + $16 (one row down, 22-byte row width) for the row-above copy.
  The "+$16" pointer's own literal ($719C -> $7094) also needs updating,
  not just the shared base bytes.
- `LE451` windowing routine ($E471/$E479): adds the terrain base onto a
  per-row offset from the (already-expanded) ViewOffsetToAddrLow/High
  tables via `ADC #imm`, rather than a two-instruction pointer setup.
- Ball-lie tile lookup, `LEE9F` ($EEC4/$EECA): same `ADC #imm` pattern,
  adds the terrain base onto a row offset from TerrainRowOffsetsLo/Hi.

All patches are single-byte immediate-operand changes - no instruction
lengths change, so nothing else in any of these routines needs to shift.
"""

from ..byte_patch import BytePatch

# --- DecompressTerrain main write pointer (SramPtr = new base $707E) ---

TERRAIN_BASE_MAIN_LO_PATCH = BytePatch(
    name="wram_expansion_terrain_base_main_lo",
    description="$E108: LDA #$86 -> LDA #$7E (DecompressTerrain SramPtr lo)",
    prg_offset=0x3E108,
    original=bytes([0x86]),
    patched=bytes([0x7E]),
)

TERRAIN_BASE_MAIN_HI_PATCH = BytePatch(
    name="wram_expansion_terrain_base_main_hi",
    description="$E10C: LDA #$71 -> LDA #$70 (DecompressTerrain SramPtr hi)",
    prg_offset=0x3E10C,
    original=bytes([0x71]),
    patched=bytes([0x70]),
)

# --- DecompressTerrain vertical-fill second pass: $20/$21 = new base ---

TERRAIN_BASE_VFILL_ROW_LO_PATCH = BytePatch(
    name="wram_expansion_terrain_base_vfill_row_lo",
    description="$E169: LDA #$86 -> LDA #$7E (vertical-fill current-row ptr lo)",
    prg_offset=0x3E169,
    original=bytes([0x86]),
    patched=bytes([0x7E]),
)

TERRAIN_BASE_VFILL_ROW_HI_PATCH = BytePatch(
    name="wram_expansion_terrain_base_vfill_row_hi",
    description="$E16D: LDA #$71 -> LDA #$70 (vertical-fill current-row ptr hi)",
    prg_offset=0x3E16D,
    original=bytes([0x71]),
    patched=bytes([0x70]),
)

# --- DecompressTerrain vertical-fill second pass: $24/$25 = new base + $16 ---

TERRAIN_BASE_VFILL_ROW_BELOW_LO_PATCH = BytePatch(
    name="wram_expansion_terrain_base_vfill_row_below_lo",
    description="$E171: LDA #$9C -> LDA #$94 (vertical-fill row-below ptr lo)",
    prg_offset=0x3E171,
    original=bytes([0x9C]),
    patched=bytes([0x94]),
)

TERRAIN_BASE_VFILL_ROW_BELOW_HI_PATCH = BytePatch(
    name="wram_expansion_terrain_base_vfill_row_below_hi",
    description="$E175: LDA #$71 -> LDA #$70 (vertical-fill row-below ptr hi)",
    prg_offset=0x3E175,
    original=bytes([0x71]),
    patched=bytes([0x70]),
)

# --- LE451 windowing routine ---

TERRAIN_BASE_WINDOWING_LO_PATCH = BytePatch(
    name="wram_expansion_terrain_base_windowing_lo",
    description="$E472: ADC #$86 -> ADC #$7E (LE451 terrain-base add, lo)",
    prg_offset=0x3E472,
    original=bytes([0x86]),
    patched=bytes([0x7E]),
)

TERRAIN_BASE_WINDOWING_HI_PATCH = BytePatch(
    name="wram_expansion_terrain_base_windowing_hi",
    description="$E47A: ADC #$71 -> ADC #$70 (LE451 terrain-base add, hi)",
    prg_offset=0x3E47A,
    original=bytes([0x71]),
    patched=bytes([0x70]),
)

# --- Ball-lie tile lookup (LEE9F) ---

TERRAIN_BASE_BALL_LIE_LO_PATCH = BytePatch(
    name="wram_expansion_terrain_base_ball_lie_lo",
    description="$EEC5: ADC #$86 -> ADC #$7E (LEE9F terrain-base add, lo)",
    prg_offset=0x3EEC5,
    original=bytes([0x86]),
    patched=bytes([0x7E]),
)

TERRAIN_BASE_BALL_LIE_HI_PATCH = BytePatch(
    name="wram_expansion_terrain_base_ball_lie_hi",
    description="$EECB: ADC #$71 -> ADC #$70 (LEE9F terrain-base add, hi)",
    prg_offset=0x3EECB,
    original=bytes([0x71]),
    patched=bytes([0x70]),
)

RELOCATE_TERRAIN_BUFFER_PATCHES = [
    TERRAIN_BASE_MAIN_LO_PATCH,
    TERRAIN_BASE_MAIN_HI_PATCH,
    TERRAIN_BASE_VFILL_ROW_LO_PATCH,
    TERRAIN_BASE_VFILL_ROW_HI_PATCH,
    TERRAIN_BASE_VFILL_ROW_BELOW_LO_PATCH,
    TERRAIN_BASE_VFILL_ROW_BELOW_HI_PATCH,
    TERRAIN_BASE_WINDOWING_LO_PATCH,
    TERRAIN_BASE_WINDOWING_HI_PATCH,
    TERRAIN_BASE_BALL_LIE_LO_PATCH,
    TERRAIN_BASE_BALL_LIE_HI_PATCH,
]
