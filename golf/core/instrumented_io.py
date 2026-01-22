"""
NES Open Tournament Golf - Instrumented ROM I/O

Instrumented versions of RomReader and RomWriter that log all read/write
operations with annotations, allowing generation of "ROM maps" showing
what data is being read from and written to specific addresses.
"""

import json
from pathlib import Path

from .rom_reader import RomReader, PRG_BANK_SIZE, FIXED_BANK_PRG_START
from .rom_writer import RomWriter


def _prg_to_bank_and_cpu(prg_offset: int) -> tuple[int, int]:
    """
    Convert PRG offset to bank number and CPU address.

    Args:
        prg_offset: Absolute offset into PRG ROM

    Returns:
        Tuple of (bank, cpu_addr)
    """
    if prg_offset >= FIXED_BANK_PRG_START:
        # Fixed bank (bank 15, $C000-$FFFF)
        cpu_addr = 0xC000 + (prg_offset - FIXED_BANK_PRG_START)
        return (15, cpu_addr)
    else:
        # Switched bank ($8000-$BFFF)
        bank = prg_offset // PRG_BANK_SIZE
        cpu_addr = 0x8000 + (prg_offset % PRG_BANK_SIZE)
        return (bank, cpu_addr)


class InstrumentedRomReader(RomReader):
    """
    RomReader subclass that logs all read operations with annotations.

    Usage:
        rom = InstrumentedRomReader("game.nes")
        data = rom.annotate("hole 1 terrain ptr").read_fixed_word(0xDBC1)
        rom.write_trace("read_trace.json")
    """

    def __init__(self, rom_path: str, require_annotations: bool = False):
        """
        Load a NES ROM file with instrumentation.

        Args:
            rom_path: Path to iNES ROM file
            require_annotations: If True, raise error on unannotated reads
        """
        super().__init__(rom_path)
        self._pending_annotation: str | None = None
        self._require_annotations = require_annotations
        self._trace: list[dict] = []

    def annotate(self, description: str) -> "InstrumentedRomReader":
        """
        Annotate the next read operation.

        Args:
            description: Human-readable description of the operation

        Returns:
            self (for method chaining)
        """
        self._pending_annotation = description
        return self

    def _log_read(
        self,
        prg_offset: int,
        length: int,
        data: bytes,
        cpu_addr: int | None = None,
        bank: int | None = None,
    ):
        """Log a read operation to the trace."""
        annotation = self._pending_annotation or "[no annotation]"
        if self._pending_annotation is None and self._require_annotations:
            raise RuntimeError(
                f"Read at PRG ${prg_offset:05X} without annotation"
            )

        # Calculate bank and cpu_addr from PRG offset if not provided
        if bank is None or cpu_addr is None:
            calc_bank, calc_cpu = _prg_to_bank_and_cpu(prg_offset)
            if bank is None:
                bank = calc_bank
            if cpu_addr is None:
                cpu_addr = calc_cpu

        self._trace.append({
            "type": "read",
            "annotation": annotation,
            "prg_offset": prg_offset,
            "cpu_addr": f"${cpu_addr:04X}",
            "bank": bank,
            "length": length,
            "value_hex": data.hex(" ").upper() if len(data) <= 32 else f"{data[:32].hex(' ').upper()}... ({length} bytes)",
        })
        self._pending_annotation = None

    # Override all read methods to log

    def read_prg(self, prg_offset: int, length: int = 1) -> bytes:
        """Read bytes from PRG ROM with logging."""
        data = super().read_prg(prg_offset, length)
        self._log_read(prg_offset, length, data)
        return data

    def read_prg_byte(self, prg_offset: int) -> int:
        """Read a single byte from PRG ROM with logging."""
        data = super().read_prg(prg_offset, 1)
        self._log_read(prg_offset, 1, data)
        return data[0]

    def read_prg_word(self, prg_offset: int) -> int:
        """Read 16-bit word from PRG ROM with logging."""
        data = super().read_prg(prg_offset, 2)
        self._log_read(prg_offset, 2, data)
        return data[0] | (data[1] << 8)

    def read_fixed(self, cpu_addr: int, length: int = 1) -> bytes:
        """Read from fixed bank with logging."""
        prg_offset = self.cpu_to_prg_fixed(cpu_addr)
        data = bytes(self.data[self.prg_start + prg_offset : self.prg_start + prg_offset + length])
        self._log_read(prg_offset, length, data, cpu_addr=cpu_addr)
        return data

    def read_fixed_byte(self, cpu_addr: int) -> int:
        """Read a single byte from fixed bank with logging."""
        prg_offset = self.cpu_to_prg_fixed(cpu_addr)
        data = bytes([self.data[self.prg_start + prg_offset]])
        self._log_read(prg_offset, 1, data, cpu_addr=cpu_addr)
        return data[0]

    def read_fixed_word(self, cpu_addr: int) -> int:
        """Read 16-bit word from fixed bank with logging."""
        prg_offset = self.cpu_to_prg_fixed(cpu_addr)
        data = bytes(self.data[self.prg_start + prg_offset : self.prg_start + prg_offset + 2])
        self._log_read(prg_offset, 2, data, cpu_addr=cpu_addr)
        return data[0] | (data[1] << 8)

    def read_switched(self, cpu_addr: int, bank: int, length: int = 1) -> bytes:
        """Read from switched bank with logging."""
        prg_offset = self.cpu_to_prg_switched(cpu_addr, bank)
        data = bytes(self.data[self.prg_start + prg_offset : self.prg_start + prg_offset + length])
        self._log_read(prg_offset, length, data, cpu_addr=cpu_addr, bank=bank)
        return data

    def get_trace(self) -> list[dict]:
        """Get the list of logged operations."""
        return self._trace

    def write_trace(self, path: str):
        """
        Write trace to JSON file.

        Args:
            path: Output file path
        """
        with open(path, "w") as f:
            json.dump({"entries": self._trace}, f, indent=2)
        print(f"Wrote read trace ({len(self._trace)} entries) to: {path}")


