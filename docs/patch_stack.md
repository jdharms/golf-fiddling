# Patch Stacks

> **Note**: This document was written by Claude based on design and ideas by jdharms.

A finished ROM is a vanilla ROM plus an ordered list of patches: the code a course needs,
the course itself, and the gameplay, quality of life, and "fit and finish"
patches on top. `PatchStack` (`golf/core/patches/stack.py`) is that list,
and builds it in memory.

```python
from golf.core.patches import (
    ATTR_STREAMING_PATCH, COURSE_MIRRORS_PATCH, MULTI_BANK_CODE_PATCH,
    CoursePatch, PatchStack, seeded_wind_patch,
)

course = CoursePatch(holes)                  # 18 HoleData
stack = PatchStack([
    MULTI_BANK_CODE_PATCH,
    COURSE_MIRRORS_PATCH,
    ATTR_STREAMING_PATCH,
    course,
    seeded_wind_patch("my seed"),
])

vanilla = Path("nes_open_us.nes").read_bytes()
build = stack.build(vanilla)                 # StackBuild: .rom and .regions
patch = stack.ips(vanilla)                   # the same build, as an IPS patch
```

Steps are built `ROMPatch` objects, and step names must be unique. A stack is assembled in
Python, or from a [recipe](#recipes) with [`golf-patch`](#golf-patch).

## What a build checks

`build(base)` copies the base, applies each step in order, and raises `StackError` (a
`PatchError`) on the first problem:

- **The base ROM.** By default the base must hash to `rom_utils.US_ROM_SHA1`, the vanilla US
  ROM file including its iNES header. `PatchStack(steps, base_sha1=None)` builds on any
  base, such as a ROM that already carries some of the patches.
- **Requirements.** Before a step is applied, every patch in its `requires` must already be
  applied, by an earlier step or in the base. The error says whether a missing requirement
  is `not in the stack` or `listed after it`. The stack never adds or reorders steps.
- **Overlaps.** Every write is attributed to the step that makes it. A step writing a byte
  that an earlier step wrote is an error, even when the value is the same, and the error
  names both steps and the address. A sub-patch shared by two steps is not an overlap:
  `BytePatch` writes nothing when it is already applied.
- **The steps themselves.** A step whose `apply` raises `PatchError` is reported with its
  name.

Overlap tracking matters most for the writes that do not check what they replace: course
data and scorecard totals in `CoursePatch`, and the scorecard QR image in bank 2.

`StackBuild.regions` maps each step name to the `[start, end)` PRG offset ranges it wrote.

## Requirements and `can_apply`

`ROMPatch.requires` lists patches a patch depends on but does not write. It is separate from
`can_apply`, which checks only the bytes a patch replaces. `apply` on `CompositePatch`,
`CoursePatch` and `ScorecardQrPatch` refuses to run while a requirement is missing, so the
rule holds outside a stack too. The [patch types](#patch-types) table lists each patch's
requirements.

## Writes and IPS output

The build runs on `RomWriter.from_bytes`. Every `RomWriter` write method goes through
`write_prg`, which is how the stack sees every write.

`stack.ips(base)` is `golf.core.ips.diff(base, stack.build(base).rom)`. IPS offsets count
from the start of the file, so the diff covers the whole `.nes` file, iNES header included.
`diff` merges changes separated by fewer than 5 unchanged bytes, writes runs of 14 or more
identical bytes as RLE records, splits records at 65,535 bytes, and never starts a record at
offset `0x454F46` (which reads as the `EOF` marker). The same inputs always produce the same
patch. `ips.apply` reads RLE records and the truncation extension.

## Recipes

A recipe is a stack written as JSON (`golf/core/patches/recipe.py`):

```json
{
  "steps": [
    {"patch": "wram_expansion"},
    {"patch": "multi_bank_lookup"},
    {"patch": "course_mirrors"},
    {"patch": "attr_streaming"},
    {"patch": "course", "course": "courses/jp/jp_uk"},
    {"patch": "menu_trim", "words": "RANDO GOLF 0001"},
    {"patch": "mercy_tap_in", "mercy_point": 9},
    {"patch": "seeded_wind", "seed": "abc123"},
    {"patch": "practice_swing"},
    {"patch": "scorecard_qr"}
  ]
}
```

- `patch` names a patch type in the registry (`golf/core/patches/registry.py`). The other
  keys are its parameters, checked against the type's parameter dataclass: unknown or
  missing parameters and values of the wrong type are errors, and integers may also be
  written as strings in any base Python reads (`"0x78"`). A list of strings may also be
  written as one whitespace-separated string (`"clubs": "1W 3W PW"`), which is how `-p`
  passes one.
- Paths are relative to the recipe file.
- `base_sha1` is optional. Omitted means the vanilla US ROM; `null` means any base.
- Patch types take concrete values and draw nothing at random, so a recipe and a base ROM
  always build the same ROM.
- `qr_credentials` reads its credentials from a separate file written by
  `golf-qr-credentials`, because the MAC keys are secret; a recipe only names the file.

In Python: `Recipe.load(path)`, `Recipe.from_dict(data, base_dir)`, `recipe.stack(base)`,
`recipe.build_steps(base)` (each patch with its parameters and report),
`recipe.to_dict(base_dir)` and `recipe.save(path)`.

## golf-patch

```bash
golf-patch nes_open_us.nes recipe.json -o out.nes
golf-patch nes_open_us.nes recipe.json --ips out.ips
golf-patch nes_open_us.nes -p multi_bank_lookup -p course_mirrors -p attr_streaming \
    -p course:course=courses/japan -p seeded_wind:seed=abc -o out.nes
golf-patch --list
```

- `-p ID[:key=value,...]` adds a step after the recipe's steps, parsed like a recipe step
  with paths relative to the current directory. A value containing a comma needs a recipe.
- `-o` writes the ROM (default `<rom>.patched.nes` unless `--ips` is given); `--ips` writes
  an IPS patch from the base to the build; `--validate-only` builds in memory and writes
  nothing.
- `--save-recipe PATH` writes the combined steps as a recipe.
- `--any-base` builds on a base other than the vanilla US ROM, such as the output of
  `golf-write`.
- `-v` adds each patch type's report: bank usage and scorecard totals for `course`, the per-hole pin and wind
  forecast for `seeded_wind`, track and space usage for `music_import`, new tiles and
  import notes for `signpost_random_banner`, the image location for `scorecard_qr`, the
  seed ID and player IDs for `qr_credentials` (never the keys), and the new-save defaults
  for `sram_defaults`.
- `--list` prints every patch type and its parameters.

`golf-write` remains the tool for writing a course from the editor: it applies the course's
three requirements and the `course` step.

## Patch types

| Patch | Parameters | Requires |
|---|---|---|
| `wram_expansion` | | |
| `multi_bank_lookup` | | |
| `course_mirrors` | | |
| `attr_streaming` | | |
| `course` | `course` (a directory) or `holes` (18 files); also writes the scorecard totals | `multi_bank_lookup`, `course_mirrors`, `attr_streaming` |
| `menu_trim` | `words` (default `OPEN GOLF RANDO`; three words of 4-6 renderable characters for the header of the main, player count and course select menus) | |
| `scorecard_course_name` | `name` (default `RANDOM`; A-Z, 0-9 and space, at most 13), `title` (optional, replaces `18H STROKE PLAY`; at most 26) | `course_mirrors` |
| `remove_course_banner` | | |
| `signpost_random_banner` | `art`, `banner` (default `us`), `hole` (default 1) | |
| `mercy_tap_in` | `mercy_point`, `mercy_result` (default `mercy_point` + 1) | |
| `seeded_wind` | `seed` | `course_mirrors` |
| `practice_swing` | `hold_frames` (default `0x78`) | |
| `scorecard_qr` | none; the seed ID, player ID and MAC key placeholders are left at the fill | `course_mirrors` |
| `qr_credentials` | `credentials` (a `golf-qr-credentials` file); fills the placeholders, expecting the fill | `scorecard_qr` |
| `qr_disable` | none; reverts the round-end splice for a guest ROM, expecting the splice `scorecard_qr` wrote | |
| `course_theme` | `music` (`$02` US, `$03` Japan or `$04` UK); plays that US ROM theme on every course | |
| `music_import` | `dump`, `track` (optional; one dump music ID, imported as `$03` and made every course's theme), `transpose_adjust` (default from the dump) | |
| `sram_defaults` | `player_name` (A-Z, `.` and space, at most 10), `clubs` (up to 14 of `1W`-`4W`, `1I`-`9I`, `PW`, `SW`, `PT`; the putter is added), `bgm` (default true), `sram_magic` (default `0x3553`, "5S"; neither byte `$00` or `$FF`). Only a save being initialised gets them | |
| `putting_practice` | (experimental) | |

`course_theme` and `music_import` with a `track` both rewrite `CourseBgmTable` at `$DA14`,
so a stack holds one or the other: `course_theme` for a theme already in the ROM,
`music_import` for one from another ROM's dump.

`remove_course_banner` and `signpost_random_banner` both rewrite the banner selection at
bank 12 `$AC5D`, so a stack with both fails: whichever comes second finds the other's bytes
where it expects vanilla ones.

`qr_credentials` and `qr_disable` rewrite bytes `scorecard_qr` wrote, so neither can share a
stack with it. They are finishing patches: build the unfinished ROM with `scorecard_qr`,
then run a second stack with `base_sha1=None` (`--any-base`) on that ROM. See the two-stage
build in `randomizer_devplan.md`.

```bash
golf-patch nes_open_us.nes recipe.json -o unfinished.nes
golf-patch unfinished.nes --any-base -p qr_credentials:credentials=keys.json -o finished.nes
golf-patch unfinished.nes --any-base -p qr_disable -o guest.nes
```

## Testing

```bash
uv run pytest tests/unit/test_patch_stack.py tests/unit/test_patch_recipe.py tests/unit/test_ips.py tests/unit/test_rom_writer.py
uv run pytest tests/integration/test_patch_stack_rom.py tests/integration/test_patch_recipe_rom.py
```

`tests/integration/test_patch_stack_rom.py` builds a stack of every patch that has no art or
file inputs beyond a music dump - WRAM expansion, the course code and a Mario Open course,
menu trim, banner removal, mercy tap-in, seeded wind, practice swing, the scorecard QR,
SRAM defaults and music import - on the vanilla ROM, then finishes that ROM with
`qr_credentials` and, separately, with `qr_disable`.
