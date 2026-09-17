"""
Stub the replay-header read so hall-of-fame replay presence always reads
as empty.

The routine at CPU $B689 (bank $0E, PRG 0x3B689) takes a replay-type
selector in $0727 (0-3, presumably Ace/Albatross/Eagle/Birdie), doubles it
to index a 4-entry pointer table at $B7EC/$B7ED, and loads the matching
*ReplayHeaders base address (one of AceReplayHeaders/AlbaReplayHeaders/
EagleReplayHeaders/BirdieReplayHeaders - all in the WRAM region this
effort is reclaiming, see docs/wram_expansion.md) into $20/$21. It then
loops Y 0..4, copying the 5-byte header FIFO via `($20),Y` into
`$0729,Y` for whatever presence/hall-of-fame check consumes it next.

As with L9_BAD4 (see stub_mp_stats_display.py), there's no shared choke
point - the single `LDA ($20),Y` read site (CPU $B69A) is patched
directly to `LDA #$FF`, same 2-byte length as the instruction it
replaces, so the `INY`/`CMP #$05`/`BNE $B69A` loop around it needs no
changes. Unlike the stat displays, $FF (not $00) is the "empty" sentinel
for a replay header slot.
"""

from ..byte_patch import BytePatch

STUB_REPLAY_HEADER_READ_PATCH = BytePatch(
    name="wram_expansion_stub_replay_header_read",
    description=(
        "$B69A (bank $0E): LDA ($20),Y -> LDA #$FF, so replay-header reads "
        "always come back empty"
    ),
    prg_offset=0x3B69A,
    original=bytes([0xB1, 0x20]),
    patched=bytes([0xA9, 0xFF]),
)
