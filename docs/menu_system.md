# Title Menu System

> **Note**: This document was written by Claude based on investigation requested by jdharms.

The title-screen menu chain (PLEASE SELECT / STROKE PLAY / ... / CLUB HOUSE) is almost
entirely data-driven. Four parallel tables in bank 12 define every menu: its text, its
options, where each option leads, and what game state the option sets. Adding or removing
menu entries is a pure data edit — no code changes and no relocation.

Everything described here lives in **bank 12** (PRG `0x30000`-`0x33FFF`). Read it with
`golf-rom-peek nes_open_us.nes read '$8B35' --bank 12 --length 88`.

The system is used only for the title menu chain. `CurrentMenuID` is written in exactly
two places (`$8016` on entry, `$892E` on transition) and the driver loop exists at exactly
one site, so there is no in-game pause menu sharing this code.

## Driver loop

`$8000` is the menu root: it resets `MenuHistoryDepth` (`$069C`) to 0, sets
`CurrentMenuID` to 0, and loads the title graphics. The loop proper:

```
$848B  JSR InitMainMenu
MenuInputLoop ($8497):
       LDA Controller_NewPress_Tmp   ; $18
       STA MenuInputByte             ; $0681
       JSR MenuTick                  ; $8698
       LDA PendingMenuID             ; $0689
       BPL MenuInputLoop             ; keep looping while < $80
       ...
$84C1  LDA PendingMenuID
       JSR LD227                     ; inline jump table, see below
```

`PendingMenuID` is the exit signal. Values `$00`-`$14` are ordinary submenus and keep the
loop running; anything with bit 7 set breaks out.

`MenuTick` (`$8698`) branches on `MenuState`: bit 7 set means "menu idle, poll input",
otherwise it runs `ConfirmMenuSelection` to animate the transition into the new menu.

## Button dispatch

`$86A3` is a `JSR LD227` with an inline `{byte, addr_lo, addr_hi}` table terminated by
`$00`. `LD227` does an **exact byte compare** against A, not a mask test, so a
simultaneous two-button press matches nothing and is ignored. It also scans the whole
table and takes the *last* match.

| Byte | Button | Target |
|---|---|---|
| `$80` | A | `$86C5` `OpenSubMenu` |
| `$10` | Start | `$86C5` `OpenSubMenu` |
| `$40` | B | `$8723` `MenuGoBack` |
| `$08` | Up | `$873A` `MenuSelectPrev` |
| `$04` | Down | `$874C` `MenuSelectNext` |
| `$20` | Select | `$874C` `MenuSelectNext` |

## The four tables

All four tables have exactly 22 entries (menu IDs `$00`-`$15`) and butt directly against
each other, which is what confirms the count.

| Table | Stride | Purpose | Ends at |
|---|---|---|---|
| `$8AA2` `MenuSubmenuIdPtrTable` | 2 | -> per-selection list of submenu IDs | `$8ACE` |
| `$8B09` `MenuChoiceHandlerPtrTable` | 2 | -> "apply the choice" handler (`$0000` = none) | `$8B35` |
| `$8B35` `MenuTextListPtrTable` | 4 | two list pointers: static text, then options | `$8B8D` |
| `$8B8D` `MenuTextListData` | — | the string-list data itself | `$8E04` |

### Text list format

Parsed by `ReadMenuTextList` (`$8665`):

```
count                       ; number of entries
ptr_lo, ptr_hi              ; x count
...
entry:  X, Y, ascii..., $FF ; column, row, string, terminator
```

`MenuEntryLength` (`$0692`) is derived by scanning to `$FF` (`LoadMenuEntryPosition`,
`$88AD`), so entry lengths are free-form.

`DrawMenuTextList` (`$8612`) is called twice per menu, with A=0 for the static text list
(e.g. "PLEASE SELECT") and A=2 for the selectable options list. The second call leaves the
option count in `MenuOptionCount` (`$068A`), which is what wraps the selection cursor.

A given entry pointer can be shared across menus — `$8B90` ("PLEASE SELECT") and the
course-select list `$8C65` are each reused by five menus. Editing one changes all of them.

## Menu graph

