"""
NES Open Tournament Golf - Compression Implementation

Implements terrain and greens data compression using the reverse of the game's
decompression algorithm. See golf/core/compression.md for algorithm details.
"""

import json
from pathlib import Path


def _get_default_tables_path() -> Path:
    """Get default path to compression_tables.json."""
    return (
        Path(__file__).parent.parent.parent
        / "data"
        / "tables"
        / "compression_tables.json"
    )


def load_compression_tables(tables_path: str | None = None) -> dict:
    """Load pre-extracted compression tables from JSON.

    Args:
        tables_path: Path to compression_tables.json. If None, uses default path.

    Returns:
        Dict with "terrain" and "greens" keys, each containing:
        - horizontal_table: List[int]
        - vertical_table: List[int]
        - dictionary_codes: Dict[str, Dict]
        - reverse_dict_lookup: Dict[str, List[str]]

    Raises:
        FileNotFoundError: If tables file not found
        ValueError: If tables structure is invalid
    """
    if tables_path is None:
        tables_path = _get_default_tables_path()
    else:
        tables_path = Path(tables_path)

    if not tables_path.exists():
        raise FileNotFoundError(f"Compression tables not found: {tables_path}")

    with open(tables_path) as f:
        tables = json.load(f)

    # Validate structure
    for category in ["terrain", "greens"]:
        if category not in tables:
            raise ValueError(f"Missing '{category}' section in tables")

        cat_tables = tables[category]
        required_keys = [
            "horizontal_table",
            "vertical_table",
            "dictionary_codes",
            "reverse_dict_lookup",
        ]
        for key in required_keys:
            if key not in cat_tables:
                raise ValueError(f"Missing '{key}' in {category} tables")

    return tables


def detect_vertical_fills(
    rows: list[list[int]], vert_table: list[int]
) -> list[list[int]]:
    """First pass: detect and mark vertical fills with 0x00.

    Replaces tiles with their corresponding vert_table value from the row above.

    Args:
        rows: 2D list of tile values
        vert_table: Vertical transformation table

    Returns:
        2D list with matching tiles replaced by 0x00
    """
    # Deep copy to avoid modifying input
    result = [row[:] for row in rows]

    # Process rows starting from row 1 (row 0 has no row above)
    for row_idx in range(1, len(result)):
        for col_idx in range(len(result[row_idx])):
            tile_above = rows[row_idx - 1][col_idx]
            current_tile = result[row_idx][col_idx]

            # Bounds check before table access
            if tile_above < len(vert_table):
                expected_tile = vert_table[tile_above]

                # Replace with 0x00 to signal vertical fill during compression.
                # The decompressor will re-expand these by looking up from tile_above.
                if current_tile == expected_tile:
                    result[row_idx][col_idx] = 0x00

    return result


def match_dict_sequence(
    byte_stream: list[int], position: int, reverse_lookup: dict[str, list[str]]
) -> tuple[str, int] | None:
    """Try to match dictionary sequence at current position (greedy longest-match).

    Args:
        byte_stream: Flattened byte array to compress
        position: Current position in stream
        reverse_lookup: Dict mapping hex sequences to code strings (pre-sorted longest-first)

    Returns:
        (code_string, match_length) if match found, None otherwise
    """
    # Iterate through reverse_lookup (pre-sorted by sequence length, longest first)
    for hex_sequence, code_list in reverse_lookup.items():
        seq_len = len(hex_sequence) // 2  # Each byte = 2 hex chars

        # Check if we have enough bytes left
        if position + seq_len > len(byte_stream):
            continue

        # Extract bytes from stream and convert to uppercase hex string
        stream_slice = byte_stream[position : position + seq_len]
        stream_hex = "".join(f"{b:02X}" for b in stream_slice)

        # Check for match (case-insensitive)
        if stream_hex == hex_sequence.upper():
            # Return first code in list
            return (code_list[0], seq_len)

    return None


def generate_repeat_code(
    byte_stream: list[int], position: int, prev_byte: int, horiz_table: list[int]
) -> tuple[int, int] | None:
    """Generate repeat code by following horizontal transitions from prev_byte.

    Args:
        byte_stream: Flattened byte array to compress
        position: Current position in stream
        prev_byte: Last byte written to output (to start transitions from)
        horiz_table: Horizontal transition table

    Returns:
        (repeat_code, match_length) where code is 1-31, or None if no match
    """
    MAX_REPEAT = 31
    count = 0
    current = prev_byte

    # Try to match up to MAX_REPEAT transitions
    while count < MAX_REPEAT and position + count < len(byte_stream):
        # Bounds check before table access
        if current >= len(horiz_table):
            break

        # Apply horizontal transition
        next_byte = horiz_table[current]

        # Check if stream matches
        if byte_stream[position + count] != next_byte:
            break

        count += 1
        current = next_byte

    # Return match if we got at least 1
    if count > 0:
        return (count, count)

    return None


