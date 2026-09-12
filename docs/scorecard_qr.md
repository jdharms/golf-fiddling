# Scorecard QR Submission

> **Note**: This document was written by Claude based on a design by jdharms.

At the end of an 18-hole stroke play round the game draws a QR code. Scanning it opens
a URL on the randomizer site; the server decodes the round out of the URL, verifies it
against a per-player MAC, and records the result. This replaces the manual
screenshot-to-Discord-to-spreadsheet flow used in League season one.

The feature lives in the space vacated by the UK course (bank 2, `$837F`-`$A553`, 8,661
bytes — see `terrain_data_locations.md`). Randomized ROMs carry exactly one course, so
that region is permanently available.

## The payload

36 bytes, fixed length.

| Bytes | Size | Field |
|---|---|---|
| 0 | 1 | Protocol version (currently `$01`) |
| 1-8 | 8 | Seed ID |
| 9-12 | 4 | Player ID |
| 13 | 1 | Flags |
| 14-31 | 18 | Hole records, holes 1-18 |
| 32-35 | 4 | HalfSipHash-2-4-32 over bytes 0-31 |

Seed ID, player ID and the MAC key are written at patch time by the randomizer. The
hole records are read out of RAM at round end.

### Hole record

One byte per hole:

```
7 6 5 4   3 2 1 0
+-------+ +-------+
strokes-1   putts
```

Strokes are representable 1-16, putts 0-15. Both clamp on overflow. The stroke range is
the known weak point in this encoding: vanilla counts to 50 per hole, and the mercy
tap-in patch (which caps at 10) is not applied by default, so a blow-up hole can exceed
16 and be recorded as 16. See Open Questions.

### Flags

| Bits | Meaning |
|---|---|
| 0-1 | Player slot: 0 = player 1, 1 = player 2 |
| 2-7 | Reserved, zero |

### MAC

`HalfSipHash-2-4` with 32-bit output, over bytes 0-31, with an 8-byte key unique per
(seed, player). The key is generated at patch time, stored server-side keyed to the
seed and player, and never appears in the manifest.

The MAC'd region is 32 bytes — exactly 8 32-bit words, so the 6502 implementation needs
no partial-word tail handling. This is a reason to keep the MAC'd length a multiple of 4
if the payload layout ever changes.

HalfSipHash is specified for both 4-byte and 8-byte output; the reference implementation
takes an `outlen` of 4 or 8 and the project publishes official test vectors for both
(`vectors_hsip32`, `vectors_hsip64`). The 4-byte variant is the shorter code path: it
skips the `v1 ^= 0xee` / `v2 ^= 0xee` / `v1 ^= 0xdd` steps and the second set of four
finalization rounds.

## The URL

```
https://nesopengolf.com/s/<48 base64url characters>
```

26 characters of prefix plus 48 characters of unpadded base64url — 36 bytes is a
multiple of 3, so there is no `=` padding — for a **74-character URL**.

Keeping the payload length a multiple of 3 is a hard design rule: it keeps base64
pad-free and byte-aligned, which keeps the QR character count constant.

## QR parameters

**Version 5, error correction level M, byte mode.** Capacity is 84 characters, so the
74-character URL leaves 10 characters of headroom — enough to grow the payload to 39
bytes (52 chars, 78-char URL) or 42 bytes (56 chars, 82-char URL) without changing any
QR geometry. 42 bytes is the ceiling.

| Property | Value |
|---|---|
| Modules | 37 x 37 |
| Alignment patterns | one, centred at (30, 30) |
| Dark module | row 29, col 8 |
| Function modules | 290 |
| Free (data region) modules | 1,079 |
| Total codewords | 134 |
| Remainder bits | 7 |
| Blocks | 2, equal |
| Per block | 43 data + 24 EC codewords |
| Data codewords | 86 |

Two equal blocks make interleaving an alternating copy rather than the ragged-block
case. (Version 5-L is a single block with no interleaving at all and 106 characters of
capacity, but only 7% error correction. Interleaving costs about 40 bytes of 6502, so
M is worth paying for. 5-L stays available as an escape hatch if the payload ever
outgrows 42 bytes.)

### Bit stream is nibble-aligned

The mode indicator is 4 bits and the byte-mode character count is 8 bits for versions
1-9, so the 12-bit header puts every payload character on a nibble boundary. Building
the data code words is a nibble-shift loop, not a general bit packer.

With a fixed 74-character URL the whole stream shape is a compile-time constant:

