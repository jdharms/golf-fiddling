"""
ROM Patch base classes and exceptions.

Provides the foundation for declarative ROM patches that can be applied
to modify game behavior.
"""

from abc import ABC, abstractmethod
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
