# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a toolset for reverse engineering and editing NES Open Tournament Golf ROM data. The project includes:
- ROM reading and decompression tools
- Course data extraction and visualization
- A graphical course editor built with Pygame

## Development Commands

### Setup
```bash
# Install dependencies (uses uv for package management)
uv sync
```

### Running Tools
The project provides several command-line tools via entry points:

```bash
# Extract all course data from ROM to JSON files
golf-dump <rom_file.nes> <output_dir>

# Analyze ROM structure and show technical details
golf-analyze <rom_file.nes> [hole_number]

# Visualize a hole as PNG (renders terrain + greens with sprites)
golf-visualize <tileset.bin> <hole.json> [output.png]

# Visualize an entire course directory
golf-visualize <tileset.bin> <course_dir> [output_dir]

# Convert hex string to binary file
golf-hex2bin

# Launch the course editor (requires CHR binary files)
golf-editor <terrain_chr.bin> <greens_chr.bin> [hole.json]
```

### Example Workflow
```bash
# Extract all courses from ROM
golf-dump nes_open_us.nes courses/

# Visualize a specific hole
golf-visualize data/chr-ram.bin courses/japan/hole_01.json output.png

# Or visualize an entire course
golf-visualize data/chr-ram.bin courses/japan/ renders/japan/

# Edit a hole in the visual editor
golf-editor data/chr-ram.bin data/green-ram.bin courses/japan/hole_01.json
```

## Code Architecture

### Package Structure

The codebase is organized into three main packages:

**`golf/`** - Shared library for ROM reading and data formats
- `core/` - ROM reading, decompression, NES graphics (CHR tiles, palettes)
- `formats/` - Hole data model, JSON serialization, hex utilities
- `rendering/` - PIL-based rendering for visualization

**`editor/`** - Interactive Pygame-based course editor
- `core/` - Pygame rendering primitives (tilesets, sprites)
- `ui/` - Widgets, dialogs, tile pickers
- `controllers/` - Editor state and event handling
- `rendering/` - Specialized renderers (terrain, greens, grid, sprites)

**`tools/`** - Command-line utilities
- `dump.py` - Extract course data from ROM to JSON
- `analyze.py` - ROM structure analysis
- `visualize.py` - Static rendering of holes to PNG
- `hex2bin.py` - Hex string converter

### Key Architecture Concepts

**ROM Memory Model**: NES ROMs use bank switching. The game has a fixed bank ($C000-$FFFF, bank 15) containing pointer tables and lookup data, plus switchable banks ($8000-$BFFF) containing compressed course data. The `RomReader` class handles CPU address translation to PRG ROM offsets.

**Decompression**: Course terrain and greens use a custom compression scheme with three stages:
1. RLE + dictionary expansion (codes $E0+ expand to multiple bytes)
2. Horizontal transitions (low byte values trigger table lookups)
3. Vertical fill (0 bytes copy from row above with transformation)

Separate decompression tables exist for terrain (in fixed bank) and greens (in switchable banks).

**Data Model**: `HoleData` is the central model for hole information. It stores:
- Terrain tiles (22 columns wide, variable height)
- Greens tiles (24x24 grid)
- Attributes (palette indices for 2x2 supertiles)
- Metadata (par, distance, tee/green positions, flag positions)

**JSON Format**: Holes are stored as JSON with hex-encoded tile rows (e.g., "A2 A3 A0 A1"). This compact format is human-readable and can be directly edited.

**CHR Graphics**: NES graphics use 8x8 tiles stored in CHR format. The codebase requires extracted CHR binaries for terrain and greens tilesets. `Tileset` class handles loading and rendering CHR tiles with NES palettes.

**Sprite Rendering**: Sprite definitions in `data/sprites/*.json` define NES sprite-based objects (ball, flag, tee markers) with tile data and palette information.

### Course Data Organization

- **3 courses**: Japan, US, UK (in that order - Japan was developed first)
- **18 holes per course** (54 total holes)
- **Course files**: `courses/{country}/hole_{01-18}.json` and `courses/{country}/course.json`
- **Coordinates**: All positions use pixel coordinates (x, y)

### Important Coordinate Systems

- **Terrain tiles**: 22 tiles wide, variable height (typically 30-40 rows)
- **Supertiles**: 2x2 tile blocks used for attribute (palette) mapping
- **Attributes**: 11 columns wide (12 supertiles minus 1 HUD column)
- **Greens tiles**: Fixed 24x24 grid centered at green position
- **Screen coordinates**: Editor uses scrollable viewport with zoom

### NES-Specific Details

- **Palettes**: 4 palettes of 4 colors each for terrain; separate palettes for greens
- **Attributes**: Packed as 4 2-bit values per byte covering 4x4 tile areas
- **BCD encoding**: Distances stored as Binary-Coded Decimal
- **Bank numbers**: Course data bank determined by `TABLE_COURSE_BANK_TERRAIN`

## Testing

Currently no automated test suite exists.
