# Practice Swing

> **Note**: This document was written by Claude based on investigation requested by jdharms.

Notes toward re-implementing the practice-swing QOL feature from the Famicom Disk System
game *Golf - Japan Course*: from the "ready to swing" state, a button toggles the golfer
back ~8 pixels into practice mode, where a full three-press swing can be taken without
hitting the ball or counting a stroke. The power and accuracy markers hold on screen for a
moment afterward, then the player can swing again or toggle back out.

Implemented as `golf/core/patches/practice_swing.py`, applied by
`golf-patch-practice-swing`. The rest of this document is the analysis of the vanilla
swing code it is built on; the implementation itself is at the end.

## The swing state machine

Everything lives in **bank 13**. Entry is `$AA09`, called from `$884F` and `$88C3` in the
club-select/pre-shot loop.

```
$AA09  JSR ShotInitialization ($A9A6)
       ...
$AA2A  loop top: JSR WaitForVblank / CalcLaunchVector ($AD0A) / $BB6D
       ... render calls ...
$AAD6  LDX $0586        ; dispatch
```

`ShotInitialization` (`$A9A6`) zeroes `$0586`, `$0589`, `$D0`/`$D1`, `$CF`, `$0587`,
`$059A` and others, then sets `$D6 = $D7 = $30`.

`$0586` is the swing phase. It is written **only** in bank 13, at `$A9BD`, `$AB31`,
`$ABD3`, `$ABE4`, `$AC48` and `$AC74` - nothing else in the ROM touches it, which makes it
safe to extend with new states.

| `$0586` | Handler | Meaning |
|---|---|---|
| 0 | `$AAED` | Ready - aim, hi/lo, wait for A |
| 1 | `$AB4C` | Backswing (power) |
| 2 | `$AC14` | Downswing (accuracy) |
| 3+ | `$AC88` | Shot committed / ball in flight |

The dispatch at `$AAD6` is an `LDX` / `DEX` / `BNE` chain, so any new state value lands in
the `3+` bucket unless the chain is extended.

### Ready state (`$AAED`)

```
$AAFD  JSR $ACC3        ; hi/lo select - Controller_Current, Up ($08) / Down ($04)
$AB00  JSR $BD57        ; aim - Left ($02) / Right ($01), every other frame
$AB03  LDX CurrentPlayerIndex ($99)
$AB05  LDA Controller_NewPress_Tmp ($18),X
$AB07  AND #$80         ; A  -> BNE $AB16, start swing
$AB0B  LDA $18,X
$AB0D  AND #$40         ; B  -> SEC / RTS, caller re-enters club select
$AB13  JMP $AA2A
```

**Select (`$20`) and Start (`$10`) are unused for the entire shot loop.** Every routine on
the per-frame path was checked, and every `AND #$10` / `AND #$20` in the ROM is either a
data-table false positive or menu code. `docs/menu_system.md` independently notes there is
no in-game pause menu. Select is the natural toggle button.

### Meter mechanics

- `$0587`/`$D6` is the 16-bit power accumulator; `$0588`/`$D7` the accuracy accumulator.
  `$0589` is the sweep direction.
- The per-frame rate comes from `$AB46`/`$AB49` indexed by `SwingSpeed` (`$CE`):
  slow `$0100`, medium `$0150`, fast `$01A0`. Halved for putting at `$AB3D`.
- Power sweeps `$30` down to 0 and back up, auto-stopping at `$30` (`$AB8B`).
- Accuracy runs from the stopped power value up to `$4C`, at **double** rate - `$AC24`
  adds `$058A`/`$058B` twice per frame.
- `$ABE7` mirrors the animation timer around `$31` (`$D1 = $62 - $D1`) so a short backswing
  jumps to the matching downswing frame.
- `$058F` is the impact frame, set at `$ABF7` from `$AC0A,Y`. The golfer animation freezes
  once `$CF >= $058F`.
