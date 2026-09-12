"""
ROM Patching System.

This package provides a declarative system for applying patches to NES ROMs.
Patches can modify game behavior by replacing specific byte sequences.

Usage:
    from golf.core.patches import BytePatch, PatchError, AVAILABLE_PATCHES

    # Apply specific patches
    for patch in patches_to_apply:
        if patch.can_apply(rom_writer):
            patch.apply(rom_writer)
        elif patch.is_applied(rom_writer):
            print(f"Already applied: {patch.name}")
        else:
            raise PatchError(f"Cannot apply: {patch.name}")
"""

from .attr_streaming import (
    ATTR_STREAMING_BANK_SWITCH_PATCH,
    ATTR_STREAMING_FREE_SPACE_PATCH,
    ATTR_STREAMING_LE451_ENTRY_PATCH,
    ATTR_STREAMING_LE451_LDA_PATCHES,
    ATTR_STREAMING_LEED5_PATCH,
    ATTR_STREAMING_LOADTERRAIN_COPY_LOOP_NOP_PATCH,
    ATTR_STREAMING_LOADTERRAIN_PTR_HIGH_PATCH,
    ATTR_STREAMING_LOADTERRAIN_PTR_LOW_PATCH,
    ATTR_STREAMING_PATCHES,
)
from .base import PatchError, ROMPatch
from .byte_patch import BytePatch
from .composite import CompositePatch
from .menu_trim import (
    RENDERABLE_CHARS,
    menu_trim_patch,
    menu_trim_patches,
    random_title,
)
from .mercy_tap_in import mercy_tap_in_patches
from .practice_swing import (
    DEFAULT_HOLD_FRAMES,
    PRACTICE_SWING_OFFSET,
    practice_swing_patch,
    practice_swing_patches,
)
from .signpost_banner import remove_course_banner_patches
from .seeded_wind import (
    HoleWindForecast,
    derive_hole_seeds,
    predict_hole,
    seeded_wind_patch,
    seeded_wind_patches,
)
from .music_import import (
    COURSE_TRACKS,
    MusicImportPatch,
    music_import_patch,
)
from .multi_bank import (
    COURSE2_MIRROR_PATCH,
    COURSE2_MIRROR_PATCH_SCORECARD,
    COURSE3_MIRROR_PATCH,
    COURSE3_MIRROR_PATCH_SCORECARD,
    MULTI_BANK_CODE_PATCH,
    MULTI_BANK_CODE_PATCH_WITH_ATTR_STREAMING,
    MULTI_BANK_PATCHES,
)
from .wram_expansion import WRAM_EXPANSION_PATCH

# Registry of all available patches by name
AVAILABLE_PATCHES: dict[str, ROMPatch] = {
    MULTI_BANK_CODE_PATCH.name: MULTI_BANK_CODE_PATCH,
    MULTI_BANK_CODE_PATCH_WITH_ATTR_STREAMING.name: MULTI_BANK_CODE_PATCH_WITH_ATTR_STREAMING,
    COURSE2_MIRROR_PATCH.name: COURSE2_MIRROR_PATCH,
    COURSE3_MIRROR_PATCH.name: COURSE3_MIRROR_PATCH,
    COURSE2_MIRROR_PATCH_SCORECARD.name: COURSE2_MIRROR_PATCH_SCORECARD,
    COURSE3_MIRROR_PATCH_SCORECARD.name: COURSE3_MIRROR_PATCH_SCORECARD,
    ATTR_STREAMING_BANK_SWITCH_PATCH.name: ATTR_STREAMING_BANK_SWITCH_PATCH,
    **{p.name: p for p in ATTR_STREAMING_PATCHES},
    WRAM_EXPANSION_PATCH.name: WRAM_EXPANSION_PATCH,
}

__all__ = [
    "ROMPatch",
    "BytePatch",
    "CompositePatch",
    "PatchError",
    "mercy_tap_in_patches",
    "remove_course_banner_patches",
    "practice_swing_patch",
    "practice_swing_patches",
    "PRACTICE_SWING_OFFSET",
    "DEFAULT_HOLD_FRAMES",
    "menu_trim_patch",
    "menu_trim_patches",
    "random_title",
    "RENDERABLE_CHARS",
    "seeded_wind_patch",
    "seeded_wind_patches",
    "derive_hole_seeds",
    "predict_hole",
    "HoleWindForecast",
    "MULTI_BANK_CODE_PATCH",
    "MULTI_BANK_CODE_PATCH_WITH_ATTR_STREAMING",
    "COURSE2_MIRROR_PATCH",
    "COURSE3_MIRROR_PATCH",
    "COURSE2_MIRROR_PATCH_SCORECARD",
    "COURSE3_MIRROR_PATCH_SCORECARD",
    "MULTI_BANK_PATCHES",
    "ATTR_STREAMING_BANK_SWITCH_PATCH",
    "ATTR_STREAMING_FREE_SPACE_PATCH",
    "ATTR_STREAMING_LE451_ENTRY_PATCH",
    "ATTR_STREAMING_LE451_LDA_PATCHES",
    "ATTR_STREAMING_LEED5_PATCH",
    "ATTR_STREAMING_LOADTERRAIN_PTR_LOW_PATCH",
    "ATTR_STREAMING_LOADTERRAIN_PTR_HIGH_PATCH",
    "ATTR_STREAMING_LOADTERRAIN_COPY_LOOP_NOP_PATCH",
    "ATTR_STREAMING_PATCHES",
    "WRAM_EXPANSION_PATCH",
    "MusicImportPatch",
    "music_import_patch",
    "COURSE_TRACKS",
    "AVAILABLE_PATCHES",
]
