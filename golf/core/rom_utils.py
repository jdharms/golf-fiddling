"""
NES Open Tournament Golf ROM constants and address utilities.

This module provides:
- ROM layout constants (header size, bank size, fixed bank location)
- Course structure constants (course names, hole counts)
- Pointer table addresses in the fixed bank (terrain, greens, metadata)
- Decompression table addresses (horizontal transitions, vertical fill, dictionary)
- Address translation functions for converting between CPU addresses and PRG offsets

Used by RomReader, RomWriter, and other ROM manipulation code.
"""

# ROM layout constants
INES_HEADER_SIZE = 0x10
PRG_BANK_SIZE = 0x4000  # 16KB banks
FIXED_BANK_PRG_START = 0x3C000  # Bank 15, maps to $C000-$FFFF

# ============================================================================
# Course Structure Constants
# ============================================================================
COURSES = [
    {"name": "japan", "display_name": "Japan"},
    {"name": "us", "display_name": "US"},
    {"name": "uk", "display_name": "UK"},
]
HOLES_PER_COURSE = 18
TOTAL_HOLES = 54

# ============================================================================
# Pointer Table Addresses (Fixed Bank $C000-$FFFF)
# ============================================================================
TABLE_COURSE_HOLE_OFFSET = 0xDBBB  # 3 bytes: 0, 18, 36
TABLE_COURSE_BANK_TERRAIN = 0xDBBE  # 3 bytes: bank numbers
TABLE_TERRAIN_START_PTR = 0xDBC1  # 54 x 2-byte pointers
TABLE_TERRAIN_END_PTR = 0xDC2D  # 54 x 2-byte pointers (also attr start)
TABLE_GREENS_PTR = 0xDC99  # 54 x 2-byte pointers
TABLE_PAR = 0xDD05  # 54 bytes
TABLE_HANDICAP = 0xDDDD  # 54 bytes
TABLE_DISTANCE_100 = 0xDD3B  # 54 bytes (BCD)
TABLE_DISTANCE_10 = 0xDD71  # 54 bytes (BCD)
TABLE_DISTANCE_1 = 0xDDA7  # 54 bytes (BCD)
TABLE_SCROLL_LIMIT = 0xDE13  # 54 bytes
TABLE_GREEN_X = 0xDE49  # 54 bytes
TABLE_GREEN_Y = 0xDE7F  # 54 bytes
TABLE_TEE_X = 0xDEB5  # 54 bytes
TABLE_TEE_Y = 0xDEEB  # 54 x 2-byte values
TABLE_FLAG_Y_OFFSET = 0xE02F  # 54 x 4 bytes (4 positions per hole)
TABLE_FLAG_X_OFFSET = 0xDF57  # 54 x 4 bytes

# ============================================================================
# Decompression Table Addresses (Fixed Bank)
# ============================================================================
TABLE_HORIZ_TRANSITION = 0xE1AC  # 224 bytes
TABLE_VERT_CONTINUATION = 0xE28C  # 224 bytes
TABLE_DICTIONARY = 0xE36C  # 64 bytes (32 x 2-byte pairs)


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
