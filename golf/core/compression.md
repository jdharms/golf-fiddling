# NES Open Tournament Golf - Compression System

## Overview

NES Open Tournament Golf uses a sophisticated two-pass compression system to store terrain and greens data within the NES ROM's limited space. The compression leverages both spatial patterns (horizontal transitions) and temporal patterns (vertical fill) to achieve compact storage.

## Decompression Algorithm (Game Implementation)

The game decompresses course data through two sequential passes:

### Pass 1: RLE + Dictionary Expansion

The compressed stream consists of:
- **Dictionary codes** ($E0-$FF): 32 special codes that expand to multi-byte sequences
- **Repeat codes** ($01-$1F): 31 codes that generate sequences from horizontal transitions
- **Literal bytes** ($20-$DF): 96 possible direct tile values
- **Zero bytes** ($00): Special markers for vertical fill

#### Dictionary Code Expansion

Each dictionary code expands based on a lookup table:
1. Start with a first_byte value
2. Apply the horizontal transition table repeat_count times
3. Build sequence: [first_byte, horiz_table[first_byte], horiz_table[result], ...]

Example (0xE0 in terrain):
- first_byte = 0x00, repeat_count = 1
- Expands to: [0x00, 0x00] (2 bytes of padding)

Example (0xFA in terrain):
- first_byte = 0x00, repeat_count = 21
- Expands to: [0x00, 0x00, ..., 0x00] (22 bytes of padding)

#### Repeat Code Expansion

Repeat codes ($01-$1F) work similarly but use the last byte written to output:
1. Take the final byte from the output buffer
2. Apply horizontal transition N times (where N is the code byte 1-31)
3. Write the resulting sequence

Example:
- If previous output ends with 0xA2, repeat code 0x05 expands to:
  [horiz_table[0xA2], horiz_table[result], ...] (5 bytes total)

### Pass 2: Vertical Fill

After decompressing the RLE/dictionary stream, any 0x00 bytes are replaced:
```
new_byte = vert_table[byte_above]
```

This allows compression to store only differences from the previous row, significantly reducing data size for terrain with vertical patterns.

Example:
- Compressed row: [0x00, 0x00, 0xA1, ...]
- Row above: [0xA0, 0xA0, 0xA3, ...]
- After vertical fill: [vert_table[0xA0], vert_table[0xA0], 0xA1, ...]

## Data Storage

### Terrain Compression Tables
Located in the fixed ROM bank, containing 224 entries (0x00-0xDF):
- **horizontal_table**: Maps each tile to its horizontal successor
- **vertical_table**: Maps each tile to its vertical fill value

Dictionary codes (0xE0-0xFF) are 32 additional entries, each with:
- first_byte: Starting tile value
- repeat_count: How many times to apply horizontal transitions

### Greens Compression Tables
Located in switchable ROM banks, containing 192 entries (0x00-0xBF):
- Similar structure to terrain but with fewer unique tile values
- Adapted for the fixed 24x24 green layout

## Compression Parameters

### Terrain
- **Row width**: 22 tiles
- **Height**: Variable (typically 30-40 rows)
- **Total data**: 22 × height = compressed with horiz+vert tables

### Greens
- **Size**: Fixed 24×24 = 576 tiles
- **Storage**: Single compressed block per hole

## Key Design Insights

### Greedy Longest-Match Principle
The dictionary codes are designed to capture the most frequent multi-byte patterns in course data. Compression uses a greedy approach: at each position, match the longest available pattern (dictionary, repeat, or literal).

### Horizontal Transitions
The horizontal_table encodes tile-to-tile transitions that occur frequently when tiles are placed horizontally. This reduces repeated bytes through a compact mapping rather than raw run-length encoding.

### Vertical Patterns
The vertical_table captures the most common tile-to-tile transformations across rows. Tiles that follow a predictable vertical pattern need only the first occurrence; subsequent rows store 0x00 as a marker.

## Compression Statistics (from ROM analysis)

### Most Common Dictionary Codes (Terrain)
- 0xE0: ~1458 uses (2 bytes of padding) - most frequent
- 0xE1: ~1031 uses (3 bytes of padding)
- 0xE2: ~703 uses (4 bytes of padding)
- 0xFA: ~37 uses (22 bytes of padding) - longest sequence

### Most Common Vertical Fill Patterns
- 0x27 → 0x27: ~4819 times (identity - tile unchanged)
- 0xA0 → 0xA2: ~2736 times (most common vertical transformation)
- 0xA1 → 0xA3: ~2636 times (second most common)

### Horizontal Transition Dominance
- 0x00 → 0x00: ~17121 times (identity for padding)
- 0xA5 → 0xAA: ~104 times
- 0x25 → 0x25: ~86 times

The high frequency of identity transitions (a tile maps to itself) shows the importance of 0x00 padding and the 0x27 water tile in course design.

## Byte Semantics

### In Compressed Stream
- $00: Vertical fill marker (not literal)
- $01-$1F: Repeat codes (generate sequences)
- $20-$DF: Literal tile values (passthrough)
- $E0-$FF: Dictionary codes (multi-byte expansion)

### Edge Cases
- **First row**: Has no row above, vertical fill cannot apply
- **Row boundaries**: Compression respects row width boundaries (22 for terrain, 24 for greens)
- **Stream end**: Handles incomplete rows if data doesn't fill exact grid

## References

- **Decompressor**: golf/core/decompressor.py
- **Compression tables**: data/tables/compression_tables.json (extracted via golf-extract-tables)
- **Analysis tools**: tools/expand_dict.py (visualize dictionary expansion)
