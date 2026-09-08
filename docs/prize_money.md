# Prize Money / DK Clubhouse Cutscene

> **Note**: This document was written by Claude based on investigation requested by jdharms.

The "PRIZE MONEY" club house entry opens a full-screen scripted cutscene: Mario walks
into the clubhouse, Donkey Kong tells him his winnings, and (if money is pending) Mario
hands over a stack of bills. It is one of **four** money/DK cutscenes that share a script
interpreter in bank 11.

This document exists mainly as a **space inventory** - the feature is a good candidate for
removal, and it accounts for roughly 4.8 KB of exclusive data across three banks.

## Two entry points

```
$8F34  LDA #$00     ; club house "PRIZE MONEY"
$8F36  BEQ $8F3A
$8F38  LDA #$01     ; post-round payout
$8F3A  STA $06DE
```

| Entry | Reached from | Mode |
|---|---|---|
| `$8F34` (bank 12) | `$84FA` `LC_84FA_OpenPrizeMoney`, club house code `$85` | `$06DE = 0` |
| `$8F38` (bank 12) | `ExecuteFarCall` at bank 9 `$B0CC`, guarded on `TotalMoney` (`$6011`/`$6012`) having changed | `$06DE = 1` |

Removing the club house menu entry alone does **not** free the code - bank 9 still calls
`$8F38` after a round. Both call sites have to go.

See `docs/menu_system.md` for how club house code `$85` reaches `$84FA`.

## Setup (`$8F34`-`$8FCB`)

The inline parameters after `WriteNametableTiles`, `LoadCompressedGraphics` and
`Load32BytesToBuffer` make a naive disassembly derail here. `LoadCompressedGraphics`
(`$D45F`) takes **3** inline bytes: `bank, lo, hi`.

```
$8F80  JSR WriteNametableTiles     .dw $9145
$8F85  JSR LoadCompressedGraphics  .db $06, $8000
$8F8B  JSR LoadCompressedGraphics  .db $05, $B4D5
$8F91  JSR LoadCompressedGraphics  .db $05, $B9FD
$8F97  JSR LoadCompressedGraphics  .db $05, $BC1D
$8F9D  JSR LoadCompressedGraphics  .db $05, $BCD7
$8FA3  JSR Load32BytesToBuffer     .dw $9125
$8FA6  ...
$8FA8  $06E7/$06E8 = $9658                 ; default script
$8FB2  LDA PendingMoneyStack ($6026)
       if nonzero: $06E7/$06E8 = $96EA, clear PendingMoneyStack, JSR $A421
$8FCC  STA $06E4                           ; scene variant, 0-4
```

`$A421` reads `PendingMoney` (SRAM `$6020`-`$6025`) and buckets its digits into a variant
index - a bigger pending amount selects a bigger stack-of-bills actor set. It lives inside
a sibling scene's block but is called only from `$8FC6`.

## Scene variant table

`$06E4` (0-4) indexes `$911B` for an object-definition list, which is handed to the object
allocator `LF7EE` (`$F7EE`) along with a count of 1 (variant 0) or 2 (variants 1-4).
Definitions are 9 bytes each, the same format `InitMainMenu` uses at `$8F10`.

| `$06E4` | Pointer | Objects |
|---|---|---|
| 0 | `$9211` | 1 |
| 1 | `$921A` | 2 |
| 2 | `$922C` | 2 |
| 3 | `$923E` | 2 |
| 4 | `$9250` | 2 |

`9 + 4*18 = 81` bytes, so the list ends exactly at `$9261` - which is what fixes the upper
bound of the bank 12 block.

## Per-frame loop

```
$8FEC  JSR WaitForVblank
       MenuInputByte ($0681) = Controller_NewPress_Tmp ($18)
       JSR $F8CA
       JSR $9020                    ; local tick
       JSR $FF7E
       loop until $0682 != 0
```

`$9020` checks `$0681 & $070D` for the exit button, then runs three things:

