"""
NES Open Tournament Golf - Decompression

Terrain and greens decompression algorithms, attribute unpacking,
and BCD conversion utilities.
"""

from typing import List, Dict, Any, Optional, Tuple, Set
from .rom_reader import (
    RomReader,
    TABLE_HORIZ_TRANSITION,
    TABLE_VERT_CONTINUATION,
    TABLE_DICTIONARY,
)
from .palettes import TERRAIN_ROW_WIDTH, GREENS_TOTAL_TILES


class DecompressionStats:
    """
    Collects statistics about decompression algorithm behavior.

    Tracks:
    - Dictionary code expansions ($E0-$FF)
    - Repeat code usage ($01-$1F)
    - Horizontal transitions (prev_byte -> next_byte pairs)
    - Vertical fills (byte_above -> new_byte pairs)
    """

    def __init__(self):
        # Dictionary code statistics
        # Key: code byte ($E0-$FF), Value: dict with first_byte, repeat_count, usage_count, holes
        self.dict_codes: Dict[int, Dict[str, Any]] = {}

        # Repeat code statistics
        # Key: repeat_count (1-31), Value: dict with usage_count, transitions
        self.repeat_codes: Dict[int, Dict[str, Any]] = {}

        # Horizontal transition statistics
        # Key: (prev_byte, next_byte) tuple, Value: usage_count
        self.horiz_transitions: Dict[Tuple[int, int], int] = {}

        # Vertical fill statistics
        # Key: (byte_above, new_byte) tuple, Value: usage_count
        self.vert_fills: Dict[Tuple[int, int], int] = {}

        # Per-hole context tracking
        self.current_hole: Optional[str] = None

    def set_hole_context(self, course: str, hole_num: int):
        """Set the current hole being processed for tracking hole coverage."""
        self.current_hole = f"{course}/hole_{hole_num:02d}"

    def record_dict_expansion(self, code: int, first_byte: int, repeat_count: int):
        """
        Record usage of a dictionary code ($E0-$FF).

        Args:
            code: The dictionary code byte (0xE0-0xFF)
            first_byte: The first byte from dict_table[idx]
            repeat_count: The repeat count from dict_table[idx+1]
        """
        if code not in self.dict_codes:
            self.dict_codes[code] = {
                "first_byte": first_byte,
                "repeat_count": repeat_count,
                "usage_count": 0,
                "holes": set()
            }

        self.dict_codes[code]["usage_count"] += 1
        if self.current_hole:
            self.dict_codes[code]["holes"].add(self.current_hole)

    def record_repeat_code(self, repeat_count: int, prev_byte: int, next_byte: int):
        """
        Record usage of a repeat code ($01-$1F) and track the transition.

        Args:
            repeat_count: The repeat count (1-31)
            prev_byte: The byte before applying horizontal transition
            next_byte: The byte after applying horizontal transition
        """
        if repeat_count not in self.repeat_codes:
            self.repeat_codes[repeat_count] = {
                "usage_count": 0,
                "transitions": {}
            }

        self.repeat_codes[repeat_count]["usage_count"] += 1

        # Track the (prev, next) transition
        transition = (prev_byte, next_byte)
        if transition not in self.repeat_codes[repeat_count]["transitions"]:
            self.repeat_codes[repeat_count]["transitions"][transition] = 0
        self.repeat_codes[repeat_count]["transitions"][transition] += 1

    def record_horiz_transition(self, prev_byte: int, next_byte: int):
        """
        Record a horizontal transition lookup.

        Args:
            prev_byte: Input byte to horizontal transition table
            next_byte: Output byte from horizontal transition table
        """
        transition = (prev_byte, next_byte)
        if transition not in self.horiz_transitions:
            self.horiz_transitions[transition] = 0
        self.horiz_transitions[transition] += 1

    def record_vert_fill(self, byte_above: int, new_byte: int):
        """
        Record a vertical fill operation.

        Args:
            byte_above: The byte from the row above (input to vert_table)
            new_byte: The byte written (output from vert_table)
        """
        fill = (byte_above, new_byte)
        if fill not in self.vert_fills:
            self.vert_fills[fill] = 0
        self.vert_fills[fill] += 1

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert statistics to JSON-serializable dictionary.

        Returns:
            Dictionary with all statistics in JSON-friendly format
        """
        # Convert dict_codes (holes is a set, needs conversion)
        dict_codes_serializable = {}
        for code, data in self.dict_codes.items():
            dict_codes_serializable[f"0x{code:02X}"] = {
                "first_byte": f"0x{data['first_byte']:02X}",
                "repeat_count": data["repeat_count"],
                "usage_count": data["usage_count"],
                "holes": sorted(list(data["holes"]))
            }

        # Convert repeat_codes (transition tuples need conversion)
        repeat_codes_serializable = {}
        for count, data in self.repeat_codes.items():
            transitions_list = [
                {
                    "prev_byte": f"0x{prev:02X}",
                    "next_byte": f"0x{next:02X}",
                    "count": trans_count
                }
                for (prev, next), trans_count in sorted(data["transitions"].items(), key=lambda x: -x[1])[:20]
            ]
            repeat_codes_serializable[str(count)] = {
                "usage_count": data["usage_count"],
                "top_transitions": transitions_list
            }

        # Convert horiz_transitions
        horiz_transitions_list = [
            {
                "prev_byte": f"0x{prev:02X}",
                "next_byte": f"0x{next:02X}",
                "count": count
            }
            for (prev, next), count in sorted(self.horiz_transitions.items(), key=lambda x: -x[1])[:50]
        ]

        # Convert vert_fills
        vert_fills_list = [
            {
                "byte_above": f"0x{above:02X}",
                "new_byte": f"0x{new:02X}",
                "count": count
            }
            for (above, new), count in sorted(self.vert_fills.items(), key=lambda x: -x[1])[:50]
        ]

        return {
            "dictionary_codes": dict_codes_serializable,
            "repeat_codes": repeat_codes_serializable,
            "horizontal_transitions": {
                "total_count": sum(self.horiz_transitions.values()),
                "unique_transitions": len(self.horiz_transitions),
                "top_transitions": horiz_transitions_list
            },
            "vertical_fills": {
                "total_count": sum(self.vert_fills.values()),
                "unique_fills": len(self.vert_fills),
                "top_fills": vert_fills_list
            }
        }

    def merge(self, other: 'DecompressionStats'):
        """
        Merge statistics from another DecompressionStats instance.

        Used to combine terrain and greens statistics, or aggregate across courses.

        Args:
            other: Another DecompressionStats instance to merge
        """
        # Merge dict_codes
        for code, data in other.dict_codes.items():
            if code not in self.dict_codes:
                self.dict_codes[code] = {
                    "first_byte": data["first_byte"],
                    "repeat_count": data["repeat_count"],
                    "usage_count": 0,
                    "holes": set()
                }
            self.dict_codes[code]["usage_count"] += data["usage_count"]
            self.dict_codes[code]["holes"].update(data["holes"])

        # Merge repeat_codes
        for count, data in other.repeat_codes.items():
            if count not in self.repeat_codes:
                self.repeat_codes[count] = {
                    "usage_count": 0,
                    "transitions": {}
                }
            self.repeat_codes[count]["usage_count"] += data["usage_count"]

            for transition, trans_count in data["transitions"].items():
                if transition not in self.repeat_codes[count]["transitions"]:
                    self.repeat_codes[count]["transitions"][transition] = 0
                self.repeat_codes[count]["transitions"][transition] += trans_count

        # Merge horiz_transitions
        for transition, count in other.horiz_transitions.items():
            if transition not in self.horiz_transitions:
                self.horiz_transitions[transition] = 0
            self.horiz_transitions[transition] += count

        # Merge vert_fills
        for fill, count in other.vert_fills.items():
            if fill not in self.vert_fills:
                self.vert_fills[fill] = 0
            self.vert_fills[fill] += count


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

    def decompress(self, compressed: bytes, row_width: int = TERRAIN_ROW_WIDTH, stats: Optional[DecompressionStats] = None) -> List[List[int]]:
        """
        Decompress terrain data.

        Args:
            compressed: Compressed terrain data
            row_width: Width of each row in tiles (default: 22)
            stats: Optional DecompressionStats instance to collect statistics

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

                # Record dictionary code usage
                if stats:
                    stats.record_dict_expansion(byte, first_byte, repeat_count)

                # Apply horizontal transition for repeat_count iterations
                for _ in range(repeat_count):
                    prev = output[-1]
                    if prev < len(self.horiz_table):
                        next_byte = self.horiz_table[prev]
                        output.append(next_byte)

                        # Record horizontal transition
                        if stats:
                            stats.record_horiz_transition(prev, next_byte)
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
                            next_byte = self.horiz_table[prev]
                            output.append(next_byte)

                            # Record repeat code transition
                            if stats:
                                stats.record_repeat_code(repeat_count, prev, next_byte)
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
                        new_byte = self.vert_table[above]
                        rows[row_idx][col_idx] = new_byte

                        # Record vertical fill
                        if stats:
                            stats.record_vert_fill(above, new_byte)

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

    def decompress(self, compressed: bytes, stats: Optional[DecompressionStats] = None) -> List[List[int]]:
        """
        Decompress greens data.

        Row width is 24 for greens.

        Args:
            compressed: Compressed greens data
            stats: Optional DecompressionStats instance to collect statistics

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

                # Record dictionary code usage
                if stats:
                    stats.record_dict_expansion(byte, first_byte, repeat_count)

                for _ in range(repeat_count):
                    prev = output[-1]
                    if prev < len(self.horiz_table):
                        next_byte = self.horiz_table[prev]
                        output.append(next_byte)

                        # Record horizontal transition
                        if stats:
                            stats.record_horiz_transition(prev, next_byte)
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
                            next_byte = self.horiz_table[prev]
                            output.append(next_byte)

                            # Record repeat code transition
                            if stats:
                                stats.record_repeat_code(repeat_count, prev, next_byte)
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
                        new_byte = self.vert_table[above]
                        rows[row_idx][col_idx] = new_byte

                        # Record vertical fill
                        if stats:
                            stats.record_vert_fill(above, new_byte)

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
