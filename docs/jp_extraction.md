# JP Course Extraction Implementation Plan

## Overview

This document describes how to extract course data from the Japanese release of NES Open Tournament Golf (Mario Open Golf) and prepare it for import into the US release.

## Key Differences Between US and JP ROMs

| Aspect | US | JP |
|--------|----|----|
| PRG Size | 256KB (16 banks) | 256KB (16 banks) |
| Mapper | MMC1 | MMC1 |
| Courses | 3 | 5 (+1 remix) |
| Total Holes | 54 | 90 |
| Attribute bytes/hole | 72 | 90 |
| Greens bank | Fixed (bank 3) | Per-course terrain bank |
| Metadata table location | Fixed bank | Split: some fixed, some in bank $0B |

## JP Table Addresses

### Fixed Bank Tables ($C000-$FFFF)

These are accessed directly without bank switching:

```python
JP_FIXED_TABLES = {
    # Course-level (indexed 0-5)
    "COURSE_HOLE_OFFSET": 0xDC7D,    # 6 bytes: [0, 18, 36, 54, 72, 0]
    "COURSE_BANK_TERRAIN": 0xDC82,   # 6 bytes: [0, 1, 2, 3, 4, 4]

    # Hole-level (indexed 0-89)
    "PAR": 0xDC87,                   # 90 bytes
    "DISTANCE_100": 0xDCE1,          # 90 bytes (BCD)
    "DISTANCE_10": 0xDD3B,           # 90 bytes (BCD)
    "DISTANCE_1": 0xDD95,            # 90 bytes (BCD)
    "HANDICAP": 0xDDEF,              # 90 bytes
}
```

### Switched Bank $0B Tables ($8000-$BFFF)

These tables are in Bank $0B:

```python
JP_SWITCHED_TABLES = {
    # Pointer tables (90 x 2-byte entries)
    "TERRAIN_START_PTR": 0xB696,
    "TERRAIN_END_PTR": 0xB74A,       # Also marks attribute start
    "GREENS_PTR": 0xB7FE,

    # Hole metadata (90 bytes each unless noted)
    "SCROLL_LIMIT": 0xB8B2,
    "GREEN_X": 0xB90C,
    "GREEN_Y": 0xB966,
    "TEE_X": 0xB9C0,
    "TEE_Y": 0xBA1A,                 # 90 x 2-byte values

    # Flag positions (90 x 4 bytes each)
    "FLAG_X_OFFSET": 0xBACE,
    "FLAG_Y_OFFSET": 0xBC36,
}

JP_METADATA_BANK = 0x0B
```

## Decompression Tables

Both US and JP use identical decompression algorithms. The lookup tables have identical content but different addresses:

### US Table Addresses (Fixed Bank)

**Greens decompression**:
**IMPORTANT**:
Greens decompression tables are at $8000, $80C0, $8180 in the switched bank on the US version
```python
prg = rom_utils.cpu_to_prg_switched(0x8000, bank)
self.horiz_table = list(rom.read_prg(prg, 192))

prg = rom_utils.cpu_to_prg_switched(0x80C0, bank)
self.vert_table = list(rom.read_prg(prg, 192))

prg = rom_utils.cpu_to_prg_switched(0x8180, bank)
self.dict_table = list(rom.read_prg(prg, 64))
```

**Terrain decompression**
```python
TABLE_HORIZ_TRANSITION = 0xE1AC    # 224 bytes - transform table
TABLE_VERT_CONTINUATION = 0xE28C  # 224 bytes - prediction table
TABLE_DICTIONARY = 0xE36C         # 64 bytes - code pair expansion
```

### JP Table Addresses (Fixed Bank)

**IMPORTANT**:
Greens tables are in the fixed bank in JP version.
**Greens decompression**:
```python
JP_GREENS_TRANSFORM = 0xE193      # 192 bytes (matches US table size; trailing bytes to $E253 are zero padding)
JP_GREENS_PREDICTION = 0xE253     # ~192 bytes
JP_GREENS_DICTIONARY = 0xE313     # 64 bytes
```

**Terrain decompression**:
```python
JP_TERRAIN_DICTIONARY = 0xE0AE    # 64 bytes
JP_TERRAIN_TRANSFORM = 0xDEEE     # 224 bytes
JP_TERRAIN_PREDICTION = 0xDFCE    # ~224 bytes
```

## Structural Differences

### Greens Bank Location