| Call | Purpose |
|---|---|
| `JSR $9040` | DK/Mario animation: advances `$06E1` (0-3) on a per-cell delay from the script, writes a 6x7 tile block to PPU `$21C9` from `$90BC,X` |
| `JSR $90C4` | Palette flash: toggles `$0683` between 0 and 1 on delays from `$9111`, writes 4 bytes to PPU `$3F00` from `$9113 + phase*4` |
| `ExecuteFarCall .db $0B,$9033` | The cutscene script interpreter (bank 11) |

### Data tables

| Address | Size | Contents |
|---|---|---|
| `$9111` | 2 | Palette-flash frame delays (`06 07`), indexed by `$0683` |
| `$9113` | 8 | Two 4-byte palettes: `0F 30 22 1C` / `0F 30 30 25` |
| `$911B` | 10 | Scene-variant object-def pointers (above) |
| `$9125` | 32 | Full palette set, copied to `$0476` by `Load32BytesToBuffer` |
| `$9145` | 4 + 32 | Nametable descriptor: 32 bytes inline to PPU `$1FE0` (CHR RAM tiles `$FE`/`$FF` of pattern table 1 - a downward triangle) |
| `$9169`, `$9193`, `$91BD`, `$91E7` | 42 each | Four 6x7 animation cells, pointed at by `$90BC` |
| `$9211`-`$9261` | 81 | Object definitions |

## The script interpreter lives in bank 11

`$06E7`/`$06E8` is a **bank 11** pointer, not bank 12 - bank 11 is switched in by the far
call before the interpreter dereferences it.

Bank 11 `$9033` walks the script byte by byte. Bytes `< $F0` are text; `>= $F0` dispatch
through `DispatchInlineJumpTable` (`$D227`) with the inline table at `$906F`:

| Opcode | Handler |
|---|---|
| `$FF` | `$913E` |
| `$FE` | `$914B` |
| `$FD` | `$9170` |
| `$FC` | `$9176` |
| `$FB` | `$91D0` (line break) |
| `$FA` | `$91F4` |
| `$F9` | `$924E` |
| `$F8` | `$9285` (jump to script address, 2-byte operand) |
| `$F7` | `$92A4` |
| `$F6` | `$92C3` (store byte to a RAM address, 3-byte operand) |
| `$F5` | `$9162` |
| `$F4` | `$92E7` |
| `$F3` | `$9324` |
| `$F2` | `$9343` |
| `$F1` | `$9373` |

Text is **plain mixed-case ASCII**, unlike the menu system's uppercase-only remapping
(see "Text encoding" in `docs/menu_system.md`). The font for it is presumably in the
shared bank 6 `$8000` blob.

```
$9658  F9 00 20 F6 E3 06 00 F8 DC 94 FE FF 06 2C "your total" FB "prize is $" ...
$96EA  F9 00 F6 E3 06 00 "Wow, You've earned quite" FB "a bit of prize money!" ...
```

The block continues into the full winnings-milestone ladder - `$100,000` through
`$1,000,000` and beyond, including *"even the Princess Toadstool Open"*, *"Can I borrow
some money from you?"* and *"You should write to Nintendo Power and tell them of your
incredible feat."* It ends at `$9F1D`; `$9F1E` begins a money-to-digit-string routine
(repeated subtraction of `$64` and `$0A`).

## The three sibling cutscenes

The bank 11 interpreter is ticked from four bank 12 sites. All four are money/DK scenes.

| Tick site | Scene entry | Entered from |
|---|---|---|
| `$9039` | `$8F34` / `$8F38` | club house `$85`; bank 9 `$B0CC` |
| `$96A0` | `$9262` | bank 13 `$804F` |
| `$A462` | `$A35F` / `$A4A4` | bank 9 `$B1A6`, `$B2C8` / `$B1A0` (around `CurrentWager` `$6018`) |
| `$A87F` | `$A7BF` | bank 9 `$B0D7` (`TotalMoney` high byte) |

