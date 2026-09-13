# Patch Stacks

> **Note**: This document was written by Claude based on design and ideas by jdharms.

A finished ROM is a vanilla ROM plus an ordered list of patches: the code a course needs,
the course itself, and the gameplay patches on top. `PatchStack`
(`golf/core/patches/stack.py`) is that list, and builds it in memory.

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

Steps are built `ROMPatch` objects, so a stack is assembled in Python. Step names must be
unique.

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
data in `CoursePatch`, and the scorecard QR image in bank 2.

`StackBuild.regions` maps each step name to the `[start, end)` PRG offset ranges it wrote.

## Requirements and `can_apply`

`ROMPatch.requires` lists patches a patch depends on but does not write. It is separate from
`can_apply`, which checks only the bytes a patch replaces. `apply` on `CompositePatch`,
`CoursePatch` and `ScorecardQrPatch` refuses to run while a requirement is missing, so the
rule holds outside a stack too.

| Patch | Requires |
|---|---|
| `CoursePatch` | `multi_bank_lookup`, `course_mirrors`, `attr_streaming` |
| `seeded_wind` | `course_mirrors` |
| `scorecard_qr` | `course_mirrors` |

## Writes and IPS output

The build runs on `RomWriter.from_bytes`. Every `RomWriter` write method goes through
`write_prg`, which is how the stack sees every write.

`stack.ips(base)` is `golf.core.ips.diff(base, stack.build(base).rom)`. IPS offsets count
from the start of the file, so the diff covers the whole `.nes` file, iNES header included.
`diff` merges changes separated by fewer than 5 unchanged bytes, writes runs of 14 or more
identical bytes as RLE records, splits records at 65,535 bytes, and never starts a record at
offset `0x454F46` (which reads as the `EOF` marker). The same inputs always produce the same
patch. `ips.apply` reads RLE records and the truncation extension.

## Testing

```bash
uv run pytest tests/unit/test_patch_stack.py tests/unit/test_ips.py tests/unit/test_rom_writer.py
uv run pytest tests/integration/test_patch_stack_rom.py
```

`tests/integration/test_patch_stack_rom.py` builds a stack of every patch that has no art or
file inputs beyond a music dump - WRAM expansion, the course code and a Mario Open course,
menu trim, banner removal, mercy tap-in, seeded wind, practice swing, the scorecard QR and
music import - on the vanilla ROM.