- **US**: All greens compressed data is in bank 3, regardless of course
- **JP**: Greens are stored in the same bank as terrain (banks 0-4 for courses 0-4)

This means the JP dumper must use `terrain_bank` for both terrain AND greens, not a hardcoded bank 3.

### Attribute Size

- **US**: 72 bytes per hole (8 rows × 9 bytes, or similar)
- **JP**: 90 bytes per hole (10 rows × 9 bytes, or similar)

**Decision: truncation is not viable.** JP courses are taller than US courses precisely
because they use the extra 18 bytes (2 attribute rows) — that's real palette data covering
real terrain, not padding. Truncating to 72 bytes silently drops the bottom two attribute
rows of any JP hole tall enough to need them, which corrupts palette assignment on import
for exactly the holes we care about extracting. This is not a "try it and see" question;
it's ruled out by construction. The only viable path is expanding the US engine to support
90 bytes (see Task 5 / Option C, now the only option).

The 72-byte assumption is baked into more than JSON serialization — it's a hardcoded read
length and hardcoded pack/truncate boundary in the current codebase (see Task 5).

## Implementation Tasks

### Task 1: Create `jp_rom_utils.py`

Create a JP-specific version of `rom_utils.py` with:

```python
# jp_rom_utils.py

INES_HEADER_SIZE = 0x10
PRG_BANK_SIZE = 0x4000
FIXED_BANK_PRG_START = 0x3C000

COURSES = [
    {"name": "jp_course1", "display_name": "Japan Course 1"},
    {"name": "jp_course2", "display_name": "Japan Course 2"},
    {"name": "jp_course3", "display_name": "Japan Course 3"},
    {"name": "jp_course4", "display_name": "Japan Course 4"},
    {"name": "jp_course5", "display_name": "Japan Course 5"},
    # Course 5 (index 5) is remix - skip for now
]
HOLES_PER_COURSE = 18
TOTAL_HOLES = 90

JP_METADATA_BANK = 0x0B
JP_ATTR_BYTES = 90

# Fixed bank tables
TABLE_COURSE_HOLE_OFFSET = 0xDC7D
TABLE_COURSE_BANK_TERRAIN = 0xDC82
TABLE_PAR = 0xDC87
TABLE_DISTANCE_100 = 0xDCE1
TABLE_DISTANCE_10 = 0xDD3B
TABLE_DISTANCE_1 = 0xDD95

# Switched bank $0B tables
TABLE_TERRAIN_START_PTR = 0xB696
TABLE_TERRAIN_END_PTR = 0xB74A
TABLE_GREENS_PTR = 0xB7FE
TABLE_SCROLL_LIMIT = 0xB8B2
TABLE_GREEN_X = 0xB90C
TABLE_GREEN_Y = 0xB966
TABLE_TEE_X = 0xB9C0
TABLE_TEE_Y = 0xBA1A
TABLE_FLAG_X_OFFSET = 0xBACE
TABLE_FLAG_Y_OFFSET = 0xBC36

# Decompression tables (fixed bank) - same content as US
TABLE_HORIZ_TRANSITION = 0xE1AC  # Can use US addresses since content is identical
TABLE_VERT_CONTINUATION = 0xE28C
TABLE_DICTIONARY = 0xE36C


def cpu_to_prg_fixed(cpu_addr: int) -> int:
    if cpu_addr < 0xC000 or cpu_addr > 0xFFFF:
        raise ValueError(f"Address ${cpu_addr:04X} not in fixed bank range")
    return FIXED_BANK_PRG_START + (cpu_addr - 0xC000)


def cpu_to_prg_switched(cpu_addr: int, bank: int) -> int:
    if cpu_addr < 0x8000 or cpu_addr > 0xBFFF:
        raise ValueError(f"Address ${cpu_addr:04X} not in switchable bank range")
    return bank * PRG_BANK_SIZE + (cpu_addr - 0x8000)
```

### Task 2: JP metadata reads

No new reader class is needed. `golf/core/rom_reader.py` already provides generic
bank-parameterized read methods, and `golf/core/rom_utils.py` already provides generic
address translation:

```python
# Already exist, use directly:
rom.read_switched(cpu_addr, bank, length=1)   # generic switched-bank read
rom.read_fixed(cpu_addr, length=1)            # generic fixed-bank read
rom_utils.cpu_to_prg_switched(cpu_addr, bank)
rom_utils.cpu_to_prg_fixed(cpu_addr)
```

