"""
NES Open Tournament Golf - ROM Reader

ROM file reading and address translation for NES Open Tournament Golf.
Handles iNES ROM format and CPU address mapping for both fixed and switched banks.
"""

from .rom_utils import (
    FIXED_BANK_PRG_START,
    INES_HEADER_SIZE,
    PRG_BANK_SIZE,
    cpu_to_prg_fixed,
    cpu_to_prg_switched,
)


class RomReader:
    """
    Reads and parses NES Open Tournament Golf ROM files.

    Handles iNES ROM format and provides methods for reading from both
    fixed bank ($C000-$FFFF) and switchable banks ($8000-$BFFF).
    """

    def __init__(self, rom_path: str):
        """
        Load a NES ROM file.

        Args:
            rom_path: Path to iNES ROM file

        Raises:
            ValueError: If file is not a valid iNES ROM
        """
        with open(rom_path, "rb") as f:
            self.data = f.read()

        # Verify iNES header
        if self.data[:4] != b"NES\x1a":
            raise ValueError("Not a valid iNES ROM file")

        self.prg_banks = self.data[4]
        self.chr_banks = self.data[5]
        self.prg_size = self.prg_banks * PRG_BANK_SIZE
        self.prg_start = INES_HEADER_SIZE

        print(f"ROM loaded: {self.prg_banks} PRG banks ({self.prg_size // 1024}KB)")

    def read_prg(self, prg_offset: int, length: int = 1) -> bytes:
        """
        Read bytes from PRG ROM at absolute PRG offset.

        Args:
            prg_offset: Offset into PRG ROM (relative to start of PRG data)
            length: Number of bytes to read

        Returns:
            Requested bytes
        """
        file_offset = self.prg_start + prg_offset
        return self.data[file_offset : file_offset + length]

    def read_prg_byte(self, prg_offset: int) -> int:
        """Read a single byte from PRG ROM."""
        return self.read_prg(prg_offset, 1)[0]

    def read_prg_word(self, prg_offset: int) -> int:
        """
        Read 16-bit little-endian word from PRG ROM.

        Args:
            prg_offset: Offset into PRG ROM

        Returns:
            16-bit value
        """
        data = self.read_prg(prg_offset, 2)
        return data[0] | (data[1] << 8)

    def read_fixed(self, cpu_addr: int, length: int = 1) -> bytes:
        """
        Read from fixed bank using CPU address.

        Args:
            cpu_addr: CPU address in range $C000-$FFFF
            length: Number of bytes to read

        Returns:
            Requested bytes
        """
        return self.read_prg(cpu_to_prg_fixed(cpu_addr), length)

    def read_fixed_byte(self, cpu_addr: int) -> int:
        """Read a single byte from fixed bank."""
        return self.read_fixed(cpu_addr, 1)[0]

    def read_fixed_word(self, cpu_addr: int) -> int:
        """
        Read 16-bit little-endian word from fixed bank.

        Args:
            cpu_addr: CPU address in range $C000-$FFFF

        Returns:
            16-bit value
        """
        data = self.read_fixed(cpu_addr, 2)
        return data[0] | (data[1] << 8)

    def read_switched(self, cpu_addr: int, bank: int, length: int = 1) -> bytes:
        """
        Read from switched bank using CPU address.

        Args:
            cpu_addr: CPU address in range $8000-$BFFF
            bank: Bank number to use
            length: Number of bytes to read

        Returns:
            Requested bytes
        """
        return self.read_prg(cpu_to_prg_switched(cpu_addr, bank), length)

    def annotate(self, description: str) -> "RomReader":
        """
        Annotate the next read operation.

        This is a no-op in the base class. The instrumented subclass
        overrides this to record annotations for tracing.

        Args:
            description: Human-readable description of the operation

        Returns:
            self (for method chaining)
        """
        return self