class TerrainCompressor:
    """Compresses terrain data using greedy longest-match algorithm."""

    def __init__(self, tables_path: str | None = None):
        """Initialize terrain compressor.

        Args:
            tables_path: Path to compression_tables.json. If None, uses default.
        """
        tables = load_compression_tables(tables_path)
        terrain = tables["terrain"]

        self.horiz_table = terrain["horizontal_table"]
        self.vert_table = terrain["vertical_table"]
        self.dict_codes = terrain["dictionary_codes"]
        self.reverse_lookup = terrain["reverse_dict_lookup"]
        self.row_width = 22

    def compress(self, rows: list[list[int]]) -> bytes:
        """Compress terrain rows to bytes.

        Args:
            rows: 2D array of terrain tiles (22 wide, variable height)

        Returns:
            Compressed byte array
        """
        # Pass 1: Vertical fill detection
        marked_rows = detect_vertical_fills(rows, self.vert_table)

        # Flatten to byte stream
        byte_stream = []
        for row in marked_rows:
            byte_stream.extend(row)

        # Pass 2: Greedy encoding
        output = []
        pos = 0
        prev_byte = None

        while pos < len(byte_stream):
            # Try dictionary match first (longest-first greedy)
            dict_match = match_dict_sequence(byte_stream, pos, self.reverse_lookup)
            if dict_match:
                code_str, length = dict_match
                code_byte = int(code_str, 16)  # Convert "0xE0" to 0xE0
                output.append(code_byte)
                pos += length

                # Track last byte of expanded sequence for potential repeat codes
                prev_byte = self._get_last_byte_from_dict(code_str)
                continue

            # Try repeat code if we have a previous byte
            if prev_byte is not None:
                repeat_match = generate_repeat_code(
                    byte_stream, pos, prev_byte, self.horiz_table
                )
                if repeat_match:
                    repeat_code, length = repeat_match
                    output.append(repeat_code)
                    pos += length

                    # Update prev_byte to last byte in sequence
                    prev_byte = self._get_last_byte_from_repeat(prev_byte, repeat_code)
                    continue

            # Fall back to literal byte
            literal = byte_stream[pos]
            output.append(literal)
            prev_byte = literal
            pos += 1

        return bytes(output)

    def _get_last_byte_from_dict(self, code_str: str) -> int:
        """Simulate dictionary expansion to get last byte.

        Dictionary code expands to:
        [first_byte, horiz[first_byte], horiz[horiz[first_byte]], ...]
        for repeat_count iterations.
        """
        dict_entry = self.dict_codes[code_str]
        first_byte = dict_entry["first_byte"]
        repeat_count = dict_entry["repeat_count"]

        current = first_byte
        for _ in range(repeat_count):
            if current < len(self.horiz_table):
                current = self.horiz_table[current]

        return current

    def _get_last_byte_from_repeat(self, prev_byte: int, repeat_code: int) -> int:
        """Simulate repeat code expansion to get last byte."""
        current = prev_byte
        for _ in range(repeat_code):
            if current < len(self.horiz_table):
                current = self.horiz_table[current]

        return current


class GreensCompressor:
    """Compresses greens data using greedy longest-match algorithm."""

    def __init__(self, tables_path: str | None = None):
        """Initialize greens compressor.

        Args:
            tables_path: Path to compression_tables.json. If None, uses default.
        """
        tables = load_compression_tables(tables_path)
        greens = tables["greens"]

        self.horiz_table = greens["horizontal_table"]
        self.vert_table = greens["vertical_table"]
        self.dict_codes = greens["dictionary_codes"]
        self.reverse_lookup = greens["reverse_dict_lookup"]
        self.row_width = 24

    def compress(self, rows: list[list[int]]) -> bytes:
        """Compress 24×24 greens grid to bytes.

        Args:
            rows: 2D array of greens tiles (must be 24x24)

        Returns:
            Compressed byte array
        """
        # Pass 1: Vertical fill detection
        marked_rows = detect_vertical_fills(rows, self.vert_table)

        # print(marked_rows)

        # Flatten to byte stream
        byte_stream = []
        for row in marked_rows:
            byte_stream.extend(row)

        # Pass 2: Greedy encoding
        output = []
        pos = 0
        prev_byte = None

        while pos < len(byte_stream):
            # Try dictionary match first (longest-first greedy)
            dict_match = match_dict_sequence(byte_stream, pos, self.reverse_lookup)
            if dict_match:
                code_str, length = dict_match
                code_byte = int(code_str, 16)
                output.append(code_byte)
                # print(dict_match)
                pos += length

                # Track last byte of expanded sequence for potential repeat codes
                prev_byte = self._get_last_byte_from_dict(code_str)
                continue

            # Try repeat code if we have a previous byte
            if prev_byte is not None:
                repeat_match = generate_repeat_code(
                    byte_stream, pos, prev_byte, self.horiz_table
                )
                if repeat_match:
                    repeat_code, length = repeat_match
                    output.append(repeat_code)
                    pos += length

                    # Track last byte of expanded sequence for potential repeat codes
                    prev_byte = self._get_last_byte_from_repeat(prev_byte, repeat_code)
                    continue

            # Fall back to literal byte
            literal = byte_stream[pos]
            output.append(literal)
            prev_byte = literal
            pos += 1

        return bytes(output)

    def _get_last_byte_from_dict(self, code_str: str) -> int:
        """Simulate dictionary expansion to get last byte."""
        dict_entry = self.dict_codes[code_str]
        first_byte = dict_entry["first_byte"]
        repeat_count = dict_entry["repeat_count"]

        current = first_byte
        for _ in range(repeat_count):
            if current < len(self.horiz_table):
                current = self.horiz_table[current]

        return current

    def _get_last_byte_from_repeat(self, prev_byte: int, repeat_code: int) -> int:
        """Simulate repeat code expansion to get last byte."""
        current = prev_byte
        for _ in range(repeat_code):
            if current < len(self.horiz_table):
                current = self.horiz_table[current]

        return current