JP metadata reads (bank `$0B`) just call `rom.read_switched(TABLE_ADDR + index, bank=JP_METADATA_BANK)`
with JP-specific addresses from Task 1's constants module. Word-sized metadata reads
(e.g. `TEE_Y`, pointer tables) can be plain helper functions in `jp_rom_utils.py`:

```python
def read_metadata_byte(rom: RomReader, table_addr: int, index: int) -> int:
    return rom.read_switched(table_addr + index, JP_METADATA_BANK)[0]

def read_metadata_word(rom: RomReader, table_addr: int, index: int) -> int:
    data = rom.read_switched(table_addr + index * 2, JP_METADATA_BANK, 2)
    return data[0] | (data[1] << 8)
```

### Task 3: Decompressor changes

Table *contents* are confirmed identical between JP and US (verified by reading both
ROMs directly at the documented addresses). Only addresses and, for greens, the bank
*kind* differ.

`golf/core/decompressor.py` currently hardcodes table addresses as constructor-time
reads from `rom_utils`:

- `TerrainDecompressor` reads its 3 tables (`TABLE_HORIZ_TRANSITION`, `TABLE_VERT_CONTINUATION`,
  `TABLE_DICTIONARY`) from the **fixed bank** via `rom_utils.cpu_to_prg_fixed`. JP terrain
  tables are also in the fixed bank, just at different addresses
  (`$DEEE`/`$DFCE`/`$E0AE` vs US `$E1AC`/`$E28C`/`$E36C`). This is a pure address swap —
  parameterizing the three addresses is sufficient.

- `GreensDecompressor` reads its 3 tables from the **switched bank** of the greens bank
  (`cpu_to_prg_switched` at $8000/$80C0/$8180, `bank` defaulting to 3). JP greens tables
  live in the **fixed bank** instead ($E193/$E253/$E313), not in any switched bank at all.
  This is a structural difference, not just new constants — `GreensDecompressor` needs a
  mode that reads its tables via `cpu_to_prg_fixed` rather than `cpu_to_prg_switched`,
  selectable per ROM version.

**Greens compressed data location** (separate from the greens *decompression tables*
above) also needs to handle: JP stores each hole's compressed greens data in the same
bank as that hole's terrain, not a hardcoded bank 3 like US.

### Task 4: Create `dump_jp_courses.py`

The current `tools/dump.py` (US dumper) hardcodes several things beyond the fixed/switched
metadata split already called out above, all of which a JP dumper needs to override:

- `greens_bank = 3` is hardcoded rather than derived — JP needs `greens_bank = terrain_bank`.
- Attribute read length is `ATTR_TOTAL_BYTES` (72, from `palettes.py`), a fixed constant —
  JP needs 90, and per Task 5 this constant needs to become height-driven anyway.
- Every metadata field (par, distance, handicap, scroll_limit, green/tee, flags, all three
  pointer tables) is read via `rom_utils.TABLE_*` fixed-bank addresses with no fixed/switched
  branch at all currently — a JP dumper needs the fixed-vs-switched split per table as
  described in "JP Table Addresses" above (course-level and PAR/DISTANCE stay fixed-bank;
  everything else moves to switched bank `$0B`).

Adapt the existing `dump_course.py` for JP:

```python
def dump_jp_course(rom: RomReader, course_idx: int, output_dir: Path):
    course = jp_rom_utils.COURSES[course_idx]
    course_dir = output_dir / course["name"]
    course_dir.mkdir(parents=True, exist_ok=True)

    # Read course-level data from FIXED bank
    hole_offset = rom.read_fixed_byte(jp_rom_utils.TABLE_COURSE_HOLE_OFFSET + course_idx)
    terrain_bank = rom.read_fixed_byte(jp_rom_utils.TABLE_COURSE_BANK_TERRAIN + course_idx)

    # JP: greens are in terrain bank, not bank 3
    greens_bank = terrain_bank

    for hole_in_course in range(jp_rom_utils.HOLES_PER_COURSE):
        hole_idx = hole_offset + hole_in_course

        # Read from FIXED bank tables
        par = rom.read_fixed_byte(jp_rom_utils.TABLE_PAR + hole_idx)
        dist_100 = rom.read_fixed_byte(jp_rom_utils.TABLE_DISTANCE_100 + hole_idx)
        dist_10 = rom.read_fixed_byte(jp_rom_utils.TABLE_DISTANCE_10 + hole_idx)
        dist_1 = rom.read_fixed_byte(jp_rom_utils.TABLE_DISTANCE_1 + hole_idx)

        # Read from SWITCHED bank $0B tables via jp_rom_utils helpers (Task 2)
        scroll_limit = jp_rom_utils.read_metadata_byte(rom, jp_rom_utils.TABLE_SCROLL_LIMIT, hole_idx)
        green_x = jp_rom_utils.read_metadata_byte(rom, jp_rom_utils.TABLE_GREEN_X, hole_idx)
        green_y = jp_rom_utils.read_metadata_byte(rom, jp_rom_utils.TABLE_GREEN_Y, hole_idx)
        tee_x = jp_rom_utils.read_metadata_byte(rom, jp_rom_utils.TABLE_TEE_X, hole_idx)
        tee_y = jp_rom_utils.read_metadata_word(rom, jp_rom_utils.TABLE_TEE_Y, hole_idx)

        terrain_start = jp_rom_utils.read_metadata_word(rom, jp_rom_utils.TABLE_TERRAIN_START_PTR, hole_idx)
        terrain_end = jp_rom_utils.read_metadata_word(rom, jp_rom_utils.TABLE_TERRAIN_END_PTR, hole_idx)
        greens_ptr = jp_rom_utils.read_metadata_word(rom, jp_rom_utils.TABLE_GREENS_PTR, hole_idx)

        # Flag positions
        flag_positions = []
        for i in range(4):
            flag_x = jp_rom_utils.read_metadata_byte(rom, jp_rom_utils.TABLE_FLAG_X_OFFSET, hole_idx * 4 + i)
            flag_y = jp_rom_utils.read_metadata_byte(rom, jp_rom_utils.TABLE_FLAG_Y_OFFSET, hole_idx * 4 + i)
            flag_positions.append({"x_offset": flag_x, "y_offset": flag_y})

        # Read compressed data from TERRAIN bank
        terrain_size = terrain_end - terrain_start
        terrain_prg = jp_rom_utils.cpu_to_prg_switched(terrain_start, terrain_bank)
        terrain_compressed = rom.read_prg(terrain_prg, terrain_size)

        # Read attributes (90 bytes for JP)
        attr_prg = jp_rom_utils.cpu_to_prg_switched(terrain_end, terrain_bank)
        attr_bytes = rom.read_prg(attr_prg, jp_rom_utils.JP_ATTR_BYTES)

        # Read greens from TERRAIN bank (not bank 3)
        greens_prg = jp_rom_utils.cpu_to_prg_switched(greens_ptr, greens_bank)
        greens_compressed = rom.read_prg(greens_prg, 576)  # Max size

        # Decompress and save...
```

### Task 5: Expand attribute size to 90 bytes (US ROM patch)

Truncation is not an option (see "Attribute Size" above) — the US engine must be patched
to support 90-byte attributes. The approach: stream attributes directly from ROM via a
banked pointer instead of copying into a fixed-size RAM buffer.

`scratch/attrs_patch.py` already implements this:
- Adds `LoadTerrainAttrBanked` (17 bytes of new code) at free space `$E1B0` (PRG offset
  `$3E1B0`), which preserves/restores the current bank while reading attribute data.
- Repoints `LoadTerrain`'s pointer-low/high stores from the old RAM buffer target to a new
  `AttrDataPtr` at RAM `$47`-`$48`, plus a new `AttrDataBank` byte at `$49`.
- NOPs out the old 10-byte copy loop at `$DB96`-`$DB9F` (`LDY #$47 / LDA (ptr),Y / STA buf,Y / DEY / BPL`)
  since attributes are read on demand instead of bulk-copied.
- Can emit either a direct-patched ROM (`apply_patch`) or an IPS patch file (`create_ips`).

This has already been generated and applied once — `attrs_patch.nes` in the repo root
(gitignored) differs from `nes_open_us.nes` by exactly 67 bytes, matching this patch's
footprint. The patch has been tested in-game against the existing 72-byte US holes with
no regressions. It has **not** been tested with actual 90-byte attribute data, because
the rest of the toolchain (JP dumper, attribute pipeline changes below) needed to produce
a 90-byte hole to inject doesn't exist yet — that testing is blocked on Tasks 1-4, not on
the patch itself.