```
codeword 0      $44                                      ; 0100 mode, $4 = high nibble of 74
codeword 1      $A0 | (url[0] >> 4)                      ; $A = low nibble of 74
codeword n      ((url[n-2] & $0F) << 4) | (url[n-1] >> 4) ; for n = 2..74
codeword 75     (url[73] & $0F) << 4                     ; 4-bit terminator in the low nibble
codewords 76-85 $EC $11 $EC $11 ...                      ; 10 pad codewords
```

**Code words 0 through 27 are constant** and live in ROM as a 28-byte table. The first
26 characters are the URL prefix, which covers code words 0-26 and half of 27; the
other half of 27, and the top of 28, come from the first base64 character, which is
always `A` because it encodes the top six bits of the protocol version byte. Only 58
of the 86 data code words actually vary.

### Mask

**The mask is fixed at 5**, and its format-information bits are baked into the static
matrix table. A fixed mask still produces a fully conformant code — decoders read the
mask out of the format info — and it removes the penalty-scoring pass, which is the
single largest and fiddliest part of a QR encoder.

The cost is moved off-cart to `golf-qr-validate`; see Mask Selection below for what it
measured.

### Placement

Standard zigzag: column pairs right to left, skipping the timing column (6), alternating
upward and downward, right column before left within each pair, skipping function
modules.

The static matrix is a 1,444-byte ROM table, one byte per cell, carrying the three
finders and their separators, both timing patterns, the alignment pattern, the dark
module, and both copies of the format info. The walker copies it to scratch RAM and
places code word bits into the free cells. No separate function-pattern mask, no bit
packing anywhere in the placement, masking, or tile-lookup stages.

Trading 1,444 bytes of an 8,661-byte budget for that simplification is the central
implementation decision on the ROM side, and the table's two departures from the
reference matrix each buy more of the same:

- **The mask is baked into the free cells.** `$00` light and `$01` dark are fixed
  modules; `$FE` and `$FF` are free, with the mask bit in bit 0. Placing a bit is
  `cell & 1` xor the data bit, and `cell >= $FE` is the entire free-module test, so
  there is no mask predicate on cart at all. Mask 5 is `(r*c) % 2 + (r*c) % 3 == 0` —
  two multiplies and two modulos per module, 1,079 times — and none of it exists.
- **A row and a column of `$00` padding**, making the grid 38x38. 37 is odd, and the
  tile builder reads 2x2 blocks of modules: the padding is what lets the last tile of
  each axis be read with no bounds test, and it makes the walker's vertical step a
  constant 38.

## NES rendering

**4 pixels per module.** 37 modules = 148 px; the spec's 4-module quiet zone adds 16 px
per side for 180 x 180.

At 4 px per module an 8x8 tile holds exactly 2x2 modules, so with the QR origin on a
tile boundary the entire code is drawn from **16 distinct tiles** — every combination of
four 4x4 quadrants. Tile index convention:

```
bit 3 = top-left     bit 1 = bottom-left
bit 2 = top-right    bit 0 = bottom-right     (set = dark)
```

The code occupies **19 x 19 tiles** (37 modules is 18.5 tiles; the last row and column
of tiles are half quiet zone, which is light anyway). 361 nametable bytes, 256 bytes of
CHR.

### Screen layout

Origin at tile (col 7, row 5), i.e. pixel (56, 40). The code spans tile columns 7-25 and
rows 5-23, leaving 56 px of clear space left, 52 px right, 40 px above and 52 px below —
all far beyond the 16 px quiet zone the spec asks for. Captions sit on row 1 above and
rows 26 and 28 below, still leaving 24 px of clear margin above the code and 20 px
below. Row 27 is left blank because the card font's glyphs are seven pixels tall in an
eight-pixel tile, and two caption lines in adjacent rows touch.

| Row | Caption |
|---|---|
| 1 | `PLAYER 1` / `PLAYER 2` |
| 26 | `SCAN TO SUBMIT` |
| 28 | `HOLD UP SELECT A` |

The captions are drawn in **the scorecard's own font**, already in bank 2 and reloaded
by the QR screen rather than assumed still resident (`LoadCompressedGraphics` with
`.db $02, $69, $B4`, landing at PPU `$1000`). It covers `A`-`Z`, `0`-`9` and space, so
the dismissal hint is worded without punctuation. The 16 QR tiles go to PPU `$1800`,
tile `$80`, clear of the font's `$00`-`$7F`; that is where the nametable builder's tile
base comes from.

Only two colours are needed, so a single palette covers the whole screen and the
attribute table is all zeroes. Universal backdrop `$30` (white) makes the quiet zone
free: the all-light QR tile is the blank tile, and the screen is cleared with it. Colour
1 is `$0F` (black) for the modules — and so is colour 2, which is the only colour the
title font draws in.

