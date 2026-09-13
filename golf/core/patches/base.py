"""
ROM Patch base classes and exceptions.

Provides the foundation for declarative ROM patches that can be applied
to modify game behavior.
"""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from golf.core.rom_writer import RomWriter


class PatchError(Exception):
    """Raised when a patch cannot be applied."""

    pass


class ROMPatch(ABC):
    """
    Base class for declarative ROM patches.

    Patches can check their current state (applied or not) and apply themselves
    to a ROM through a RomWriter instance.
    """

    name: str
    description: str

    #: Patches that must already be applied before this one. A requirement is
    #: something this patch depends on but does not write, which is why it is
    #: not part of `can_apply`: that checks only the bytes this patch replaces,
    #: so a whole stack of patches can be checked before any is applied.
    requires: Sequence["ROMPatch"] = ()

    def missing_requirements(self, rom_writer: "RomWriter") -> list["ROMPatch"]:
        """The required patches that are not applied to this ROM."""
        return [patch for patch in self.requires if not patch.is_applied(rom_writer)]

    def check_requirements(self, rom_writer: "RomWriter") -> None:
        """Raise PatchError naming every required patch that is not applied."""
        missing = self.missing_requirements(rom_writer)
        if missing:
            raise PatchError(
                f"Cannot apply patch '{self.name}': requires "
                f"{', '.join(patch.name for patch in missing)} to be applied first"
            )

    @abstractmethod
    def can_apply(self, rom_writer: "RomWriter") -> bool:
        """
        Check if this patch can be applied.

        Returns True if the ROM contains the expected original bytes
        that this patch is designed to modify.

        Args:
            rom_writer: ROM writer with current ROM state

        Returns:
            True if original bytes are present and patch can be applied
        """
        pass

    @abstractmethod
    def is_applied(self, rom_writer: "RomWriter") -> bool:
        """
        Check if this patch has already been applied.

        Returns True if the ROM contains the patched bytes.

        Args:
            rom_writer: ROM writer with current ROM state

        Returns:
            True if patch is already applied
        """
        pass

    @abstractmethod
    def apply(self, rom_writer: "RomWriter") -> None:
        """
        Apply this patch to the ROM.

        This method should be idempotent - if the patch is already applied,
        it should be a no-op. If the ROM is in an unexpected state (neither
        original nor patched bytes), it should raise PatchError.

        Args:
            rom_writer: ROM writer to modify

        Raises:
            PatchError: If ROM is in unexpected state and cannot be patched
        """
        pass
