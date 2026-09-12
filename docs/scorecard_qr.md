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

The static matrix is a 1,369-byte ROM table, one byte per module, holding `$00` light,
`$01` dark, and `$FF` for a free data module. It carries the three finders and their
separators, both timing patterns, the alignment pattern, the dark module, and both
copies of the format info. The walker copies it to scratch RAM and places codeword bits
into the `$FF` cells, applying the mask as it goes. No separate function-pattern mask,
no bit packing anywhere in the placement, masking, or tile-lookup stages.

Trading 1,369 bytes of a 8,661-byte budget for that simplification is the central
implementation decision on the ROM side.

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
all far beyond the 16 px quiet zone the spec asks for. Tile rows 0-1 above and 26-29
below are available for a caption, which still leaves 24 px of clear margin above the
code and 20 px below — both over the 16 px minimum.

Only two colours are needed, so a single palette covers the whole screen and the
attribute table is irrelevant. Universal backdrop `$30` (white) makes the quiet zone
free: any all-zero tile reads as quiet zone. Colour 1 is `$0F` (black).

Rendering is off while the screen is built, so the nametable, CHR and palette all go out
in one pass with no vblank budgeting.

## ROM-side plan

### Hook

`ReturnToMainMenu`, which runs when a round ends. It is also reachable by quitting
mid-round, so the QR screen is gated on the round actually being complete — the cheapest
test is a recorded score for hole 18.

Bank 2 is a switchable bank, so the hook needs a trampoline that pages bank 2 in, runs
the routine, and restores the previous bank. The MMC1 PRG bank register lives at
`$E000`-`$FFFF` in the fixed bank, so the switch itself is callable from anywhere; the
routine must be self-contained while bank 2 is mapped.

### Data sources

From `scorecard.md`:

| Data | Address |
|---|---|
| Per-hole strokes | `$0134 + player * 36 + hole` |
| Per-hole putts | `$017C + player * 18 + hole` |
| Holes played | `GameProgress` `$95` |
| Player count | `PlayerCount` `$9A` |

### Scratch RAM

SRAM `$0F9C`-`$17E5` (CPU `$6F9C`-`$77E5`, 2,122 bytes) is inert at round end — it
covers the reclaimed stats/replay region plus the terrain and greens decompression
buffers, none of which are live once the round is over.

| Use | Bytes |
|---|---|
| Module matrix (1 byte per module) | 1,369 |
| Interleaved code words | 134 |
| URL string | 74 |
| HalfSipHash state and scratch | ~32 |
| **Total** | **~1,609** |

About 513 bytes spare of the 2,122 available.

### ROM budget

Table sizes are measured from the reference implementation; code sizes are estimates.

| Item | Bytes |
|---|---|
| Static matrix table | 1,369 |
| GF(256) antilog + log tables | 512 |
| RS generator polynomial | 25 |
| 16 QR CHR tiles | 256 |
| base64url alphabet | 64 |
| Constant code word head | 28 |
| **Tables subtotal** | **2,254** |
| Reed-Solomon encoder | ~150 |
| Bit stream builder | ~80 |
| Interleaver | ~60 |
| Placement walker + mask | ~200 |
| HalfSipHash-2-4-32 | ~400 |
| base64url encoder | ~100 |
| Nametable / CHR upload | ~150 |
| Screen setup, input loop, glue | ~600 |
| **Total** | **~4,000** |

Roughly half of the 8,661-byte region.

### Dismissal

The QR screen is not re-summonable; instead it is deliberately hard to leave by
accident. Dismissal requires **Up + Select + A held for three seconds**. A player who
walks away from a finished round comes back to a still-displayed code.

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

Two tools drive it: `golf-qr-preview` renders a payload to PNG, and `golf-qr-validate`
runs the mask sweep.

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
3. **Table export** — emit the static matrix, GF tables, generator polynomial, CHR and
   constant code word head as ROM tables.
4. **6502 implementation**, differentially tested against the oracle.
5. **Display layer** — screen setup, caption, dismissal gesture.
6. **Patch integration** — `ROMPatch` in `golf/core/patches/`, seed ID / player ID / MAC
   key insertion at patch time.
7. **Server endpoint.**

Phases 1-3 touch no ROM and carry the bulk of the design risk.

## ROM investigation still owed

Deferred deliberately — none of it blocks phases 1-3.

- Per-hole strokes are at `$0134 + player * 36 + hole` and putts at
  `$017C + player * 18 + hole` (from `scorecard.md`); the encoding — binary or BCD — and
  their liveness at the hook point still need confirming.
- The `ReturnToMainMenu` hook site: whether there is a single entry, whether quitting
  reaches it, and which bank is live there.
- How the game uploads CHR-RAM, so the 16 QR tiles can ride along with this screen's
  font tiles.
- That the mirror patches free the whole `$837F`-`$A553` span in the configuration the
  randomizer ships.

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