Rendering is off while the screen is built, so the nametable, CHR and palette all go out
in one pass with no vblank budgeting. That is also what makes direct `$2006`/`$2007`
writes safe: `NMIHandler` tests the mask shadow `$12` first and, with rendering off,
skips the OAM DMA, the PPU update queue and the scroll write entirely — only the music
engine runs.

## ROM-side plan

### Hook

**The round-over path, bank 13 `LD_84F9`.** `LD_84C5` decides the round is finished with
`LDA GameProgress : LDX GolfGameMode : CMP HolesPerRoundTable ($85D2),X : BCS LD_84F9`,
so `LD_84F9` runs exactly once per completed round, with `GameProgress` equal to the
holes the mode requires (18 for mode 0). From there:

```
$851D  JSR ExecuteFarCall  .db $09, $8F, $B3
$8523  JSR ExecuteFarCall  .db $02, $76, $AE   ; DrawScorecardScreen, bank 2
$8529  LDA #$0A : STA MusicRequest             ; the round-end jingle
$852D  JSR $85BA                               ; wait for A or B on the scorecard
$8530  ...                                     ; mode dispatch; single-round modes
                                               ; fall into LD_858C -> JMP LD_8000
```

The splice is **a two-byte edit of the `JSR` operand at `$852E`-`$852F`**, pointing it at
a 10-byte trampoline in bank 13's tail padding (`$BF83`-`$BFAE`, 44 bytes free below the
seeded-wind trampoline at `$BFAF`):

```
QrAfterScorecard:
    JSR LD_85BA_WaitForScorecardInput   ; what the site used to call
    JSR ExecuteFarCall
    .db $02, <QrRoundEnd, >QrRoundEnd
    RTS
```

`$85BA` is also called from `$8599` on the tournament path; repointing only the `$852D`
call leaves that alone. Everything else — which modes qualify, whether the round is
real — is decided in bank 2, where there is room: `GolfGameMode` `$0100` must be `$00`
(18-hole stroke play) and `PlayerCount` `$9A` says whether a second code is owed.

`ReturnToMainMenu` (bank 12 `$9A8A`) is **not** the hook. `find-refs` gives it exactly one
reference — the `BNE` at `$9A82` — inside the standee scene's two-option prompt, which
means it only fires when the player picks the exit option; a player who finishes a round
and immediately starts another would never see a code. By then `GameProgress` is also
`$00`, zeroed unconditionally at bank 13 `$8018` on the way back through `LD_8000`, so the
gate there would have to be "hole 18's stroke byte is not `$FF`" instead. The per-hole
arrays themselves are still intact at that point, so the site remains a usable fallback:
a 3-byte `JMP` over `LDA GolfGameMode` at `$9A8A`, with a 12-byte trampoline in bank 12's
tail padding (`$BFD7`-`$BFF2`, 28 bytes, claimed by no existing patch) that far-calls,
re-executes the `LDA`, and jumps back to `$9A8D`.

### The springboard to bank 2

`ExecuteFarCall` (`$D372`, fixed bank) is the whole answer: `JSR` plus three inline bytes
`bank, lo, hi`, six bytes at the call site. It saves A/X/Y in `$30`-`$32`, pushes
`CurrentBank` `$5C`, reads the inline bytes off its own stacked return address, switches
via `BankSwitchRoutine`, advances the return address past them, restores A/X/Y for the
callee, `JSR`s a `JMP ($4E)` trampoline, then restores the previous bank and returns with
A, X and the flags intact.

A long-running routine in bank 2 is safe across NMIs: `NMIHandler` (`$D2BF`) saves `$5C`,
pages in bank 14 for the music engine, and restores `$5C` afterwards — unless
`BankSwitchLock` `$61` is set, which is exactly the window `BankSwitchRoutine` holds it
for. It also does the OAM DMA, `ProcessPpuBuffer`, `ApplyScrollSettings`,
`ProcessBothControllers` and `INC VblankFlag` `$13`, so the QR screen's input loop can
pace on `$13` and read the controller state the NMI maintains.

`BankSwitchRoutine` (`$D352`) is the raw form — `LDA #bank : JSR $D352`, no restore. Using
it means saving and restoring `$5C` by hand (14 bytes for a call-and-return, against six),
so it is only worth it if the QR routine ever needs to page a third bank in mid-run.

### Data sources

