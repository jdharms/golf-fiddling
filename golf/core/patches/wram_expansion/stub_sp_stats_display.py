"""
Stub the Stroke Play stats display so it always shows zeros.

StrokePlayStatsDisplay (CPU $B8D9, bank $09) reads every field of
StrokePlayStats through a shared helper, LoadStatSramPointer (CPU $BA92,
same bank): given a field index in A, it doubles it and pulls a literal
2-byte address out of a 7-entry table (reached via zero page $20/$21,
set up elsewhere per stats page) into SramPtr ($22/$23). Every subsequent
`LDA (SramPtr+0),Y` in the display routine reads through that pointer.
The seven indices (0-6) it's called with tile StrokePlayStats's 24 bytes
exactly (2+4+4+2+4+4+4), so every address LoadStatSramPointer can ever
produce here falls inside the WRAM region this effort is reclaiming (see
docs/wram_expansion.md).

That makes LoadStatSramPointer a single choke point for this display
routine: patching its entry to always point SramPtr at a fixed all-zero
source, ignoring the requested index entirely, zeroes every stat this
routine reads without touching any of its per-field call sites.

The zero source itself is 4 bytes (covers the widest field read, Y=0..3)
written into $CA93-$CA96 - part of the still-unused tail of the $CA40-
$CAFF free space block (see "Known Free Space" in docs/wram_expansion.md).
It's in the always-mapped fixed bank, so it's safe to point at regardless
of which switchable bank is paged in when the read fires.

Match Play stats needed separate handling (see stub_mp_stats_display.py).
Stroke Tournament stats display, at $BB96 (same bank), turns out to share
the direct-$20/$21 style of that Match Play routine rather than going
through LoadStatSramPointer: $20/$21 is set up once before the routine
runs and it loops 5 times, reading two consecutive bytes per iteration
via `($20),Y` (Y=0,1) straight into a local buffer. Both read sites (CPU
$BBA2 and $BBA8) are patched the same way as the Match Play ones - in
place, `LDA ($20),Y` (`B1 20`) to `LDA #$00` (`A9 00`), same 2-byte
length so the surrounding loop needs no changes.
"""

from ..byte_patch import BytePatch

STAT_ZERO_SOURCE_PATCH = BytePatch(
    name="wram_expansion_stat_zero_source",
    description=(
        "$CA93-$CA96: FF FF FF FF -> 00 00 00 00, a 4-byte always-zero "
        "source for stubbed stat-display reads to point at"
    ),
    prg_offset=0x3CA93,
    original=bytes([0xFF, 0xFF, 0xFF, 0xFF]),
    patched=bytes([0x00, 0x00, 0x00, 0x00]),
)

STUB_SP_STATS_DISPLAY_PATCH = BytePatch(
    name="wram_expansion_stub_sp_stats_display",
    description=(
        "LoadStatSramPointer ($BA92, bank $09): always point SramPtr at "
        "the zero source instead of looking up the requested field's "
        "real address, so StrokePlayStatsDisplay reads zero for every "
        "stat"
    ),
    prg_offset=0x27A92,
    original=bytes(
        [0x0A, 0xA8, 0xB1, 0x20, 0x85, 0x22, 0xC8, 0xB1, 0x20, 0x85, 0x23, 0x60]
    ),
    patched=bytes(
        [
            0xA9, 0x93,  # LDA #$93
            0x85, 0x22,  # STA $22       ; SramPtr lo
            0xA9, 0xCA,  # LDA #$CA
            0x85, 0x23,  # STA $23       ; SramPtr hi
            0x60,        # RTS
            0xEA, 0xEA, 0xEA,  # NOP x3  ; padding, keeps the 12-byte slot intact
        ]
    ),
)

STUB_STROKE_TOURNAMENT_STATS_DISPLAY_FIRST_READ_PATCH = BytePatch(
    name="wram_expansion_stub_stroke_tournament_stats_display_first_read",
    description=(
        "$BBA2 (bank $09): LDA ($20),Y -> LDA #$00 for the first of two "
        "per-iteration field reads in the Stroke Tournament stats display"
    ),
    prg_offset=0x27BA2,
    original=bytes([0xB1, 0x20]),
    patched=bytes([0xA9, 0x00]),
)

STUB_STROKE_TOURNAMENT_STATS_DISPLAY_SECOND_READ_PATCH = BytePatch(
    name="wram_expansion_stub_stroke_tournament_stats_display_second_read",
    description=(
        "$BBA8 (bank $09): LDA ($20),Y -> LDA #$00 for the second of two "
        "per-iteration field reads in the Stroke Tournament stats display"
    ),
    prg_offset=0x27BA8,
    original=bytes([0xB1, 0x20]),
    patched=bytes([0xA9, 0x00]),
)
