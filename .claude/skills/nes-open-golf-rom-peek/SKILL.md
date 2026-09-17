---
name: nes-open-golf-rom-peek
description: >
  How to inspect and reverse-engineer a NES Open Tournament Golf ROM with
  golf-rom-peek (tools/research/rom_peek.py, logic in golf/core/rom_analysis.py). Use
  whenever reading ROM bytes, disassembling 6502 code, tracing what calls a
  routine, checking whether an address or region is referenced, or looking for
  reclaimable space in this project. Covers the subcommands, the three ways a
  naive byte search or linear disassembly silently lies about this ROM, and the
  confidence discipline for null results - a "no references found" is never
  proof an address is dead.
---

# Inspecting the ROM with golf-rom-peek

`golf-rom-peek` is the project's tool for targeted ROM reads, searches and
disassembly. **Use it instead of writing one-off Python.** Analysis logic lives
in `golf/core/rom_analysis.py` and is unit-tested, so extend it there rather
than reimplementing a scan in a scratch script.

```bash
uv run golf-rom-peek <rom.nes> [--labels <file.mlb>] <subcommand> ...
```

Always pass `--labels "NES Open Tournament Golf (USA).mlb"`. A sidecar
(`...sidecar.mlb`) next to it loads automatically and shadows the base file, so
output is annotated with everything the project has named so far. `--labels`
and `--sidecar` are top-level options and must come **before** the subcommand.

## Address grammar

Shared by every subcommand:

- `$XXXX` — a CPU address. Resolved in the fixed bank (`$C000-$FFFF`) unless
  `--bank N` is given, in which case it's a switchable-bank address
  (`$8000-$BFFF`) in bank N.
- `0xNNNN` or bare hex — a raw PRG ROM offset, used as-is.

Bank 15 is the fixed bank. `addr` converts between the two forms without
reading anything.

## Subcommands

| Command | Purpose |
|---|---|
| `read <addr> [--bank N] [--length N] [--format hex\|python\|ascii]` | Raw bytes. `--format python` emits a `bytes([...])` literal ready to paste into a `BytePatch`. |
| `find <hex pattern> [--bank N] [--follow N] [--flag-range LO-HI]` | Byte-pattern search. `--follow 2` decodes the trailing bytes as a little-endian pointer. |
| `addr <addr> [--bank N]` | CPU address ↔ PRG offset, no ROM read. |
| `disasm <addr> [--bank N] [--count N \| --routine] [--max N]` | Disassemble. See below. |
| `find-refs <addr> [--bank N] [--type prg\|ram] [--reach N]` | Find references across every encoding. See below. |
| `label <addr> [--type ...] [--bank N]` | Look up the label at an address. |
| `find-label <substring>` | Search labels by name. |

Use `golf-labels` (separate tool) to *add* labels; it writes to the sidecar by
default. See the `nes-open-golf-label-conventions` skill for naming.

## Three ways this ROM lies to a naive reading

These are the reason the tool exists. Each has burned a previous session.

### 1. Inline arguments desynchronise a linear disassembly

Several routines read bytes that follow their own `JSR` and then skip past
them. A disassembler that doesn't know this decodes the arguments as opcodes
and produces plausible-looking garbage for the next ten to twenty
instructions.

`disasm` handles all of these automatically, rendering the arguments as
`.db`/`.dw` and resuming on the correct boundary:

| Routine | Bank | Inline |
|---|---|---|
| `ExecuteFarCall` `$D372` | fixed | 3 bytes: bank, lo, hi |
| `LoadCompressedGraphics` `$D45F` | fixed | 3 bytes: bank, lo, hi |
| `WriteNametableTiles` `$CE84` | fixed | 2 bytes: descriptor pointer |
| `WriteNametableTilesMode2` `$CE7E` | fixed | 2 bytes: descriptor pointer (no PPU address in the descriptor) |
| `Load32BytesToBuffer` `$D80A` | fixed | 2 bytes: source pointer |
| `CopyInlineMemoryBlock` `$D41A` | fixed | 6 bytes: src, dst, length |
| `DispatchInlineJumpTable` `$D227` | fixed | `(key, lo, hi)` triples, `$00`-terminated — **and it JMPs instead of returning** |
| `DispatchInlineJumpTableFF` `$D267` | fixed | the same, but `$FF`-terminated, so `$00` is a usable key |
| `LookupInlineByteTable` `$8A14` | 12 | `(key, value)` pairs, `$00`-terminated |
| `LookupInlineRangeTable` `$8A56` | 12 | `(lo, hi, value)` triples, `$00`-terminated |

**`$D8A2 ReadInlineWordParameter` and `$D436` are not on this list, and must not be
added to it.** Both do `TSX` then read `$0103,X`, skipping their own return address — so
the inline word belongs to whoever called *their* caller. A `JSR $D8A2` consumes nothing
itself; it is the enclosing routine (`$D80A`, `$D41A`, and a dozen others) that carries
the inline bytes. Listing `$D8A2` here desynchronises every direct call site by two
bytes. Check for this `$0103,X` pattern before adding any new entry.

```
$8F85  20 5F D4    JSR LoadCompressedGraphics[$D45F]
$8F88  06 00 80    .db $06, $00, $80   ; -> bank $06 $8000
```

If you find another such routine, add it to `INLINE_ARG_ROUTINES` in
`golf/core/rom_analysis.py` — confirm first by disassembling it and checking
that it advances its own return address past the arguments.

