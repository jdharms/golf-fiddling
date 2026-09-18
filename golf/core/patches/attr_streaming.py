"""
Terrain attribute streaming patch.

Streams terrain attribute bytes directly from ROM instead of bulk-copying
them into a fixed 72-byte RAM buffer when a hole loads. This removes the
72-byte ceiling on attribute data, which JP-derived holes exceed (up to 90
bytes - see docs/jp_extraction.md).

RAM introduced:
  $47-$48: AttrDataPtr  - pointer to the current hole's attribute data in ROM
  $49:     AttrDataBank - bank number containing that data

New code occupies free space at $E1AD-$E1D0 (36 bytes) in the fixed bank.

The patch set applies the same way with or without MULTI_BANK_CODE_PATCH
(multi_bank.py): that patch rewrites the six bytes before the terrain
bank-switch call at $DB6E, and this one redirects the call itself.
"""

from .byte_patch import BytePatch
from .composite import CompositePatch

# New routines written into fixed-bank free space at $E1AD (36 bytes, all
# zero in a vanilla ROM).
#
# LoadTerrainAttrBanked ($E1AD, 17 bytes) - saves/restores the current bank
# around a single on-demand attribute byte read. Called by the ball-lie
# calculation (LEED5), which needs its own bank preserved afterward.
#   LDA $5C          ; CurrentBank
#   PHA
#   LDA $49          ; AttrDataBank
#   JSR $D352        ; BankSwitchRoutine
#   LDA ($47),Y       ; load from AttrDataPtr
#   TAX
#   PLA
#   JSR $D352        ; restore original bank
#   TXA
#   RTS
_LOAD_TERRAIN_ATTR_BANKED = bytes(
    [
        0xA5,
        0x5C,
        0x48,
        0xA5,
        0x49,
        0x20,
        0x52,
        0xD3,
        0xB1,
        0x47,
        0xAA,
        0x68,
        0x20,
        0x52,
        0xD3,
        0x8A,
        0x60,
    ]
)
assert len(_LOAD_TERRAIN_ATTR_BANKED) == 17

# SaveBankAndSwitch ($E1BE, 5 bytes) - records the bank about to be switched
# to in AttrDataBank, then tail-calls BankSwitchRoutine. The terrain
# bank-switch call site is redirected here (see module docstring) so later
# attribute reads know which bank the current hole's data lives in.
#   STA $49
#   JMP $D352
_SAVE_BANK_AND_SWITCH = bytes([0x85, 0x49, 0x4C, 0x52, 0xD3])
assert len(_SAVE_BANK_AND_SWITCH) == 5

# LE451_Entry ($E1C3, 14 bytes) - trampoline for the windowing routine at
# $E451. Switches to the attribute bank once up front (no restore - unlike
# LoadTerrainAttrBanked, LE451 doesn't resume other bank-sensitive code
# afterward), then replays the 3 instructions its entry point overwrote.
#   LDA $49
#   JSR $D352
#   LDA #$00         ; original: displaced instruction
#   STA $1C          ; original: displaced instruction
#   STA $1D          ; original: displaced instruction
#   JMP $E457        ; continue at the first untouched instruction
_LE451_ENTRY = bytes(
    [
        0xA5,
        0x49,
        0x20,
        0x52,
        0xD3,
        0xA9,
        0x00,
        0x85,
        0x1C,
        0x85,
        0x1D,
        0x4C,
        0x57,
        0xE4,
    ]
)
assert len(_LE451_ENTRY) == 14

_NEW_CODE = _LOAD_TERRAIN_ATTR_BANKED + _SAVE_BANK_AND_SWITCH + _LE451_ENTRY
assert len(_NEW_CODE) == 36

ATTR_STREAMING_FREE_SPACE_PATCH = BytePatch(
    name="attr_streaming_free_space",
    description=(
        "New LoadTerrainAttrBanked/SaveBankAndSwitch/LE451_Entry routines "
        "in free space at $E1AD"
    ),
    prg_offset=0x3E1AD,
    original=bytes(36),
    patched=_NEW_CODE,
)

# LE451 windowing routine: replace its 6-byte init sequence with a jump to
# the trampoline above (which replays those 3 instructions after switching
# banks). The 3 extra bytes beyond the JMP are never executed.
ATTR_STREAMING_LE451_ENTRY_PATCH = BytePatch(
    name="attr_streaming_le451_entry",
    description="LE451: jump to entry trampoline instead of inline init",
    prg_offset=0x3E451,
    original=bytes([0xA9, 0x00, 0x85, 0x1C, 0x85, 0x1D]),
    patched=bytes([0x4C, 0xC3, 0xE1, 0xEA, 0xEA, 0xEA]),
)

