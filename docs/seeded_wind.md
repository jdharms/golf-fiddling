# Seeded Wind Patch

> **Note**: This document was written by Claude based on reverse-engineering requested by jdharms. Debugger values quoted below were captured by jdharms in Mesen on the vanilla US ROM.

Makes every hole's pin position and wind sequence a pure function of a build-time seed, so all players of a given ROM face the same conditions on the same swing of the same hole. Implemented in `golf/core/patches/seeded_wind.py`; applied with `golf-patch-seeded-wind`.

## Vanilla RNG

`LSFR_RNG_ALGO` (fixed bank `$D29C`, PRG `0x3D29C`) is a 16-bit shift-register generator on `RngState` (`$42` low, `$43` high). Each call runs 11 shift steps and returns the new `$42` in A. X is preserved. Nothing in the NMI handler advances it; it only moves when game logic calls it. All 16 call sites:

| Site | Purpose |
|---|---|
| fixed `$DB15` | Pin position: result AND 3 selects one of the hole's 4 flag offsets (`InitHole`) |
| fixed `$DBA0` | Wind direction anchor: result AND $F0 (`InitHole`) |
| fixed `$DBA8` | Wind speed anchor: result AND $0F, values 11-15 become 3-7 (`InitHole`) |
| fixed `$DA2F` | Per-swing speed jitter (`WindAdjustmentRoutine`) |
| fixed `$DA76` | Tournament long-drive / nearest-pin hole picker (game start) |
| bank 13 `$ADDD` | Putt aim noise (putter selected, BallLie != 6) |
| bank 13 `$AE55` | Rough / bunker power variance |
| bank 13 `$B357` | Water skip check |
| bank 12 `$8089`, `$93F0`, `$B8C8` | Title screen loop, menus |
| bank 9 `$936A` | Replay / animation |
| bank 3 `$A8AA` | Demo (restores its own state from `$067D`) |
| bank 2 `$BBE0`, `$BBEC`, `$BCCE` | Scorecard / tournament setup |

## Wind computation

`WindAdjustmentRoutine` (`$DA25`) returns immediately when bit 7 of `$04F6` is set. That is the practice-mode "set your own wind" flag; bank 13 `$89C2` / `$89CF` implement the manual adjustment under it. Bit 7 of `$04F7` is the replay-playback flag, set by `InitializeHoleReplay`.

Otherwise: `WindDirection` = `WindDirectionAnchor`; one RNG draw; low 3 bits map to a jitter:

| rng & 7 | 0 | 1 | 2 | 3 | 4 | 5 | 6 | 7 |
|---|---|---|---|---|---|---|---|---|
| jitter | 0 | 0 | -1 | 0 | 0 | +1 | +1 | +2 |

Speed = anchor + jitter. If negative, direction is flipped (EOR $80) and speed becomes 1. While speed >= 10, subtract 5. Direction never jitters.

