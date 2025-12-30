"""
NES Open Tournament Golf - Compression System

This module implements terrain and greens data compression for NES Open Tournament Golf.

## Compression Algorithm Overview

The compression system mirrors the decompression process in reverse:

### Decompression (what we decode):
1. FIRST PASS: RLE + dictionary expansion
   - Dictionary codes ($E0-$FF) expand to (first_byte, repeat_count) with horizontal transitions
   - Repeat codes ($01-$1F) apply horizontal transitions from the last byte
   - Literal bytes ($20-$DF) are written directly
   - Zero bytes ($00) are written directly

2. SECOND PASS: Vertical fill
   - Any 0 bytes in the decompressed data are replaced by looking up the byte above
   - new_byte = vert_table[byte_above]

### Compression (what we must encode) - REVERSE order:
1. FIRST PASS: Vertical fill detection
   - Scan each row and compare tiles with vert_table[tile_above]
   - If tile == vert_table[tile_above], replace tile with 0x00
   - This creates more 0x00 runs for better dictionary compression

2. SECOND PASS: RLE + dictionary encoding
   - Flatten rows into a byte stream with the 0x00 markers from vertical fill
   - Try to match longest dictionary/repeat codes first (greedy algorithm)
   - Fall back to literal bytes when no match found

## Data Format and Tables

The compression system uses pre-extracted tables stored in data/tables/compression_tables.json:

### Terrain Tables (from fixed bank, addresses 0xE1AC, 0xE28C, 0xE36C):
- horizontal_table: 224 bytes - maps prev_byte -> next_byte for horizontal transitions
- vertical_table: 224 bytes - maps byte_above -> new_byte for vertical fill
- dictionary_codes: 32 codes (0xE0-0xFF), each with (first_byte, repeat_count)
- reverse_dict_lookup: Pre-computed sequences sorted by length (longest first)

### Greens Tables (from bank 3, addresses 0x8000, 0x80C0, 0x8180):
- horizontal_table: 192 bytes - greens use fewer unique tiles than terrain
- vertical_table: 192 bytes
- dictionary_codes: 32 codes
- reverse_dict_lookup: Sequences sorted by length
- Max sequence length: 24 bytes (fits 24×24 greens grid)

## Compression Algorithm Details

### Key Insight: Greedy Longest-Match
The reverse_dict_lookup is pre-sorted by sequence length (longest first).
This enables greedy longest-match compression:
- At each position, try to match the longest possible dictionary sequence
- If no dictionary match, try repeat codes
- If still no match, write a literal byte
- This is fast and gives good compression for existing terrain patterns

### Dictionary Code Expansion
Dictionary codes expand as follows:
1. Start with first_byte
2. Apply horizontal transition (lookup in horiz_table) repeat_count times
3. Build sequence: [first_byte, horiz_table[first_byte], horiz_table[result], ...]

Example (terrain code 0xE0):
- first_byte = 0x00, repeat_count = 1
- sequence = [0x00, horiz_table[0x00]] = [0x00, 0x00] (2 bytes)

Example (terrain code 0xFA):
- first_byte = 0x00, repeat_count = 21
- sequence = [0x00, 0x00, 0x00, ..., 0x00] (22 bytes of 0x00)

### Repeat Codes
Repeat codes ($01-$1F) work similarly to dictionary codes but:
- Start from the last byte in the output buffer
- Apply horizontal transition N times (where N is the code byte 1-31)
- Used when a specific tile pattern isn't in the dictionary

Example:
- If output ends with 0xA2, and we see repeat code 0x05:
- Apply horiz_table[0xA2] 5 times to generate the sequence

### Vertical Fill Detection
Before RLE/dictionary encoding:
1. Iterate through each row (starting from row 1)
2. For each tile in the row:
   - Check if tile == vert_table[tile_above]
   - If yes, replace with 0x00
3. This creates markers that will be re-interpreted as vertical fill during decompression

Example:
- Input row: [0xA0, 0xA0, 0xA1, ...]
- If tile_above row: [0xA0, 0xA0, 0xA3, ...]
- After vertical fill detection: [0x00, 0x00, 0xA1, ...]
  (First two tiles match vert_table[A0] and vert_table[A0], so become 0x00)

## Compression Parameters

### Terrain:
- Row width: 22 tiles
- Variable height: 30-40 rows typical
- Horizontal table: 224 bytes
- Vertical table: 224 bytes
- Dictionary codes: 32 (0xE0-0xFF)
- Longest dictionary sequence: 22 bytes

### Greens:
- Fixed size: 24*24 = 576 tiles total
- Horizontal table: 192 bytes
- Vertical table: 192 bytes
- Dictionary codes: 32 (0xE0-0xFF)
- Longest dictionary sequence: 24 bytes

## Compression Statistics (from meta.json analysis)

### Most Common Dictionary Codes (Terrain):
- 0xE0: 1458 uses (2 bytes of 0x00) - most common
- 0xE1: 1031 uses (3 bytes of 0x00)
- 0xE2: 703 uses (4 bytes of 0x00)
- 0xFA: 37 uses (22 bytes of 0x00) - longest run

### Most Common Vertical Fill Patterns:
- 0x27 -> 0x27: 4819 times (identity - tile doesn't change)
- 0xA0 -> 0xA2: 2736 times (most common transformation)
- 0xA1 -> 0xA3: 2636 times

### Most Common Horizontal Transitions:
- 0x00 -> 0x00: 17121 times (identity for padding)
- 0xA5 -> 0xAA: 104 times
- 0x25 -> 0x25: 86 times

## Implementation Roadmap

### Phase 1: Basic Infrastructure
- [ ] Load compression_tables.json
- [ ] Implement vertical fill detection pass
- [ ] Implement byte stream flattening

### Phase 2: Pattern Matching
- [ ] Implement dictionary sequence matching (greedy longest-match)
- [ ] Implement repeat code generation
- [ ] Implement reverse horizontal transition lookup

### Phase 3: Encoding
- [ ] Implement RLE encoding logic
- [ ] Implement literal byte handling
- [ ] Implement row boundary handling (row width = 22 for terrain, 24 for greens)

### Phase 4: Integration
- [ ] Integrate with HoleData model
- [ ] Add compression methods to Terrain/Greens classes
- [ ] Implement round-trip testing (compress -> decompress -> validate)

### Phase 5: Optimization
- [ ] Profile compression performance
- [ ] Optimize greedy matching algorithm
- [ ] Consider alternative compression strategies if needed

## Testing Strategy

### Unit Tests:
1. Vertical fill detection accuracy
2. Dictionary code matching correctness
3. Repeat code generation validation
4. Round-trip compression/decompression consistency

### Integration Tests:
1. Compress all 54 holes, compare file sizes with original
2. Verify decompressor produces identical data from compressed output
3. Test edge cases (very short holes, long runs of same tile, boundary conditions)

### Quality Metrics:
- Compression ratio: Compare output size vs. original
- Match original: Can decompressed data be bit-identical to original?
- Performance: Compression speed (should be < 1 second per hole)

## Important Notes

### Byte Semantics:
- In compressed stream: 0x00 is a special marker for vertical fill (not a literal)
- In literal bytes: 0x00 must be encoded as a literal $00 byte
- Dictionary codes: $E0-$FF (32 codes, only valid in compressed stream)
- Repeat codes: $01-$1F (31 codes, applied to generate sequences)
- Literal bytes: $20-$DF (96 possible literal values)

### Table Lookup Safety:
- Always bounds-check before accessing tables
- prev_byte < len(horiz_table) before horiz_table[prev_byte]
- byte_above < len(vert_table) before vert_table[byte_above]

### Edge Cases:
- First row has no "row above" for vertical fill - leave as-is
- Row boundaries: Ensure row width is enforced (22 for terrain, 24 for greens)
- Stream end: Handle partial rows correctly
- Empty holes: Some holes might be fully 0x00 or pattern-based

## References

- Decompressor implementation: golf/core/decompressor.py
- Compression tables: data/tables/compression_tables.json
- Decompression statistics: courses/meta.json (from golf-dump)
- Dictionary expansion tool: tools/expand_dict.py (see golf-expand-dict command)
- Table extraction tool: tools/extract_tables.py (see golf-extract-tables command)

## Future Enhancements

1. **Optimal compression**: Use dynamic programming to find globally optimal encoding
2. **Custom dictionaries**: Learn optimal dictionary codes from user-created courses
3. **Adaptive encoding**: Choose between greedy/optimal based on size/time tradeoff
4. **Compression hints**: Analyze course data to pre-optimize dictionary usage
5. **Stream format**: Support compressed course patches (delta compression)
"""

