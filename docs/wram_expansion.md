# WRAM Expansion Plan

## Overview

The vanilla terrain decompression buffer in WRAM is only sized for 48 rows of terrain
(1,056 bytes = 22 columns x 48 rows), with the greens tile buffer packed immediately
after it. This was discovered while testing a real 60-row JP-derived hole (see
`docs/jp_extraction.md`, Open Question 2): the written ROM's compressed data is correct
- verified byte-for-byte by decompressing it back out of the written ROM - but at
runtime, decompressing a hole taller than 48 rows overflows the buffer, corrupting both
the terrain past row 48 and the adjacent greens buffer.

"WRAM" here means RAM the cartridge provides (as opposed to the console's own
internal RAM) - in practice this is battery-backed SRAM at CPU `$6000`-`$7FFF`, but
that's an implementation detail that doesn't affect this plan, so addresses below are
given as offsets from `$6000` (e.g. "`$1186`" means CPU `$7186`) matching how they're
referenced in-game via the `SramPtr` pointer.

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
- The region immediately before `$1186` is mapped out back to `$0F98`, per prior
  disassembly/annotation work:
  - `$0F98`-`$0F9B` (4 bytes): user settings (BGM on/off, swing speed default, putt
    swing speed default, ball spin default) - **keep as-is**, not part of the
    reclaimable region.
  - `$0F9C`-`$1185` (490 bytes): long-term stats and replay data - the reclaimable
    region. Fully mapped out:

    | Address | Name | Size |
    |---|---|---|
    | `$0F9C` | `AceReplayHeaders` | 5 |
    | `$0FA1` | `AlbaReplayHeaders` | 5 |
    | `$0FA6` | `EagleReplayHeaders` | 5 |
    | `$0FAB` | `BirdieReplayHeaders` | 5 |
    | `$0FB0` | `AceReplayData` | 35 |
    | `$0FD3` | `AlbaReplayData` | 60 |
    | `$100F` | `EagleReplayData` | 85 |
    | `$1064` | `BirdieReplayData` | 110 |
    | `$10D2` | `StrokePlayStats` | 24 |
    | `$10EA` | `MatchPlayStats` | 20 |
    | `$10FE` | `StrokeTournamentStats` | 24 |
    | `$1116` | `MatchPlayTournamentStats` | 32 |
    | `$1136` | `StrokeTournamentStats18H` | 40 |
    | `$115E` | `StrokeTournamentStats36H` | 40 |

    Each row's address plus size equals the next row's address, ending exactly at
    `$1186`.
- 490 bytes reclaimable comfortably covers the 264-byte minimum need for 60-row
  terrain, leaving **226 bytes** of margin for anything taller than 60 rows later.
- `L8_9B43` (CPU `$9B43`, bank `$08`), the routine hit when a birdie is recorded,
  appends a packed `($065D:$065E)` byte to the appropriate `*ReplayHeaders` 5-slot
  FIFO (shifting out the oldest entry if full) and copies a corresponding block from
  a live WRAM scratch area into the matching `*ReplayData` region. The
  `ReplayDestPtrLoTable`/`ReplayDestPtrHiTable` pointer tables (bytes `9C 6F AB 6F A6
  6F A1 6F B0 6F 64 70 0F 70 D3 6F`) confirm both the header write and the data write
  land inside this reclaimable region - the whole routine is in scope for the
  step-1/2 NOP work, not just the byte the first breakpoint hit landed on.
- `$AD43` (bank `$02`) updates the driving-distance stats shared by `StrokePlayStats`
  (X=0) and `StrokeTournamentStats` (X=`$2C`, the two 24-byte blocks with an identical
  layout): the running distance total (+2..+5), drive count (+6), and longest-drive
  record (+10/+11). Gated on not-two-player-mode, game mode 0-3, driver selected,
  first stroke of the hole, and ball lie 0 or 6 - fires per-shot on a qualifying tee
  shot, not just at round end (no `Par` check anywhere, despite it only having been
  observed triggering on a par 5 so far). `$AD43` itself opens with an unconditional
  `JSR $ADC7` unrelated to this gating, so the NOP patches at `$AD46` instead of the
  routine's own entry point, preserving that call.
- A whole-ROM scan for absolute/absolute-indexed `STA`/`INC`/`DEC` instructions
  targeting any address in `$0F9C`-`$1185` turned up 23 hits beyond the two routines
  above. 21 were scan artifacts (opcode-shaped byte sequences inside compressed
  course data or other lookup tables, confirmed unreachable - no `JSR`/`JMP` anywhere
  targets them). The remaining 2 (`$B061`/`$B06C`, bank `$09`) are real, uncalled-from-
  anywhere-found code: two unconditional loops zeroing all six stats blocks in their
  entirety (`$70D2`-`$7185`, 180 bytes), no gating at all - the shape of SRAM
  initialization, not a per-play save. Not treated as a threat to the reclaimed
  region (a zero-fill at init time can't corrupt an in-progress hole's terrain the
  way a per-shot/per-round save could) and left unpatched; if this assumption ever
  needs re-checking, a live breakpoint on PC `$B061` during new-game setup would
  confirm when it actually fires.