Confirmed by disassembly (`scorecard.md` has the scorecard's own reading of them):

| Data | Address | Notes |
|---|---|---|
| Per-hole strokes | `$0134 + player * 36 + hole` | binary, not BCD |
| Per-hole putts | `$017C + player * 18 + hole` | binary |
| Holes played | `GameProgress` `$95` | `$12` at the hook |
| Player count | `PlayerCount` `$9A` | |

`LD_8392_CommitHoleScores` (bank 13 `$8392`) writes both arrays at each hole's end,
indexed by `GameProgress` plus a per-player stride from `$83CC` (strokes) and `$83CA`
(putts); putts are only written for stroke-play modes (`GolfGameMode < 4`).

`LD_80C4_ClearPerHoleStrokes` (bank 13 `$80C4`) is the only clear of the strokes array —
`LDX #$47 : LDA #$FF : STA $0134,X : DEX : BPL` — and it runs at **round setup**, not
round end. So `$FF` means "hole not played", and the arrays hold the finished round from
the last hole's commit until the next round is set up. The vanilla scorecard reads them
from bank 2 two instructions before the splice point, which is the strongest available
evidence that they are live there; a Mesen breakpoint on the trampoline is the cheap
confirmation before writing the payload builder.

### Getting the tiles into CHR-RAM

The cartridge has no CHR ROM, so every screen uploads its own patterns through the
`$D4C3` stream codec (`golf/core/graphics_codec.py`, `docs/course_intro_scene.md`). That
codec has a literal mode, and its long form reaches 1,024 bytes, so **the 16 QR tiles go
up as a single literal stream with no new cart code at all**:

```
$E0 $FF   <256 bytes of CHR>   $FF        ; opcode, length-1, data, terminator
```

259 bytes in bank 2, uploaded by the routine the scorecard already uses — `JSR
LoadCompressedGraphics` (`$D45F`) with inline `.db $02, lo, hi`. Round-tripped through the
existing decoder to confirm the opcode encoding and that the 256 bytes land where they
should.

**The display layer does not use it**, and carries the tiles raw instead. The nametable
cannot ride along either way — its 361 bytes are computed per round — so the screen needs
a PPU write loop regardless, and once there is one, pointing it at the raw 256 bytes
costs less than the 3-byte stream wrapper plus a second graphics-table header. The trick
stays recorded here because it is the right answer for any *fixed* pattern data a later
screen wants.

### Scratch RAM

SRAM `$0F9C`-`$17E5` (CPU `$6F9C`-`$77E5`, 2,122 bytes) is inert at round end — it
covers the reclaimed stats/replay region plus the terrain and greens decompression
buffers, none of which are live once the round is over.

Addresses are fixed in `golf/qr/port/layout.py`:

| Use | Address | Bytes |
|---|---|---|
| Module matrix, 38 x 38 | `$7000` | 1,444 |
| HalfSipHash state, key and scratch | `$75B0` | 32 |
| General scratch | `$75D0` | 16 |
| Payload | `$75E0` | 36 |
| URL | `$7610` | 74 |
| Data code words | `$7660` | 86 |
| EC code words | `$76C0` | 48 |
| Interleaved code words | `$76F0` | 134 |
| Reed-Solomon remainder | `$7776` | 24 |
| Nametable (overlaid, see below) | `$75E0` | 361 |

**The nametable deliberately overlays the payload, URL and code word buffers.** Those
378 bytes are all dead once the walk is finished, and without the overlay the total is
2,207 bytes against 2,122 available. The consequence for the display layer: **the URL
string does not survive the nametable build**, so anything that wants to show it as a
caption has to do so first.

The port also borrows four zero page pointers at `$50`-`$57` — the graphics
decompressor's state (`CompressedDataPtr`, `BaseAddrCopy`, `PpuWriteAddr`,
`CompressionLookbackPtr`). No decompression is ever in flight while this routine owns the
CPU and the NMI does not touch them, but a call to the game's graphics routines clobbers
all four, so nothing may be held across one.

### ROM budget

Measured, not estimated: table sizes come from `golf-qr-tables`, code sizes from
`golf-qr-port`.

| Item | Bytes |
|---|---|
| Static matrix table | 1,444 |
| GF(256) antilog + log tables | 512 |
| RS generator polynomial | 25 |
| 16 QR CHR tiles | 256 |
| base64url alphabet | 64 |
| Constant code word head | 28 |
| **Tables subtotal** | **2,329** |
| Payload builder | 155 |
| base64url encoder and URL assembly | 136 |
| HalfSipHash-2-4-32 | 361 |
| Data code word builder | 82 |
| Reed-Solomon encoder | 136 |
| Interleaver | 45 |
| Matrix copy | 46 |
| Placement walker | 201 |
| Nametable builder | 154 |
| Entry point, URL prefix, patch-time constants | 82 |
| Display layer: screen, captions, dismissal | 446 |
| **Code subtotal** | **1,849** |
| **Tables plus code** | **4,178** |

