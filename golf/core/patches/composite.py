"""
CompositePatch implementation for grouping multiple patches into one unit.
"""

from typing import TYPE_CHECKING

from .base import PatchError, ROMPatch

if TYPE_CHECKING:
    from golf.core.rom_writer import RomWriter


class CompositePatch(ROMPatch):
    """
    A patch that groups multiple sub-patches and treats them as one named
    ROMPatch.

    The group is applicable only when every sub-patch is either already
    applied or independently applicable, and applied only when every
    sub-patch is applied. This lets a partially-applied group be completed
    by a later `apply()` call, while still rejecting the group outright if
    any sub-patch's ROM region is in an unexpected state.
    """

    def __init__(self, name: str, description: str, patches: list[ROMPatch]):
        self.name = name
        self.description = description
        self.patches = patches

    def can_apply(self, rom_writer: "RomWriter") -> bool:
        return all(
            p.can_apply(rom_writer) or p.is_applied(rom_writer)
            for p in self.patches
        )

    def is_applied(self, rom_writer: "RomWriter") -> bool:
        return all(p.is_applied(rom_writer) for p in self.patches)

    def apply(self, rom_writer: "RomWriter") -> None:
        if not self.can_apply(rom_writer):
            blocked = [
                p.name
                for p in self.patches
                if not (p.can_apply(rom_writer) or p.is_applied(rom_writer))
            ]
            raise PatchError(
                f"Cannot apply composite patch '{self.name}': sub-patch(es) "
                f"in unexpected state: {', '.join(blocked)}"
            )

        for p in self.patches:
            p.apply(rom_writer)

    def __repr__(self) -> str:
        return (
            f"CompositePatch(name={self.name!r}, "
            f"patches={[p.name for p in self.patches]!r})"
        )
