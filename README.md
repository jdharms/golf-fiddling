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
- **server/** - the randomizer website; see `server/CLAUDE.md`
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
| `golf-catalog-sync [courses_root] [--check]` | Add dumped vanilla holes to the randomizer catalog and verify the rest -> `data/catalog/holes.json`; see `docs/catalog.md` |

### Utilities

| Command | Description |
|---------|-------------|
| `golf-hex2bin <input.txt> <output.bin>` | Convert a hex string file to binary |
| `golf-expand-dict <meta.json> [terrain or greens]` | Expand dictionary codes into their horizontal transition sequences |

### ROM patches

| Command | Description |
|---------|-------------|
| `golf-patch <rom> [recipe.json] [-p ID[:key=value,...]]` | Build a ROM or IPS patch from a recipe and/or inline patch steps; `--list` shows every patch type; see `docs/patch_stack.md` |
| `golf-randomize generate [-o manifest.json] [--seed S] [settings]` | Generate a randomizer seed manifest from settings; see `docs/manifest.md` |
| `golf-randomize build <rom> <manifest.json> [-o out.nes] [--ips out.ips]` | Build a seed's ROM or IPS: a finished guest ROM by default, `--unfinished` or `--credentials keys.json` for the other stages |
| `golf-randomize show <manifest.json>` | Print a manifest's course, totals, music and required ROMs |

### Randomizer site

| Command | Description |
|---------|-------------|
| `golf-site [--host H] [--port P] [--reload]` | Run the randomizer website under uvicorn; see "Running the site" below |
| `golf-site-screenshot [pages] [-o dir] [--viewports ...] [--schemes ...] [--rom ID=PATH] [--generate] [--login NAME]` | Render site pages to PNG in headless Chromium at desktop and phone widths, light and dark, and with `--generate` the seed page the generate form lands on, with `--rom` loading the ROMs first so its download form is ready, and with `--login` signed in as a development user; needs `uv run playwright install chromium` |
| `golf-site-strings [--notes] [--dir DIR]` | List the site's unwritten strings (entries in `server/strings/` with empty text), grouped by file, with `--notes` printing what each one has to say |
| `new-page <title> [--slug SLUG]` | Create a Markdown page under `server/content/pages/` with explicit default frontmatter; refuses to overwrite an existing page |

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
| `golf-qr-credentials -o <keys.json>` | Write the seed ID, player IDs and secret MAC keys the `qr_credentials` patch reads |

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

## Running the site

```bash
uv run golf-site --reload
# then open http://127.0.0.1:8000/
```

The course rangefinder is available at `/rangefinder`. Its checked-in maps and metadata
can be regenerated after course data changes with:

```bash
uv run golf-render-web data/chr-ram.bin data/green-ram.bin courses/ server/static/rangefinder/
```

The ROM setup page hashes ROMs in the browser, which needs HTTPS or localhost. The site
reads its configuration from environment variables:

| Variable | Default | Meaning |
|----------|---------|---------|
| `GOLF_DATABASE` | `golf_site.db` | SQLite database path, created and migrated at startup |
| `GOLF_ROM_DIR` | the repository root | Directory holding the server's vanilla ROMs as `nes_open_us.nes` and `mario_open_jp.nes`; generating a seed needs the first |
| `GOLF_HOLES_DIR` | `courses/` | Hole store root |
| `GOLF_BASE_URL` | `http://127.0.0.1:8000` | Public base URL, also the OAuth redirect base |
| `GOLF_DISCORD_CLIENT_ID`, `GOLF_DISCORD_CLIENT_SECRET` | unset | Discord sign-in |
| `GOLF_SESSION_SECRET` | unset | Signs the session cookie |
| `GOLF_ADMIN_USERS` | unset | Discord ids, separated by commas or spaces, of the users the `/admin` pages admit; `dev:<name>` ids only with `GOLF_DEV_LOGIN` |
| `GOLF_DEV_LOGIN` | off | Development-only sign-in bypass (`1`, `true`, `yes` or `on`) |

For development, keep these in a `.env` file in the repository root (gitignored) and run
`uv run --env-file .env golf-site --reload`, or set `UV_ENV_FILE=.env` in your shell so
every `uv run` loads it.

Discord sign-in needs the client id, secret and session secret, and the Discord
application's OAuth2 redirect URI registered as `<GOLF_BASE_URL>/auth/callback`. Without a
session secret, sessions are signed with a secret that lasts until the process exits. With
`GOLF_DEV_LOGIN` on, `/auth/login?as=alice` signs in as the development user `alice`
(created on first use) without Discord; the site refuses to start with it on unless
`GOLF_BASE_URL` is a localhost address.

## Running tests

```bash
uv run pytest
```
