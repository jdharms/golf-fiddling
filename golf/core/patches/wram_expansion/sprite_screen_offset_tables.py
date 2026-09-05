"""
Expand the ViewVerticalOffset -> sprite screen-Y adjustment tables from 10
to 17 entries, to support scrolling through 60-row terrain.

Found chasing a follow-up to the TerrainRowOffsets bug (see
terrain_row_offset_tables.py): fixing that got the ball's *lie* reporting
correctly, but the ball/tee-block *sprites* were still drawn at the wrong
screen position on tall holes, only appearing correctly at one specific
scroll position. That pointed at a second, separate table pair -
`$8F21`/`$8F2B` in bank $0D - indexed by `ViewVerticalOffset` ($AB, the
same value `LD_8F73` computes in scroll_threshold_tables.py) and added
onto a sprite's world Y (`ADC $8F21,X` for the low byte, `ADC $8F2B,X`
for the high byte) to get its on-screen Y. Conceptually this is the same
"per-scroll-step Y adjustment" idea as `ViewOffsetToAddrLow`/`High` (used
for terrain buffer addressing), just a separate implementation for sprite
positioning, living in a different bank.

Table values are two's-complement: `Lo[0]=$10`, `Lo[1]=$00`, then each
step decreases by 16 (`Lo[n] = 16*(1-n) mod 256`), and `Hi[n]` is the
sign-extension of `Lo[n]` (`$00` while `Lo[n]` is still non-negative,
`$FF` once it goes negative) - both vanilla-sized at 10 entries (indices
0-9), immediately followed by real code with only 1 byte of slack.

**17 entries, not 16 - `ViewVerticalOffset` itself can reach `ScrollLimit`,
not just `ScrollLimit-1`.** First pass at this fix only allocated 16
entries (0-15), which was wrong: re-tracing `LD_8F73` (scroll_threshold_
tables.py), it exits via `CPX ScrollLimit; BCS` *before* ever reading
`ScrollThresholdLow/High` at index `ScrollLimit` - so that table's read
range tops out at `ScrollLimit-1` and 16 entries is correct for it - but
the loop can still *store* `X == ScrollLimit` as the final
`ViewVerticalOffset` (when the ball's Y clears every threshold up through
`ScrollLimit-1`, `X` increments one more time before the next iteration's
check catches it). For a 60-row hole, `ScrollLimit = (60-28)/2 = 16`, so
`ViewVerticalOffset` needs a valid entry at index 16 too. This is exactly
why the original `ViewOffsetToAddrLow`/`High`/`AttrIndex` tables (from
before this effort) were already sized to 17 entries - that work already
accounted for this; this table just hadn't been checked against it. With
only 16 entries, `ViewVerticalOffset=16` read one byte past both tables -
stale dead bytes left over in Lo's old space, and unclaimed `$FF` free
space for Hi - and the two `$FF`s plus carry wrapped the high byte back
to `$00`, which every consumer's clip check reads as "definitely
on-screen": this is very likely why the green kept appearing at roughly
the same screen position regardless of actual scroll on the tallest hole.

Found 4 read sites (all bank $0D, all `LDX ViewVerticalOffset` then
reading both tables the same way) via a whole-ROM search for the table's
operand bytes:
  - `LD_8FCC` ($8FD8/$8FDF) - ball sprite position
  - `LD_8ED2` ($8ED5/$8EDB) - shared clip-check-and-render helper, called
    by `LD_8E8A` for the flag, green, and tee-block markers (`LD_8ED0`
    falls through into it with Y forced to 0 for the single-byte flag/
    green positions; tee blocks pass an explicit Y high byte)
  - $8FA5/$8FAF - same shape as `LD_8FCC` (reads `BallY`/`BallYHighByte`
    directly too), so ball-related, but not confirmed which ball-adjacent
    thing this is
  - $9510/$9517 - fourth consumer, not yet identified

All 4 need their `Hi` read redirected; none need touching for `Lo`, same
reasoning as terrain_row_offset_tables.py: `Lo` grows in place using the
space `Hi` vacates, so `Lo`'s base address never moves.

`Hi`'s new 17 bytes go into free space at $CA97-$CAFF (documented in
"Known Free Space") - the tail after everything already carved out of
that block ($CA97-$CAD2 is TerrainRowOffsetsHi's new home; this table's
new home starts right after, at $CAD3).
"""

from ..byte_patch import BytePatch

# Lo grows from 10 to 17 entries (indices 10-16), reusing the first 7
# bytes of Hi's vacated space (which held Hi's old indices 0-6: 00 00 FF
# FF FF FF FF).
_LO_NEW_ENTRIES_10_TO_16 = bytes(
    [0x70, 0x60, 0x50, 0x40, 0x30, 0x20, 0x10]
)
assert len(_LO_NEW_ENTRIES_10_TO_16) == 7

SPRITE_SCREEN_OFFSET_LO_GROW_PATCH = BytePatch(
    name="wram_expansion_sprite_screen_offset_lo_grow",
    description=(
        "$8F2B (bank $0D): grow the ViewVerticalOffset sprite-screen-Y-lo "
        "table from 10 to 17 entries, reusing its Hi counterpart's "
        "vacated space"
    ),
    prg_offset=0x34F2B,
    original=bytes([0x00, 0x00, 0xFF, 0xFF, 0xFF, 0xFF, 0xFF]),
    patched=_LO_NEW_ENTRIES_10_TO_16,
)

# Full 17-entry Hi table (sign-extension of Lo), relocated to free space
# at $CA97 (2 zeros for indices 0-1, then FF for indices 2-16 - all
# negative once Lo goes negative at index 2).
_HI_NEW_TABLE = bytes([0x00, 0x00] + [0xFF] * 15)
assert len(_HI_NEW_TABLE) == 17

SPRITE_SCREEN_OFFSET_HI_FREE_SPACE_PATCH = BytePatch(
    name="wram_expansion_sprite_screen_offset_hi_free_space",
    description=(
        "New 17-entry sprite-screen-Y-hi table written into free space "
        "at $CAD3 (expanded from vanilla's 10 entries to support 60-row "
        "terrain)"
    ),
    prg_offset=0x3CAD3,
    original=bytes([0xFF] * 17),
    patched=_HI_NEW_TABLE,
)

# The 4 read sites that need their Hi-table reference redirected to
# $CAD3. Lo's base address never changes, so none of these routines'
# `ADC $8F21,X` reads need any patch.
_HI_READ_SITES = [
    ("8fdf", 0x34FDF),  # LD_8FCC (ball sprite position)
    ("8edb", 0x34EDB),  # LD_8ED2 (flag/green/tee-block clip-check-and-render)
    ("8faf", 0x34FAF),  # ball-related, exact purpose unconfirmed
    ("9517", 0x35517),  # fourth consumer, not yet identified
]

SPRITE_SCREEN_OFFSET_HI_ADC_PATCHES = [
    BytePatch(
        name=f"wram_expansion_sprite_screen_offset_hi_adc_{label}",
        description=f"${label.upper()} (bank $0D): ADC $8F2B,X -> ADC $CAD3,X",
        prg_offset=offset,
        original=bytes([0x7D, 0x2B, 0x8F]),
        patched=bytes([0x7D, 0xD3, 0xCA]),
    )
    for label, offset in _HI_READ_SITES
]

SPRITE_SCREEN_OFFSET_TABLE_PATCHES = [
    SPRITE_SCREEN_OFFSET_LO_GROW_PATCH,
    SPRITE_SCREEN_OFFSET_HI_FREE_SPACE_PATCH,
    *SPRITE_SCREEN_OFFSET_HI_ADC_PATCHES,
]
