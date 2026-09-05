# Curiosities

Side findings noticed while working on other things - not yet investigated, not
confirmed relevant to anything, parked here so they aren't lost or conflated with
whatever they were found alongside.

## Fixed-bank code reading WRAM `$0F9C,X` right after `TerrainRowOffsetsHi`

Found while investigating the tall-hole ball-lie bug (see `docs/wram_expansion.md`,
"Terrain Buffer Reference Sites" - this is unrelated to that bug, which turned out to
be `TerrainRowOffsetsLo`/`TerrainRowOffsetsHi` only having 48 entries).

Immediately after `TerrainRowOffsetsHi` ends (CPU `$F6CE`, fixed bank, PRG `0x3F6CE`),
there's a block of code that does:

```
$F6CE  AA        TAX
$F6CF  A9 80     LDA #$80
$F6D1  8D F7 04  STA $04F7
$F6D4  A9 00     LDA #$00
$F6D6  85 9A     STA $9A
$F6D8  8D F6 04  STA $04F6
$F6DB  8D 00 01  STA $0100
$F6DE  8D 33 01  STA $0133
$F6E1  A9 80     LDA #$80
$F6E3  85 F4     STA $F4
$F6E5  BD 9C 6F  LDA $6F9C,X
$F6E8  29 1F     AND #$1F
$F6EA  85 94     STA $94
$F6EC  85 95     STA $95
$F6EE  BD 9C 6F  LDA $6F9C,X
$F6F1  4A        LSR A
$F6F2  4A        LSR A
$F6F3  4A        LSR A
$F6F4  4A        LSR A
$F6F5  4A        LSR A
$F6F6  8D 02 01  STA $0102
$F6F9  A9 00     LDA #$00
$F6FB  8D 7F 06  STA $067F
$F6FE  BD 76 F7  LDA $F776,X
$F701  8D 80 06  STA $0680
$F704  8A        TXA
```

`$6F9C` is CPU-space for WRAM `$0F9C` - the very first byte of the region reclaimed
for stats/replay data in `docs/wram_expansion.md`, and now (post-relocation) the start
of the margin before the new terrain buffer base (`$107E`, only 226 bytes past
`$0F9C`).

What's read from `$6F9C,X` gets split into two fields: the low 5 bits (`AND #$1F`,
range 0-31) stored to `$94`/`$95`, and the upper 3 bits (`LSR`x5, range 0-7) stored to
`$0102`. `X` is also used to index a parallel ROM table at `$F776,X` (fixed bank), read
into `$0680`. The `AA`/`TAX` just before this block means `X` comes from whatever `A`
held at the (unknown) call site - haven't traced that yet.

Open questions:
- What actually calls into this code, and under what circumstances (hole load only?
  every frame during play? some specific menu/mode)? Never traced the caller.
- What does `X` represent, and what's its actual range at runtime? If it's small (a
  handful of course-prop/marker indices, say), this is probably harmless. If it can
  range far enough that `$0F9C + X` reaches into where terrain now lives (anything
  past offset 226), it would read live terrain tile bytes instead of whatever this
  code expects, post-relocation.
- Is this genuinely a *different* consumer of that WRAM region entirely (a per-hole
  scratch table written by some routine we haven't found, unrelated to
  AceReplayHeaders et al.), or something else?

Not currently believed to be the cause of any known bug - flagged here purely because
it showed up unexpectedly while looking for something else, and touches memory this
project cares a lot about.