| ID | Static text | Options | Leads to |
|---|---|---|---|
| `$00` | PLEASE SELECT | STROKE PLAY / MATCH,PLAY / TOURNAMENT / CLUB HOUSE | `$01` / `$05` / `$09` / `$15` |
| `$01` | PLEASE SELECT | 1 PLAYER / 2 PLAYER | `$02` / `$02` |
| `$02` | PLEASE SELECT COURSE | US / JAPAN / UK COURSE | `$03` x3 |
| `$03` | PLEASE SELECT | CONTINUE / NEW GAME | `$FF` / `$04` |
| `$04` | CAN PREVIOUS SAVED GAME BE ERASED? | YES / NO | `$FF` / `$03` |
| `$05` | PLEASE SELECT | 1 PLAYER / 2 PLAYER | `$06` x2 |
| `$06` | (course select) | US / JAPAN / UK | `$07` x3 |
| `$07` | PLEASE SELECT | CONTINUE / NEW GAME | `$FF` / `$08` |
| `$08` | (erase prompt) | YES / NO | `$FF` / `$07` |
| `$09` | PLEASE SELECT | STROKE PLAY / MATCH PLAY | `$0A` / `$0E` |
| `$0A` | PLEASE SELECT | 18H / 36H TOURNAMENT | `$0B` x2 |
| `$0B` | (course select) | US / JAPAN / UK | `$0C` x3 |
| `$0C` | PLEASE SELECT | CONTINUE / NEW GAME | `$FF` / `$0D` |
| `$0D` | $1000 WILL BE DEDUCTED... INTERRUPT TOURNAMENT? | YES / NO | `$FF` / `$0C` |
| `$0E` | PLEASE SELECT | 18H / 36H TOURNAMENT / BET ON 1 HOLE | `$0F` / `$0F` / `$12` |
| `$0F` | (course select) | US / JAPAN / UK | `$10` x3 |
| `$10` | PLEASE SELECT | CONTINUE / NEW GAME | `$FF` / `$11` |
| `$11` | (interrupt prompt) | YES / NO | `$FF` / `$10` |
| `$12` | (course select) | US / JAPAN / UK | `$13` x3 |
| `$13` | PLEASE SELECT | CONTINUE / NEW GAME | `$FF` / `$14` |
| `$14` | (interrupt prompt) | YES / NO | `$FF` / `$13` |
| `$15` | (none) | 9 club house entries | `$81`-`$89` |

`$FF` is the terminal "start the game" code. It falls out of the `$84C1` dispatch table
with no match and lands on `$84E6`, which sets `$07FF`/`$F4` and returns into gameplay.

## Choice handlers

`MenuChoiceHandlerPtrTable` (`$8B09`) is dereferenced by `OpenSubMenu` and called through
`$899F` (`JMP ($22)`). The handler turns the current selection into game state.

| Handler | Used by | Effect |
|---|---|---|
| `$89A2` `ApplyPlayModeSelection` | `$00`, `$09` | if sel < 2: `GolfGameMode = sel * 4` (stroke=0, match=4); always clears `MaybeTwoPlayerFlag` |
| `$89B4` `ApplyPlayerCountSelection` | `$01`, `$05` | `MaybeTwoPlayerFlag = sel` (0 = 1 player) |
| `$89BB` `ApplyContinueSelection` | `$03`,`$07`,`$0C`,`$10`,`$13` | `LoadSavedGameFlag ($04D7) = (sel & 1) ^ 1` — CONTINUE sets it |
| `$89C6` `ApplyTournamentLengthSelection` | `$0A`, `$0E` | if sel < 2: `GolfGameMode = (mode & $FC) \| (sel + 1)`; sel 2 (BET ON 1 HOLE) forces `GolfGameMode = $07` |
| `$89E1` `ApplyCourseSelection` | `$02`,`$06`,`$0B`,`$0F`,`$12` | maps selection through an inline `LookupInlineByteTable` table: US->1, JAPAN->0, UK->2, stores to `CurrCourse`, then `JSR $D939` |
| `$89F8` `ApplyConfirmPromptSelection` | `$04`,`$08`,`$0D`,`$11`,`$14` | YES (sel 0): if `MenuStateBeforeOpen != 0` and `GolfGameMode & 3` then `JSR $D9AD` (erase / deduct); NO: pops the history stack and sets `SuppressMenuHistoryPushFlag` |

