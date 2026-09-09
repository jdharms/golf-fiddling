# Music Engine and Track Format

> **Note**: This document was written by Claude based on investigation requested by jdharms.

The entire audio engine — sequencer, sound effects, and all music data — lives in
**bank 14** (PRG `0x38000`-`0x3BFFF`, CPU `$8000`-`$BFFF`). The only audio data outside
that bank is the DPCM sample set, which sits in the fixed bank at `$C000`-`$CA3F`
(`DmcDrum2Data`, `DmcDrumData`, `DmcUnknownData`).

Music is fully data-driven: a track is an order list of patterns, and a pattern is an
11-byte header plus one contiguous block holding five channel streams. Adding a track
means adding an order list, headers, and stream bytes — no code changes.

Read anything below with, e.g.:

```bash
golf-rom-peek nes_open_us.nes read '$8F2E' --bank 14 --length 88
golf-rom-peek nes_open_us.nes --labels "NES Open Tournament Golf (USA).mlb" disasm '$8899' --bank 14 --count 60
```

## Per-frame entry

The NMI handler switches to bank `$0E` and calls `$8000`:

```
$D2F2  LDA #$0E
$D2F4  JSR SetPrgBank
$D2F7  JSR $8000          ; AudioEngineMain
```

`AudioEngineMain` (`$8000`) does, in order:

1. `$4017 = $C0` (4-step frame counter, IRQ inhibited).
2. Builds the `$4015` enable mask from `SfxActiveFlag` (`$FE`) and `SfxChannelMask` (`$07FE`).
3. `JSR $83C1`, `JSR $8578`, `JSR $8784` — three sound-effect handlers.
4. Reads `$FF`. **While `$FF` is non-zero the music sequencer does not run at all**; on a
   change it resets the sequencer state and re-enables `$4015`. When `$FF` is zero it calls
   `$8899`, the music sequencer.
5. Zeroes `$F0`-`$F4`, the one-shot request registers.

## Control registers

| Addr | Role |
|---|---|
| `$F0`-`$F3` | sound-effect request bytes, consumed and cleared each frame |
| **`$F4`** | **music request** — `$01`-`$17` start that track; any value with bit 7 set (the game always uses `$80`) stops all music. Cleared each frame. |
| `$F5`,`$F6`,`$F7` | ID of the SFX currently occupying each SFX channel (persistent) |
| `$F9` | **currently playing music ID** |
| `$FA`/`$FB` | pointer to the active pattern's stream block |
| `$FC`/`$FD` | scratch (header pointer, then period math) |
| `$FF` | music suspend — non-zero disables the sequencer entirely |
| `$07DC` | music ID latched for the order-list lookup |
| `$07DD` | position within the order list |
| `$07D7` | loop position within the order list |
| `$07CE` | master volume, `$0F` at full; the fade path decrements it |

Note the two pre-existing `.mlb` labels here read the wrong way round: `$FF`
(`MusicRequest`) is the *suspend* gate and `$07FC` (`CurrentMusicID`) only mirrors it. The
actual request register is `$F4` and the playing track is `$F9`.

Starting a track: `LDA #id : STA $F4`. Stopping: `LDA #$80 : STA $F4`. The engine ignores a
request equal to the track already playing only where the caller checks — `$8899` itself
restarts unconditionally, so callers such as the title screen (`bank 12 $8066`) compare
`$F9` first.

## Order lists

**`MusicOrderBaseTable`** — `$8E9E`-`$8EB5`, 24 bytes, indexed by music ID `$00`-`$17`.
Entry `$FF` (ID `$00`) means "no track". The value is an offset into the order data.

**`MusicOrderData`** — `$8EB6`-`$8F29`. A track's list starts at `$8E9F + base`:

- **byte 0** is the *loop position* — the order-list index to jump back to when the list ends.
- **bytes 1..** are order entries, terminated by `$00`.

Entry values:

