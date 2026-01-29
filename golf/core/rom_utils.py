"""
NES ROM address translation utilities.

Pure functions for converting between CPU addresses and PRG ROM offsets.
These are used by RomReader, RomWriter, and other ROM manipulation code.
"""

# ROM layout constants
INES_HEADER_SIZE = 0x10
PRG_BANK_SIZE = 0x4000  # 16KB banks
FIXED_BANK_PRG_START = 0x3C000  # Bank 15, maps to $C000-$FFFF


def cpu_to_prg_fixed(cpu_addr: int) -> int:
    """
    Convert fixed bank CPU address ($C000-$FFFF) to PRG offset.

    Args:
        cpu_addr: CPU address in range $C000-$FFFF

    Returns:
        PRG ROM offset

    Raises:
        ValueError: If address is not in fixed bank range
    """
    if cpu_addr < 0xC000 or cpu_addr > 0xFFFF:
        raise ValueError(f"Address ${cpu_addr:04X} not in fixed bank range")
    return FIXED_BANK_PRG_START + (cpu_addr - 0xC000)


def cpu_to_prg_switched(cpu_addr: int, bank: int) -> int:
    """
    Convert switched bank CPU address ($8000-$BFFF) to PRG offset.

    Args:
        cpu_addr: CPU address in range $8000-$BFFF
        bank: Bank number to use

    Returns:
        PRG ROM offset

    Raises:
        ValueError: If address is not in switchable bank range
    """
    if cpu_addr < 0x8000 or cpu_addr > 0xBFFF:
        raise ValueError(f"Address ${cpu_addr:04X} not in switchable bank range")
    return bank * PRG_BANK_SIZE + (cpu_addr - 0x8000)


def prg_to_cpu_switched(prg_offset: int) -> int:
    """
    Convert PRG offset to CPU address in switched bank ($8000-$BFFF).

    Args:
        prg_offset: Absolute PRG offset

    Returns:
        CPU address in switched bank range
    """
    offset_in_bank = prg_offset % PRG_BANK_SIZE
    return 0x8000 + offset_in_bank


def prg_to_bank_and_cpu(prg_offset: int) -> tuple[int, int]:
    """
    Convert PRG offset to (bank, cpu_addr) tuple.

    Args:
        prg_offset: Absolute offset into PRG ROM

    Returns:
        Tuple of (bank, cpu_addr) where bank is 15 for fixed bank
    """
    if prg_offset >= FIXED_BANK_PRG_START:
        cpu_addr = 0xC000 + (prg_offset - FIXED_BANK_PRG_START)
        return (15, cpu_addr)
    else:
        bank = prg_offset // PRG_BANK_SIZE
        cpu_addr = 0x8000 + (prg_offset % PRG_BANK_SIZE)
        return (bank, cpu_addr)
