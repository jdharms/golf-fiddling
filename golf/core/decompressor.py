"""
NES Open Tournament Golf - Decompression

Terrain and greens decompression algorithms, attribute unpacking,
and BCD conversion utilities.
"""

from typing import List
from .rom_reader import (
    RomReader,
    TABLE_HORIZ_TRANSITION,
    TABLE_VERT_CONTINUATION,
    TABLE_DICTIONARY,
)
from .palettes import TERRAIN_ROW_WIDTH, GREENS_TOTAL_TILES


class TerrainDecompressor:
    """Decompresses terrain data using the game's RLE + dictionary + vertical fill algorithm."""

    def __init__(self, rom: RomReader):
        """
        Initialize terrain decompressor with decompression tables from ROM.

        Args:
            rom: RomReader instance
        """
        self.rom = rom

        # Load decompression tables from fixed bank
        prg = rom.cpu_to_prg_fixed(TABLE_HORIZ_TRANSITION)
        self.horiz_table = list(rom.read_prg(prg, 224))

        prg = rom.cpu_to_prg_fixed(TABLE_VERT_CONTINUATION)
        self.vert_table = list(rom.read_prg(prg, 224))

        prg = rom.cpu_to_prg_fixed(TABLE_DICTIONARY)
        self.dict_table = list(rom.read_prg(prg, 64))

    def decompress(self, compressed: bytes, row_width: int = TERRAIN_ROW_WIDTH) -> List[List[int]]:
        """
        Decompress terrain data.

        Args:
            compressed: Compressed terrain data
            row_width: Width of each row in tiles (default: 22)

        Returns:
            2D array of tile values, one row per list
        """
        # First pass: RLE + dictionary expansion
        output = []
        src_idx = 0

        while src_idx < len(compressed):
            byte = compressed[src_idx]
            src_idx += 1

            if byte >= 0xE0:
                # Dictionary code: expands to 2+ bytes
                dict_idx = (byte - 0xE0) * 2
                first_byte = self.dict_table[dict_idx]
                repeat_count = self.dict_table[dict_idx + 1]

                output.append(first_byte)

                # Apply horizontal transition for repeat_count iterations
                for _ in range(repeat_count):
                    prev = output[-1]
                    if prev < len(self.horiz_table):
                        output.append(self.horiz_table[prev])
                    else:
                        output.append(0)

            elif byte == 0x00:
                # Zero: written directly (row terminator or special)
                output.append(0)

            elif byte < 0x20:
                # Repeat count: apply horizontal transition
                repeat_count = byte
                for _ in range(repeat_count):
                    if len(output) > 0:
                        prev = output[-1]
                        if prev < len(self.horiz_table):
                            output.append(self.horiz_table[prev])
                        else:
                            output.append(0)
                    else:
                        output.append(0)

            else:
                # Literal terrain value ($20-$DF)
                output.append(byte)

        # Convert to rows
        rows = []
        for i in range(0, len(output), row_width):
            row = output[i:i + row_width]
            # Pad if necessary
            while len(row) < row_width:
                row.append(0)
            rows.append(row)

        # Second pass: vertical fill (0 = derive from row above)
        for row_idx in range(1, len(rows)):
            for col_idx in range(row_width):
                if rows[row_idx][col_idx] == 0:
                    above = rows[row_idx - 1][col_idx]
                    if above < len(self.vert_table):
                        rows[row_idx][col_idx] = self.vert_table[above]

        return rows


