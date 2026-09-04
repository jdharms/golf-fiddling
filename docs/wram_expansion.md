# WRAM Expansion Plan

## Overview

The vanilla terrain decompression buffer in WRAM is only sized for 48 rows of terrain
(1,056 bytes = 22 columns x 48 rows), with the greens tile buffer packed immediately
after it. This was discovered while testing a real 60-row JP-derived hole (see
`docs/jp_extraction.md`, Open Question 2): the written ROM's compressed data is correct
- verified byte-for-byte by decompressing it back out of the written ROM - but at
runtime, decompressing a hole taller than 48 rows overflows the buffer, corrupting both
the terrain past row 48 and the adjacent greens buffer.

This document plans the two patches needed to fix this:

1. **Reclaim WRAM immediately before the vanilla terrain buffer.** That space
   currently holds long-term player stats (longest drive, average round score, etc.)
   and replay data - state that isn't needed during hole play.
2. **Move the terrain buffer "up" into the reclaimed space** so it (and the greens
   buffer after it) can grow to fit a full 60 rows.

## What We Know

- Terrain buffer: WRAM `$1186`, 1,056 bytes (22 x 48), decompressed once per hole in
  `LoadTerrainAndAttrs` via a `JSR DecompressTerrain` at PRG offset `$3DB87` (fixed bank).
  The target address of that JSR - `DecompressTerrain`'s actual entry point - is not
  yet known; needed for the next step (see Open Items).
- Greens buffer: immediately follows the terrain buffer, 576 bytes (24x24), written by
  `JSR DecompressGreen` (called just before the terrain bank switch in
  `LoadTerrainAndAttrs`, at PRG offset `$3DB65`). Its entry point isn't known either.
- Combined current buffer: `$1186` - `$17E6` (1,632 bytes total).
- Across all 90 dumped JP holes, 6 exceed 48 rows; max is 60 rows.
- Target combined buffer size for a 60-row max: `22 * 60 + 576 = 1,896` bytes - **264
  bytes** more than today.
- If we keep the buffer's *end* address fixed at `$17E6` (so nothing after it moves)
  and only extend backward, the new layout would be:
  - Terrain: `$107E` - `$15C6` (1,320 bytes)
  - Greens: `$15C6` - `$17E6` (576 bytes, unchanged)
- The region immediately before `$1186` holds long-term stats (longest drive, average
  round score, etc.) and replay data, per prior disassembly/annotation work. Exact
  start address and total reclaimable size are not yet documented anywhere in this
  repo - needed before we know how much headroom we actually have (264 bytes is the
  minimum; more would be worth having as margin for anything taller than 60 rows later).

## High-Level Plan

Reclaiming the stats/replay region has to happen in a way that's provably safe before
we let terrain decompression write into it - corrupting long-term save data instead of
transient hole state would be a much worse failure mode than the current bug. The plan
front-loads that verification:

1. Find and NOP out the routine(s) that *save* stats to this WRAM region.
2. Find and NOP out the routine(s) that *save* replay data to this WRAM region.
3. Change the code that *reads* stats from this region (stats/scorecard pages) to read
   literal `#$00` instead of the real memory.
4. Change the code that checks whether a replay is present to return early with "no
   replay present," instead of reading this region.
5. Add a sentinel value written to the candidate region in the SRAM init routine, then
   playtest: confirm the sentinel is never overwritten by anything other than our own
   future terrain-buffer code, and that nothing crashes with stats/replay reads and
   saves stubbed out per steps 1-4.
6. Once confirmed, the region is reclaimed.
7. Change the terrain decompression routine to decompress into the new, larger region.
8. Change every routine that *reads* decompressed terrain (rendering, scrolling,
   ball-lie/physics - see `docs/jp_extraction.md` for the ball-lie and windowing
   routines already touched by the attr-streaming patch) to read from the new region
   instead of `$1186`.

Steps 1-6 are entirely about proving the reclaimed region is safe to use, without yet
touching terrain/greens decompression at all - each is independently testable and
revertible. Steps 7-8 are the actual buffer relocation, and should only start once 1-6
are confirmed solid.

## Open Items (need disassembly to proceed)

- `DecompressTerrain`'s entry point (JSR target from `$3DB87`) and its full body - needed
  to find every hardcoded reference to `$1186` (or its component bytes) so all of them
  get patched consistently, not just the write.
- `DecompressGreen`'s entry point (JSR target from `$3DB65`) and body, for the same reason.
- Every other reader of the terrain/greens buffers (rendering, scrolling, ball-lie
  physics) - a "find all references to `$1186`" sweep in a debugger/disassembler is the
  fastest way to get a complete list, rather than tracing call graphs by hand.
- The stats-saving and replay-saving routines: locations and sizes, to plan the NOPs in
  steps 1-2.
- The stats-page read sites and the replay-presence check, for steps 3-4.
- Exact start address and size of the reclaimable region before `$1186`, to confirm 264
  bytes fits comfortably and see how much margin is available.

## Infrastructure Needed First

This effort will produce many small, individually-scoped patches (NOP a save routine,
redirect a read, etc.) that only make sense applied together as one unit. We don't yet
have a way to group multiple `ROMPatch` instances into one - `golf/core/patches/`
currently only has `BytePatch` for single byte-range replacements, and existing
multi-patch groups (`MULTI_BANK_PATCHES`, `ATTR_STREAMING_PATCHES`) are just plain
lists that callers iterate manually. Before writing the patches above, add a composite
patch class (e.g. `CompositePatch`) implementing the same `ROMPatch` interface
(`can_apply`/`is_applied`/`apply`) over a list of sub-patches, so a whole group -
stats NOPs, replay NOPs, buffer relocation, all of it - can be treated as a single
named patch wherever `ROMPatch` is expected (`AVAILABLE_PATCHES`, `PackedCourseWriter`,
etc.), the same way an individual `BytePatch` is today.