- CPU and demo players take a parallel path gated on `$D5` bit 7, pressing at targets held
  in `$051D`-`$0523,X`.

## Where the shot gets committed

Three sites, all performing the same triple: `JSR IncrementStrokeCount ($868C)`,
`JSR $8D96`, and a bump of `ShotPhaseState` (`$D2`).

| Site | Trigger | Effect |
|---|---|---|
| `$ABDC` | Putter - commits at the end of the backswing (`INC $0586` twice, skipping the accuracy phase) | `INC $D2` |
| `$AC44` | Accuracy marker ran off the end (`$D7 >= $4C`) | `LDA #$02 / STA $D2` |
| `$AC72` | A pressed during the downswing | `INC $D2` (`$FF` -> `$00`, launch) |

`$AC44` is the **missed shot**. `$D2 = 2` means "stopped", so `$AC9B` falls straight
through to `CLC / RTS` - the stroke is counted and the ball never launches.

A practice mode has to divert all three.

## The golfer renderer is bank 8 `$8000`

> Covered in more depth, including the metasprite format and the club tables, in
> `docs/golfer_sprites.md`.

Not the power bar, despite `$CF`'s `SwingPowerBarPos` label. `$CF` is the **golfer
animation frame index**: it is computed each frame by comparing `$D1` against threshold
tables `$80E7` (13 frames, non-putter) or `$80F4` (6 frames, putter), *written* by the
renderer, and *read* by the state machine (`$AA42`, `$AC14`, `$AC88`).

```
$804F  LDY ClubSelection ($CD)
$8051  LDA $80FA,Y
$8054  STA $26                ; X coordinate
$8056  LDA #$A6
$8058  ADC $05BC
$805E  STA $27                ; Y coordinate
$8060  LDA $CF
$8062  CMP #$05               ; frames 5 and $0B draw the body first, then the club;
$8066  CMP #$0B               ; every other frame draws the club first (sprite priority)
```

The four body-pointer tables are contiguous - `$810A` + 78 = `$8158`, + 78 = `$81A6`,
+ 36 = `$81CA` - which confirms the 6-golfer x 13-frame / 6-frame layout.

| Table | Size | Contents |
|---|---|---|
| `$80DB` | 6 | Per-golfer base offset, non-putter (stride `$0D`) |
| `$80E1` | 6 | Per-golfer base offset, putter (stride `$06`) |
| `$80E7` | 13 | Animation frame thresholds vs `$D1`, non-putter |
| `$80F4` | 6 | Animation frame thresholds vs `$D1`, putter |
| `$80FA` | 16 | **Golfer X coordinate, indexed by `ClubSelection`** - `7C 7C 7C 7C 80 80 80 80 83 83 83 83 85 85 85 8B` |
| `$810A` / `$8158` | 78 each | Body metasprite pointers, lo/hi (6 golfers x 13 frames) |
| `$81A6` / `$81CA` | 36 each | Body metasprite pointers, putter (6 golfers x 6 frames) |

`$0132` selects which of six animation sets to use (0-5). Two writers: bank 13 `$8237`
(`STX $0132`, X from `$0131`, clamped with `CPX #$06` / `DEX`) on the gameplay path, and
bank 11 `$9FC7` (from `$06F4`) on the cutscene path. What the six sets actually are -
characters, outfits, something else - was not established.

`$8083` renders the club as a second metasprite, with per-frame offsets from `$96B8` /
`$96FA`. It **pushes `$26`/`$27` at `$80A1`-`$80A6` and restores them at
`$80D4`-`$80D9`**, so adjusting `$26` at the single site `$8054` shifts the golfer *and*
the club together.

## The markers hold for free

`$A8DD` draws the power and accuracy markers at X = `$D6`/`$D7` + `$5D`, Y = `$D0` +
`$05BC`. Two things fall out favourably:

- Sprite choice is `TYA / SEC / SBC $0586` (`$A90E`), so with `$0586 >= 3` both markers
  render in the committed style and simply stay put.
