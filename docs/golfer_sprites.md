# Golfer Sprites

> **Note**: This document was written by Claude based on investigation requested by jdharms.

How the swinging golfer and his club are drawn during a shot, and how the game decides
*which* golfer to draw.

Confidence is marked per claim:

- **[C]** Confirmed - read directly out of code/data, or verified live by jdharms.
- **[D]** Derived - follows from arithmetic on table addresses/strides that closes exactly.
- **[G]** Guess - plausible reading, not verified.

## Where it happens

**[C]** The golfer is rendered by **bank 8 `$8000`**, reached once per frame from the shot
loop via `ExecuteFarCall` at bank 13 `$AAA2` (`.db $08, $00, $80`). It is the only caller.

**[C]** Two metasprites are drawn per frame:

| Sub | Renders | Sprite attribute (`$29`) |
|---|---|---|
| `$8073` | The golfer's body | `$00` |
| `$8083` | The club | `$01` |

**[C]** `$8060` picks the draw order: on animation frames `$05` and `$0B` the body is drawn
first and the club second; on every other frame the club goes first. Since both write into
OAM through a shared cursor, this is a sprite-priority swap - the club passes in front of
the body for two frames of the swing.

**[C]** `$8083` pushes `$26`/`$27` on entry (`$80A1`-`$80A6`) and restores them on exit
(`$80D4`-`$80D9`), so the club's position is expressed relative to the body's. Moving the
body moves the club with it.

## Metasprite data format

**[C]** Both go through `$FF38` (fixed bank), which reads a list at `PointerToSpriteData`
(`$45`/`$46`) and appends to OAM at `$0200 + $4A`:

```
count                  ; $00 = empty, renders nothing
per sprite, 3 bytes:
  dY    signed, added to $27  -> OAM+0  (Y)
  tile                        -> OAM+1  (tile)
  dX    signed, added to $26  -> OAM+3  (X)
```

**[C]** OAM+2 (attributes) is **not** in the data - it comes from `$29` and is therefore
identical for every sprite in one metasprite. Sign extension of `dY` goes through `$38`;
if the result carries out, that sprite is skipped (`$FF74`) rather than wrapping.

**[C]** The first body metasprite (`$81EE`) begins `13 10 11 F8 10 10 F0 ...` - a count of
`$13` = **19 sprites**, then 19 triplets. That matches jdharms' recollection of ~20 sprites
for the golfer.

## Choosing the body metasprite

**[C]** Two inputs combine into a flat index:

```
$803C  LDX $0132                  ; which golfer
$803F  TYA / CLC / ADC $80DB,X    ; Y = animation frame + per-golfer base
$8045  LDX $810A,Y                ; pointer low
$8048  LDA $8158,Y                ; pointer high
```

`$CF` is the animation frame, found at `$802E`-`$8039` by scanning `$D1` (the swing
animation timer) against a threshold table. **[C]** Despite its `SwingPowerBarPos` label in
the `.mlb`, `$CF` is the golfer animation frame index - it is *written* here by the
renderer and *read* by the swing state machine in bank 13. See `docs/practice_swing.md`.

### Body tables (bank 8)

| Table | Size | Contents |
|---|---|---|
| `$80DB` | 6 | Per-golfer base offset, non-putter (stride `$0D` = 13) |
| `$80E1` | 6 | Per-golfer base offset, putter (stride `$06`) |
| `$80E7` | 13 | Frame thresholds vs `$D1`, non-putter |
| `$80F4` | 6 | Frame thresholds vs `$D1`, putter |
| `$810A` / `$8158` | 78 each | Metasprite pointer lo/hi, non-putter (6 x 13) |
| `$81A6` / `$81CA` | 36 each | Metasprite pointer lo/hi, putter (6 x 6) |
| `$81EE` | - | Metasprite data begins |

**[D]** The four pointer tables are contiguous with no padding: `$810A` + 78 = `$8158`,
+ 78 = `$81A6`, + 36 = `$81CA`, + 36 = `$81EE` - and `$810A[0]`/`$8158[0]` is `$81EE`, so
the tables run straight into the data they point at. This closes the 6-golfer x 13-frame /
6-frame layout exactly.

## Choosing the club metasprite

**[C]** Three inputs, not two:

```
$8085  LDA $959D,Y   ; Y = ClubSelection    -> club-group base
$8089  ADC $CF                              ; + animation frame
$808E  ADC $9597,X   ; X = $0132            -> golfer base
$8093  LDA $95AD,Y -> $45 ;  $9621,Y -> $46
```

### Club tables (bank 8)

| Table | Size | Contents |
|---|---|---|
| `$9597` | 6 | Per-golfer base: `00 3A 3A 00 3A 3A` |
| `$959D` | 16 | Per-club base: `00 00 00 00 0D 0D 0D 0D 1A 1A 1A 1A 27 27 27 34` |
| `$95AD` / `$9621` | 116 each | Club metasprite pointer lo/hi |
| `$9695` | 16 | Club position-offset base, per club: `00` x4, `0B` x11, `FF` |
| `$96A5` | 6 | Club position-offset base, per golfer: `FF 00 16 FF 2C FF` |
| `$96AB` | 13 | Club position-offset base, per frame: `00 01 02 03 04 05 04 03 06 07 08 09 0A` |
| `$96B8` / `$96FA` | ? | Club dX / dY nudges, indexed by the sum of the three above |

**[D]** These are contiguous too: `$9597` +6 = `$959D`, +16 = `$95AD`, +116 = `$9621`,
+116 = `$9695`, +16 = `$96A5`, +6 = `$96AB`, +13 = `$96B8`.