## Known Free Space

Unused (`$FF`-filled) regions found in the fixed bank, useful for relocating
tables or code that need more room than their current spot allows. Recorded
here as they're found so remaining capacity stays visible at a glance.

### PRG `$3CA40`-`$3CAFF` (CPU `$CA40`-`$CAFF`, 192 bytes)

All `$FF` in vanilla ROM. Preceded by `$55`-filled bytes (possibly audio
data, unconfirmed); followed immediately at `$CB00` by a half-square-wave
table.

- **Carved off - `$CA40`-`$CA72` (51 bytes):** relocated
  `ViewOffsetToAddrLow` / `ViewOffsetToAddrHigh` / `ViewOffsetToAttrIndex`
  tables (read by the vertical-scroll windowing routine at `LE451`,
  CPU `$E451`), expanded from the vanilla 10 entries to 17 to support
  scrolling through 60-row terrain.
  - `ViewOffsetToAddrLow`: `$CA40`-`$CA50`
  - `ViewOffsetToAddrHigh`: `$CA51`-`$CA61`
  - `ViewOffsetToAttrIndex`: `$CA62`-`$CA72`
- **Carved off - `$CA73`-`$CA92` (32 bytes):** relocated
  `ScrollThresholdLow` / `ScrollThresholdHigh` tables (read by the routine
  at CPU `$8F73`, bank `$0D`, which scans `BallY` against these thresholds
  to compute `ViewVerticalOffset`), expanded from the vanilla 9 entries to
  16 to support scrolling through 60-row terrain. Confirmed via debugger
  sweep that CPU `$8F81` and `$8F86` are the only two readers.
  - `ScrollThresholdLow`: `$CA73`-`$CA82`
  - `ScrollThresholdHigh`: `$CA83`-`$CA92`
- **Remaining - `$CA93`-`$CAFF` (109 bytes):** unused.

### PRG `$3E4F9`-`$3E516` (CPU `$E4F9`-`$E516`, 30 bytes) - vacated, not yet reclaimed

Former location of the vanilla `ViewOffsetToAddrLow`/`ViewOffsetToAddrHigh`/
`ViewOffsetToAttrIndex` tables, relocated to `$CA40` above (see
`wram_expansion_view_offset_*` patches in
`golf/core/patches/wram_expansion/view_offset_tables.py`). Confirmed via
breakpoint testing (full playthrough of a long hole, including deliberate
camera panning) that nothing reads this region once those patches are
applied - every known caller has been redirected to `$CA40`.

Unlike the region above, this one still holds its original (now-dead) table
bytes rather than `$FF` filler - the relocation patch never overwrote the
old location, only the code that pointed at it. Available for reuse by a
future patch if needed; would need a `BytePatch` (or extending
`view_offset_tables.py`) whose `original` matches whatever the old table
bytes still are at that point in the patch chain.

### PRG `$34F91`-`$34FA2` (CPU `$8F91`-`$8FA2`, bank `$0D`, 18 bytes) - vacated, not yet reclaimed

Former location of the vanilla `ScrollThresholdLow`/`ScrollThresholdHigh`
tables, relocated to `$CA73` above (see `wram_expansion_scroll_threshold_*`
patches in `golf/core/patches/wram_expansion/scroll_threshold_tables.py`).
Confirmed via debugger sweep that CPU `$8F81` and `$8F86` were the only
readers, both now redirected to `$CA73`.

Unlike the two fixed-bank regions above, this one is in **switchable** bank
`$0D` ($8000-$BFFF), not the always-mapped fixed bank - so it's only usable
by code that executes while bank `$0D` is paged in (which is guaranteed for
the routine at CPU `$8F73`, since that's the bank it lives in, but would need
checking for any other prospective user). Like the `$E4F9` region, it still
holds its original (now-dead) table bytes rather than `$FF` filler.

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
- The stats-page read sites and the replay-presence check, for steps 3-4. Steps 1-2
  (the save routines) are done - see `L8_9B43` and `$AD43` above, both patched in
  `golf/core/patches/wram_expansion/`.

Patches are grouped via `CompositePatch` (`golf/core/patches/composite.py`), which
implements the same `ROMPatch` interface (`can_apply`/`is_applied`/`apply`) over a
list of sub-patches - `WRAM_EXPANSION_PATCH` in
`golf/core/patches/wram_expansion/__init__.py` is one, growing as each step of this
plan lands.