Because handlers key off the *selection index*, not the entry text, reordering options
inside a menu changes behaviour. Removing an option only matters if it shifts an index
the handler special-cases.

## Back navigation

`MenuHistoryDepth` (`$069C`) with the stack at `MenuHistoryStack` (`$069D`). `OpenSubMenu`
pushes `CurrentMenuID` whenever the new `PendingMenuID` is < `$80` and
`SuppressMenuHistoryPushFlag` (`$071D`) is clear. B (`$8723`) pops it. The default when
the stack is empty is `$80`, which dispatches to `$84F5` — `PLA PLA; JMP $8000`, i.e. back
out to the title screen.

## Club house dispatch

Menu `$15` is special-cased throughout (`CMP #$15` at `$857E`, `$85D5`, `$8630`, `$87E8`,
`$894C`): it renders on **nametable 1** rather than 0, so `MaybeSetupMenuBackround` sets
`NametableX` to 1, copies the attribute set at `$8ED0` into `CurrentTerrainAttrs`, and
writes it to `$27C0` instead of `$23C0`.

Its nine option codes (`$81`-`$89`, at `$8B00`) exit the loop and dispatch through the
inline table at `$84C4`. Each target does an `ExecuteFarCall` with inline
`bank, lo, hi` and then `JMP $8565`, which unwinds the stack and re-enters the driver at
`$8459`.

| Code | Entry | Handler | Target |
|---|---|---|---|
| `$81` | REGISTER NAME | `$8500` | bank `$0B` `$843E` |
| `$82` | CHOOSE CLUBS | `$850D` | bank `$0E` `$AE14` |
| `$83` | OPTIONS | `$851A` | bank `$0B` `$8B1B` |
| `$84` | PLAYER STATS | `$8527` | bank `$09` `$B519` |
| `$85` | PRIZE MONEY | `$84FA` | local `JSR $8F34` |
| `$86` | TOURNAMENT ROSTER | `$8534` | bank `$0B` `$8000` |
| `$87` | TRAINING | `$8541` | bank `$0E` `$BD04` |
| `$88` | HALL OF FAME HOLES | `$854E` | bank `$0E` `$B420` |
| `$89` | CLEAR SAVED DATA | `$855B` | bank `$0E` `$B8C7` |

`$80` is also in that table (`-> $84F5`) and is the "backed out of the root menu" case.

## Text encoding

Strings are stored as plain ASCII and remapped to tile indices at draw time by
`LookupInlineRangeTable` (`$8A56`), called from `$8863`. That routine takes an inline
table of `(lo, hi, delta)` triples terminated by `$00`, and **the last matching range
wins**. The table at `$8866` is:

```
30 5A 70   ; '0'-'Z'  ->  char + $70
2E 2E 7C   ; '.'      ->  $AA
24 24 87   ; '$'      ->  $AB
3F 3F 6D   ; '?'      ->  $AC   (overrides the 30-5A range)
5F 5F 4E   ; '_'      ->  $AD   (the hyphen in "INTE_/RRUPT")
00
```

Anything not covered — including space **and comma** — falls through to `LDA #$00`, i.e.
tile `$00`, which is blank. That is why "MATCH,PLAY" renders correctly: the comma is just
a blank.

Practical rule for editing text: uppercase A-Z and 0-9 work, `.` `$` `?` `_` work,
everything else renders as a space.

## Selection highlight

Two mechanisms, both driven off `MenuEntryX` (`$0693`), `MenuEntryY` (`$0694`) and
`MenuEntryLength` (`$0692`), which `LoadMenuEntryPosition` fills in:

- **Tiles**: `$AE` written one row above the entry and `$AF` one row below, via
  `WriteMenuTile` (`$8824`).
- **Attributes**: `SetMenuEntryPalette` (`$88D7`) walks the entry's column span calling
  `LD8E9` (attribute-table palette setter), writing palette 1 normally or palette 2 when
  `MenuHighlightPaletteFlag` (`$0695`) is set.
