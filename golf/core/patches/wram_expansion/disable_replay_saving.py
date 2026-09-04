"""
Disable saving of hall-of-fame replay data (Ace/Birdie/Eagle/Albatross).

L8_9B43 (CPU $9B43, bank $08) appends a shot record to the appropriate
*ReplayHeaders 5-slot FIFO and copies a corresponding block into the
matching *ReplayData region - both of which live in the WRAM region this
effort is reclaiming (see docs/wram_expansion.md). It's entered with X set
to how far under par the hole was played (0 = hole-in-one/Ace, 1 = Birdie,
2 = Eagle, 3 = Albatross); the single confirmed call site at CPU $9B3F
computes X immediately beforehand, making a second entry path implausible.

Patching the entry point itself (rather than the call site) covers that
call site and any other caller for free, at a smaller cost (1 byte vs. 3):
the routine now returns immediately without touching the replay region.
"""

from ..byte_patch import BytePatch

DISABLE_REPLAY_SAVING_PATCH = BytePatch(
    name="wram_expansion_disable_replay_saving",
    description=(
        "L8_9B43 ($9B43): TXA -> RTS, so hall-of-fame replay data is no "
        "longer written to the WRAM region being reclaimed"
    ),
    prg_offset=0x21B43,
    original=bytes([0x8A]),
    patched=bytes([0x60]),
)
