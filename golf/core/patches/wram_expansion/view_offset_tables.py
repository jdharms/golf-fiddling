"""
Relocate and expand the ViewOffsetToAddrLow/High/AttrIndex tables.

These three parallel tables, indexed by ViewVerticalOffset ($AB), are read
by the vertical-scroll windowing routine at LE451 (CPU $E451) to compute
where in the terrain buffer to read from when writing the current screen's
worth of nametable tiles. Vanilla has 10 entries per table (index 0 is a
duplicate of index 1; indices 1-9 give `scroll_row = (index - 1) * 2`,
topping out at scroll_row=16, i.e. 16 + 30 visible rows = 46 max terrain
height) packed with zero slack at CPU $E4F9-$E516 in the fixed bank -
$E517 is already the start of the next table.

Supporting 60-row terrain requires scroll_row up to 30, i.e. index up to 16
- 17 entries per table. Since there's no room to grow in place, the tables
move to the free ($FF-filled) space at $CA40 documented in
docs/wram_expansion.md under "Known Free Space". New entries 10-16 continue
the existing linear progression (see docs/wram_expansion.md for the
worked-out table).
"""

from ..byte_patch import BytePatch

_VIEW_OFFSET_ADDR_LOW = bytes(
    [
        0x00, 0x00, 0x2C, 0x58, 0x84, 0xB0, 0xDC, 0x08,
        0x34, 0x60, 0x8C, 0xB8, 0xE4, 0x10, 0x3C, 0x68, 0x94,
    ]
)
assert len(_VIEW_OFFSET_ADDR_LOW) == 17

_VIEW_OFFSET_ADDR_HIGH = bytes(
    [
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x01,
        0x01, 0x01, 0x01, 0x01, 0x01, 0x02, 0x02, 0x02, 0x02,
    ]
)
assert len(_VIEW_OFFSET_ADDR_HIGH) == 17

_VIEW_OFFSET_ATTR_INDEX = bytes(
    [
        0xFA, 0x00, 0x00, 0x06, 0x06, 0x0C, 0x0C, 0x12,
        0x12, 0x18, 0x18, 0x1E, 0x1E, 0x24, 0x24, 0x2A, 0x2A,
    ]
)
assert len(_VIEW_OFFSET_ATTR_INDEX) == 17

# New tables, packed in order at $CA40:
#   ViewOffsetToAddrLow:   $CA40-$CA50
#   ViewOffsetToAddrHigh:  $CA51-$CA61
#   ViewOffsetToAttrIndex: $CA62-$CA72
_NEW_TABLES = _VIEW_OFFSET_ADDR_LOW + _VIEW_OFFSET_ADDR_HIGH + _VIEW_OFFSET_ATTR_INDEX
assert len(_NEW_TABLES) == 51

VIEW_OFFSET_TABLES_FREE_SPACE_PATCH = BytePatch(
    name="wram_expansion_view_offset_tables_free_space",
    description=(
        "New 17-entry ViewOffsetToAddrLow/High/AttrIndex tables written "
        "into free space at $CA40 (expanded from vanilla's 10 entries to "
        "support 60-row terrain)"
    ),
    prg_offset=0x3CA40,
    original=bytes([0xFF] * 51),
    patched=_NEW_TABLES,
)

# LE451: LDA ViewOffsetToAddrLow,X -> new table at $CA40
VIEW_OFFSET_ADDR_LOW_LDA_PATCH = BytePatch(
    name="wram_expansion_view_offset_addr_low_lda",
    description="LE451: LDA ViewOffsetToAddrLow,X -> LDA $CA40,X",
    prg_offset=0x3E46D,
    original=bytes([0xBD, 0xF9, 0xE4]),
    patched=bytes([0xBD, 0x40, 0xCA]),
)

# LE451: LDA ViewOffsetToAddrHigh,X -> new table at $CA51
VIEW_OFFSET_ADDR_HIGH_LDA_PATCH = BytePatch(
    name="wram_expansion_view_offset_addr_high_lda",
    description="LE451: LDA ViewOffsetToAddrHigh,X -> LDA $CA51,X",
    prg_offset=0x3E476,
    original=bytes([0xBD, 0x03, 0xE5]),
    patched=bytes([0xBD, 0x51, 0xCA]),
)

# LE451: LDY ViewOffsetToAttrIndex,X -> new table at $CA62
VIEW_OFFSET_ATTR_INDEX_LDY_PATCH = BytePatch(
    name="wram_expansion_view_offset_attr_index_ldy",
    description="LE451: LDY ViewOffsetToAttrIndex,X -> LDY $CA62,X",
    prg_offset=0x3E493,
    original=bytes([0xBC, 0x0D, 0xE5]),
    patched=bytes([0xBC, 0x62, 0xCA]),
)

VIEW_OFFSET_TABLE_PATCHES = [
    VIEW_OFFSET_TABLES_FREE_SPACE_PATCH,
    VIEW_OFFSET_ADDR_LOW_LDA_PATCH,
    VIEW_OFFSET_ADDR_HIGH_LDA_PATCH,
    VIEW_OFFSET_ATTR_INDEX_LDY_PATCH,
]
