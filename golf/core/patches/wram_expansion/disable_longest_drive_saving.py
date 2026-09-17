"""
Disable saving of longest-drive / total-distance stroke-play stats.

The routine at CPU $AD43 (bank $02) updates the driving-distance stats
shared by StrokePlayStats (X=0) and StrokeTournamentStats (X=$2C, the two
24-byte blocks with an identical layout) - both of which live in the WRAM
region this effort is reclaiming (see docs/wram_expansion.md). It's gated
on: not two-player mode, some completion flag at $04F6, game mode 0-3,
driver selected, first stroke of the hole, and ball lie 0 or 6 - firing
per-shot on a qualifying tee shot, not just at round end. It updates the
running distance total (+2..+5) and drive count (+6) unconditionally past
those gates, and the longest-drive record (+10/+11) if the new drive beats
the current one.

$AD43 itself starts with `JSR $ADC7`, executed unconditionally before any
of the gating checks - an unrelated routine we don't want to skip. So the
patch point is $AD46 (LDA MaybeTwoPlayerFlag, TXA->RTS style: LDA->RTS),
right after that call, rather than the routine's own entry point.
"""

from ..byte_patch import BytePatch

DISABLE_LONGEST_DRIVE_SAVING_PATCH = BytePatch(
    name="wram_expansion_disable_longest_drive_saving",
    description=(
        "$AD46: LDA MaybeTwoPlayerFlag -> RTS, so longest-drive/distance "
        "stats are no longer written to the WRAM region being reclaimed "
        "(preserves the unconditional JSR $ADC7 at $AD43 that precedes it)"
    ),
    prg_offset=0xAD46,
    original=bytes([0xAD]),
    patched=bytes([0x60]),
)
