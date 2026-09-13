---
name: nes-open-golf-rom-layout
description: |
  NES Open Tournament Golf ROM layout reference. Use when working with ROM reading, writing,
  decompression, or course data extraction for the NES Open Tournament Golf game. Includes
  memory maps, pointer table addresses, bank layouts, data region boundaries, and metadata
  table locations. Essential for: modifying golf/core/patches/courses.py, rom_reader.py, dump.py, or
  any code that reads/writes ROM data.
---

# NES Open Tournament Golf ROM Layout

## ROM Structure

- **Format**: iNES (16-byte header + PRG ROM + CHR ROM)
- **PRG ROM**: 16 banks × 16KB = 256KB
- **Bank switching**: Fixed bank ($C000-$FFFF = bank 15) + switchable bank ($8000-$BFFF)

## Bank Assignments

| Bank | Purpose | Data Region | Available Space |
|------|---------|-------------|-----------------|
| 0 | Japan terrain + lookup tables | $8000-$A23D | 8,766 bytes |
| 1 | US terrain + lookup tables | $8000-$A1E5 | 8,678 bytes |
| 2 | UK terrain + lookup tables | $837F-$A553 | 8,661 bytes |
| 3 | All greens + decompression tables + code | $81C0-$A773 | 9,652 bytes |
| 15 | Fixed bank (pointer tables, metadata, decompression tables) | $C000-$FFFF | N/A |

### Bank 2 (UK) Special Layout
- $8000-$837E: Pre-terrain lookup tables (895 bytes) - MUST PRESERVE
- $837F-$A553: Terrain data region
- $A554-$BFFF: Post-terrain lookup tables - MUST PRESERVE

### Bank 3 (Greens) Layout
- $8000-$81BF: Greens decompression tables (448 bytes)
  - $8000-$80BF: Horizontal transition table (192 bytes)
  - $80C0-$817F: Vertical continuation table (192 bytes)
  - $8180-$81BF: Dictionary table (64 bytes)
- $81C0-$A773: Greens data for all 54 holes (9,652 bytes max)
- $A774-$BFFF: Executable code (6,284 bytes) - MUST PRESERVE

## Fixed Bank Pointer Tables ($C000-$FFFF)

All addresses are CPU addresses in the fixed bank.

### Course Configuration
| Address | Size | Description |
|---------|------|-------------|
| $DBBB | 3 bytes | Hole offset per course (0, 18, 36) |
| $DBBE | 3 bytes | Terrain bank per course (0, 1, 2) |

### Terrain Pointers (54 entries × 2 bytes each)
| Address | Description |
|---------|-------------|
| $DBC1 | Terrain start pointers (108 bytes) |
| $DC2D | Terrain end pointers / attribute start (108 bytes) |

### Greens Pointers
| Address | Description |
|---------|-------------|
| $DC99 | Greens pointers, all 54 holes (108 bytes) |

### Hole Metadata Tables (54 entries each)
| Address | Size | Description |
|---------|------|-------------|
| $DD05 | 54 × 1 | Par (values 3-5) |
| $DD3B | 54 × 1 | Distance hundreds digit (BCD) |
| $DD71 | 54 × 1 | Distance tens digit (BCD) |
| $DDA7 | 54 × 1 | Distance ones digit (BCD) |
| $DDDD | 54 × 1 | Handicap |
| $DE13 | 54 × 1 | Scroll limit |
| $DE49 | 54 × 1 | Green X position |
| $DE7F | 54 × 1 | Green Y position |
| $DEB5 | 54 × 1 | Tee X position |
| $DEEB | 54 × 2 | Tee Y position (16-bit) |
| $DF57 | 54 × 4 | Flag X offsets (4 per hole) |
| $E02F | 54 × 4 | Flag Y offsets (4 per hole) |

### Terrain Decompression Tables (Fixed Bank)
| Address | Size | Description |
|---------|------|-------------|
| $E1AC | 224 bytes | Horizontal transition table |
| $E28C | 224 bytes | Vertical continuation table |
| $E36C | 64 bytes | Dictionary (32 × 2-byte pairs) |

## Course Organization

- **3 courses**: Japan (index 0), US (index 1), UK (index 2)
- **18 holes per course**, 54 total holes
- **Hole indexing**: Global index = course_index × 18 + hole_in_course
  - Japan: holes 0-17
  - US: holes 18-35
  - UK: holes 36-53

## Data Formats

### Terrain Data
- Width: 22 tiles (fixed)
- Height: 30-48 rows (always even)
- Stored compressed, followed by 72 bytes of attribute data
- Attributes: 11 columns × variable rows (ceil(terrain_height/2))

### Greens Data
- Size: 24×24 tiles (576 tiles total)
- Stored compressed
- Decompressor reads until output buffer fills (576 tiles)
- No end pointer - size determined by decompression

### Compression Algorithm (3 stages)
1. **RLE + Dictionary**: Bytes $E0+ expand via dictionary table
2. **Horizontal transitions**: Low byte values trigger table lookups
3. **Vertical fill**: Zero bytes copy from row above with transformation

## Cross-Bank Calls: `ExecuteFarCall`

`ExecuteFarCall` (fixed bank, CPU `$D372`) is the game's mechanism for calling
a routine in a specific *other* switchable bank from code that doesn't know
or care what bank is currently paged in, then returning to the original bank
afterward.

**The 3 bytes immediately after `JSR $D372` are inline parameters, not
code**: `[bank_number, target_addr_lo, target_addr_hi]`. `ExecuteFarCall`
reads those 3 bytes via the return address it finds on the stack, switches
to `bank_number`, calls the target address, switches back to the original
bank, and - critically - adjusts its own return address so the caller
resumes execution at the first byte *after* those 3 parameter bytes, not
right after the `JSR`.

Practical consequence: when disassembling a call site, a naive linear
disassembly of the bytes right after `JSR $D372` will decode as garbage
(real opcodes that happen to overlap the parameter bytes) - this is
expected. Always treat those 3 bytes as `[bank, lo, hi]` data and resume
disassembly after them - `golf-rom-peek disasm` already does this for you
(see the `nes-open-golf-rom-peek` skill), so the manual fix-up is only
needed with other disassemblers. Confirmed empirically (Mesen breakpoint
on a live call) at bank 13 `$834A` → bytes `08 21 9B` → bank 8, CPU
`$9B21`, and at bank 13 `$8142` → bytes `03 69 A8` → bank 3, CPU `$A869`.

## Address Conversion

```
PRG offset from CPU address:
- Fixed bank: prg_offset = 0x3C000 + (cpu_addr - 0xC000)
- Switched bank: prg_offset = bank × 0x4000 + (cpu_addr - 0x8000)

File offset = 16 (iNES header) + prg_offset
```

## Space Constraints

Original game uses ~95-97% of available terrain space and ~98% of greens space. When writing modified courses:

1. Check terrain fits within bank boundaries
2. Check total greens for all 54 holes fits in 9,652 bytes
3. Use decompression to find actual compressed sizes (not pointer differences)
4. Greens have ~171 bytes headroom scattered as small gaps between holes
