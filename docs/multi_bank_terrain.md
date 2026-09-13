# Multi-Bank Terrain Distribution

> **Note**: This document was written by Claude based on design and ideas by jdharms.

## Problem Statement

The vanilla NES Open Tournament Golf ROM has three courses (Japan, US, UK) with terrain data tightly packed into three separate banks (0, 1, 2). Each bank has ~8,600-8,800 bytes available for terrain data, and the original courses use 95-97% of this space.

A custom course, or one built from Mario Open holes, often does not compress as well as the originals and does not fit in a single bank's terrain region.

## Solution: Per-Hole Bank Lookup

Instead of looking up the terrain bank by course number (3 entries), look it up by hole number. A ROM carries exactly one 18-hole course, whose terrain fills bank 0 and spills into bank 1:

- **~17,400 bytes for 18 holes** = ~969 bytes/hole, twice the vanilla ~484 bytes/hole
- Holes overflow from bank 0 into bank 1 as needed
- Bank 2's terrain region (`$837F-$A553`) is not used for terrain, and is left to other patches (the scorecard QR image lives there)

## Code Patch

The terrain bank lookup occurs at `$DB68` in the fixed bank. At this point in execution:
- Bank 3 is currently switched in (from greens decompression)
- `$31` contains the doubled hole index (0, 2, 4, ..., 34)

### Original Code

```
$DB68  AE 02 01    LDX CourseNumber              ; 3 bytes
$DB6B  BD BE DB    LDA BankNumTerrainDataTable,X ; 3 bytes (3-entry table)
$DB6E  20 52 D3    JSR BankSwitchRoutine         ; 3 bytes
```

### Patched Code (6 bytes, byte-neutral)

```
$DB68  A6 31       LDX $31                       ; 2 bytes (doubled hole index)
$DB6A  BD 00 A7    LDA $A700,X                   ; 3 bytes (per-hole table in bank 3)
$DB6D  EA          NOP                           ; 1 byte
$DB6E  20 52 D3    JSR BankSwitchRoutine         ; untouched
```

The patch stops before the `JSR` at `$DB6E`. The attr-streaming patch set
(`golf/core/patches/attr_streaming.py`) redirects that `JSR` to its
`SaveBankAndSwitch` routine, so the two patches apply independently and in either
order.

### Patch Bytes

At PRG offset `$3DB68` (CPU `$DB68` in fixed bank):
```
Original: AE 02 01 BD BE DB
Patched:  A6 31 BD 00 A7 EA
```

## Per-Hole Bank Table

Located at `$A700` in bank 3 (PRG `$E700`), 36 bytes. Uses doubled indexing, so entries are at even offsets:

| Offset | Hole | Value |
|--------|------|-------|
| $00 | Hole 0 | Bank for hole 0 |
| $02 | Hole 1 | Bank for hole 1 |
| ... | ... | ... |
| $22 | Hole 17 | Bank for hole 17 |

Odd-offset bytes are don't-care values.

The table address `$A700` sits inside bank 3's greens data region (`$81C0-$A773`), after the greens (which end before `$A700`) and before the executable code at `$A774`.

## Course Mirroring

Every course slot plays the one course. `COURSE_MIRRORS_PATCH` sets both hole offsets in
`CourseHoleOffsetTable` at `$DBBB` to 0:

```
Original: 00 12 24  (offsets 0, 18, 36)
Patched:  00 00 00
```

Bank 2 holds a private copy of the same table at `$B1F1`, read by the scorecard's
eagle/birdie/par/bogey faces, and the patch sets it the same way. Hole slots 18-53 are
never read, so their pointer and metadata entries are free for other patches.

## Bank Distribution Strategy

Fill banks greedily in hole order:

```
Bank 0 ($8000-$A23D): holes until full (8,766 bytes)
Bank 1 ($8000-$A1E5): the rest (8,678 bytes)
```

## Implementation

`CoursePatch` in `golf/core/patches/courses.py` is a `ROMPatch` built from exactly 18 `HoleData`. `golf-write` applies it.

### Usage

```bash
# Write a course (all 3 course slots play it)
golf-write rom.nes courses/japan/ -o output.nes

# Validate without writing
golf-write rom.nes courses/japan/ --validate-only --verbose
```

### Required Patches

`CoursePatch` writes course data only. It lists the code patches the data needs in
`requires`, and `apply` raises `PatchError` if any is not applied. `golf-write` applies
them first:

1. **`multi_bank_lookup`** at `$DB68`: 6 bytes to change bank lookup from course-based to hole-based
2. **`course_mirrors`**: every course slot plays holes 0-17
3. **`attr_streaming`**: attributes are written at their real size, which can exceed the vanilla 72-byte buffer

The multi-bank and mirror patches are defined in `golf/core/patches/multi_bank.py`.

### Course Data

Building the patch does all the work, without a ROM:

1. **Compress all holes**: Terrain, attributes, and greens for the 18 holes
2. **Pack terrain across banks**: Greedy first-fit fills bank 0, then bank 1
3. **Generate per-hole bank table**: 36 bytes at `$A700` in bank 3 (doubled indexing)
4. **Lay out every write**: Terrain to assigned banks, greens to bank 3, pointers and
   metadata (par, distance, positions) for holes 0-17 to the fixed bank, collected in
   `CoursePatch.writes`

`CoursePatch.stats` reports bank usage. The data writes do not check the bytes they
overwrite.

### Validation

A course that does not fit raises `BankOverflowError` when the patch is built:

- Total terrain must fit in combined bank 0+1 space (17,444 bytes)
- Total greens must fit in bank 3 region ($81C0-$A6FF = 9,536 bytes)
- Each hole's terrain is contiguous within its assigned bank

## Testing

```bash
uv run pytest tests/unit/test_course_patch.py -v
uv run pytest tests/integration/test_course_patch_rom.py -v
```

## Future Work

- **Menu/UI changes**: Remove the second and third course options
- **Dynamic packing**: Optimize hole distribution across banks for best fit

## References

- Use the `nes-open-golf-rom-layout` skill for complete pointer table addresses and bank layouts
- `golf/core/patches/courses.py` - Course patch implementation
