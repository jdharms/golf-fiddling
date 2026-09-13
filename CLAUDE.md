# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A toolset for reverse engineering, editing and patching the NES Open Tournament Golf ROM:

- Course extraction, compression and writing, plus a Pygame course editor
- ROM research tooling (reads, disassembly, reference finding, a Mesen label file)
- Gameplay and presentation patches (seeded wind, practice swing, signpost art, music, ...)
- An end-of-round scorecard QR code with a 6502 port
- Groundwork for a randomizer website (`docs/randomizer.md`)

## Finding Things

- **Commands**: every CLI tool is indexed in `README.md`; each tool's `--help` is its
  full reference. Run them with `uv run <command>`.
- **Docs**: `docs/README.md` indexes the design and reverse-engineering notes.
- **Area-specific guidance** loads from nested files when you work there:
  `editor/CLAUDE.md` (editor architecture, adding editor tools) and `golf/qr/CLAUDE.md`
  (the QR oracle and its 6502 port).
- **Skills** in `.claude/skills/`:
  - `nes-open-golf-rom-layout` - memory map, pointer tables, bank layouts, data region
    boundaries. Use for ROM reading/writing and course data work.
  - `nes-open-golf-rom-peek` - **use whenever inspecting a ROM**: reading bytes,
    disassembling, tracing callers, looking for reclaimable space.
  - `nes-open-golf-label-conventions` - naming rules for the `.mlb` label file.

## Repository Layout

- `golf/` - shared library
  - `core/` - ROM reading/writing, both compression codecs, NES graphics, golfer sprites,
    signpost, audio, `asm6502.py` assembler, `rom_analysis.py`, `ips.py` (IPS patch files)
  - `golf/core/patches/` - ROM patches (`ROMPatch`, `BytePatch`, `CompositePatch`), and
    `PatchStack` for building a ROM from an ordered list of them (`docs/patch_stack.md`)
  - `formats/` - hole data model and JSON serialization (see `docs/course_data.md`)
  - `rendering/` - PIL rendering for static images
  - `qr/` - scorecard QR reference implementation and 6502 port
- `editor/` - the course editor
- `tools/` - CLI entry points: `data/` (regenerates checked-in `data/` files), `research/`,
  `art/`, `music/`, `qr/`; course and patch tools at the top level; `archive/` for retired
  one-off scripts (no entry points)
- `docs/`, `data/`, `courses/`, `web/` (course measurement app), `renders/` (render scripts and output)
- `tests/unit/`, `tests/integration/` - integration tests need `nes_open_us.nes` in the repo root

## Key Concepts

**ROM memory model**: NES ROMs use bank switching. The fixed bank ($C000-$FFFF, bank 15)
holds pointer tables and lookup data; switchable banks ($8000-$BFFF) hold compressed
course data. `RomReader` translates CPU addresses to PRG ROM offsets.

**Bank layout constraints**: the switchable banks hold tables and code as well as course data:

| Bank | Contents | Course Data Region | Available Space |
|------|----------|-------------------|-----------------|
| 0 | Japan terrain + tables | $8000-$A23D | 8,766 bytes |
| 1 | US terrain + tables | $8000-$A1E5 | 8,678 bytes |
| 2 | UK terrain + tables | $837F-$A553 | 8,661 bytes |
| 3 | All greens + code | $81C0-$A773 | 9,652 bytes |

Bank 2 has tables *before* terrain at $8000-$837E. Bank 3 has decompression tables at
$8000-$81BF and executable code at $A774-$BFFF. `CoursePatch` (`golf/core/patches/course.py`) enforces these
boundaries, and uses only banks 0 and 1 for terrain. Full details: the `nes-open-golf-rom-layout` skill.

**One course per ROM**: `golf-write` writes a single 18-hole course with `CoursePatch`,
packing terrain across banks 0 and 1 with a per-hole bank table at $A700 in bank 3. The
patch requires `multi_bank_lookup`, `course_mirrors` (every course slot plays course 1)
and `attr_streaming`, which `golf-write` applies first. See `docs/multi_bank_terrain.md`.