- They are suppressed only when `$059A != 0`, which is set at `$AC51` on the overrun path -
  exactly the path a practice swing skips.

## Implementation

`golf-patch-practice-swing <rom> [-o out.nes] [--hold-frames N]`. Ten `BytePatch`es, every
one length-preserving, so nothing else in the ROM moves.

**Depends on `wram_expansion`** - the toggle routine lives at fixed-bank `$CAE4`, the tail
of the `$CA40`-`$CAFF` block that `wram_expansion` carves its relocated tables from. Apply
it to a ROM that has already been through `golf-patch-wram`.

### Space

| Pool | Free | Used | Routine |
|---|---|---|---|
| bank 8 `$BFE5`-`$BFF2` | 14 | 12 | `ApplyGolferPracticeOffset` |
| bank 13 `$BFBF`-`$BFF2` | 52 | 48 | `CommitShotOrPractice` (17) + `HoldPracticeSwing` (31) |
| fixed `$CAE4`-`$CAFF` | 28 | 28 | `TogglePracticeSwing` |

Bank 13's 52 bytes is what remains after `mercy_tap_in` (`$BF83`-`$BFAE`) and
`seeded_wind` (`$BFAF`-`$BFBE`); the patch coexists with both, and a test asserts it never
touches their spans.

The toggle routine is in the **fixed bank** rather than bank 13 on purpose. `$C000`-`$FFFF`
is always mapped, so bank 13 reaches it with a plain 3-byte `JSR`/`JMP`, and - because the
only entry is from bank 13 - it can still `JMP $AA2A` back into bank 13 with no bank
switching anywhere in the feature. Bank 12 free space (e.g. from removing the Donkey Kong
scenes, `docs/prize_money.md`) is *not* usable here: it would need `ExecuteFarCall` at 6
bytes a site, and the relocated code could not call back into bank 13's
`IncrementStrokeCount`, `$8D96`, `ShotInitialization` or `$AA2A`.

### State

`PracticeSwingOffset` (`$05BB`) is both the mode flag and the pixel shift: 0 in normal
play, 8 in practice mode. Nothing in the vanilla ROM reads or writes it, and the two
indexed tables nearest it in bank 13 (`$059C,X` and `$05A5,X`) are both bounded at
X = 0..6.

The hold timer reuses `$0586` itself. Practice hold is entered with `$0586` at 3 (or 4
after a putt) and the dispatch at `$AAD6` routes every value >= 3 to the state-3 handler,
so the counter climbs freely to `--hold-frames` (default `$78`, about two seconds).
`ShotInitialization` resets it to 0. No second RAM byte is needed.

### The four routines

**`ApplyGolferPracticeOffset`** - bank 8 `$BFE5`. Splices `$804F` (7 bytes ->
`JSR` + 4 `NOP`).
```
LDY ClubSelection / LDA GolferScreenXTable,Y / SEC / SBC PracticeSwingOffset
STA $26 / RTS
```
With the offset at 0 the arithmetic is a no-op, so vanilla rendering is bit-identical.
`RenderGolferClub` (`$8083`) saves and restores `$26`/`$27`, so the club follows the body.

**`TogglePracticeSwing`** - fixed `$CAE4`. Splices the ready state's B-button test at
`$AB0B` (8 bytes -> `JMP` + 5 `NOP`), leaving the A test at `$AB05` and the idle
`JMP $AA2A` at `$AB13` untouched. One routine owns both buttons that matter:
```
LDA Controller_NewPress_Tmp,X / AND #$60   ; B or Select
BEQ Exit
AND #$40 / BEQ ToggleSelect                ; B wins if both are held
LDA #$00 / STA PracticeSwingOffset         ; B: leaving the shot
SEC / RTS                                  ; vanilla's "cancelled" return
ToggleSelect: LDA PracticeSwingOffset / EOR #$08 / STA PracticeSwingOffset
Exit:         JMP $AA2A
```
Taking over B rather than the idle path is what lets practice mode clear on the way out,
and it costs nothing: only human players reach `$AB0B`, because `$AAF3` sends CPU and demo
players to the timeout path at `$AAF5`, so the `BIT $D5` guard an idle-path hook would
have needed is unnecessary. The `SEC / RTS` returns from `SwingSequenceEntry` with the
stack exactly as vanilla left it - `$AB0B` is entered by `JMP`, not `JSR`.