from typing import List, Dict, Tuple, Optional
import json
from pathlib import Path


def _get_default_tables_path() -> Path:
    """Get default path to compression_tables.json."""
    return Path(__file__).parent.parent.parent / "data" / "tables" / "compression_tables.json"


def load_compression_tables(tables_path: Optional[str] = None) -> Dict:
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
        required_keys = ["horizontal_table", "vertical_table", "dictionary_codes", "reverse_dict_lookup"]
        for key in required_keys:
            if key not in cat_tables:
                raise ValueError(f"Missing '{key}' in {category} tables")

    return tables


def detect_vertical_fills(rows: List[List[int]], vert_table: List[int]) -> List[List[int]]:
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
            tile_above = result[row_idx - 1][col_idx]
            current_tile = result[row_idx][col_idx]

            # Bounds check before table access
            if tile_above < len(vert_table):
                expected_tile = vert_table[tile_above]

                # If current matches expected, replace with 0x00 marker
                if current_tile == expected_tile:
                    result[row_idx][col_idx] = 0x00

    return result


def match_dict_sequence(
    byte_stream: List[int],
    position: int,
    reverse_lookup: Dict[str, List[str]]
) -> Optional[Tuple[str, int]]:
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
        stream_slice = byte_stream[position:position + seq_len]
        stream_hex = ''.join(f'{b:02X}' for b in stream_slice)

        # Check for match (case-insensitive)
        if stream_hex == hex_sequence.upper():
            # Return first code in list
            return (code_list[0], seq_len)

    return None


def generate_repeat_code(
    byte_stream: List[int],
    position: int,
    prev_byte: int,
    horiz_table: List[int]
) -> Optional[Tuple[int, int]]:
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

    def __init__(self, tables_path: Optional[str] = None):
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

    def compress(self, rows: List[List[int]]) -> bytes:
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

                # Update prev_byte to last byte that would be decompressed
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

    def __init__(self, tables_path: Optional[str] = None):
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

    def compress(self, rows: List[List[int]]) -> bytes:
        """Compress 24×24 greens grid to bytes.

        Args:
            rows: 2D array of greens tiles (must be 24x24)

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
                code_byte = int(code_str, 16)
                output.append(code_byte)
                pos += length

                # Update prev_byte
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

                    # Update prev_byte
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