**[D]** The club animation is heavily shared. `$959D` collapses 16 clubs into 5 groups
(`{0-3} {4-7} {8-11} {12-14} {15}`) with stride 13, and the putter's base is `$34`; `$34`
+ 6 putter frames = `$3A`, which is exactly the per-golfer stride in `$9597`. And `$9597`
has only **two** distinct values (`$00` and `$3A`), so six golfers share just two club
animation sets: golfers 0 and 3 use one, golfers 1, 2, 4 and 5 use the other. 2 x 58 = 116,
matching the pointer table size exactly.

**[C]** The per-frame index table `$96AB` reads `00 01 02 03 04 05 04 03 ...` - frames 6
and 7 reuse the entries for frames 4 and 3. **[G]** That is presumably the backswing being
replayed in reverse on the way down, consistent with `$ABE7` mirroring the animation timer
around `$31`.

**[C]** The club offset is skipped entirely (`BMI` at `$80AC` / `$80B4`) when either
`$9695[club]` or `$96A5[golfer]` is negative. That means the putter (club 15, `$FF`) never
gets a nudge, and neither do golfers 0, 3 and 5 (`$FF` in `$96A5`).

**Open:** the extent of `$96B8`/`$96FA` is unverified. If they are back-to-back that is 66
entries each, but the largest index the three base tables can produce is
`$2C + $0B + $0A = $47` = 71. Either not all combinations occur at runtime, or the layout
differs from what adjacency suggests.

## Position on screen

**[C]**

```
$804F  LDY ClubSelection ($CD)
$8051  LDA $80FA,Y
$8054  STA $26          ; X
$8056  LDA #$A6
$8058  ADC $05BC        ; scroll; carry out -> skip drawing entirely
$805E  STA $27          ; Y
```

`$80FA` is 16 bytes: `7C 7C 7C 7C 80 80 80 80 83 83 83 83 85 85 85 8B`. **[C]** The
golfer's X therefore varies with the club - he stands further from the ball with the long
clubs and closest with the putter (`$8B`). **[G]** The four-club grouping matches `$959D`'s
grouping, so this is presumably the same club-class split (woods / long irons / short irons
/ wedges / putter).

## Which golfer: `$0132`

**[C]** (verified live by jdharms) `$0132` selects the character, and changing it before
the "ready to swing" state changes who is drawn:

| `$0132` | Golfer |
|---|---|
| 0 | Mario |
| 1 | Luigi |
| 2-5 | The four computer opponents |

### How it gets set

**[C]** Written in two places. The gameplay one is bank 13 `$8237`, reached from `$8220`:

```
$8220  LDX CurrentPlayerIndex ($99)
       LDA MaybePlayerHoleStatus ($0111),X
       CMP #$03 / BEQ -> $8392
$822C  TXA
       BEQ $8237        ; player 0 -> X still 0 -> Mario
       LDX $0131        ; otherwise take the opponent id
       CPX #$06 / BNE $8237
       DEX              ; clamp 6 -> 5
$8237  STX $0132
```

**[C]** This runs per shot, which explains jdharms' observation that a manual change to
`$0132` is reverted on the next shot in a one-player game: `CurrentPlayerIndex` is always
0 there, so the `BEQ` path forces `$0132` back to 0 (Mario) every time.

**[C]** `$0131` is the *opponent* slot - the identity used for anyone who is not player 0:

| Site | Effect |
|---|---|
| bank 13 `$806A` | Two-player game (`MaybeTwoPlayerFlag` `$0101` nonzero) -> `$0131 = 1`, i.e. Luigi as player 2 |
| bank 13 `$8035` | If X == 7: `$0131 = $6003 + 2`; otherwise `$0131 = 1` |
| bank 13 `$857F` | `LDA $0131 / CMP #$06 / BCS skip / INC $0131` - advance to the next opponent, capped at 6 |
| bank 11 `$9FC1`/`$9FC7` | Cutscene path: `$0131 = $06F3`, `$0132 = $06F4`, then `INC $0131` |
| bank 9 `$AF49` | Not investigated |

**[D]** The `+ 2` at `$8035` lines up with the confirmed mapping: opponent ids start at 2,
so `$6003` is a 0-based progression counter through the four computer opponents. The `INC`
at `$857F` walks it forward, and the `6 -> 5` clamp at `$8236` means the fourth opponent is
also the last.

**[G]** `$6003` is labelled `SramMagic` in the `.mlb`. Given it feeds an opponent index
via `+2`, that label looks wrong - it reads more like a tournament progression or rank
counter. Worth re-checking before relying on the existing name.

## Notes for anyone scanning bank 8 for free space

**[C]** A naive "runs of identical bytes" scan of bank 8 reports candidate free regions at
`$9621` (26 x `$97`), `$963B` (34 x `$98`), `$965D` (29 x `$99`) and `$967D` (24 x `$9A`).
These are **not** free - they are stretches of the `$9621` club-pointer *high-byte* table,
where consecutive metasprites happen to live in the same page.

## Open questions

- Extent of `$96B8`/`$96FA` (above).
- What distinguishes the two club animation sets in `$9597` - golfers 0 and 3 versus
  1, 2, 4 and 5. **[G]** Possibly body height or handedness.
- Why golfers 0, 3 and 5 need no club position nudge while 1, 2 and 4 do.
- bank 9 `$AF49`, the third writer of `$0131`.
- Whether the six golfers have distinct CHR, or share tiles with palette swaps. Nothing
  here touches CHR loading; `$29` is fixed at `$00`/`$01` for body/club, so any per-golfer
  colour difference would have to come from the sprite palette set up elsewhere.