This routine fills `$CAE4`-`$CAFF` exactly; `HalfSquareTableLo` begins at `$CB00`.

**`CommitShotOrPractice`** - bank 13 `$BFBF`. All three commit sites open with the same
`JSR IncrementStrokeCount` / `JSR $8D96` pair, so one routine and three identical 6-byte
splices (`$ABDC`, `$AC4B`, `$AC77`) cover them. In practice mode it skips both and presets
`ShotPhaseState` to `$FE`, so the `INC $D2` that follows two of the three sites lands on
`$FF` ("no shot in progress") rather than `$00` (launch).

Skipping `$8D96` matters beyond the stroke count: it gates `$DA17` -> `$D94C`, which
advances wind RNG state. A practice swing that reached it would desync `seeded_wind`.

**`HoldPracticeSwing`** - bank 13 `$BFD0`. Splices `$AC92` (3 bytes, exactly a `JMP`).
Hooking here rather than at `$AC88` lets the follow-through animation play out first.
```
LDA PracticeSwingOffset / BEQ Normal
LDA #$FF / STA ShotPhaseState        ; also covers the whiff site, which stores $02
INC $0586 / LDA $0586 / CMP #hold_frames / BCC Loop
JSR ShotInitialization
Loop:   JMP $AA2A
Normal: LDA WaterLandingCount / JMP $AC95
```
`ShotInitialization` is a complete reset here because a practice swing happens before the
ball has moved: it restores `$0586`, `$0587`, `$0589`, `$059A`, `$D0`, `$D1`, `$CF`, `$D2`
and `$D6`/`$D7` to exactly their values at `$AA09`, and its one subroutine call (`$B75C`)
merely zeroes the velocity accumulators `$B3`-`$B6` - no RNG, fully idempotent.

### Deliberate behaviours

- **Practice mode never survives leaving the shot.** Taking a real shot requires toggling
  it off, and backing out with B clears it, so the flag can never be set while another
  player is at the tee.
- **A practice whiff hides the accuracy marker.** The overrun site's `INC $059A` at
  `$AC51` still runs, and `$059A != 0` suppresses that marker in `RenderSwingMeterMarkers`
  - the same as a real whiff.
- **Putting is included.** `$804F` is downstream of the putter/non-putter split, so the
  golfer shift applies to putts too, and the putter's early commit at `$ABDC` is one of the
  three spliced sites.

### To verify in an emulator

1. Ready state, press Select: the golfer and club step 8 px left, together.
2. Swing. No stroke is added, the ball does not launch, both markers hold for ~2 s, then
   the ready state returns with the meter back at `$30`.
3. Let the accuracy marker run off the end: same, no stroke, no whiff exit.
4. Press Select again: golfer returns, and the next swing plays normally.
5. In practice mode, press B: club select opens and `$05BB` is back to 0, so returning to
   the shot is out of practice mode.
6. Watch `$05BB` (0/8), `$0586` (climbing 3 -> `$78` during the hold) and
   `CurrentHoleStrokes` (`$011F,X`, unchanged across practice swings).


## Open questions

- The full contents of the `$058F` source table at `$AC0A`; only the first five bytes
  (`0A 0A 0A 0B 0C`) were read.
- The swing SFX (`MusicRequest = 1` at `$AB16` and `$ABB8`) is left alone, so a practice
  swing sounds like a real one. Worth revisiting once it has been heard in an emulator.
- `$D4` (`MaybeIsPuttingFlag`) causes the ready state to auto-start the swing at `$AAED`
  when nonzero, which does not obviously match the label. Not chased.
