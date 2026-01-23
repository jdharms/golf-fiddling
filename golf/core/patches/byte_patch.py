"""
BytePatch implementation for simple byte replacement patches.
"""

from typing import TYPE_CHECKING

from .base import PatchError, ROMPatch

if TYPE_CHECKING:
    from golf.core.rom_writer import RomWriter


class BytePatch(ROMPatch):
    """
    A patch that replaces a sequence of bytes at a specific PRG offset.

    This is the simplest form of ROM patch - it checks for expected bytes
    at a location and replaces them with new bytes.
    """

    def __init__(
        self,
        name: str,
        description: str,
        prg_offset: int,
        original: bytes,
        patched: bytes,
    ):
        """
        Create a byte replacement patch.

        Args:
            name: Short identifier for the patch
            description: Human-readable description of what the patch does
            prg_offset: Absolute offset into PRG ROM
            original: Expected original bytes at this location
            patched: Bytes to write when applying patch
        """
        self.name = name
        self.description = description
        self.prg_offset = prg_offset
        self.original = original
        self.patched = patched

    def can_apply(self, rom_writer: "RomWriter") -> bool:
        """
        Check if the original bytes are present at the patch location.

        Args:
            rom_writer: ROM writer with current ROM state

        Returns:
            True if original bytes match
        """
        current = rom_writer.read_prg(self.prg_offset, len(self.original))
        return current == self.original

    def is_applied(self, rom_writer: "RomWriter") -> bool:
        """
        Check if the patched bytes are present at the patch location.

        Args:
            rom_writer: ROM writer with current ROM state

        Returns:
            True if patched bytes are already present
        """
        current = rom_writer.read_prg(self.prg_offset, len(self.patched))
        return current == self.patched

    def apply(self, rom_writer: "RomWriter") -> None:
        """
        Apply the patch by writing patched bytes.

        This is idempotent - if already applied, it's a no-op.
        Raises PatchError if the ROM is in an unexpected state.

        Args:
            rom_writer: ROM writer to modify

        Raises:
            PatchError: If ROM bytes don't match original or patched
        """
        if self.is_applied(rom_writer):
            # Already applied, nothing to do
            return

        if not self.can_apply(rom_writer):
            current = rom_writer.read_prg(self.prg_offset, len(self.original))
            raise PatchError(
                f"Cannot apply patch '{self.name}': unexpected bytes at PRG offset "
                f"0x{self.prg_offset:X}. Expected {self.original.hex().upper()}, "
                f"found {current.hex().upper()}"
            )

        rom_writer.write_prg(self.prg_offset, self.patched)

    def __repr__(self) -> str:
        return (
            f"BytePatch(name={self.name!r}, prg_offset=0x{self.prg_offset:X}, "
            f"original={self.original.hex().upper()}, patched={self.patched.hex().upper()})"
        )
