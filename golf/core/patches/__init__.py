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

from .base import PatchError, ROMPatch
from .byte_patch import BytePatch
from .multi_bank import (
    COURSE2_MIRROR_PATCH,
    COURSE3_MIRROR_PATCH,
    MULTI_BANK_CODE_PATCH,
    MULTI_BANK_PATCHES,
)

# Registry of all available patches by name
AVAILABLE_PATCHES: dict[str, ROMPatch] = {
    MULTI_BANK_CODE_PATCH.name: MULTI_BANK_CODE_PATCH,
    COURSE2_MIRROR_PATCH.name: COURSE2_MIRROR_PATCH,
    COURSE3_MIRROR_PATCH.name: COURSE3_MIRROR_PATCH,
}

__all__ = [
    "ROMPatch",
    "BytePatch",
    "PatchError",
    "MULTI_BANK_CODE_PATCH",
    "COURSE2_MIRROR_PATCH",
    "COURSE3_MIRROR_PATCH",
    "MULTI_BANK_PATCHES",
    "AVAILABLE_PATCHES",
]