# LE451 reads terrain attributes 3 times via a hardcoded RAM buffer address;
# each becomes an indirect read through AttrDataPtr instead (one byte
# shorter, padded with a NOP to stay byte-neutral).
ATTR_STREAMING_LE451_LDA_PATCHES = [
    BytePatch(
        name=f"attr_streaming_le451_lda_{i + 1}",
        description="LE451: LDA TerrainAttrs,Y -> LDA (AttrDataPtr),Y",
        prg_offset=offset,
        original=bytes([0xB9, 0x33, 0x05]),
        patched=bytes([0xB1, 0x47, 0xEA]),
    )
    for i, offset in enumerate([0x3E4A7, 0x3E4B7, 0x3E4D9])
]

# Ball-lie calculation: same RAM-buffer read, replaced with a call to the
# save/restore helper since this routine must preserve its caller's bank.
ATTR_STREAMING_LEED5_PATCH = BytePatch(
    name="attr_streaming_leed5",
    description="LEED5: LDA TerrainAttrs,Y -> JSR LoadTerrainAttrBanked",
    prg_offset=0x3EF04,
    original=bytes([0xB9, 0x33, 0x05]),
    patched=bytes([0x20, 0xAD, 0xE1]),
)

# LoadTerrainAndAttrs: repoint the pointer it stores from the old RAM
# buffer target to AttrDataPtr.
ATTR_STREAMING_LOADTERRAIN_PTR_LOW_PATCH = BytePatch(
    name="attr_streaming_loadterrain_ptr_low",
    description="LoadTerrainAndAttrs: STA $50 -> STA $47 (AttrDataPtr low)",
    prg_offset=0x3DB8F,
    original=bytes([0x85, 0x50]),
    patched=bytes([0x85, 0x47]),
)

ATTR_STREAMING_LOADTERRAIN_PTR_HIGH_PATCH = BytePatch(
    name="attr_streaming_loadterrain_ptr_high",
    description="LoadTerrainAndAttrs: STA $51 -> STA $48 (AttrDataPtr high)",
    prg_offset=0x3DB94,
    original=bytes([0x85, 0x51]),
    patched=bytes([0x85, 0x48]),
)

# LoadTerrainAndAttrs: redirect its terrain bank-switch call through
# SaveBankAndSwitch so AttrDataBank gets recorded.
ATTR_STREAMING_BANK_SWITCH_PATCH = BytePatch(
    name="attr_streaming_bank_switch",
    description="LoadTerrainAndAttrs: JSR BankSwitchRoutine -> JSR SaveBankAndSwitch",
    prg_offset=0x3DB6E,
    original=bytes([0x20, 0x52, 0xD3]),
    patched=bytes([0x20, 0xBE, 0xE1]),
)

# The 72-byte bulk copy into the old RAM buffer is no longer needed since
# attributes are streamed on demand instead.
ATTR_STREAMING_LOADTERRAIN_COPY_LOOP_NOP_PATCH = BytePatch(
    name="attr_streaming_loadterrain_copy_loop_nop",
    description="LoadTerrainAndAttrs: NOP out the attribute bulk-copy loop",
    prg_offset=0x3DB96,
    original=bytes([0xA0, 0x47, 0xB1, 0x50, 0x99, 0x33, 0x05, 0x88, 0x10, 0xF8]),
    patched=bytes([0xEA] * 10),
)

# The whole attr-streaming patch set, in application order: the new routines
# first, so no redirect ever points at code that isn't there yet.
ATTR_STREAMING_PATCHES = [
    ATTR_STREAMING_FREE_SPACE_PATCH,
    ATTR_STREAMING_LE451_ENTRY_PATCH,
    *ATTR_STREAMING_LE451_LDA_PATCHES,
    ATTR_STREAMING_LEED5_PATCH,
    ATTR_STREAMING_LOADTERRAIN_PTR_LOW_PATCH,
    ATTR_STREAMING_LOADTERRAIN_PTR_HIGH_PATCH,
    ATTR_STREAMING_BANK_SWITCH_PATCH,
    ATTR_STREAMING_LOADTERRAIN_COPY_LOOP_NOP_PATCH,
]

ATTR_STREAMING_PATCH = CompositePatch(
    name="attr_streaming",
    description="Stream terrain attributes from ROM instead of copying them into the 72-byte RAM buffer",
    patches=ATTR_STREAMING_PATCHES,
)