At the origins the port currently assembles against — `$8400` for the tables, `$8E00`
for the code — the image spans 4,409 bytes including the page-alignment gap between the
two, leaving **4,252 bytes of the 8,661-byte region** spare for the patch integration and
anything that comes after. `golf-qr-port` prints all of this.

### Table export

`golf-qr-tables` (`golf/qr/tables.py`) emits the seven tables above. Every one is
*derived* from the reference implementation rather than transcribed beside it — the
static matrix from `encoder.build_static_matrix`, the GF pair from `galois`, the code
word head from `encoder.data_codewords` run on a dummy URL — so a change to the encoder
changes the export and cannot leave the ROM carrying a stale copy.

```bash
golf-qr-tables                             # print the layout and checksums, write nothing
golf-qr-tables data/qr --origin '$8400'    # write the tables, with CPU addresses
```

It writes `qr_tables.bin` (the flat 2,329-byte blob), `qr_tables.inc` (`.byte`
directives, one label and one `...End` label per table), `qr_tables.json` (sizes,
offsets, addresses, SHA-256s and the constants they were built from) and one `.bin` per
table. A checked-in copy at `data/qr/` is the reference for the 6502 work.

Blob order is `antilog`, `log`, `chr`, `base64`, `codeword_head`, `generator`,
`static_matrix`. The two 256-byte GF tables lead so that a page-aligned origin makes both
page-aligned, which is the only layout constraint the 6502 side has; the manifest reports
whether that actually held. The static matrix is written one QR row per line, 37 bytes, so
the include reads as the picture it is.

The 28-byte code word head's *length* is derived too: the exporter encodes two URLs that
differ in every variable character, keeps what they agree on, and fails if the code word
just past the head does not differ. It also refuses to build a head if the protocol
version ever exceeds 3, since the first base64 character is only constant while the
version byte's top six bits are zero.

`tests/unit/test_qr_tables.py` checks each table against something other than the code
that built it: the GF tables against carry-less multiplication done longhand, the
generator polynomial against its own 24 roots, the static matrix module-for-module
against `qrcode` for all eight masks, the CHR against its decoded pixels, the code word
head against real encoded rounds. The EC stage is re-implemented there as the LFSR the
6502 runs, reading only the exported bytes, and must reproduce the encoder's output.

### The 6502 port

`golf/qr/port/` is the cartridge implementation, written as assembly and assembled by
`golf/core/asm6502.py`, an in-repo two-pass assembler. Keeping the assembler in the repo
means the tests can assemble the routine and run it under py65 with no external
toolchain; it is itself checked byte-for-byte against `ca65` where cc65 is installed.

```bash
golf-qr-port                     # per-routine sizes and what is left of the region
golf-qr-port --asm               # the assembled source, constants and all
golf-qr-port -o build/qr.bin     # tables plus code, as spliced into bank 2
```

Sources assemble against `layout.symbols()`, so no `.s` file hardcodes an address and
the ROM table addresses come from the phase-3 exporter itself. The URL prefix, the
payload geometry and the per-build seed, player IDs and MAC keys are generated into the
source from `golf.qr.payload`, so the domain exists in exactly one place.

| Entry point | What it does |
|---|---|
| `QrBuildCode` | the whole pipeline for the player slot in A |
| `QrBuildPayload` | 36 bytes from the game's score arrays, MAC included |
| `QrHashMac` | HalfSipHash-2-4-32 over the payload body |
| `QrBuildUrl` | prefix plus 48 base64url characters |
| `QrBuildCodewords` | the 86 data code words, off the constant head |
| `QrReedSolomon` | 24 EC code words per block, LFSR form |
| `QrInterleaveCodewords` | the 134-byte interleave |
| `QrCopyMatrix` / `QrWalkMatrix` | static matrix to RAM, then the placement walk |
| `QrBuildNametable` | the 19x19 nametable |

Two specializations worth recording, both from the payload being a fixed 36 bytes:

- **HalfSipHash has no tail path.** The MAC'd body is 32 bytes — exactly 8 whole words —
  so the spec's final block is the message length in the top byte and nothing else:
  the constant `$20000000`. Together with `outlen = 4` skipping the `$EE`/`$DD` tweaks
  and the second finalization, the whole routine is 361 bytes.
- **Rotations go the short way round.** The round schedule wants rotate-left by 5, 16,
  8, 7 and 13. Each is a whole-byte rotation plus at most three single-bit ones —
  `rotl 5` is `rotl 8` then `rotr 1` three times — instead of up to thirteen shift-and-
  carry passes.