- **Sprites**: `InitMainMenu` allocates four objects via `LF7EE` from the 9-byte
  definitions at `$8F10`. Two of them (`$0699`, `$069A`) are the cursor arrows, moved in
  `MoveMenuCursor` (`$8795`) to `(MenuEntryX - 2) * 8` and
  `(MenuEntryX + MenuEntryLength) * 8`, both at row `MenuEntryY * 8 - 9`. The other two
  (`$0697`, `$0698`) are decorations whose `$78F1` attribute is toggled between `$00` and
  `$FF` depending on whether the club house menu is active.

## PPU transfer descriptors

The inline bytes after `JSR WriteNametableTiles` at `$8637`/`$863F` and `$87EF`/`$87F7`
are a 2-byte pointer to a descriptor, not data. Descriptor format (decoded from `$CE84`
through `$CEE8`):

```
dest_lo, dest_hi     ; PPU address (omitted for WriteNametableTilesMode2, which uses $22/$23)
flags | width        ; width in low 6 bits; bit7 = a 2-byte source pointer follows,
                     ; bit6 = repeat a single byte
height               ; number of rows
[src_lo, src_hi]     ; only if bit7 set, else inline data follows
```

So `$8E04` = `C0 23 A0 02 97 04` means "write 32x2 = 64 bytes from `$0497`
(`CurrentTerrainAttrs`) to `$23C0`", and `$8E0A` is the same thing to `$27C0` for the
club house nametable.

## Editing recipes

### Removing a menu entry

Shorten the count and drop the pointer. Bytes past the new count are simply never read, so
nothing has to be moved.

Removing TOURNAMENT from the main menu is three writes:

| CPU (bank 12) | PRG | From | To | Why |
|---|---|---|---|---|
| `$8BA0` | `0x30BA0` | `04 A9 8B B7 8B C4 8B D1 8B` | `03 A9 8B B7 8B D1 8B` | count 3; drop the TOURNAMENT pointer |
| `$8ACE` | `0x30ACE` | `01 05 09 15` | `01 05 15` | drop the `$09` submenu ID |
| `$8BD2` | `0x30BD2` | `14` | `12` | move CLUB HOUSE up one row so there is no gap |

No handler assumption breaks: `ApplyPlayModeSelection` only special-cases `sel < 2`, and
CLUB HOUSE stays at index >= 2. Menus `$09`-`$14` become orphaned but harmless.

The same recipe works for individual club house entries: edit the count at `$8D64` and the
matching code in the `$8B00` list, and shift the Y coordinates of the entries below it.

Note that the Y coordinate is baked into each entry, so removing an entry from the middle
of a list leaves a visual gap unless the entries below it are moved up.

### Worked example

`golf/core/patches/menu_trim.py` implements all of the above as a proof of
concept: it retitles menu `$00`, cuts the main menu to STROKE PLAY + CLUB HOUSE,
and cuts the club house to five entries. Ten `BytePatch`es, 33 bytes changed,
every one of them length-preserving and inside bank 12.

```python
from golf.core.patches import menu_trim_patch
from golf.core.rom_writer import RomWriter

writer = RomWriter("nes_open_us.nes", "out.nes")
menu_trim_patch(seed=1234).apply(writer)   # or title_text="MY OWN TITLE.."
writer.save()
```

Two things it has to handle beyond the raw table edits, both of which generalise
to any removal:

- **Row gaps.** Y is baked into each entry, so retained entries below a removed
  one have to be moved up.
- **Handler index assumptions.** `ApplyPlayModeSelection` keys off the selection
  index (`sel < 2` sets `GolfGameMode = sel * 4`). Removing MATCH,PLAY and
  TOURNAMENT slides CLUB HOUSE from index 3 to index 1, where it would start
  silently setting match play. The patch tightens the guard to `CMP #$01`.

A longer replacement title also needs somewhere to live: 14 characters need 17
bytes plus a 3-byte list header, and the shared `$8B90` "PLEASE SELECT" entry has
room for 16 and is used by eleven menus. The patch builds a private list for menu
`$00` in the 26 bytes freed by the two removed entries and repoints
`MenuTextListPtrTable[$00]+0` at it, so every other menu is untouched.

### Space budget

Bank 12 is effectively **full**. The largest run of filler is 32 bytes at `$826D`, and the
whole bank has roughly 197 bytes across all runs of 16 or more identical bytes. Removing
entries is free; adding a new menu means finding space in another bank or reclaiming the
strings orphaned by a removal.