`scratch/wram_analyze.py` (a static 6502 disassembly scanner for WRAM accesses) was used
to confirm `$47`-`$49` is safe to repurpose for `AttrDataPtr`/`AttrDataBank`.

Once the RAM read path is patched, the software-side hardcoded 72-byte assumptions also
need to change:
- `golf/core/palettes.py`: `ATTR_TOTAL_BYTES = 72` — used as a fixed read length in
  `tools/dump.py` regardless of actual hole height.
- `golf/core/packing.py`: `pack_attributes` pads/truncates its output to exactly 72 bytes
  (`while len(output) < 72: ...`, `return bytes(output[:72])`).

Both need to become height-driven (attribute row count depends on the hole's actual
terrain height) rather than a hardcoded constant, for JP-derived holes to round-trip
correctly through the pipeline.

## Verification Checklist

Before running full extraction:

- [ ] Verify JP ROM loads correctly (check header, bank count)
- [ ] Verify course structure reads correctly (offsets 0,18,36,54,72)
- [ ] Verify terrain banks are 0,1,2,3,4
- [ ] Verify a few holes have sensible metadata (par 3-5, distances 100-800)
- [ ] Verify terrain pointers are in $8000-$BFFF range
- [ ] Verify decompression produces 22-byte rows for terrain
- [ ] Verify decompression produces 24-byte rows for greens
- [ ] Compare one decompressed hole visually to emulator screenshot

## File Structure

```
golf/
├── core/
│   ├── rom_utils.py           # US ROM constants
│   ├── jp_rom_utils.py        # JP ROM constants + metadata read helpers
│   ├── rom_reader.py          # Generic reader, unchanged - already bank-parameterized
│   ├── decompressor.py        # TerrainDecompressor/GreensDecompressor take table addresses
│   │                          # as constructor args; GreensDecompressor has a
│   │                          # tables_in_fixed_bank mode for JP's fixed-bank greens tables
│   ├── packing.py             # pack_attributes returns the real byte count for the
│   │                          # given attribute row count, no fixed-size padding
│   └── patches/
│       ├── multi_bank.py      # MULTI_BANK_CODE_PATCH_WITH_ATTR_STREAMING: use this
│       │                      # instead of MULTI_BANK_CODE_PATCH when attr_streaming
│       │                      # is also applied - both touch $DB68-$DB70
│       └── attr_streaming.py  # Streams attributes from ROM instead of a fixed
│                               # 72-byte RAM buffer copy
tools/
├── dump.py                    # US dumper
└── dump_jp_courses.py         # JP dumper (golf-dump-jp)
```

## Open Questions

1. **Handicap data**: Resolved. `TABLE_HANDICAP = 0xDDEF` in the fixed bank, 90 bytes,
   immediately following `TABLE_DISTANCE_1` in the same layout order as the US table.
   Verified against the real JP ROM: each course's 18 values form a clean 1-18
   permutation. Added to `jp_rom_utils.py`.

2. **Attrs streaming patch**: Done, and no longer blocked on missing plumbing.
   Converted to the declarative patch framework as `golf/core/patches/attr_streaming.py`,
   plus `MULTI_BANK_CODE_PATCH_WITH_ATTR_STREAMING` in `multi_bank.py` (both patches
   touch the same bytes at `$DB68`-`$DB70`, so a merged variant replaces using both
   independently). Verified byte-identical to the hand-tested `attrs_patch.nes` when
   applied without multi-bank. `pack_attributes` no longer pads/truncates to 72 bytes -
   it returns the real byte count for the hole's actual attribute row count.
   `PackedCourseWriter` auto-detects when any hole needs more than 72 bytes and applies
   the streaming patch set instead of the plain multi-bank patch.

   A **new** blocker turned up while testing an actual 60-row JP hole end-to-end: the
   vanilla terrain decompression buffer in WRAM is only sized for 48 rows (1,056 bytes
   = 22 x 48), with the greens buffer packed immediately after it. 6 of the 90 JP holes
   exceed 48 rows (max 60). The written ROM's compressed data is correct - verified
   byte-for-byte by decompressing it back out of the written ROM - but decompressing it
   at runtime overflows that buffer, corrupting both the terrain past row 48 and the
   adjacent greens buffer. See `docs/wram_expansion.md` for the follow-up plan.

3. **Course 5 (remix)**: Still open, low priority. The remap table at $6DE7 (in cart RAM
   space) is interesting - may be populated at runtime from another location. Could
   search PRG for the initialization data.