| Value | Meaning |
|---|---|
| `$00` | end of list — reload position from `$07D7` and keep playing |
| `$01` | set `$07C1 = 1`, then continue to the next entry |
| `$02` | set `$07C1 = 0`, then continue to the next entry |
| `>= $03` | offset of an 11-byte pattern header |

`$07C1` doubles a note byte before the octave/period lookup (`$808B`). Every track's first
order entry is `$02`, so it is always 0 for music; it exists for the SFX paths.

A header offset is added to one of three bases, chosen by music ID:

| Music ID | Header base |
|---|---|
| `< $04` | `$8F2A` |
| `< $10` | `$900A` |
| `>= $10` | `$90C5` |

All three point into **one** table — `$900A` is `$8F2A + $E0` and `$90C5` is `$900A + $BB`.
The split exists only because the offset byte is 8-bit. `$8F2A`-`$8F2D` is four bytes of
`$00` padding, which is why offsets from the first base are always `4 + 11k`: it keeps a
real header from ever having offset `$00`, `$01`, or `$02` and colliding with the commands
above.

## Pattern headers

**`MusicPatternHeaderTable`** — `$8F2E`-`$913D`: **48 headers, 11 bytes each**. 47 are
referenced by some track; header #34 (`$90A4`) is an orphan.

| Off | Loaded into | Meaning |
|---|---|---|
| 0 | `$07E0` | tempo — base index into the duration table |
| 1-2 | `$FA`/`$FB` | little-endian pointer to this pattern's stream block |
| 3 | `$07F0` | start offset of the **triangle** stream |
| 4 | `$07F1` | start offset of the **pulse 1** stream |
| 5 | `$07EF`, `$07DB` | start offset of the **noise** stream, and its loop point |
| 6 | `$07EE`, `$07D9` | start offset of the **DMC** stream, and its loop point |
| 7 | `$07D5`, `$07D3` | pulse 2 duty/volume envelope base into `$81A4` |
| 8 | `$07D4`, `$07D2` | pulse 1 duty/volume envelope base |
| 9 | `$07B9` | pulse 2 vibrato parameter |
| 10 | `$07B8` | pulse 1 vibrato parameter |

Pulse 2 always starts at offset 0, so it needs no header field.

**A start offset of `$00` disables that channel for the pattern** — each channel handler
begins `LDA <offset> : BEQ skip` (`$8B52`, `$8C94`, `$8CEC`, `$8D74`). Header `$90AF` uses
this to run without the DMC channel.

Because the offsets are single bytes, **one pattern's stream block cannot exceed 255 bytes**
— and the ROM already runs close to that ceiling: the largest block (header `$90E6`, stream
`$A18E`) is 247 bytes. A denser or longer pattern has to be split across two order entries.

## Stream encoding

The five channel streams sit contiguously in the block, in the order
pulse 2, pulse 1, triangle, noise, DMC.

**The stream order does not match the APU register order.** The first stream — the one at
offset 0, which usually carries the melody — drives **pulse 2** (`$4004`-`$4007`), and the
second drives **pulse 1** (`$4000`-`$4003`). The period writer at `$8084` is entered with
`X` = 4, 0 and 8 respectively (`$8077`, `$8082`, `$807B`), and `STA $4002,X` does the rest.
This is easy to get backwards from a static read; it shows up immediately in an APU write log.

Common to every channel: **a byte with bit 7 set sets the current duration.**
`duration = DurationTable[tempo + (byte & $1F)]` frames, and it applies to every following
note until changed.

Otherwise:

| Channel | Reader | `$00` | `$01` | `$02`-`$7E` | `$7F` |
|---|---|---|---|---|---|
| Pulse 2 | `$8A06` | **end of pattern** — advance the order list | next byte → `$4005` sweep | note | rest |
| Pulse 1 | `$8B64` | next byte → `$4001` sweep | note | note | rest |
| Triangle | `$8CA6` | (not handled) | note | note | rest |
| Noise | `$8CFE` | loop back to this pattern's noise start | drum | drum | drum |
| DMC | `$8D86` | loop back to this pattern's DMC start | no-op | clear `SfxChannelMask` | sample |