class GreensDecompressor:
    """Decompresses greens data - similar algorithm but different tables in switched bank."""

    def __init__(self, rom: RomReader, bank: int):
        """
        Initialize greens decompressor with decompression tables from ROM.

        Args:
            rom: RomReader instance
            bank: Bank number containing greens decompression tables
        """
        self.rom = rom
        self.bank = bank

        # Greens decompression tables are at $8000, $80C0, $8180 in the switched bank
        prg = rom.cpu_to_prg_switched(0x8000, bank)
        self.horiz_table = list(rom.read_prg(prg, 192))

        prg = rom.cpu_to_prg_switched(0x80C0, bank)
        self.vert_table = list(rom.read_prg(prg, 192))

        prg = rom.cpu_to_prg_switched(0x8180, bank)
        self.dict_table = list(rom.read_prg(prg, 64))

    def decompress(self, compressed: bytes) -> List[List[int]]:
        """
        Decompress greens data.

        Row width is 24 for greens.

        Args:
            compressed: Compressed greens data

        Returns:
            2D array of tile values, one row per list
        """
        row_width = 24

        # First pass: RLE + dictionary expansion
        output = []
        src_idx = 0

        while src_idx < len(compressed) and len(output) < GREENS_TOTAL_TILES:
            byte = compressed[src_idx]
            src_idx += 1

            if byte >= 0xE0:
                dict_idx = (byte - 0xE0) * 2
                first_byte = self.dict_table[dict_idx]
                repeat_count = self.dict_table[dict_idx + 1]

                output.append(first_byte)

                for _ in range(repeat_count):
                    prev = output[-1]
                    if prev < len(self.horiz_table):
                        output.append(self.horiz_table[prev])
                    else:
                        output.append(0)

            elif byte == 0x00:
                output.append(0)

            elif byte < 0x20:
                repeat_count = byte
                for _ in range(repeat_count):
                    if len(output) > 0:
                        prev = output[-1]
                        if prev < len(self.horiz_table):
                            output.append(self.horiz_table[prev])
                        else:
                            output.append(0)
                    else:
                        output.append(0)

            else:
                output.append(byte)

        # Truncate output to exactly 576 tiles if we overshot during decompression
        output = output[:GREENS_TOTAL_TILES]

        # Convert to rows
        rows = []
        for i in range(0, len(output), row_width):
            row = output[i:i + row_width]
            while len(row) < row_width:
                row.append(0)
            rows.append(row)

        # Second pass: vertical fill
        for row_idx in range(1, len(rows)):
            for col_idx in range(row_width):
                if rows[row_idx][col_idx] == 0:
                    above = rows[row_idx - 1][col_idx]
                    if above < len(self.vert_table):
                        rows[row_idx][col_idx] = self.vert_table[above]

        return rows


def unpack_attributes(attr_bytes: bytes, num_rows: int) -> List[List[int]]:
    """
    Unpack NES attribute bytes into 2D palette index array.

    Each attribute byte covers a 4x4 tile (2x2 supertile) area.
    We return per-supertile (2x2 tile) palette indices.

    The first supertile column is HUD, so we skip it and return 11 course columns.

    Args:
        attr_bytes: Raw attribute bytes (72 bytes)
        num_rows: Number of rows to unpack

    Returns:
        Array of shape (num_rows, 11) with values 0-3
    """
    # Attributes are stored in rows of 6 bytes (covering 12 supertiles)
    # First supertile column is HUD, we want columns 1-11 (11 total)

    rows = []
    attr_idx = 0

    for megatile_row in range(num_rows // 2):
        # Each megatile row produces 2 supertile rows
        top_row = []
        bottom_row = []

        for megatile_col in range(6):  # 6 megatiles wide (covers 12 supertile columns)
            if attr_idx >= len(attr_bytes):
                break

            attr = attr_bytes[attr_idx]
            attr_idx += 1

            # Unpack 4 palette indices from attribute byte
            top_left = attr & 0x03
            top_right = (attr >> 2) & 0x03
            bottom_left = (attr >> 4) & 0x03
            bottom_right = (attr >> 6) & 0x03

            top_row.extend([top_left, top_right])
            bottom_row.extend([bottom_left, bottom_right])

        # Skip first column (HUD), take next 11 columns (course data)
        rows.append(top_row[1:12])
        rows.append(bottom_row[1:12])

    return rows[:num_rows]


def bcd_to_int(hundreds: int, tens: int, ones: int) -> int:
    """
    Convert BCD distance values to integer.

    Args:
        hundreds: BCD-encoded hundreds digit
        tens: BCD-encoded tens digit
        ones: BCD-encoded ones digit

    Returns:
        Decoded integer value
    """
    h = ((hundreds >> 4) * 10 + (hundreds & 0x0F)) * 100
    t = ((tens >> 4) * 10 + (tens & 0x0F)) * 10
    o = (ones >> 4) * 10 + (ones & 0x0F)
    return h + t + o
