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

# Implementation placeholder - to be filled in during development
# from typing import List, Dict, Tuple, Optional
# import json
# from pathlib import Path
# from .decompressor import DecompressionStats

# class TerrainCompressor:
#     """Compresses terrain data using greedy longest-match algorithm."""
#     pass

# class GreensCompressor:
#     """Compresses greens data using greedy longest-match algorithm."""
#     pass

# def load_compression_tables(tables_path: str) -> Dict:
#     """Load pre-extracted compression tables from JSON."""
#     pass

# def detect_vertical_fills(rows: List[List[int]], vert_table: List[int]) -> List[List[int]]:
#     """First pass: detect and mark vertical fills with 0x00."""
#     pass

# def compress_terrain(rows: List[List[int]]) -> bytes:
#     """Compress terrain rows to bytes."""
#     pass

# def compress_greens(grid: List[List[int]]) -> bytes:
#     """Compress 24×24 greens grid to bytes."""
#     pass
