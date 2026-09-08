# Putting Practice

> **Note**: This document was written by Claude based on reverse-engineering requested by jdharms. Everything below was verified against the US ROM, and the mechanism was confirmed working in a throwaway prototype that was not kept. No patch module implements this yet.

Places the ball at a random point on the green's putting surface at hole init instead of on the tee, so every hole starts as a putt.

This is a design note, not a description of shipped code. The assembly is given in full because it was built and run; the payload address is deliberately left open - see [Placing the payload](#placing-the-payload).

## Why this is cheap

The shot loop recomputes the lie from the ball's coordinates at the top of every shot and branches on the result. Bank 13 `LD_877A`, at `$87B5`:

```
$87B3  86 D4       STX MaybeIsPuttingFlag[$D4]   ; 0
$87B5  20 BC ED    JSR LEDBC                     ; ball position -> BallLie
$87B8  A5 C9       LDA BallLie[$C9]
$87BA  C9 06       CMP #$06
$87BC  D0 05       BNE LD_87C3                   ; normal course view
$87BE  E6 D4       INC MaybeIsPuttingFlag[$D4]
$87C0  4C 6E 88    JMP LD_886E                   ; green / putting view
```

Lie 6 is a pure function of position. No persistent "on the green" state gates it. Put the ball inside the green box and the putter, the green view, the putting physics and the green-space HUD all follow with no further patching.

The `BallLie == 6` branch at `$87BC` also jumps clear over the tee-shot presentation path at `$87C3`-`$87E0` (`LD_8F73`, `LD_A170`, `LD_9C4D`), so nothing has to be suppressed by hand.

## Where the ball position lives

`InitHole` (fixed bank `$DA90`) does **not** set the ball position. It loads par, distance, scroll limit, `GreenX`/`GreenY`, `TeeBlocksX/Y/YHigh`, picks the pin, decompresses the green and terrain, and draws wind.

The ball is placed by bank 13's fresh-hole init loop, which runs for X = 1 then X = 0:

```
$8155  A2 01       LDX #$01
$8157  ...                            ; zero per-player counters
$816B  A9 80       LDA #$80
$816D  9D 13 01    STA $0113,X        ; ball X fraction
$8170  9D 17 01    STA $0117,X        ; ball Y fraction
$8173  AD 0E 01    LDA TeeBlocksX     ; <-- splice site, $8173-$8184, 18 bytes
$8176  9D 15 01    STA $0115,X        ; ball X
$8179  AD 0F 01    LDA TeeBlocksY
$817C  9D 19 01    STA $0119,X        ; ball Y low
$817F  AD 10 01    LDA TeeBlocksYHigh
$8182  9D 1B 01    STA $011B,X        ; ball Y high
$8185  A5 42       LDA RngState[$42]  ; per-player wind slots
       ...
$8190  10 C5       BPL $8157
```

`$0113/$0115/$0117/$0119/$011B,X` is the per-player ball position: X fraction, X, Y fraction, Y low, Y high. `LD_86C8` (`$86C8`) loads it into `$AD`-`$B2` at shot start; `LD_86ED` (`$86ED`) saves it back.

The `$80` fractions written at `$816B`-`$8172` sit **above** the splice site and can be left alone - they put the ball at the centre of whichever tile is chosen.

The other three `InitHole` callers (`$813C`, `$8D13`, `$8D66`) are resume paths that restore a saved position; they must not be touched.

## Green geometry

`LEE13` (`$EE13`) is the in-bounds test:

```
$EE13  A5 9C       LDA $9C            ; ball X
$EE16  E5 A3       SBC GreenX[$A3]
$EE18  C9 18       CMP #$18           ; must be < 24
$EE1A  B0 F4       BCS LEE10          ; -> terrain lie
$EE1C  85 26       STA $26
$EE1E  A5 9E       LDA $9E            ; ball Y low
$EE21  E5 A4       SBC GreenY[$A4]
$EE23  85 27       STA $27
$EE25  A5 9F       LDA $9F            ; ball Y high
$EE27  E9 00       SBC #$00
$EE29  D0 E5       BNE LEE10          ; must resolve to 0
$EE2B  A5 27       LDA $27
$EE2D  C9 18       CMP #$18
$EE2F  B0 DF       BCS LEE10
```

So the green is a 24x24 tile box whose top-left corner is (`GreenX`, `GreenY`). `GreenY` is 8-bit while `TeeBlocksY` is 16-bit: greens always sit in the low 256 rows and the tee further down. Japan hole 1 has `green.y = 47` against `tee.y = 258`; hole 5 has 33 against 242. **Ball Y high is 0 on the green.**

Tiles are read from a 24x24 row-major buffer in WRAM. `DecompressGreen` (`$E3AC`) establishes the base:

```
$E3AC  A9 A6       LDA #$A6
$E3AE  85 22       STA SramPtr[$22]
$E3B0  A9 75       LDA #$75
$E3B2  85 23       STA SramPtr[$23]
```

**Green tile buffer = `$75A6`**, 576 bytes, indexed `24 * tileY + tileX`. `InitHole` fills it at `$DB65`, before the init loop runs, so it is already populated at the splice site.

The lie check indexes it at `$EE52`-`$EE7F` and classifies:

```
$EE7F  B1 20       LDA ($20),Y
$EE81  C9 30       CMP #$30
$EE83  B0 03       BCS LEE88
$EE85  4C D5 EE    JMP LEED5          ; < $30: fall through to terrain lie
$EE88  C9 48       CMP #$48
$EE8A  90 08       BCC LEE94
$EE8C  C9 88       CMP #$88
$EE8E  B0 04       BCS LEE94
$EE90  A9 80       LDA #$80
$EE92  85 CA       STA $CA            ; $48-$87 only
$EE94  ...
$EE9A  A9 06       LDA #$06
$EE9C  85 C9       STA BallLie[$C9]
```

### Tile classification

The game's own test is `>= $30`, which is BallLie 6. That is **not** the right predicate for choosing a spawn point. The project's classification, in `golf/formats/putting_surface.py` (shared with `editor/tools/carpet_paint_tool.py`):

| Range | Meaning |
|---|---|
| `< $30` | off the green |
| `$30-$47` | putting surface, dark slopes |
| `$48-$87` | fringe / edge transition tiles - the band `$EE88`-`$EE92` singles out to set `$CA = $80` |
| `$88-$A7` | putting surface, light slopes |
| `$B0` | putting surface, flat |

Two traps here, both confirmed against all 72 vanilla greens:

1. **The interior fill tile differs per green.** Japan 1 uses `$96`/`$9C`/`$B0`; US 10 uses `$3B` for 255 of its tiles; UK 10 uses `$44`/`$46`. Any predicate keyed to one family fails on others - `>= $88` matches *zero* tiles on US 10 and UK 10 and would reject their entire greens.
2. **`$48`-`$87` must be rejected even though it is legal putting surface.** It is the fringe outline; a ball there is at the green's edge.

Nothing in the vanilla data falls in `$A0`-`$AF` or above `$B0`, which means the vanilla greens cannot distinguish `$88-$9F` from `$88-$A7`. A green painted in this project's editor can use `$A0`-`$A7`. Derive the ranges from `PUTTING_SURFACE_TILES` rather than restating them.

### Coordinate conversion

Green sub-unit space is 1/8 tile, 0-191 across the green - the same units as the `x_offset`/`y_offset` values in each hole's `flag_positions`. `LD_94E7` (`$9523` onward) converts ball position into it; `InitHole` `$DB21`-`$DB5B` does the inverse for the pin. Going from a chosen tile back to a ball position:

```
BallX     = GreenX + tileX          BallXfrac = (subX & 7) << 5
BallY     = GreenY + tileY          BallYfrac = (subY & 7) << 5
BallYHigh = carry out of the Y add
```

With the vanilla `$80` fractions left in place, the ball lands at tile centre and only the integer parts need writing.

## Placing the payload

**Do not trust an `$FF` scan.** Several regions that read as padding are already claimed by patches in `golf/core/patches/`, and the claims chain across modules - `seeded_wind`'s trampoline is documented as "first free byte after the mercy tap-in routines". Re-derive occupancy at implementation time by enumerating `prg_offset` and `len(patched)` across every patch factory, not by reading the ROM.

State of play as of this writing:

- **Bank 13 tail**, `$BF83`-`$BFF2`, 112 bytes: 108 claimed by `mercy_tap_in` (`$BF83`-`$BFAE`), `seeded_wind` (`$BFAF`-`$BFBE`) and `practice_swing` (`$BFBF`-`$BFEE`). 4 bytes left. `tests/integration/test_practice_swing_rom.py` asserts those boundaries.
- **Fixed bank `$CA40`-`$CAFF`**, 192 bytes: fully consumed by `wram_expansion` (`$CA40`-`$CAE3`) and `practice_swing` (`$CAE4`-`$CAFF`).
- The rest of bank 13 has no run over 16 bytes.

The fixed bank is the scarce resource. This routine does not need to be in it.

### Reaching a switchable bank

`ExecuteFarCall` (`$D372`) costs 6 bytes at the call site - `JSR` plus 3 inline bytes of bank, target low, target high - and its register contract is good enough to call from inside the init loop:

```
$D372  85 30       STA TempA[$30]        ; A/X/Y saved on entry
$D374  86 31       STX TempX[$31]
$D376  84 32       STY TempY[$32]
$D378  A5 5C       LDA CurrentBank[$5C]  ; caller's bank saved
$D37A  48          PHA
       ...                               ; inline args read via a stack-relative
       ...                               ; pointer to the return address
$D3A6  A5 30       LDA TempA[$30]        ; A/X/Y restored before entering target
$D3A8  A6 31       LDX TempX[$31]
$D3AA  A4 32       LDY TempY[$32]
$D3AC  20 BE D3    JSR LD3BE_FarCallTrampoline
$D3AF  85 30       STA TempA[$30]        ; A/X preserved across the bank restore
$D3B1  86 31       STX TempX[$31]
$D3B3  68          PLA
$D3B4  08          PHP                   ; target's flags survive
$D3B5  20 52 D3    JSR BankSwitchRoutine
$D3B8  A5 30       LDA TempA[$30]
$D3BA  A6 31       LDX TempX[$31]
$D3BC  28          PLP
$D3BD  60          RTS
```

- The target receives the caller's A, X and Y intact, so the player index in X survives into the routine.
- A and X are preserved on return; the target's flags are preserved, so it can return carry. Y is not managed on return - irrelevant here, since `$8157`-`$8190` uses only A and X.
- It clobbers `$30`/`$31`/`$32` and `$4C`-`$4F`. None are live at `$8173`.
- The `LDA $0102,X` / `LDA $0103,X` at `$D37C`/`$D381` render as `CurrCourse` / `HoleMatchStatus` in a labelled listing. That is the `.mlb` mislabelling a stack-page access - with `TSX` those are stack-relative reads of the return address. It nests correctly.

A payload reached this way must not call into banked code. This routine does not: zero page `$A3`/`$A4`, WRAM `$75A6`, `LSFR_RNG_ALGO` in the always-mapped fixed bank, and writes to `$0113`-`$011B,X`.

`LSFR_RNG_ALGO` (`$D29C`) preserves both X and Y - it saves X around its own use of it as a shift counter (`TXA`/`PHA` ... `PLA`/`TAX`) and never touches Y. Only A is clobbered. So the player index can stay in X across any number of draws.

Candidate homes are the switchable bank tails. Every bank ends with an identical 13-byte stub at `$BFF3`-`$BFFF`, and every padding run terminates at exactly `$BFF2` - that uniformity across all 15 banks is better evidence of real padding than any single-bank scan, and `practice_swing` already uses bank 8's tail. Banks 0-3 are course data and greens and must be excluded.

## The routine

Entered with X = player index, which it preserves. 127 bytes as written.

```
        LDA #$0C            ; default to the centre tile so a run of
        STA $26             ; rejected draws still lands somewhere sane
        STA $27
        LDA #$FF
        STA $2A             ; attempt counter
Retry:
        JSR LSFR_RNG_ALGO   ; $D29C - preserves X and Y, clobbers A
        AND #$1F
        CMP #$18            ; reject 24-31
        BCS Next
        STA $26             ; tileX
        JSR LSFR_RNG_ALGO
        AND #$1F
        CMP #$18
        BCS Next
        STA $27             ; tileY, and A = tileY

        ; pointer = $75A6 + 24*tileY + tileX
        ASL A
        ASL A
        ASL A               ; 8Y, max 184, never carries out
        STA $28
        LDA #$75
        STA $29             ; high byte starts at the buffer's page
        LDA $28
        ASL A               ; 16Y
        BCC +
        INC $29
    +   CLC
        ADC $28             ; 24Y
        BCC +
        INC $29
    +   CLC
        ADC $26             ; + tileX
        BCC +
        INC $29
    +   CLC
        ADC #$A6            ; + buffer base low
        BCC +
        INC $29
    +   STA $28

        LDY #$00
        LDA ($28),Y
        CMP #$30            ; \
        BCC Next            ;  |
        CMP #$48            ;  | one CMP/BCC pair per contiguous run of
        BCC Found           ;  | PUTTING_SURFACE_TILES, ascending, so
        CMP #$88            ;  | "below this run's start" means every
        BCC Next            ;  | lower value was already tested
        CMP #$A8            ;  |
        BCC Found           ;  |
        CMP #$B0            ;  |
        BCC Next            ;  |
        CMP #$B1            ;  |
        BCC Found           ; /
                            ; past the last run: falls into Next
Next:
        DEC $2A
        BNE Retry
        ; exhausted: fall through with the last accepted tile
Found:
        LDA $A3             ; GreenX
        CLC
        ADC $26
        STA $0115,X         ; ball X
        LDA $A4             ; GreenY
        CLC
        ADC $27
        STA $0119,X         ; ball Y low
        LDA #$00
        ADC #$00            ; carry out of the Y add
        STA $011B,X         ; ball Y high
        RTS
```

Zero page `$26`-`$29` are unlabelled general scratch; `$2A` is `Tmp_2A`. Nothing is live across the splice site - the init loop uses only A and X.

`$0C` as the pre-seeded default matters: if every draw is rejected the routine falls through with whatever tile was last accepted, and on the first pass through there is none. The centre of the grid is on the surface for every vanilla green.

### Generating the acceptance chain

The compare chain is one `CMP`/`BCC` pair per contiguous run of `PUTTING_SURFACE_TILES`, emitted in ascending order. Because the runs are disjoint and ascending, "below this run's start" is a rejection: every lower value was already tested by an earlier pair. Generating it from the set rather than hand-writing it keeps the patch honest if the editor's palette changes:

```python
def contiguous_runs(values: set[int]) -> list[tuple[int, int]]:
    """Ascending (start, end_exclusive) runs covering `values`."""
    runs: list[tuple[int, int]] = []
    for v in sorted(values):
        if runs and v == runs[-1][1]:
            runs[-1] = (runs[-1][0], v + 1)
        else:
            runs.append((v, v + 1))
    return runs

for lo, end in contiguous_runs(PUTTING_SURFACE_TILES):
    emit(0xC9, lo)                  # CMP #lo
    reject_branches.append(len(code))
    emit(0x90, 0x00)                # BCC Next   (fixed up later)
    emit(0xC9, end)                 # CMP #end
    accept_branches.append(len(code))
    emit(0x90, 0x00)                # BCC Found  (fixed up later)
```

`PUTTING_SURFACE_TILES` currently yields `[($30,$48), ($88,$A8), ($B0,$B1)]`, so this costs 24 bytes. Resolve the forward branches after both targets are known rather than hand-counting displacements, and assert the assembled routine ends at or before the host bank's last padding byte.

The splice, length-preserving so nothing else moves:

```
$8173  original: AD 0E 01 9D 15 01 AD 0F 01 9D 19 01 AD 10 01 9D 1B 01
       patched:  20 72 D3 <bank> <lo> <hi> EA EA EA EA EA EA EA EA EA EA EA EA
```

### Rejection sampling coverage

Simulated over all 72 greens, 500 spawns each, with 255 attempts: 71 of 72 holes never reach the fallback. The exception is `courses/close/hole_12.json` at 481/500, which has 13 surface tiles out of 576 and is not a vanilla course. Sparse greens are the reason for a high attempt count; it costs one immediate byte.

The fallback path is benign - an off-surface tile simply produces a normal lie and a normal approach shot.

The attempt count sits in the `DEC`/`BNE` loop, so `$FF` is the maximum and costs nothing over a smaller value except worst-case time. At roughly 220 cycles per `LSFR_RNG_ALGO` call and two calls per attempt, 255 attempts is on the order of four frames, twice per hole init. Hole init is not frame-critical - it already decompresses terrain and greens.

## Confirmed working

A prototype of exactly the code above was assembled into a US ROM and played. The lie recompute at `$87B5` returns 6 and routes to the putting view as predicted; the tee-shot presentation is skipped; the putter is selected automatically; the green renders with the ball on it and the putt plays normally.

The prototype was not kept, so the assembly and the byte-level splice above are the record of it.

## Gaps to close in a production version

- Each loop iteration draws its own randoms, so `RngState` advances twice per hole init and the per-player wind slots written at `$8185` desync. Wind does not affect putting, so this is cosmetic for this feature, but a production patch that coexists with `seeded_wind` should save and restore `$42`/`$43` around the sampling block. The sidecar notes the invariant: both slots are "set from RngState at bank13 `$8185` after InitHole (so identical)".
- The ball can land on the pin's own tile and hole out on contact, roughly 1 in 200.
- `MaybePlayerHoleStatus` (`$0111,X`) is left at 0 rather than 2. `LD_870C` (`$870C`) uses that to choose between course-space and green-space distance. In practice the putt detail screen does not display distance to the pin at all, so this is inert.
- There is no way to leave putting practice or return to normal play; it applies to every hole unconditionally.

## Open questions for the production version

- What `$CA = $80` means. It is set only for fringe tiles `$48`-`$87` and is cleared at `$EE52`.
- Whether to bias the spawn away from the pin to guarantee a non-trivial putt, and whether to bias toward or away from slopes.
- How the mode should be entered and exited. `docs/practice_swing.md` establishes that Select and Start are unused for the entire shot loop.