The whole pipeline runs in about 106,000 instructions and 367,000 cycles — a fifth of a
second, or twelve frames — once per player at the end of a round. It is not on a frame
budget: rendering is off and the screen is not drawn until it finishes.

#### Differential tests

`tests/unit/test_qr_port.py` runs the port under py65 with the exported tables in place
and compares **every stage** against `golf.qr` for the same round: payload, MAC, URL,
data code words, error correction, interleave, module matrix, nametable. Then it takes
the 6502's own nametable, renders it through the CHR pipeline, and decodes it with
zxing-cpp — a self-consistently wrong port cannot pass that. Hole records are checked at
the clamping edges (17+ strokes, 16+ putts, the `$FF` of an unplayed hole, and a
corrupt-RAM zero), and both player slots are checked to read their own IDs, keys and
score arrays and nobody else's.

### The display layer

`display.s`, 446 bytes. `QrShowCodes` is the whole screen flow: build the code for a
slot, draw it, wait to be dismissed, and go round again for player 2 when `PlayerCount`
`$9A` says there is one.

`QrDrawScreen` turns rendering off (`$CDB3`), parks every sprite off-screen (`$D291`),
reloads the card font, uploads the 16 QR tiles, blanks the nametable and attribute
table, writes the 19x19 block one row per PPU address, draws the three captions, uploads
the palette, sets `PpuCtrl_Cache` `$10` to `$90` (NMI on, background patterns at
`$1000`), `$11` to `$1E`, zeroes the scroll, and turns rendering back on (`$CDBE`).

### Installing it: the patch

`golf/core/patches/scorecard_qr.py`, driven by `golf-patch-qr`:

```bash
golf-patch-qr rom.nes -o out.nes --manifest keys.json
golf-patch-qr rom.nes --validate-only
```

Three writes: the 4,420-byte image (tables, routine, credentials) into bank 2 from
`$8400`; the ten-byte trampoline into bank 13's tail padding at `$BF83`; and the two-byte
splice at `$852E` that repoints the post-round wait at it.

**This patch does not verify the bytes it overwrites**, unlike `BytePatch`. The region
write is four kilobytes of vanilla course data and carrying a copy to compare against
would be absurd. What it verifies instead is the hook: the six-byte far call to
`DrawScorecardScreen` at `$8523`, the vanilla `JSR $85BA` operand, and that the
trampoline's ten bytes are still `$FF` padding. That is a precise enough anchor to
catch a wrong ROM or a rearranged routine. A future "reclaim" patch that fills the freed
region with `$FF` would let this one assert on the region too.

Each build gets a fresh seed ID, one player ID per slot and one MAC key per slot, written
into placeholders the assembler reserved (`QrSeedId`, `QrPlayerId`, `QrMacKey`). They
default to zero, so **a ROM that was never patched produces an all-zero seed and player
ID** — something the server rejects rather than silently accepting. `--manifest` writes
the credentials out as JSON; the keys are secret and nothing else prints them.

`tests/integration/test_qr_patch_rom.py` applies the patch to the real ROM, checks that
exactly those three regions change, then reads bank 2 back out of the patched file, runs
it in the simulator, and decodes the screen it draws — the whole chain from
`golf-patch-qr` to a scannable, MAC-verifying code.

### Dismissal

The QR screen is not re-summonable; instead it is deliberately hard to leave by
accident. Dismissal requires **Up + Select + A held for three seconds** — `$A8` in
`Controller_Current` `$14`, on either controller, for 180 consecutive frames, with a
release resetting the count. It advances rather than exits: player 1's code, then player
2's, then the menu. A player who walks away from a finished round comes back to a
still-displayed code.

#### Tested through video memory

`sim.Machine` models the slice of the PPU the display layer uses — an address latch,
VRAM, OAM — and stubs the five fixed-bank routines the port calls at their real
addresses, so the assembled code under test is byte-identical to what goes on cart.
`tests/unit/test_qr_display.py` therefore checks the screen as drawn rather than as
intended: the CHR at `$1800`, the palette, that every tile outside the code and captions
is blank, that the attribute table is zero, that the quiet zone is clear, and that the
`LoadCompressedGraphics` call really carries bank 2 and `$B469`.

The end-to-end test pulls the 19x19 block back out of the nametable, decodes it through
the CHR the 6502 uploaded, and hands it to zxing-cpp: **the QR is read out of simulated
video memory, not out of the encoder.** The dismissal gesture is driven frame by frame
through the `WaitForVblank` stub — 180 frames to dismiss, a release at frame 100 pushing
it to 280, incomplete gestures never dismissing, extra buttons not breaking it — and the
two-player flow is checked to produce two different screens that decode to the two
players' own URLs.

