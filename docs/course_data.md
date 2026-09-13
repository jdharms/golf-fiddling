# Course Data Model

How hole data is represented once it is out of the ROM: the model `golf-dump` writes,
the editor edits, and `golf-write` compresses back in. For how the bytes are packed in
the ROM, see `golf/core/compression.md` and the `nes-open-golf-rom-layout` skill.

## Organization

- **3 courses**: Japan, US, UK (in that order - Japan was developed first)
- **18 holes per course** (54 total holes)
- **Course files**: `courses/{country}/hole_{01-18}.json` and `courses/{country}/course.json`
- **JP courses** (Mario Open Golf): `courses/jp/jp_{course}/`, written by `golf-dump-jp`
- **Coordinates**: all positions use pixel coordinates (x, y)

## HoleData

`HoleData` (`golf/formats/hole_data.py`) is the central model. It stores:

- Terrain tiles (22 columns wide, variable height)
- Terrain height (`terrain_height` field) - visible height, separate from physical terrain data length
- Greens tiles (24x24 grid)
- Attributes (palette indices for 2x2 supertiles)
- Metadata (par, distance, tee/green positions, flag positions, scroll_limit)

## Terrain height

Terrain uses a dual-height system:

- **Physical terrain data** (`terrain` list): can hold up to 48 rows of tile data
- **Visible terrain height** (`terrain_height` field): how many rows are rendered (30-48 rows)
- **Soft removal**: removing rows decreases `terrain_height` but keeps the data in the `terrain` list
- **Restoration**: adding rows restores hidden data (if present) before creating new rows
- **Scroll limit**: calculated as `(terrain_height - 28) / 2` and updated on every add/remove

Row constraints:

- **Minimum** 30 rows, **maximum** 48 rows
- Rows are always added/removed in pairs, so every hole has an even row count

Holes taller than 48 rows (some JP holes) need the WRAM expansion patch; see
`docs/wram_expansion.md`.

## JSON format

Holes are stored as JSON with hex-encoded tile rows (e.g. `"A2 A3 A0 A1"`), so they can
be read and edited directly. `terrain.height` stores the visible terrain height, which may
be less than the number of rows in `terrain.rows` (soft removal). Prefer `jq` over Python
one-liners for inspecting these files.

## Coordinate systems

- **Terrain tiles**: 22 tiles wide, visible height 30-48 rows (always even)
- **Supertiles**: 2x2 tile blocks used for attribute (palette) mapping
- **Attributes**: 11 columns wide (12 supertiles minus 1 HUD column)
- **Greens tiles**: fixed 24x24 grid centered at green position

## NES details

- **Palettes**: 4 palettes of 4 colors each for terrain; separate palettes for greens
- **Attributes**: packed as 4 2-bit values per byte covering 4x4 tile areas
- **BCD encoding**: distances are stored as Binary-Coded Decimal
- **CHR graphics**: 8x8 tiles in CHR format. The terrain and greens tilesets are extracted
  binaries (`data/chr-ram.bin`, `data/green-ram.bin`); `Tileset` loads and renders them
  with NES palettes
- **Sprites**: `data/sprites/*.json` define sprite-based objects (ball, flag, tee markers)
  with tile data and palette information; `golf/rendering/pil_sprite.py` loads them for
  static renders
