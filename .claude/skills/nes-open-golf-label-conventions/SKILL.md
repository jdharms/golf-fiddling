---
name: nes-open-golf-label-conventions
description: >
  Naming conventions for entries in the NES Open Tournament Golf Mesen .mlb
  label file (golf/core/mlb_labels.py, tools/research/labels.py "golf-labels",
  tools/research/rom_peek.py "golf-rom-peek"). Use whenever adding, renaming, or
  reviewing a label in that file - via the golf-labels CLI, by hand, or when
  proposing a name for a ROM address during reverse-engineering. Covers the
  three-tier PRG code label scheme (auto-generated jump-target stubs, "cheap
  local" semi-auto labels, full PascalCase names for higher-level routines)
  and the RAM/data label pattern ([Maybe][Purpose][MechanicalType]). These
  conventions are borrowed from an external NES hacker's label-file-to-
  disassembly tool, so they are not derivable from this repo's code alone.
---

# NES Open Golf label conventions

Match these when choosing or reviewing a name in the project's `.mlb` label
file. They come from an external disassembly tool the user pairs with this
file, so a label that "looks wrong" by normal naming standards may in fact be
correct by this scheme - check here before renaming it.

## PRG code labels: three tiers

1. **Auto-generated stub** - `L<bank>_<addr>` (bank 0-9 as a digit, 10-15 as
   A-F; the fixed bank drops the bank character entirely, e.g. `LD5ED`). This
   is the *correct, final* name for a jump target that is purely internal
   control flow within a routine (a loop back-edge, a short conditional
   skip). Do not rename these away just because they look unfinished.

2. **Semi-auto / "cheap local" label** - the auto stub with a descriptive
   suffix appended, e.g. `LD_AD5D_PutterOverride`, `LC_8081_TitleScreenLoop`.
   Equivalent to a CA65 cheap local label: the address prefix keeps the name
   globally unique while the suffix (e.g. `Loop`, `Initialization`,
   `WaitForVblank`) is free to repeat across many unrelated routines. Use
   this tier for a control-flow point inside one routine that deserves a
   description but is not an entry point called from elsewhere.

3. **Full name** - the address prefix is removed entirely and the label gets
   a unique PascalCase name, preferring an active-tense verb phrase:
   `ReadController`, `LoadTotalDriveDistance`, `ApplyScrollSettings`,
   `SetChrBank0`. Use this tier for anything called from elsewhere, or that
   represents one complete unit of computation or I/O rather than being
   internal control flow.

Unnamed jump targets (no label at all) should be rare - only for extremely
tight, close-by control-flow jumps. When in doubt between tiers 1 and 2,
prefer tier 1 (plain stub) until the routine's structure is well understood.

## RAM / data labels

Pattern: `[Maybe]<Purpose><MechanicalType>`

- `Maybe` (optional prefix) is the *only* confidence marker in this scheme -
  it means "not convinced this is correct." Don't invent other confidence
  markers (no `?`, `_TODO`, `Unconfirmed`, etc. in the name itself; an
  uncertain comment is fine in addition).
- `Purpose` - semantic name for what the value represents, e.g. `WindSpeed`,
  `CurrentPlayerIndex`, `BallLie`.
- `MechanicalType` - suffix describing the storage shape: `Table`, `Ptr`,
  `Count`, `X`/`Y`, `BCD`, `Flag`, `State`, `Data`, etc.

Examples: `WindSpeedAnchor`, `CompressionLookbackPtr`, `MaybeWindDelayCounter`,
`DistanceOnesBCD`, `ScrollLimitTable`.

## Applying this via golf-labels

`golf-labels add <type> <address> <name>` writes to the sidecar file by
default (see the tool's own docstring for the base/sidecar model). When
proposing a name for that command:

- For `prg` addresses that are jump targets: default to leaving the
  auto-generated stub name as-is unless it's clearly tier 2 or 3.
- Comments are sparse in this file (~5% of entries) and informal - a short
  uncertain note (e.g. "maybe MusicPosition?") is consistent with existing
  style; full sentences with terminal punctuation are not the norm.
