"""
Relocate and expand the BallY threshold tables used to compute
ViewVerticalOffset.

These two parallel tables, indexed by X starting at 1, are read by the
routine at CPU $8F73 (bank $0D) to scan the ball's Y position against a
list of thresholds and store how many scroll steps down the ball has
progressed into ViewVerticalOffset ($AB) - the same variable the
already-relocated ViewOffsetToAddrLow/High/AttrIndex tables (see
view_offset_tables.py) are later indexed by by the $E451 windowing
routine. In effect this table decides *how far* to scroll; the $CA40
tables decide *where in the buffer* that scroll amount reads from.

Vanilla packs both tables with zero slack at CPU $8F91-$8FA2 in bank $0D
(9 entries each, indices 0-8), immediately followed by other code/data -
no room to grow in place. Table values are 16-bit thresholds split
low/high across the two tables (BallY:table1, BallYHighByte:table2),
climbing by 0x10 per step from index 1 onward; index 0 (0x0018/0x00) is
never read by the only two confirmed call sites (both start X at 1) and
is carried over unchanged as dead filler.

Reads happen for index 1 through ScrollLimit - 1; when the ball's Y
exceeds every threshold, X reaches ScrollLimit itself and is stored
directly without a table read. So for 60-row terrain (ScrollLimit up to
16, see docs/wram_expansion.md), the tables only need entries through
index 15 to match the range already supported by the $CA40 tables -
7 new entries per table, continuing the existing +0x10 progression.

Like the $CA40 relocation, the new tables move to the free ($FF-filled)
space documented in docs/wram_expansion.md under "Known Free Space" -
specifically the $CA73-$CAFF remainder left after that relocation, since
$C000-$FFFF is always mapped and reachable from bank $0D's code without
a bank switch.
"""

from ..byte_patch import BytePatch

_SCROLL_THRESHOLD_LOW = bytes(
    [
        0x18, 0xD0, 0xE0, 0xF0, 0x00, 0x10, 0x20, 0x30,
        0x40, 0x50, 0x60, 0x70, 0x80, 0x90, 0xA0, 0xB0,
    ]
)
assert len(_SCROLL_THRESHOLD_LOW) == 16

_SCROLL_THRESHOLD_HIGH = bytes(
    [
        0x00, 0x00, 0x00, 0x00, 0x01, 0x01, 0x01, 0x01,
        0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01,
    ]
)
assert len(_SCROLL_THRESHOLD_HIGH) == 16

# New tables, packed in order at $CA73:
#   ScrollThresholdLow:  $CA73-$CA82
#   ScrollThresholdHigh: $CA83-$CA92
_NEW_TABLES = _SCROLL_THRESHOLD_LOW + _SCROLL_THRESHOLD_HIGH
assert len(_NEW_TABLES) == 32

SCROLL_THRESHOLD_TABLES_FREE_SPACE_PATCH = BytePatch(
    name="wram_expansion_scroll_threshold_tables_free_space",
    description=(
        "New 16-entry BallY scroll-threshold tables written into free "
        "space at $CA73 (expanded from vanilla's 9 entries to support "
        "60-row terrain)"
    ),
    prg_offset=0x3CA73,
    original=bytes([0xFF] * 32),
    patched=_NEW_TABLES,
)

# $8F73 (bank $0D): SBC ScrollThresholdLow,X -> new table at $CA73
SCROLL_THRESHOLD_LOW_SBC_PATCH = BytePatch(
    name="wram_expansion_scroll_threshold_low_sbc",
    description="$8F81: SBC ScrollThresholdLow,X -> SBC $CA73,X",
    prg_offset=0x34F81,
    original=bytes([0xFD, 0x91, 0x8F]),
    patched=bytes([0xFD, 0x73, 0xCA]),
)

# $8F73 (bank $0D): SBC ScrollThresholdHigh,X -> new table at $CA83
SCROLL_THRESHOLD_HIGH_SBC_PATCH = BytePatch(
    name="wram_expansion_scroll_threshold_high_sbc",
    description="$8F86: SBC ScrollThresholdHigh,X -> SBC $CA83,X",
    prg_offset=0x34F86,
    original=bytes([0xFD, 0x9A, 0x8F]),
    patched=bytes([0xFD, 0x83, 0xCA]),
)

SCROLL_THRESHOLD_TABLE_PATCHES = [
    SCROLL_THRESHOLD_TABLES_FREE_SPACE_PATCH,
    SCROLL_THRESHOLD_LOW_SBC_PATCH,
    SCROLL_THRESHOLD_HIGH_SBC_PATCH,
]
