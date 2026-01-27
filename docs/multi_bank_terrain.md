# Multi-Bank Terrain Distribution

> **Note**: This document was written by Claude based on design and ideas by jdharms.

## Problem Statement

The vanilla NES Open Tournament Golf ROM has three courses (Japan, US, UK) with terrain data tightly packed into three separate banks (0, 1, 2). Each bank has ~8,600-8,800 bytes available for terrain data, and the original courses use 95-97% of this space.

When creating custom courses, compression efficiency varies. A course that doesn't compress as well as the originals may not fit in a single bank's terrain region.

## Solution: Per-Hole Bank Lookup

Instead of looking up the terrain bank by course number (3 entries), look it up by hole number (54 entries). This allows:

- **Two courses spread across three banks**: ~26,100 bytes for 36 holes = ~725 bytes/hole average
- **50% more space per hole** compared to vanilla (~484 bytes/hole for 54 holes)
- Courses can overflow from one bank to the next as needed

## Code Patch

The terrain bank lookup occurs at `$DB68` in the fixed bank. At this point in execution:
- Bank 3 is currently switched in (from greens decompression)
- `$31` contains the doubled hole index (0, 2, 4, ..., 106)

### Original Code (9 bytes)

```
$DB68  AE 02 01    LDX CourseNumber              ; 3 bytes
$DB6B  BD BE DB    LDA BankNumTerrainDataTable,X ; 3 bytes (3-entry table)
$DB6E  20 52 D3    JSR BankSwitchRoutine         ; 3 bytes
```

### Patched Code (9 bytes, byte-neutral)

```
$DB68  A6 31       LDX $31                       ; 2 bytes (doubled hole index)
$DB6A  BD 00 A7    LDA $A700,X                   ; 3 bytes (per-hole table in bank 3)
$DB6D  20 52 D3    JSR BankSwitchRoutine         ; 3 bytes
$DB70  EA          NOP                           ; 1 byte
```

### Patch Bytes

At PRG offset `$3DB68` (CPU `$DB68` in fixed bank):
```
Original: AE 02 01 BD BE DB 20 52 D3
Patched:  A6 31 BD 00 A7 20 52 D3 EA
```

## Per-Hole Bank Table

Located at `$A700` in bank 3 (PRG offset `$E700`). Uses doubled indexing, so entries are at even offsets:

| Offset | Hole | Value |
|--------|------|-------|
| $00 | Hole 0 | Bank for hole 0 |
| $02 | Hole 1 | Bank for hole 1 |
| ... | ... | ... |
| $46 | Hole 35 | Bank for hole 35 |

Odd-offset bytes are don't-care values. Table requires 72 bytes minimum (36 holes × 2).

The table address `$A700` is chosen to be:
- Within bank 3's greens data region (`$81C0-$A773`)
- After where 36 holes of greens data would end (~6,300 bytes from `$81C0`)
- Well before the executable code at `$A774`

## Course 3 Duplication

To avoid UI/menu changes while supporting only 2 courses, make course 3 (UK) mirror course 1 (Japan):

Patch `CourseHoleOffsetTable` at `$DBBB`:
```
Original: 00 12 24  (offsets 0, 18, 36)
Patched:  00 12 00  (offsets 0, 18, 0)
```

Single byte change at PRG offset `$3DBBD` (CPU `$DBBD`): `24` → `00`

When "UK" is selected, the game uses hole offset 0, accessing the same holes as Japan. All pointer tables and metadata are indexed by the computed hole number, so everything works automatically.

## Bank Distribution Strategy

Fill banks greedily based on compressed size:

```
Bank 0 ($8000-$A23D): Course 1 holes until full (~8,766 bytes)
Bank 1 ($8000-$A1E5): Course 1 overflow + Course 2 start (~8,678 bytes)
Bank 2 ($837F-$A553): Course 2 remainder (~8,661 bytes)
```

Note: Bank 2 has pre-terrain tables at `$8000-$837E` that must be preserved.

## Implementation

The multi-bank terrain feature is implemented in `golf/core/packed_course_writer.py` as the `PackedCourseWriter` class. This is now the **default behavior** for `golf-write`.

### Usage

```bash
# Write 1 course (all 3 course slots show the same course)
golf-write rom.nes courses/japan/ -o output.nes

# Write 2 courses (Japan slot shows course 1, US slot shows course 2, UK mirrors Japan)
golf-write rom.nes courses/japan/ courses/us/ -o output.nes

# Validate without writing
golf-write rom.nes courses/japan/ courses/us/ --validate-only --verbose
```

### ROM Patches (auto-applied in packed mode)

1. **`multi_bank_lookup`** at `$DB68`: 9 bytes to change bank lookup from course-based to hole-based
2. **`course3_mirror`** at `$DBBD`: 1 byte to make course 3 mirror course 1

Patches are defined in `golf/core/patches/multi_bank.py` and auto-applied by `PackedCourseWriter`.

### PackedCourseWriter Responsibilities

1. **Compress all holes**: Terrain, attributes, and greens for 18 or 36 holes
2. **Pack terrain across banks**: Greedy first-fit algorithm fills bank 0, then 1, then 2
3. **Generate per-hole bank table**: 72 bytes at `$A700` in bank 3 (doubled indexing)
4. **Write all data**: Terrain to assigned banks, greens to bank 3, pointers to fixed bank
5. **Update metadata**: Par, distance, positions for all written holes

### Validation

- Total terrain must fit in combined bank 0+1+2 space (~26,100 bytes)
- Total greens must fit in bank 3 region ($81C0-$A6FF = ~9,536 bytes after bank table)
- Each hole's terrain is contiguous within its assigned bank

## Testing

```bash
# Run packed course writer tests
pytest tests/unit/test_packed_course_writer.py -v
pytest tests/integration/test_packed_course_write.py -v
```

## Future Work

- **Menu/UI changes**: Remove or rename the third course option
- **Course selection**: Allow choosing which slot (1 or 2) a custom course occupies
- **Dynamic packing**: Optimize hole distribution across banks for best fit

## References

- Use the `nes-open-golf-rom-layout` skill for complete pointer table addresses and bank layouts
- `golf/core/packed_course_writer.py` - Multi-bank writer implementation