**Building ROMs**: `golf-patch` builds a ROM or IPS patch from a JSON recipe and/or inline
`-p` steps through `PatchStack`, which checks the base ROM hash, each patch's `requires`,
and that no two steps write the same byte. Patch types are registered in
`golf/core/patches/registry.py`; a new patch needs an entry there to be reachable from
recipes and the CLI. See `docs/patch_stack.md`.

**Two compression schemes**, easily confused:
- Course terrain/greens: RLE + dictionary, horizontal transitions, vertical fill
  (`golf/core/decompressor.py`, `compressor.py`; `golf/core/compression.md`). Terrain
  tables live in the fixed bank, greens tables in bank 3.
- *Everything the PPU displays* - pattern data, nametables, attribute tables - uses a
  separate stream codec (`$D4C3`, `golf/core/graphics_codec.py`). The cartridge has no CHR
  ROM, so about a third of the PRG is data in this format. See `docs/course_intro_scene.md`.

**Inspecting the ROM**: use `golf-rom-peek` (logic in `golf/core/rom_analysis.py`) and its
skill rather than one-off Python. The skill documents three ways a naive byte search or
linear disassembly silently lies about this ROM; a "no references found" is never proof
an address is dead.

**Writing new 6502 code**: use `golf/core/asm6502.py` (two-pass, labels, local labels,
`.org/.byte/.word/.res/.align`, branch-range checks) rather than hand-assembling byte
arrays. Existing small patches in `golf/core/patches/` predate it and stay as they are.

## Development Notes

### Adding CLI tools

1. Put the tool in the matching `tools/` subpackage (or the top level if none fits) with a
   `main()` function. Keep it a thin CLI: logic that tests or other tools would import
   belongs in `golf/`.
2. Add an entry point under the matching comment group in `[project.scripts]` in
   `pyproject.toml`, then `uv sync`.
3. Add it to the command index in `README.md`.

### Keeping the repo navigable

The indexes and pointers above only stay useful if changes keep them current:

- **New or renamed doc**: add it to `docs/README.md`.
- **Moving or renaming a file**: grep for the old path across the CLAUDE.md files,
  `docs/` and `.claude/skills/`, and fix every reference - tests catch backticked paths in
  the agent-facing docs, but not prose or the individual docs under `docs/`.
- **Rules that only apply to one area** go in that area's nested CLAUDE.md (create one if
  needed), keeping this file about repo-wide concerns.
- **Skills are versioned in `.claude/skills/`**: when you learn something a skill should
  say, or find a statement in one that is no longer true, edit the skill.

`tests/meta/` holds tests of the repository itself, which enforce the mechanical parts:

- `test_cli_index.py` - every entry point is in the `README.md` command index
- `test_entry_points.py` - every entry point's module and function resolve
- `test_docs_index.py` - every doc is in `docs/README.md`, and its links resolve
- `test_referenced_paths.py` - backticked paths in the CLAUDE.md files, `README.md`,
  `docs/README.md` and the skills exist
- `test_tools_layering.py` - nothing imports from `tools/`, and `tools/archive/` has no entry points
- `test_import_order.py` - every `golf` module imports cleanly in a fresh interpreter

### JSON inspection

When inspecting JSON files in `courses/` and `data/`, prefer `jq` over `python -c` one-liners.

## Testing

Tests must be executed and must pass after all changes. There are no "ok failures". Ever.

```bash
uv run pytest                                   # everything, with coverage
uv run pytest tests/unit/                       # unit tests only
uv run pytest tests/integration/                # integration tests only
uv run pytest tests/meta/                       # tests of the repo's docs, indexes and layering
uv run pytest tests/unit/test_vertical_fill.py  # one file
```

Fixtures live in `tests/fixtures/` and `tests/conftest.py`: real compression tables from
`data/tables/compression_tables.json`, minimal mock tables, real holes from `courses/japan/`,
and hand-crafted terrain/greens.

## Claude Code Preferences

- **Commit messages**: Please do not author commit messages. I prefer to write them myself to capture the specific context and rationale.
- **Updating documentation**: When planning changes that would contradict or obsolete information in this CLAUDE.md file, a nested one, a doc under `docs/`, or a skill, include a step in your plan to update it accordingly. This ensures documentation stays current with the codebase; the tests in `tests/meta/` can only check that references exist, not that what they say is still true.