`--no-inline-args` restores the raw behaviour if you need to see the bytes as
the CPU would misread them.

### 2. Data decodes as convincing code

Range labels in the `.mlb` (`GolferScreenXTable:$80FA-$8109`) mark tables;
single-address labels mark code. `disasm` renders labelled ranges as `.db`
rows instead of decoding them. `--no-data-ranges` opts out.

This only works for ranges someone has already labelled. Unlabelled tables
still decode as nonsense — if a listing suddenly fills with `BRK`, `???`, and
implausible branches, suspect data and go check the bytes with `read`. When
you confirm a table, label it as a range so the next agent doesn't re-derive
it.

### 3. References the obvious search cannot find

A relative branch stores a *displacement*, not an address, so **no byte
pattern will ever find it**. Far calls bury the target in inline arguments.
Dispatch tables store it as inline data.

A previous session ran `find '20 C0 D1'` looking for callers of `$D1C0`, got
"No matches found", concluded it was unreachable, and moved on. Its only
reference is `$D1BC BEQ $D1C0`.

Use `find-refs`, which covers `JSR` / `JMP` / `JMP (ind)`, relative branches,
`ExecuteFarCall` inline targets, and every entry in the inline tables of all
`DispatchInlineJumpTable` and `DispatchInlineJumpTableFF` call sites, in one
command.

## `disasm --routine`

Decodes until the routine plausibly ends rather than a guessed instruction
count — you usually know an address, and bytes-to-instructions isn't
computable without decoding.

Stops at: a terminator (`RTS`/`RTI`/`JMP`) once no forward branch is still
pending; a non-returning call (`JSR DispatchInlineJumpTable`); or the start of
a labelled data range. Always prints why it stopped.

`--max N` (default 200) caps the output so a wrong guess about where code
lives can't dump a whole bank. **If the cap is hit the output says
`INCOMPLETE` — the routine continues past what you were shown.** Don't reason
about a routine's ending from a truncated listing.

```bash
uv run golf-rom-peek rom.nes --labels notes.mlb disasm '$AB16' --bank 13 --routine
```

## `find-refs` and the confidence discipline

Every hit is checked two ways and reported in one of three states:

- **confirmed** — starts on a real instruction boundary (verified by decoding
  forward from the nearest code label) and isn't inside a labelled data range.
- **UNVERIFIED** — no code label within 192 bytes to anchor an alignment check
  from. Reported, but you must read it yourself.
- **discarded** — lands mid-instruction, or sits inside a labelled data range.
  Byte coincidences, listed separately so you can see what was thrown away.

The mid-instruction case is common and convincing: `$88B3` looks exactly like
`JSR $91AD`, but those bytes straddle the operand of `STA $20` and the next
opcode.

### A null result is not proof

**`find-refs` finding nothing does not mean an address is unused.** It cannot
see:

- indirect jumps through a runtime pointer — every menu choice handler is
  reached by `JMP ($22)` and has zero static references;
- addresses computed at run time;
- DMA, the decompressor, and anything the PPU reads directly.

On an empty result the tool says all of this and escalates to a raw
pointer-pair scan. **For pointers the usual reading inverts**: a byte pair
inside a labelled table is a *likely* real indirect reference, not a
coincidence.

So: **static analysis proposes, the emulator disposes.** For anything
expensive to get wrong — reclaiming space, taking over a splice site,
declaring a feature dead — confirm with a Mesen breakpoint, then record the
result in the `.mlb` comment or a doc so it is never re-derived. `docs/
wram_expansion.md` is the model: *"Confirmed via debugger sweep that CPU
`$8F81` and `$8F86` are the only two readers."* That, not a byte search, is
what justified reclaiming `$E4F9`.

### RAM addresses

`--type ram --reach N` also lists indexed bases up to N bytes below the
target, because `LDA $059C,X` can touch `$05BB` if X ranges far enough. **How
far X or Y actually ranges is not determined** — those are candidates to go
read, not findings.

```bash
uv run golf-rom-peek rom.nes --labels notes.mlb find-refs '05BB' --type ram --reach 48
```

## Recipes

**Understand a routine**
```bash
disasm '$AA09' --bank 13 --routine        # the whole thing, with inline args resolved
find-refs '$AA09' --bank 13               # who reaches it
```

**Trace a far call.** `disasm` shows `.db $0B, $33, $90 ; -> bank $0B $9033`;
follow it with `disasm '$9033' --bank 11 --routine`. Remember the target's
addresses are in *that* bank, so data pointers it sets up (e.g. a script
pointer) resolve against the switched-in bank, not the caller's.

**Find every consumer of a table.** `find '20 5F D4'` for a specific inline
routine, or `find-refs` on the table's address.

**Assess free space.** Never conclude a run of `$FF`/`$00` is free from a scan
alone. `$FF` is a meaningful value inside tile strings and music data, and
several regions that look like padding are already claimed by patches in
`golf/core/patches/`. Check the patch modules' hardcoded offsets, check for
range labels, and confirm with a breakpoint before writing anything there.

## Limits worth stating out loud

- `disasm` does not track bank switches mid-listing; operand labels resolve
  against the single `--bank` you passed.
- `--routine`'s terminator heuristic is wrong for jump tables, deliberate
  fall-through into an adjacent routine, and data interleaved mid-routine.
  `--count` and plain `read` remain the escape hatches.
- The alignment check needs a nearby code label. In unlabelled regions it
  returns "unknown", which is why labelling as you go makes the tool better
  for everyone after you.