### Testing a build without playing eighteen holes

The round-over path is the only way in, so a test still has to hole out once — but the
seventeen holes before it can be written straight into RAM. Start an 18-hole stroke play
round (`GolfGameMode` `$0100` = `$00`), and before holing out on the current hole:

| Address | Set to |
|---|---|
| `$94` `HoleNumber` | `$11` (hole 18) |
| `$95` `GameProgress` | `$11` (seventeen holes played) |
| `$0134`-`$0144` | per-hole strokes for holes 1-17, e.g. `$04` |
| `$017C`-`$018C` | per-hole putts for holes 1-17, e.g. `$02` |

Then hole out. `LD_8392_CommitHoleScores` writes the current hole at index `GameProgress`
— so hole 18 lands at `$0145`/`$018D` — the counters increment to `$12`, `LD_84C5` sees
the round is over, and the scorecard appears. Press A or B and the QR screen follows.

The strokes array is `$FF`-filled at round setup, so any hole left unwritten clamps to 16
strokes in the payload rather than reading as a zero. For the second player, the same
arrays at `$0158` (strokes) and `$018E` (putts), with `PlayerCount` `$9A` = 1.

## Server contract

- `GET /s/<48 chars>` decodes the payload, recomputes the MAC with the key stored for
  that (seed, player), and records the round.
- **First submission per (seed, player) is authoritative.** Anything after it is
  rejected.
- Two players on one cart are treated as teammates. Player slot 1 submissions are
  attributed to the cart's player ID in the second slot of a team entry.

The MAC's purpose is to stop a player submitting a scorecard *as someone else*, which a
per-(seed, player) key does. It is not a defence against a player forging their own
score; implausible scorecards are handled by a human on the backend.

## Reference implementation

`golf/qr/` is the oracle for the 6502 port. It is written to produce byte-for-byte the
same intermediates the ROM will, and every stage is exposed individually
(`encoder.encode_stages`) so the port can be tested one stage at a time rather than
only on the finished matrix.

| Module | Contents |
|---|---|
| `halfsiphash.py` | HalfSipHash-2-4, both output lengths |
| `payload.py` | the 36-byte payload, hole records, base64url, URL assembly, MAC verify |
| `galois.py` | GF(256) tables, generator polynomial, Reed-Solomon |
| `encoder.py` | version 5-M encoder: code words, EC, interleave, static matrix, walk, mask, penalty |
| `nes.py` | the 16 CHR tiles, the 19x19 nametable, screen placement, and the reverse path |
| `render.py` | PNG rendering, through the CHR and nametable |
| `capture.py` | simulated capture conditions |
| `decode.py` | zxing-cpp and OpenCV decoders |
| `submission.py` | round -> URL -> QR -> NES bytes, at the fixed mask |
| `sample.py` | plausible random rounds |
| `tables.py` | the ROM tables, derived from all of the above |

Three tools drive it: `golf-qr-preview` renders a payload to PNG, `golf-qr-validate`
runs the mask sweep, and `golf-qr-tables` exports the ROM tables.

Correctness is pinned three ways:

- **Structurally**, module for module against `qrcode`, an independent implementation of
  the same spec, for every mask and at the capacity edges. This is the check the 6502
  port will be held to in turn.
- **Semantically**, by decoding real renders with two independent decoders.
- **Against the reference vectors** for HalfSipHash — all 64 `vectors_hsip32` and all 64
  `vectors_hsip64` cases from veorq/SipHash.

The renderer deliberately works from the CHR and nametable rather than the module
matrix, so a mistake in the tile pipeline shows up in the picture and in the decode
tests, not just in a unit assertion.

## Mask selection

Raw sweep output is in `scorecard_qr_mask_sweep.md`.

`golf-qr-validate -n 100` — 100 random rounds x 8 masks x 11 simulated capture
conditions x 2 decoders, 17,600 decodes:

- **zxing-cpp decoded every single image, under every mask.** It is the closest
  stand-in for what phone scanners run, so on that evidence any mask is viable and a
  fixed mask is safe.
- **Every failure came from OpenCV's detector.** 800 of 925 were the `scanlines`
  condition, where OpenCV fails 100% of the time on all eight masks — a limitation of
  its binarizer, carrying no information about masks.
- Excluding `scanlines`, OpenCV failures per mask out of 1,000: **mask 5 is best at 7**,
  then 0 (11), 1 and 3 (13), 4 (15), 6 and 7 (20), 2 (26).