**Pulse 2's `$00` is what ends a pattern.** The other melodic channels have no terminator —
they are simply sized to match, and stop being read when pulse 2 finishes. Noise and DMC
loop within the pattern, so a two-bar drum figure is stored once.

Across the 47 referenced patterns, pulse 2's `$00` lands exactly on the pulse 1 start
offset in all 47, and the summed frame counts of pulse 2, pulse 1 and triangle agree
exactly in 43. The four that differ (`$8FA7`, `$900A`, `$90BA`, `$90C5`) have one channel
over- or under-running by a single note, which the pattern boundary truncates.

### Noise values

A drum byte `v`:

- `v < $40` — three parallel byte tables indexed by `v` supply `$400C`, `$400E` and `$400F`
  from `$8232+v`, `$8233+v`, `$8234+v`. Records overlap, so `v` is a byte offset, not a
  record index.
- `v >= $40` — `v << 2` is stashed in `$07DA`, `$400F = 8`, and a 16-step decay envelope is
  driven from `$8866` or `$8876`, writing `$400C` and `$400E` each frame.

### DMC values

High nibble = DPCM sample id, written to `$F3` and played by `DmcUpdate` (`$8DF3`) via
`DmcSampleDurationTable` (`$8DCB`), `DmcSampleRateTable` (`$8DD5`) and `DmcSamplePtrTable`
(`$8DDF`, 10 address/length pairs). Low nibble goes to `$07D8`.

## Pitch

A note byte is **not** an absolute pitch. Every melodic channel routes its note through
`ApplyNoteTranspose` (`$8887`) first, which adds a per-track semitone offset:

```
$8887  LDY PlayingMusicID
       LDA MusicTransposeTable,X   ; $884F, signed
       LDX MusicNoteDoublingFlag   ; $07C1
       BEQ +
       SEC : SBC #$0E              ; doubling mode transposes a further -14
+      CLC : ADC <note byte>
```

So, for a note byte `b` in `$02`-`$7E`:

```
n      = (MusicTransposeTable[music_id] + b) & $FF
r      = ((n - 1) mod 12) + 1        ; 1 = C ... 12 = B
shift  = 1 + (n - 1) / 12
period = PeriodTable[r] >> shift
```

`PeriodTable` is 12 little-endian words at **`$818C`-`$81A3`** (the word at `$818A` itself is
not a note); `r = 1` is `$0D5C` = 3420. The note name is
`['C','C#','D','D#','E','F','F#','G','G#','A','A#','B'][(n-1) mod 12]` at octave
`2 + (n-1)/12`.

`$7F` is a rest and silences the channel.

**`MusicTransposeTable`** (`$884F`, indexed by music ID) is what makes several tracks that
share order data distinct songs rather than duplicates:

| ID | `$01` | `$02` | `$03` | `$04` | `$05` | `$06` | `$07` | `$08` | `$09` | `$0A` | `$0B` |
|---|---|---|---|---|---|---|---|---|---|---|---|
| semitones | -4 | -3 | 0 | -8 | +4 | -8 | -2 | 0 | -4 | -6 | +6 |

| ID | `$0C`-`$0F` | `$10` | `$11` | `$12` | `$13` | `$14` | `$15` | `$16` | `$17` |
|---|---|---|---|---|---|---|---|---|---|
| semitones | 0 | -8 | +4 | 0 | -4 | -8 | -2 | 0 | 0 |

Tracks `$05`, `$08` and `$10` share one order list but play at +4, 0 and -8; tracks
`$09`-`$0F` share another at -4, -6, +6 and 0.

