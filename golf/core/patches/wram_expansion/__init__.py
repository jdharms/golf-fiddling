"""
WRAM expansion composite patch.

Groups the patches needed to reclaim the WRAM region immediately before the
vanilla terrain buffer and relocate terrain/greens decompression into the
enlarged space, so holes taller than 48 rows stop overflowing into the
greens buffer. See docs/wram_expansion.md for the full plan.

Sub-patches live in dedicated modules under this package and are added to
WRAM_EXPANSION_PATCH incrementally as each step of the plan is
disassembled and verified against a real ROM.
"""

from ..composite import CompositePatch
from .disable_longest_drive_saving import DISABLE_LONGEST_DRIVE_SAVING_PATCH
from .disable_replay_saving import DISABLE_REPLAY_SAVING_PATCH
from .scroll_threshold_tables import (
    SCROLL_THRESHOLD_HIGH_SBC_PATCH,
    SCROLL_THRESHOLD_LOW_SBC_PATCH,
    SCROLL_THRESHOLD_TABLE_PATCHES,
    SCROLL_THRESHOLD_TABLES_FREE_SPACE_PATCH,
)
from .view_offset_tables import (
    VIEW_OFFSET_ADDR_HIGH_LDA_PATCH,
    VIEW_OFFSET_ADDR_LOW_LDA_PATCH,
    VIEW_OFFSET_ATTR_INDEX_LDY_PATCH,
    VIEW_OFFSET_TABLE_PATCHES,
    VIEW_OFFSET_TABLES_FREE_SPACE_PATCH,
)

WRAM_EXPANSION_PATCH = CompositePatch(
    name="wram_expansion",
    description=(
        "Reclaim WRAM before the terrain buffer and relocate terrain/greens "
        "decompression to support holes taller than 48 rows"
    ),
    patches=[
        *VIEW_OFFSET_TABLE_PATCHES,
        *SCROLL_THRESHOLD_TABLE_PATCHES,
        DISABLE_REPLAY_SAVING_PATCH,
        DISABLE_LONGEST_DRIVE_SAVING_PATCH,
    ],
)

__all__ = [
    "WRAM_EXPANSION_PATCH",
    "VIEW_OFFSET_TABLE_PATCHES",
    "VIEW_OFFSET_TABLES_FREE_SPACE_PATCH",
    "VIEW_OFFSET_ADDR_LOW_LDA_PATCH",
    "VIEW_OFFSET_ADDR_HIGH_LDA_PATCH",
    "VIEW_OFFSET_ATTR_INDEX_LDY_PATCH",
    "SCROLL_THRESHOLD_TABLE_PATCHES",
    "SCROLL_THRESHOLD_TABLES_FREE_SPACE_PATCH",
    "SCROLL_THRESHOLD_LOW_SBC_PATCH",
    "SCROLL_THRESHOLD_HIGH_SBC_PATCH",
    "DISABLE_REPLAY_SAVING_PATCH",
    "DISABLE_LONGEST_DRIVE_SAVING_PATCH",
]
