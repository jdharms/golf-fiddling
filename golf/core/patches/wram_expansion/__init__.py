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
from .stub_mp_stats_display import (
    STUB_MP_STATS_DISPLAY_FIRST_READ_PATCH,
    STUB_MP_STATS_DISPLAY_SECOND_READ_PATCH,
)
from .relocate_terrain_buffer import RELOCATE_TERRAIN_BUFFER_PATCHES
from .stub_replay_header_read import STUB_REPLAY_HEADER_READ_PATCH
from .stub_sp_stats_display import (
    STAT_ZERO_SOURCE_PATCH,
    STUB_SP_STATS_DISPLAY_PATCH,
    STUB_STROKE_TOURNAMENT_STATS_DISPLAY_FIRST_READ_PATCH,
    STUB_STROKE_TOURNAMENT_STATS_DISPLAY_SECOND_READ_PATCH,
)
from .sprite_screen_offset_tables import SPRITE_SCREEN_OFFSET_TABLE_PATCHES
from .terrain_row_offset_tables import TERRAIN_ROW_OFFSET_TABLE_PATCHES
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
        STAT_ZERO_SOURCE_PATCH,
        STUB_SP_STATS_DISPLAY_PATCH,
        STUB_MP_STATS_DISPLAY_FIRST_READ_PATCH,
        STUB_MP_STATS_DISPLAY_SECOND_READ_PATCH,
        STUB_REPLAY_HEADER_READ_PATCH,
        STUB_STROKE_TOURNAMENT_STATS_DISPLAY_FIRST_READ_PATCH,
        STUB_STROKE_TOURNAMENT_STATS_DISPLAY_SECOND_READ_PATCH,
        *RELOCATE_TERRAIN_BUFFER_PATCHES,
        *TERRAIN_ROW_OFFSET_TABLE_PATCHES,
        *SPRITE_SCREEN_OFFSET_TABLE_PATCHES,
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
    "STAT_ZERO_SOURCE_PATCH",
    "STUB_SP_STATS_DISPLAY_PATCH",
    "STUB_MP_STATS_DISPLAY_FIRST_READ_PATCH",
    "STUB_MP_STATS_DISPLAY_SECOND_READ_PATCH",
    "STUB_REPLAY_HEADER_READ_PATCH",
    "STUB_STROKE_TOURNAMENT_STATS_DISPLAY_FIRST_READ_PATCH",
    "STUB_STROKE_TOURNAMENT_STATS_DISPLAY_SECOND_READ_PATCH",
    "RELOCATE_TERRAIN_BUFFER_PATCHES",
    "TERRAIN_ROW_OFFSET_TABLE_PATCHES",
    "SPRITE_SCREEN_OFFSET_TABLE_PATCHES",
]