Verified against the hardware registers the engine actually writes: for track `$01`, note
bytes `$2E`/`$25`/`$1E` on pulse 2 / pulse 1 / triangle produce timer periods
160 / 269 / 403, matching an emulated run of the engine exactly.

## Duration table

**`$8107`-`$8189`** — seven tempo rows of 19 bytes, at offsets 0, 19, 38, 57, 76, 95 and 114.
Each row is built on a beat unit of 18, 16, 14, 12, 10, 8 and 6 frames respectively — so a
lower tempo base is a slower song.

Within a row, `d = byte & $1F`:

- `d = 0..9` — straight durations: ¼, ⅓, ½, 1½, 1, 2, 3, 4, 6, 8 beats.
- `d = 10..18` — triplet and subdivided durations.

Only three rows are used by music headers: **38**, **57** (nearly every pattern) and **76**.
The rest belong to the SFX paths.

## Volume and duty

**`$81A4`** is a table of `$4000`/`$4004` register values (`DDLC VVVV`) in rows of 16. The
index is `header envelope base + current volume`, where the volume counter (`$07E3` for
pulse 2, `$07E2` for pulse 1, seeded from `$07CE`) counts down — so the envelope reads
backwards and decays, holding on the row's first entry. Envelope bases seen in headers are
`$00`, `$10`, `$20`, `$30`, `$40`, `$50`, `$60`.

## Tracks