A confirmation run on a different seed — `-n 250 --masks 0,2,5`, another 8,250 zxing
decodes with again zero failures — reproduces mask 5 as the best: OpenCV failures out
of 2,500 were 21 for mask 5, 31 for mask 2, 36 for mask 0. Pooling both runs, mask 5
fails 0.80% of OpenCV attempts against 1.34% for mask 0 and 1.63% for mask 2.

Note what did *not* replicate: mask 2 came out worst in the first run and middling in
the second, so the ordering below the top is within noise. Mask 5 being best held in
both.

Hence **mask 5**, recorded as `submission.FIXED_MASK` and pinned by
`tests/unit/test_qr_submission.py`, which re-runs every capture condition against both
decoders.

Worth recording: **the spec's penalty heuristic is not predictive of decoder
robustness here.** It scores mask 2 best in both runs — lowest mean penalty, and the
mask it would have chosen for 51 of 100 and 113 of 250 rounds — while mask 2 measured
no better than mask 5 either time. Implementing penalty scoring faithfully on cart
would have cost several hundred bytes of the fiddliest code in the encoder and chosen a
mask no more robust than the one picked by measurement.

The condition that most often costs decode margin is `aspect`, the 8:7 horizontal
stretch a real display applies — the top or joint-top non-scanline failure mode for six
of the eight masks. Worth remembering if the payload ever grows and the module count
goes up.

## Work phases

1. **Python reference implementation** — *done*, `golf/qr/`.
2. **Offline validation harness** — *done*, `golf-qr-validate`; mask chosen, see above.
3. **Table export** — *done*, `golf-qr-tables`; 2,329 bytes, see Table export above.
4. **6502 implementation** — *done*, `golf/qr/port/`; 1,403 bytes, every stage
   differentially tested against the oracle. See The 6502 port above.
5. **Display layer** — *done*, `golf/qr/port/display.s`; 446 bytes, tested through
   simulated video memory. See The display layer above.
6. **Patch integration** — *done*, `golf-patch-qr`; three writes, credentials inserted
   at patch time. See Installing it above.
7. **Server endpoint.**

Phases 1-5 touch no ROM: the port is assembled and tested entirely in the repo, and
nothing is spliced into a cartridge until phase 6.

## ROM investigation

Settled above: the hook site and its single reference, the springboard, the score arrays'
encoding and liveness, and the CHR upload. Space in bank 2 is not investigated and does
not need to be — a randomized ROM cannot reach course 3's data once course mirroring and
menu trimming remove any way to play a round on it.

### Confirmed on an emulator

A ROM built by `golf-patch-qr` was played to the end of a round (jdharms, 2026-09-12,
seventeen holes written into `$0134`/`$017C` by hand and the eighteenth played out) and
the code on screen was scanned with a phone. It read:

```
https://nesopengolf.com/s/AR_cbT0P8ylmKPnlHAAiMTJBIjIxQkIxMiEyMjFCMjFnxQAZ
```

which decodes to the ROM's own seed ID and slot 0 player ID, verifies against slot 0's
MAC key and fails against slot 1's, and carries all eighteen holes — including the
played one, so `LD_8392_CommitHoleScores` is confirmed as well as the array liveness.
Both gates passed, which means `GolfGameMode` is `$00` and `GameProgress` is at least 18
at the hook.

That settles what was owed: the arrays are live at the splice, the trampoline fires, the
far call lands, and the screen the display layer draws is scannable off a real display.
The one thing still unobserved is whether anything the scorecard's input wait tail-calls
(`$D83C`) leaves the PPU in a state the QR screen has to undo beyond its own `$CDB3` /
`$CDBE` pair — and the scan above is evidence that it does not.

## Open Questions

- **Stroke field width.** 4/4 gives strokes 1-16 and putts 0-15. A 5/3 split gives
  strokes 1-32 and putts 0-7. Clamping putts leaves the total score valid; clamping
  strokes does not. An 8-putt is more likely than a 17-stroke hole, which argues for
  4/4; the asymmetry in what clamping costs argues for 5/3. Making the mercy tap-in
  mandatory in randomized ROMs would settle it in favour of 4/4. Currently 4/4.

  The split lives in one constant, `payload.STROKE_BITS`, and both candidates are
  covered by tests, so changing it is a one-line edit rather than a hunt for hardcoded
  nibbles. It does not affect the QR geometry either way.
- **Domain.** Whatever host is chosen is baked into every ROM ever generated and
  `/s/` has to keep working indefinitely.