class InstrumentedRomWriter(RomWriter):
    """
    RomWriter subclass that logs all read/write operations with annotations.

    Usage:
        writer = InstrumentedRomWriter("game.nes", "output.nes")
        writer.annotate("hole 1 terrain data").write_prg(0x0000, data)
        writer.write_trace("write_trace.json")
    """

    def __init__(
        self, rom_path: str, output_path: str, require_annotations: bool = False
    ):
        """
        Load ROM for writing with instrumentation.

        Args:
            rom_path: Source ROM file
            output_path: Output ROM file path
            require_annotations: If True, raise error on unannotated operations
        """
        super().__init__(rom_path, output_path)
        self._pending_annotation: str | None = None
        self._require_annotations = require_annotations
        self._trace: list[dict] = []

    def annotate(self, description: str) -> "InstrumentedRomWriter":
        """
        Annotate the next read/write operation.

        Args:
            description: Human-readable description of the operation

        Returns:
            self (for method chaining)
        """
        self._pending_annotation = description
        return self

    def _log_operation(
        self,
        op_type: str,
        prg_offset: int,
        length: int,
        data: bytes,
        cpu_addr: int | None = None,
        bank: int | None = None,
    ):
        """Log an operation to the trace."""
        annotation = self._pending_annotation or "[no annotation]"
        if self._pending_annotation is None and self._require_annotations:
            raise RuntimeError(
                f"{op_type.capitalize()} at PRG ${prg_offset:05X} without annotation"
            )

        # Calculate bank and cpu_addr from PRG offset if not provided
        if bank is None or cpu_addr is None:
            calc_bank, calc_cpu = _prg_to_bank_and_cpu(prg_offset)
            if bank is None:
                bank = calc_bank
            if cpu_addr is None:
                cpu_addr = calc_cpu

        self._trace.append({
            "type": op_type,
            "annotation": annotation,
            "prg_offset": prg_offset,
            "cpu_addr": f"${cpu_addr:04X}",
            "bank": bank,
            "length": length,
            "value_hex": data.hex(" ").upper() if len(data) <= 32 else f"{data[:32].hex(' ').upper()}... ({length} bytes)",
        })
        self._pending_annotation = None

    # Override write methods to log

    def write_prg(self, prg_offset: int, data: bytes):
        """Write bytes to PRG ROM with logging."""
        self._log_operation("write", prg_offset, len(data), data)
        super().write_prg(prg_offset, data)

    def write_prg_byte(self, prg_offset: int, value: int):
        """Write a single byte to PRG ROM with logging."""
        data = bytes([value])
        self._log_operation("write", prg_offset, 1, data)
        super().write_prg_byte(prg_offset, value)

    def write_prg_word(self, prg_offset: int, value: int):
        """Write 16-bit word to PRG ROM with logging."""
        data = bytes([value & 0xFF, (value >> 8) & 0xFF])
        self._log_operation("write", prg_offset, 2, data)
        super().write_prg_word(prg_offset, value)

    def write_fixed(self, cpu_addr: int, data: bytes):
        """Write bytes to fixed bank with logging."""
        prg_offset = self.cpu_to_prg_fixed(cpu_addr)
        self._log_operation("write", prg_offset, len(data), data, cpu_addr=cpu_addr)
        super().write_fixed(cpu_addr, data)

    def write_fixed_byte(self, cpu_addr: int, value: int):
        """Write a single byte to fixed bank with logging."""
        prg_offset = self.cpu_to_prg_fixed(cpu_addr)
        data = bytes([value])
        self._log_operation("write", prg_offset, 1, data, cpu_addr=cpu_addr)
        super().write_fixed_byte(cpu_addr, value)

    def write_fixed_word(self, cpu_addr: int, value: int):
        """Write 16-bit word to fixed bank with logging."""
        prg_offset = self.cpu_to_prg_fixed(cpu_addr)
        data = bytes([value & 0xFF, (value >> 8) & 0xFF])
        self._log_operation("write", prg_offset, 2, data, cpu_addr=cpu_addr)
        super().write_fixed_word(cpu_addr, value)

    def write_switched(self, cpu_addr: int, bank: int, data: bytes):
        """Write bytes to switched bank with logging."""
        prg_offset = self.cpu_to_prg_switched(cpu_addr, bank)
        self._log_operation("write", prg_offset, len(data), data, cpu_addr=cpu_addr, bank=bank)
        super().write_switched(cpu_addr, bank, data)

    # Override read methods to log

    def read_prg(self, prg_offset: int, length: int) -> bytes:
        """Read bytes from PRG ROM with logging."""
        data = super().read_prg(prg_offset, length)
        self._log_operation("read", prg_offset, length, data)
        return data

    def read_prg_byte(self, prg_offset: int) -> int:
        """Read a single byte from PRG ROM with logging."""
        value = super().read_prg_byte(prg_offset)
        data = bytes([value])
        self._log_operation("read", prg_offset, 1, data)
        return value

    def read_prg_word(self, prg_offset: int) -> int:
        """Read 16-bit word from PRG ROM with logging."""
        value = super().read_prg_word(prg_offset)
        data = bytes([value & 0xFF, (value >> 8) & 0xFF])
        self._log_operation("read", prg_offset, 2, data)
        return value

    def read_fixed_byte(self, cpu_addr: int) -> int:
        """Read a single byte from fixed bank with logging."""
        prg_offset = self.cpu_to_prg_fixed(cpu_addr)
        value = super().read_fixed_byte(cpu_addr)
        data = bytes([value])
        self._log_operation("read", prg_offset, 1, data, cpu_addr=cpu_addr)
        return value

    def read_fixed_word(self, cpu_addr: int) -> int:
        """Read 16-bit word from fixed bank with logging."""
        prg_offset = self.cpu_to_prg_fixed(cpu_addr)
        value = super().read_fixed_word(cpu_addr)
        data = bytes([value & 0xFF, (value >> 8) & 0xFF])
        self._log_operation("read", prg_offset, 2, data, cpu_addr=cpu_addr)
        return value

    def get_trace(self) -> list[dict]:
        """Get the list of logged operations."""
        return self._trace

    def write_trace(self, path: str):
        """
        Write trace to JSON file.

        Args:
            path: Output file path
        """
        with open(path, "w") as f:
            json.dump({"entries": self._trace}, f, indent=2)
        print(f"Wrote write trace ({len(self._trace)} entries) to: {path}")
