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
The project provides several command-line tools via entry points (defined in `pyproject.toml`):

```bash
# Extract all course data from ROM to JSON files with compression statistics
golf-dump <rom_file.nes> <output_dir>

# Analyze ROM structure and show technical details
golf-analyze <rom_file.nes> [hole_number]

# Visualize a hole as PNG (renders terrain + greens with sprites)
golf-visualize <tileset.bin> <hole.json> [output.png]

# Visualize an entire course directory
golf-visualize <tileset.bin> <course_dir> [output_dir]

# Convert hex string to binary file
golf-hex2bin

# Expand dictionary codes into their complete horizontal transition sequences
golf-expand-dict <meta.json> [terrain|greens]

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

### JSON Inspection

The various JSON files (in courses/ and data/) can be efficiently inspected using `jq`. Useful `jq` commands should be added to this section as they are discovered during development.

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

## Development Notes

### Adding New Tools

To add a new command-line tool:
1. Create the tool as a Python module in `tools/` with a `main()` function
2. Add an entry point in `pyproject.toml` under `[project.scripts]`
3. Tools become available as `golf-<tool-name>` after running `uv sync`

Example: `golf-expand-dict = "tools.expand_dict:main"` makes `golf-expand-dict` available as a command.

## Testing

### Running Tests

A comprehensive test suite for the compression system is located in the `tests/` directory. Tests are written using pytest and cover both unit and integration testing.

```bash
# Run all tests with coverage
pytest

# Run only unit tests (tests individual compression functions)
pytest tests/unit/

# Run only integration tests (round-trip compression/decompression)
pytest tests/integration/

# Run specific test file
pytest tests/unit/test_vertical_fill.py -v

# Run with verbose output and see print statements
pytest -v -s

# Generate coverage report
pytest --cov=golf --cov-report=html
```

### Test Structure

- **Unit Tests** (`tests/unit/`): 23 tests validating individual compression functions
  - `test_vertical_fill.py` - Vertical fill detection (7 tests)
  - `test_dict_matching.py` - Dictionary sequence matching (6 tests)
  - `test_repeat_codes.py` - Repeat code generation (6 tests)
  - `test_table_loading.py` - Compression table validation (4 tests)

- **Integration Tests** (`tests/integration/`): 11 tests for round-trip validation
  - `test_terrain_roundtrip.py` - Terrain compress/decompress (6 tests)
  - `test_greens_roundtrip.py` - Greens compress/decompress (5 tests)

- **Test Fixtures** (`tests/fixtures/` and `tests/conftest.py`):
  - Real compression tables from `data/tables/compression_tables.json`
  - Mock minimal tables for unit testing
  - Real hole data from `courses/japan/`
  - Hand-crafted test fixtures (simple terrain/greens)

## Claude Code Preferences

- **Commit messages**: Please do not author commit messages. I prefer to write them myself to capture the specific context and rationale.