| ID | Order list (after the loop byte) | Requested from |
|---|---|---|
| `$01` | `02 04 0F 0F 1A 0F 0F 1A 25 30 30 25 3B 46` | title screen, bank 12 `$8071` (guarded by `CMP $F9`), `$846A` |
| `$02` | `02 51 5C 67 51 5C 72 7D 88 7D 93` | US course BGM — `CourseBgmTable` |
| `$03` | `02 9E A9 B4 9E A9 BF CA D5 CA E0` | Japan course BGM — `CourseBgmTable` |
| `$04` | `02 0B 16 0B 21 2C 37 2C 42 4D 58` | UK course BGM — `CourseBgmTable`; also bank 12 `$A372` |
| `$05` | `02 63 6E` | bank 12 `$9493` |
| `$06` | `02 79 84 79 8F` | bank 9 `$BDC3`, bank 11 `$876B`, `$8E92` |
| `$07` | `02 A5` | bank 12 `$9994` |
| `$08` | `02 63 6E` | bank 12 `$8F58` (prize money screen) |
| `$09`-`$0F` | `02 B0 BB` | bank 12 `$A4C8`, `$A7CC` (as `$09`; `$0B`-`$0F` share the order data and have no caller) |
| `$0A` | *(shares `$09`'s base)* | bank 13 `$8529`, `$8595` — hole start |
| `$10` | `02 63 6E` | bank 12 `$AB94` |
| `$11` | `02 58` | bank 12 `$AD03`, `$B800` |
| `$12` | `02 21` | bank 12 `$AD08`, `$B817` |
| `$13` | `02 16` | bank 12 `$B7E9` |
| `$14` | `02 42` | bank 12 `$B1C8` |
| `$15` | `02 4D` | no immediate-mode caller found |
| `$16` | `02 0B` | no immediate-mode caller found |
| `$17` | `02 2C 2C 37` | no immediate-mode caller found |

Tracks `$11`-`$17` are single-pattern jingles. Their order entries look like track `$04`'s
(`0B`, `16`, `21`, ...) but resolve against a different header base (`$90C5` rather than
`$900A`), so they are *different* patterns despite the shared offsets — no pattern in the
ROM is used by more than one track.

### Course BGM

`$D9FE` in the fixed bank is the only place `BGMOnFlag` gates music. The flag has four
references in all: the OPTIONS screen writes it at bank 11 `$8BCE` and reads it back at
`$8BF2`, bank 9 `$AD4A` initialises it, and this routine consumes it:

```
$D9FE  LDA #$00
$DA00  STA $FF                  ; lift the music suspend
$DA02  LDX CurrCourse           ; $0102
$DA05  LDA BGMOnFlag            ; $6F98 (SRAM)
$DA08  BEQ done                 ; music off -> play nothing
$DA0A  LDA CourseBgmTable,X     ; $DA14
$DA0D  CMP $F9                  ; already playing?
$DA0F  BEQ done
$DA11  STA $F4
```

`CourseBgmTable` at **`$DA14`** is three bytes: `03 02 04` — Japan → `$03`, US → `$02`,
UK → `$04`.

## Composing for this engine

`docs/composing.md` is the composer-facing version of this document: the same constraints
stated musically (voices, tempos, note lengths, ranges, the seven instrument presets) with a
text notation to write in and no ROM detail. Hand that one to a musician; this one is for
whoever wires the result into the ROM.

The seven instrument presets in that guide are the envelope rows of `MusicVolumeEnvelopeTable`:
`round` = base `$00`, `soft` = `$10`, `blip` = `$20`, `bright` = `$30`, `swell` = `$40`,
`reed` = `$50`, `accent` = `$60`.

## Playback

`golf-export-music` (`tools/export_music.py`, logic in `golf/core/audio.py`) turns the ROM
into something you can actually listen to, two ways.

**NSF** — the faithful one. Bank 14 plus the DPCM page are packaged as a bankswitched NSF
so a real player runs the original 6502 engine, vibrato, envelopes and all:

```bash
golf-export-music nes_open_us.nes -o nes_open_golf.nsf
```

23 songs, one per music ID `$01`-`$17`. The file is 24,704 bytes: a 128-byte header and six
4 KB pages — bank 14 at `$8000`-`$BFFF`, the DPCM sample page at `$C000`, and a small stub
at `$D000`. INIT clears RAM (but never the stack page, or it could not return), sets
`MusicRequest` to song + 1 and sets `SfxActiveFlag` so the percussion plays; PLAY is
`JMP AudioEngineMain`. The engine needs nothing outside those two banks — it makes no calls
into the fixed bank, and `$C000`+ is touched only by DPCM DMA.

**Relocatable JSON** — `--dump` writes tracks as data an inserter can place anywhere:
the order list, each pattern header with its stream pointer replaced by an index, and the
raw stream bytes. `--tracks courses` (the default) picks the three course themes out of
`CourseBgmTable`.

```bash
golf-export-music mario_open_jp.nes --dump --reference nes_open_us.nes -o jp.music.json
```

**The DPCM kit** — `--drums` exports the ten built-in drum samples as their own NSF, one
song per slot, so they can be auditioned on real hardware rather than through the software
APU:

```bash
golf-export-music nes_open_us.nes --drums -o docs/drum_kit.nsf
```

Its stub stops the music, sets `SfxActiveFlag`, and writes the sample id to
`DmcSampleRequest` every 48 frames, letting the game's own `DmcUpdate` start and cut off each
hit.

There are ten slots but only three recordings: `DmcSamplePtrTable` points 1/2/4/5/6 at
`$C000`, 3 at `$C340`, and 7/8/9/10 at `$C540`; the duplicates differ only in playback rate.
The music uses almost none of them — across all 47 patterns it is 676 hits of slot 3, 15 of
slot 1, one of slot 2, and nothing else; the `$C540` recording never appears in music at all.
On the noise channel it is `$02` x240, `$06` x35 and `$0A` x7, plus `$16` as a rest.
Samples 4-10 take their rate from `DmcSampleRateTable`, but **1-3 take it from the low nibble
of the stream byte**, so they can be pitched per note and have no single correct speed - the
renderer defaults to the value the music uses most. Each hit is truncated when `DmcUpdate`'s
frame counter expires and it clears the `$4015` enable bit, so the stored sample is usually
longer than what you hear; the renderer reproduces that cut-off.

An APU write log (`run_engine`) is the most direct way to check a claim about the engine.
Reading one is what showed that the first stream drives pulse 2 rather than pulse 1, and
that note bytes pass through `MusicTransposeTable` — neither was obvious from the
disassembly.

## The Japanese ROM

`mario_open_jp.nes` (Mario Open Golf) runs the **same engine**, assembled at shifted
addresses — routines move by +14, +42 and +62 bytes at different points — so nothing can be
hardcoded. `discover_layout()` recovers every table by matching the instruction that reads
it, and everything in this document applies to both ROMs.

What is the same:

- the zero-page and `$07xx` RAM map, exactly — `$F4`, `$F9`, `$FA/$FB`, `$FE`, `$FF`, `$07DC`…
- `AudioEngineMain` at bank 14 `$8000`, so the NSF stub needs no changes
- `MusicOrderBaseTable` at `$8E9E`, by coincidence
- the **duration table**, byte for byte: tempos and note lengths port unchanged
- the noise drum table for every value the music uses

What differs:

| | US | JP |
|---|---|---|
| header bases | `$8F2A` / `$900A` / `$90C5` | `$8F3C` / `$8FFB` / `$90A0` / `$9119` (four) |
| duration table | `$8107` | `$8115` |
| period table | `$818A` | `$8198` |
| envelope table | `$81A4` | `$81B2` |
| transpose table | `$884F` | `$888D` |
| `StartCourseBgm` | `$D9FE` | `$D9C8` |
| `BGMOnFlag` | `$6F98` | `$6BE1` |
| `CourseBgmTable` | `$DA14` = `03 02 04` | `$D9DE` = `04 03 0B 02 0C 03` |
| courses | 3, three themes | **6 slots, five distinct themes** (slots 2 and 6 share `$03`) |
| patterns | 47 | 53 |

The course table's length is stored nowhere, so it is read until a byte stops being a
playable music ID — in both ROMs the byte after the table is `$2C` (`BIT abs`), which is not
a valid track. The JP course themes are `$02`, `$03`, `$04`, `$0B` and `$0C`, and unlike the
US ones they span four different tempo bases (0, 19, 38 and 57) rather than all sitting at
57.

**The one thing that matters for porting a track between them**: the JP period table is the
US table's window shifted up two semitones, so the same note byte sounds a whole tone
sharper. Adding **+2 to a JP track's transpose byte** makes it play identically in the US
ROM — the octave arithmetic works out exactly, including across the wrap at the top of the
table. Envelope row `$00` also sustains one volume step louder in JP, which is inaudible.

## Space

| Region | Extent | Bytes |
|---|---|---|
| Order base table | `$8E9E`-`$8EB5` | 24 |
| Order data | `$8EB6`-`$8F29` | 116 |
| Pattern headers | `$8F2E`-`$913D` | 528 (48 × 11) |
| Stream data | `$913E`-`$A60F` | 5330 |
| Padding | `$A610`-`$A63F` | 48 (`$FF`, unconfirmed) |

Bank 14 above `$A640` is **not audio at all**: it holds four menu screens — Choose Clubs
(`$AE14`), Hall of Fame Holes (`$B420`), Clear Saved Data (`$B8C7`) and Training (`$BD04`) —
plus their data. Each is reached only by `ExecuteFarCall bank $0E <addr>` from bank 12, so
relocating them is a matter of retargeting four inline argument triples. That is the one
realistic way to free a large contiguous block in the bank the sequencer can actually reach;
see the note on addressing above.

## Confidence

Everything above is derived from static disassembly plus a decoder that round-trips the
data (see "Stream encoding" for the two consistency checks it passes). What that
establishes is the *format*; it does not establish the ID → in-game-cue mapping. The
`CourseBgmTable` entries and the title theme are pinned by their call sites; the rest of
the "Requested from" column is the call site only, and which screen or event each one
belongs to has not been confirmed in an emulator.
