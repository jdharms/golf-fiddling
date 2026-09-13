"""
ROM Patching System.

This package provides a declarative system for applying patches to NES ROMs.
Patches can modify game behavior by replacing specific byte sequences.

Patch types are registered in `registry.PATCH_SPECS`; a `PatchStack` builds an
ordered list of patches onto a base ROM, and a `Recipe` is a stack written as
JSON. See docs/patch_stack.md.

Usage:
    from golf.core.patches import Recipe

    recipe = Recipe.load("recipe.json")
    rom = recipe.stack(base).build(base).rom
"""

from .attr_streaming import (
    ATTR_STREAMING_PATCH,
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
from .course import CoursePatch, CourseWriteStats
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
from .scorecard_course_name import (
    scorecard_course_name_patch,
    scorecard_course_name_patches,
)
from .scorecard_qr import (
    QrCredentials,
    ScorecardQrPatch,
    load_credentials,
    scorecard_qr_patch,
)
from .signpost_banner import remove_course_banner_patches
from .signpost_random_banner import (
    build_code,
    build_layout,
    data_region,
    random_banner_patches,
)
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
    COURSE_MIRRORS_PATCH,
    MULTI_BANK_CODE_PATCH,
    MULTI_BANK_PATCHES,
)
from .stack import PatchStack, StackBuild, StackError
from .wram_expansion import WRAM_EXPANSION_PATCH
from .registry import PATCH_SPECS, BuildContext, PatchSpec
from .recipe import (
    BuiltStep,
    Recipe,
    RecipeError,
    RecipeStep,
    describe_params,
    parse_step_arg,
)


__all__ = [
    "ROMPatch",
    "QrCredentials",
    "load_credentials",
    "PATCH_SPECS",
    "BuildContext",
    "PatchSpec",
    "BuiltStep",
    "Recipe",
    "RecipeError",
    "RecipeStep",
    "describe_params",
    "parse_step_arg",
    "ScorecardQrPatch",
    "scorecard_qr_patch",
    "scorecard_course_name_patch",
    "scorecard_course_name_patches",
    "BytePatch",
    "CompositePatch",
    "PatchStack",
    "StackBuild",
    "StackError",
    "CoursePatch",
    "CourseWriteStats",
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
    "COURSE2_MIRROR_PATCH",
    "COURSE3_MIRROR_PATCH",
    "COURSE2_MIRROR_PATCH_SCORECARD",
    "COURSE3_MIRROR_PATCH_SCORECARD",
    "COURSE_MIRRORS_PATCH",
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
    "ATTR_STREAMING_PATCH",
    "WRAM_EXPANSION_PATCH",
    "MusicImportPatch",
    "music_import_patch",
    "COURSE_TRACKS",
]