Their scripts are also in bank 11: pointers `$A0EE`, `$A2D5`, `$A33C`, `$A8A2`, `$AA2F`,
`$ABED`, `$AFDB`, `$B105`, `$B656`, `$B6A3`, `$B6F3`, `$B75F`, `$B8DD`, `$B93C`, `$BBAF`,
`$BC7D`. Bank 11's printable-ASCII span runs `$8886`-`$BEB3` overall, though the tail
(`$BE42` onward - `MASAYUKI ABE`, `HIROSHI SATO`, ...) is the tournament roster, not
dialogue.

## Space inventory

### Exclusive to Prize Money - 4,796 bytes

| Region | Size | Contents |
|---|---|---|
| bank 12 `$8F34`-`$9261` | 814 | Driver, tables, animation cells, object definitions |
| bank 5 `$B4D5`-`$B9FC` | 1,320 | Compressed graphics; only loader is `$8F8B` |
| bank 5 `$BC1D`-`$BCD6` | 186 | Compressed graphics; only loader is `$8F97` |
| bank 5 `$BCD7`-`$BDBC` | 230 | Compressed graphics; only loader is `$8F9D` |
| bank 11 `$9658`-`$9F1D` | 2,246 | DK dialogue scripts |

### Shared with the sibling cutscenes - freed only if all four go

| Region | Size | Note |
|---|---|---|
| bank 11 `$9033`-`$9657` | 1,573 | The interpreter itself |
| bank 11 `$9F1E`-`$A07F` | 354 | Money-to-digit-string formatting (shared status not confirmed) |
| bank 5 `$B9FD`-`$BC1C` | 544 | Also loaded by `$A3C5` and `$A7F2` |
| bank 12 `$A421` | - | Called only from `$8FC6`, but sits inside the `$A3xx` block |

Removing the whole DK-cutscene family would add each sibling's bank 12 block and bank 11
dialogue on top of this - plausibly 15-20 KB in total, though the sibling blocks have not
been individually bounded.

### Not reclaimable

- **bank 6 `$8000`** - six loaders including non-money screens (`$A3B3`, `$A4CC`,
  `$B14B`, `$B831`, `$B903`). Almost certainly the shared mixed-case font.
- **`$8158`, `$80B7`, `$80D6`, `$8208`** (bank 12) - 10-14 callers each; general
  menu/scene infrastructure.

## How the boundaries were established

- **bank 12 `$8F34`-`$9261`**: the object-def list arithmetic lands exactly on `$9262`,
  which is independently a far-call target from bank 13 `$804F`. The only two apparent
  external `JSR`s into the range (`$88B3` -> `$91AD`, `$A64D` -> `$9190`) are false
  positives from scanning data as opcodes: `$88B3` is inside `LDA MenuEntryPtr` and
  `$A64D` is mid-table.
- **bank 5 blobs**: sizes are next-loader-target minus this-loader-target. This holds
  because bank 5 is one contiguous data run `$8000`-`$BDBC` followed by code starting at
  `$BDBD` (`JSR WaitForVblank`). Every blob start was recovered by decoding the inline
  params of all 139 `JSR $D45F` sites in the ROM.
- **bank 11 `$9658`-`$9F1D`**: `$9658` is the first script pointer; `$9F1E` is where
  printable text stops and the digit-formatting code starts.

## Open questions

- The split between interpreter code and shared sub-script fragments in bank 11
  `$94DC`-`$9657`. The `$F8` (jump-to-script) operands inside the Prize Money scripts
  target `$94DC`, `$9511`, `$9554`, `$956B` and `$95D5`, all of which are inside that
  range.
- Whether `$9F1E`'s formatter is genuinely shared with the siblings or merely adjacent.
- Full semantics of opcodes `$FF`-`$F1`; only `$FB` (line break), `$F8` (jump) and `$F6`
  (store to RAM) were decoded.
