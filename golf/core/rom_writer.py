"""
NES Open Tournament Golf - ROM Writer

Low-level ROM byte writing with address translation.
This class mirrors RomReader's interface for writes.
"""

from pathlib import Path

from .rom_utils import (
    FIXED_BANK_PRG_START,
    INES_HEADER_SIZE,
    PRG_BANK_SIZE,
    cpu_to_prg_fixed,
    cpu_to_prg_switched,
    prg_to_cpu_switched,
)


class BankOverflowError(Exception):
    """Raised when compressed data exceeds bank capacity."""

    pass


class RomWriter:
    """
    Low-level ROM byte writing with address translation.

    Provides symmetric write operations to match RomReader's read operations.
    """

    def __init__(self, rom_path: str, output_path: str):
        """
        Load ROM for writing.

        Args:
            rom_path: Source ROM file (read-only)
            output_path: Output ROM file path (will be created/overwritten)

        Raises:
            ValueError: If ROM is not valid iNES format
        """
        # Read entire ROM into bytearray for modification
        with open(rom_path, "rb") as f:
            self.rom_data = bytearray(f.read())

        # Validate iNES header
        if self.rom_data[:4] != b"NES\x1a":
            raise ValueError("Not a valid iNES ROM file")

        self.output_path = output_path
        self.prg_banks = self.rom_data[4]
        self.prg_start = INES_HEADER_SIZE

    # =========================================================================
    # Write methods (low-level)
    # =========================================================================

    def write_prg(self, prg_offset: int, data: bytes):
        """
        Write bytes to PRG ROM at absolute offset.

        Args:
            prg_offset: Offset into PRG ROM
            data: Bytes to write
        """
        file_offset = self.prg_start + prg_offset
        self.rom_data[file_offset : file_offset + len(data)] = data

    def write_prg_byte(self, prg_offset: int, value: int):
        """Write a single byte to PRG ROM."""
        self.rom_data[self.prg_start + prg_offset] = value

    def write_prg_word(self, prg_offset: int, value: int):
        """Write 16-bit little-endian word to PRG ROM."""
        self.write_prg_byte(prg_offset, value & 0xFF)
        self.write_prg_byte(prg_offset + 1, (value >> 8) & 0xFF)

    def write_fixed(self, cpu_addr: int, data: bytes):
        """
        Write bytes to fixed bank using CPU address.

        Args:
            cpu_addr: CPU address in range $C000-$FFFF
            data: Bytes to write
        """
        prg_offset = self.cpu_to_prg_fixed(cpu_addr)
        self.write_prg(prg_offset, data)

    def write_fixed_byte(self, cpu_addr: int, value: int):
        """Write a single byte to fixed bank."""
        prg_offset = self.cpu_to_prg_fixed(cpu_addr)
        self.rom_data[self.prg_start + prg_offset] = value

    def write_fixed_word(self, cpu_addr: int, value: int):
        """Write 16-bit little-endian word to fixed bank."""
        self.write_fixed_byte(cpu_addr, value & 0xFF)
        self.write_fixed_byte(cpu_addr + 1, (value >> 8) & 0xFF)

    def write_switched(self, cpu_addr: int, bank: int, data: bytes):
        """
        Write bytes to switched bank using CPU address.

        Args:
            cpu_addr: CPU address in range $8000-$BFFF
            bank: Bank number
            data: Bytes to write
        """
        prg_offset = self.cpu_to_prg_switched(cpu_addr, bank)
        self.write_prg(prg_offset, data)

    # =========================================================================
    # Read methods (for reading current ROM state)
    # =========================================================================

    def read_prg(self, prg_offset: int, length: int) -> bytes:
        """
        Read bytes from PRG ROM at absolute offset.

        Args:
            prg_offset: Offset into PRG ROM
            length: Number of bytes to read

        Returns:
            Requested bytes
        """
        file_offset = self.prg_start + prg_offset
        return bytes(self.rom_data[file_offset : file_offset + length])

    def read_prg_byte(self, prg_offset: int) -> int:
        """Read a single byte from PRG ROM."""
        return self.rom_data[self.prg_start + prg_offset]

    def read_prg_word(self, prg_offset: int) -> int:
        """Read 16-bit little-endian word from PRG ROM."""
        low = self.read_prg_byte(prg_offset)
        high = self.read_prg_byte(prg_offset + 1)
        return low | (high << 8)

    def read_fixed_byte(self, cpu_addr: int) -> int:
        """Read a single byte from fixed bank."""
        prg_offset = self.cpu_to_prg_fixed(cpu_addr)
        return self.rom_data[self.prg_start + prg_offset]

    def read_fixed_word(self, cpu_addr: int) -> int:
        """Read 16-bit little-endian word from fixed bank."""
        low = self.read_fixed_byte(cpu_addr)
        high = self.read_fixed_byte(cpu_addr + 1)
        return low | (high << 8)

    # =========================================================================
    # Address translation
    # =========================================================================

    def cpu_to_prg_fixed(self, cpu_addr: int) -> int:
        """
        Convert fixed bank CPU address ($C000-$FFFF) to PRG offset.

        Args:
            cpu_addr: CPU address in fixed bank

        Returns:
            Absolute PRG offset
        """
        return cpu_to_prg_fixed(cpu_addr)

    def cpu_to_prg_switched(self, cpu_addr: int, bank: int) -> int:
        """
        Convert CPU address in switched bank to PRG offset.

        Args:
            cpu_addr: CPU address ($8000-$BFFF)
            bank: Bank number

        Returns:
            Absolute PRG offset
        """
        return cpu_to_prg_switched(cpu_addr, bank)

    def prg_to_cpu_switched(self, prg_offset: int) -> int:
        """
        Convert PRG offset to CPU address in switched bank ($8000-$BFFF).

        Args:
            prg_offset: Absolute PRG offset

        Returns:
            CPU address in switched bank range
        """
        return prg_to_cpu_switched(prg_offset)

    # =========================================================================
    # Annotation (no-op in base class, overridden in instrumented version)
    # =========================================================================

    def annotate(self, description: str) -> "RomWriter":
        """
        Annotate the next read/write operation.

        This is a no-op in the base class. The instrumented subclass
        overrides this to record annotations for tracing.

        Args:
            description: Human-readable description of the operation

        Returns:
            self (for method chaining)
        """
        return self

    # =========================================================================
    # File operations
    # =========================================================================

    def save(self):
        """Write modified ROM to output file."""
        with open(self.output_path, "wb") as f:
            f.write(self.rom_data)
        print(f"Wrote modified ROM to: {self.output_path}")

    @classmethod
    def from_file(cls, rom_path: str, output_path: str | None = None) -> "RomWriter":
        """
        Create RomWriter from file path.

        Args:
            rom_path: Source ROM file
            output_path: Output ROM file (default: <rom>.modified.nes)

        Returns:
            RomWriter instance
        """
        if output_path is None:
            path = Path(rom_path)
            output_path = str(path.with_suffix("")) + ".modified.nes"

        return cls(rom_path, output_path)