The routine is called from bank 13 `$824F` (normal shot setup) and `$8D28` (a save/restore routine at `$8CBE` that re-derives a player's wind from a stored RNG snapshot after restoring it into `RngState`).

## Per-player wind slots

Bank 13 already isolates each player's wind stream from the other player's turn:

1. **Hole start** (`$8157` loop): after `InitHole`, `RngState` is copied into `$0525,X` / `$0527,X` for X = 1 and 0. No draw happens inside the loop, so both slots start identical.
2. **Shot setup** (`$823A`): the current player's slot is loaded into `RngState` and snapshotted to `$04FB/$04FC`; `LDA17` (replay recording far call) runs; `WindAdjustmentRoutine` draws once.
3. **Shot end** (`$82BE`): `RngState` is written back into the slot.

The unfairness is the in-shot draws (putt noise, rough/bunker variance, water skip) advancing `RngState` between steps 2 and 3, so the next jitter depends on what the previous shot hit. The hole anchor is the other leak: `InitHole` derives it from whatever the global RNG state is at hole start.

Confirmed in Mesen (2-player stroke play, vanilla ROM):

| Break | `$42 $43` | Notes |
|---|---|---|
| `0x34192` hole start | slots `$0525..$0528` = `88 88 15 15` | both players seeded identically |
| `0x34252` P0 swing 1 | `74 44` | wind speed 8 |
| `0x342BE` P0 shot end | `74 44` | clean fairway shot, no in-shot draw |
| `0x34252` P1 swing 1 | `74 44` | same wind as P0 |
| `0x34252` P1 swing 2 | `CB A7` | one step from `7444` |
| `0x342BE` P1 shot end | `B7 58` | in-shot draw happened; stream polluted |
| `0x34252` P1 swing 3 | `23 BC` | derived from the polluted state |
| `0x34252` P0 swing 2 | `CB A7` | same as P1 swing 2, because P0's swing 1 was clean |

## The patch

### 1. `InitHole` seeding (fixed bank, byte-neutral)

The 10 bytes at `$DB0B` (PRG `0x3DB0B`) save `RngState` to `$04F9/$04FA`. Every consumer of that snapshot (`$8132`, `$8D09`, `$8D5C`, bank 9 replay playback) copies it back into `RngState` immediately before calling `InitHole`, and `InitHole` now overwrites `RngState` from the seed table, so the save is dead. It becomes:

```
LDA $DFE7,X   ; X = doubled global hole index, set at $DAEE
STA $42
LDA $DFE8,X
STA $43
```

Pin position, both anchors and both player slots then derive from the seed, with vanilla distributions intact. The bank 3 replay header at `$A784` still copies the stale `$04F9/$04FA`; playback re-runs `InitHole`, which ignores it.

### 2. Slot write-back moved (bank 13)

- `$82C0` (PRG `0x342C0`): the 10 bytes after `LDX CurrentPlayerIndex` become NOPs. `LDX` stays because `$82D1` uses X.
- `$BFAF` (PRG `0x37FAF`): 16-byte trampoline in bank 13 tail padding, directly after the mercy tap-in routines (`$BF83-$BFAE`) and clear of the MMC1 reset stub at `$BFF3`:

```
LDX CurrentPlayerIndex
JSR WindAdjustmentRoutine
LDA $42 ; STA $0525,X
LDA $43 ; STA $0527,X
RTS
```

- `$824F` (PRG `0x3424F`): `JSR WindAdjustmentRoutine` becomes `JSR $BFAF`.

The slot now advances exactly one LFSR step per swing. In-shot draws still use the live RNG, which is discarded and reloaded from the slot at the next shot setup. The `$8D28` resume path restores the shot-start snapshot and re-derives the same wind; it never touches the slots. The trampoline reloads X itself rather than trusting the replay-recording far call at `$824C` to preserve it. Under practice mode the wind routine returns without drawing and the trampoline writes the unchanged state back, a no-op.

### 3. Seed table

Two bytes per hole (`$42` then `$43`) at `$DFE7` (PRG `0x3DFE7`), the course-3 block of `GreenFlagXTable` (72 bytes, 36 holes). Under `COURSE3_MIRROR_PATCH` the course-3 offset is 0, so indexes 36-53 are never read. `PackedCourseWriter` only writes metadata for the holes it is given (0-17 or 0-35), so the seed table survives `golf-write` in either order.

Seeds come from `derive_hole_seeds(meta_seed, hole_count)`: SHA-256 of a fixed prefix, the meta-seed string and the hole index, first two bytes little-endian. The same string always rebuilds the same ROM. The seed string itself is not yet recorded in the ROM.

## Usage

```bash
# 1-course ROM produced by golf-write (course3_mirror already applied)
golf-patch-seeded-wind modified.nes --seed "my seed" -o seeded.nes

# print the expected pin index, anchors and first 6 winds per hole
golf-patch-seeded-wind modified.nes --seed "my seed" --forecast 6 --validate-only

# 2-course ROM
golf-patch-seeded-wind modified.nes --seed "my seed" --holes 36 -o seeded.nes
```

Forecast columns: `pin` is the 0-based flag index; `dir` is `WindDirectionAnchor` (`$012F`, bit 7 = reversed); `spd` is `WindSpeedAnchor` (`$0130`); each `dir/spd` pair is (`$96`, `$97`) for that swing.

## Verifying in Mesen

1. Break at PRG `0x34192` at hole start. `$0525/$0527` should equal the forecast's `slot_state` (low byte in `$0525`), `$012F/$0130` the anchors, and the chosen flag the forecast's pin index.
2. Break at PRG `0x37FBE` (the trampoline's `RTS`) each swing. `$96/$97` should match the forecast's wind for that swing number, for either player, regardless of what the previous shot hit.
3. Break at PRG `0x342BE` after a rough or bunker shot. `$42/$43` will differ from the swing-setup value, but the player's slot must still hold the swing-setup value.

## Constraints

- Requires `COURSE3_MIRROR_PATCH`. Without it the UK flag X offsets are live and get clobbered; the CLI warns.
- Fixed bank: net zero bytes. Bank 13: 16 bytes at `$BFAF-$BFBE` plus 10 NOPs at `$82C0`. Free bank 13 padding after this patch: `$BFBF-$BFF2` (52 bytes).
- Practice mode manual wind and replay playback are untouched. The hole-in-one auto replay should still reproduce, since playback restores the slots and re-runs `InitHole`, but this has not been exercised.
