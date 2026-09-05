"""
Stub the Match Play stats display so it always shows zeros.

Unlike StrokePlayStatsDisplay (see stub_sp_stats_display.py), L9_BAD4 (CPU
$BAD4, bank $09) doesn't go through a shared per-field pointer helper - $20/
$21 is set up once before this routine runs (presumably pointing at
MatchPlayStats) and the routine reads directly through `($20),Y`, walking Y
0,1 then 2,3 across two loop iterations to pull two 2-byte fields into a
local buffer ($29/Tmp_2A and $2B/$2C), which are then differenced and used
for a win-percentage calculation. Both of those fields live in the WRAM
region this effort is reclaiming (see docs/wram_expansion.md).

With no shared choke point to patch, the two `LDA ($20),Y` read sites
(CPU $BAE4 and $BAED) are patched directly to `LDA #$00` instead - same
2-byte length as the instruction they replace, so nothing else in the
routine (notably the `BNE L9_BAE2` loop branch) needs to shift.
"""

from ..byte_patch import BytePatch

STUB_MP_STATS_DISPLAY_FIRST_READ_PATCH = BytePatch(
    name="wram_expansion_stub_mp_stats_display_first_read",
    description=(
        "L9_BAD4 ($BAE4, bank $09): LDA ($20),Y -> LDA #$00 for the first "
        "of two per-iteration field reads"
    ),
    prg_offset=0x27AE4,
    original=bytes([0xB1, 0x20]),
    patched=bytes([0xA9, 0x00]),
)

STUB_MP_STATS_DISPLAY_SECOND_READ_PATCH = BytePatch(
    name="wram_expansion_stub_mp_stats_display_second_read",
    description=(
        "L9_BAD4 ($BAED, bank $09): LDA ($20),Y -> LDA #$00 for the second "
        "of two per-iteration field reads"
    ),
    prg_offset=0x27AED,
    original=bytes([0xB1, 0x20]),
    patched=bytes([0xA9, 0x00]),
)
