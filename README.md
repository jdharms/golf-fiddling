# NES Open Tournament Golf Tools

Reverse engineering, editing and patching tools for NES Open Tournament Golf: course
extraction and a course editor, ROM research tools, gameplay patches, and the groundwork
for a randomizer.

## Requirements

- Python >= 3.12
- [uv](https://docs.astral.sh/uv/) package manager

## Setup

### Linux / macOS

```bash
# Install uv (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone the repository
git clone git@github.com:jdharms/golf-fiddling.git
cd golf-fiddling

# Install dependencies
uv sync
```

### Windows

```powershell
# Install uv (if not already installed)
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"

# Clone the repository
git clone git@github.com:jdharms/golf-fiddling.git
cd golf-fiddling

# Install dependencies
uv sync
```

Run any command below with `uv run <command>`. Every command takes `--help`, which is the
full reference for its options.

## Layout

- **golf/** - shared library: ROM reading/writing, compression, graphics, patches
  (`golf/core/patches/`), data formats, rendering, and the scorecard QR code (`golf/qr/`)
- **editor/** - the Pygame course editor
- **tools/** - command-line entry points, grouped into `data/` (regenerates `data/`
  files), `research/`, `art/`, `music/` and `qr/`; course and patch tools sit at the top
  level; `archive/` holds retired one-off scripts
- **docs/** - design and reverse-engineering notes; start at `docs/README.md`
- **data/** - checked-in tables, tilesets, sprites and exports the tools and editor load
- **courses/** - extracted course JSON
- **web/** - the course measurement web app

## Commands

### Course editor

| Command | Description |
|---------|-------------|
| `golf-editor [terrain_chr] [greens_chr] [hole.json]` | Launch the course editor; see `editor/CLAUDE.md` |

Build a standalone editor executable with `uv run pyinstaller run_editor.spec`.

### Course data

| Command | Description |
|---------|-------------|
| `golf-dump <rom> <out_dir>` | Extract all courses from the US ROM to JSON, with compression statistics |
| `golf-dump-jp <jp_rom> [out_dir]` | Extract the Mario Open Golf (JP) courses; see `docs/jp_extraction.md` |
| `golf-write <rom> <course_dir>` | Write one course back into a ROM, packed across terrain banks 0 and 1; see `docs/multi_bank_terrain.md` |
| `golf-visualize <tileset> <hole.json or course_dir> [out]` | Render holes to PNG |
| `golf-render-web <tileset> <greens_tileset> <courses> <web_dir>` | Render every hole for the web app |

### Regenerating data/ files

| Command | Description |
|---------|-------------|
| `golf-extract-tables <rom> [out.json]` | Decompression tables -> `data/tables/compression_tables.json` |
| `golf-analyze-neighbors` | Terrain tile neighbor data -> `data/tables/terrain_neighbors.json` (editor validation) |
| `golf-analyze-greens-neighbors` | Greens tile neighbor data -> `data/tables/greens_neighbors.json` (fringe generation) |
| `golf-analyze-putting` | Putting surface sizes -> `data/statistics/putting_surface_sizes.json` |

### Utilities

| Command | Description |
|---------|-------------|
| `golf-hex2bin <input.txt> <output.bin>` | Convert a hex string file to binary |
| `golf-expand-dict <meta.json> [terrain or greens]` | Expand dictionary codes into their horizontal transition sequences |

### ROM patches

| Command | Description |
|---------|-------------|
| `golf-patch-wram <rom>` | Expand the terrain buffer past 48 rows; see `docs/wram_expansion.md` |
| `golf-patch-seeded-wind <rom> --seed <seed>` | Seed pins and wind per hole; see `docs/seeded_wind.md` |
| `golf-patch-practice-swing <rom>` | Practice swings (apply `golf-patch-wram` first); see `docs/practice_swing.md` |
| `golf-patch-music <rom> <music.json>` | Replace the course themes from a music dump; see `docs/music_format.md` |
| `golf-patch-signpost <rom> <edited.aseprite>` | Install new signpost banner art; see `docs/prehole_signpost.md` |
| `golf-patch-qr <rom>` | Install the end-of-round QR screen; see `docs/scorecard_qr.md` |

### Reverse-engineering research

| Command | Description |
|---------|-------------|
| `golf-rom-peek <rom> <subcommand>` | Targeted reads, searches, disassembly and reference finding; see the `nes-open-golf-rom-peek` skill |
| `golf-labels <file.mlb> list/add/edit/remove` | Edit the Mesen `.mlb` label file; see the `nes-open-golf-label-conventions` skill |

### Art

| Command | Description |
|---------|-------------|
| `golf-golfer-export <rom> <out_dir>` | Export golfer animations as layered Aseprite files; see `docs/golfer_sprites.md` |
| `golf-signpost-import <edited.aseprite>` | Read edited signpost banner art back out of a screen export; see `docs/prehole_signpost.md` |

### Music

| Command | Description |
|---------|-------------|
| `golf-export-music <rom>` | Export music as NSF, the DPCM drum kit, or a relocatable JSON dump; works on the US and JP ROMs |

### Scorecard QR

| Command | Description |
|---------|-------------|
| `golf-qr-preview` | Build a payload, encode it as the ROM will, render the NES screen |
| `golf-qr-validate` | Sweep masks x rounds x capture conditions x decoders |
| `golf-qr-tables [out_dir]` | Export the ROM tables |
| `golf-qr-port` | Assemble the 6502 port and report sizes against the bank 2 budget |

## Example workflow

```bash
# Extract all courses from ROM
golf-dump nes_open_us.nes courses/

# Edit a hole using the course editor
golf-editor courses/japan/hole_01.json

# Write a course (all 3 course slots play it)
golf-write nes_open_us.nes courses/japan/ -o modified.nes

# Check a course will fit without writing
golf-write nes_open_us.nes courses/japan/ --validate-only --verbose
```

## Running tests

```bash
uv run pytest
```
