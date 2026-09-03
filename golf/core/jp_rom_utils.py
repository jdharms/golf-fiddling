"""
NES Open Tournament Golf (Japan release / Mario Open Golf) ROM constants.

JP-specific table addresses and metadata read helpers. Address translation
(cpu_to_prg_fixed, cpu_to_prg_switched) and ROM layout constants are shared
with the US version via rom_utils - the iNES layout is identical between
releases, only table locations and the greens bank scheme differ.
"""

from .rom_reader import RomReader
from .rom_utils import cpu_to_prg_switched  # noqa: F401 (re-exported for callers)

# ============================================================================
# Course Structure Constants
# ============================================================================
COURSES = [
    {"name": "jp_japan", "display_name": "Japan"},
    {"name": "jp_australia", "display_name": "Australia"},
    {"name": "jp_france", "display_name": "France"},
    {"name": "jp_hawaii", "display_name": "Hawaii"},
    {"name": "jp_uk", "display_name": "UK"},
    # Course index 5 (remix) is skipped - see Open Question 3 in docs/jp_extraction.md
]
HOLES_PER_COURSE = 18
TOTAL_HOLES = 90

JP_METADATA_BANK = 0x0B
JP_ATTR_BYTES = 90

# ============================================================================
# Fixed Bank Tables ($C000-$FFFF)
# ============================================================================
TABLE_COURSE_HOLE_OFFSET = 0xDC7D  # 6 bytes: [0, 18, 36, 54, 72, 0]
TABLE_COURSE_BANK_TERRAIN = 0xDC82  # 6 bytes: bank numbers
TABLE_PAR = 0xDC87  # 90 bytes
TABLE_DISTANCE_100 = 0xDCE1  # 90 bytes (BCD)
TABLE_DISTANCE_10 = 0xDD3B  # 90 bytes (BCD)
TABLE_DISTANCE_1 = 0xDD95  # 90 bytes (BCD)
TABLE_HANDICAP = 0xDDEF  # 90 bytes; verified as a 1-18 permutation per course

# ============================================================================
# Switched Bank $0B Tables ($8000-$BFFF)
# ============================================================================
TABLE_TERRAIN_START_PTR = 0xB696  # 90 x 2-byte pointers
TABLE_TERRAIN_END_PTR = 0xB74A  # 90 x 2-byte pointers (also attribute start)
TABLE_GREENS_PTR = 0xB7FE  # 90 x 2-byte pointers
TABLE_SCROLL_LIMIT = 0xB8B2  # 90 bytes
TABLE_GREEN_X = 0xB90C  # 90 bytes
TABLE_GREEN_Y = 0xB966  # 90 bytes
TABLE_TEE_X = 0xB9C0  # 90 bytes
TABLE_TEE_Y = 0xBA1A  # 90 x 2-byte values
TABLE_FLAG_X_OFFSET = 0xBACE  # 90 x 4 bytes
TABLE_FLAG_Y_OFFSET = 0xBC36  # 90 x 4 bytes

# ============================================================================
# Decompression Table Addresses (Fixed Bank - JP-specific, content identical
# to US tables at different addresses; verified by direct byte comparison)
# ============================================================================
TABLE_TERRAIN_HORIZ_TRANSITION = 0xDEEE  # 224 bytes
TABLE_TERRAIN_VERT_CONTINUATION = 0xDFCE  # 224 bytes
TABLE_TERRAIN_DICTIONARY = 0xE0AE  # 64 bytes

TABLE_GREENS_HORIZ_TRANSITION = 0xE193  # 192 bytes (32 bytes zero padding to $E253)
TABLE_GREENS_VERT_CONTINUATION = 0xE253  # 192 bytes
TABLE_GREENS_DICTIONARY = 0xE313  # 64 bytes


def read_metadata_byte(rom: RomReader, table_addr: int, index: int) -> int:
    """Read a single byte from a switched-bank $0B metadata table."""
    return rom.read_switched(table_addr + index, JP_METADATA_BANK)[0]


def read_metadata_word(rom: RomReader, table_addr: int, index: int) -> int:
    """Read a 16-bit little-endian word from a switched-bank $0B metadata table."""
    data = rom.read_switched(table_addr + index * 2, JP_METADATA_BANK, 2)
    return data[0] | (data[1] << 8)
