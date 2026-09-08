# Writing Music for NES Open Tournament Golf

> This document is currently not fit for human consumption!

> **Note**: This document was written by Claude based on investigation requested by jdharms.

This is a guide for a composer. You don't need to know anything about the game, the console,
or programming — you need to know what the instrument can and can't do, and how to write
music down so it can be entered into the game.

The short version: you have **five voices**, **three of which can play pitches**, no volume
control within a phrase, and a fixed menu of note lengths and tempos. It's closer to writing
for a small, stubborn music box than for a synthesizer.

Write your piece in the text format described under [How to write it down](#how-to-write-it-down)
and hand it back. Everything in this guide is a hard limit of the game's sound engine unless
it says otherwise.

---

## The five voices

| Voice | What it is | Notes at once |
|---|---|---|
| **lead** | Bright square-wave tone. Carries the tune. | 1 |
| **harmony** | Second square-wave tone. Counter-melody or a second line. | 1 |
| **bass** | Softer, rounder tone. The bass line. | 1 |
| **drums** | Noise. Three unpitched sounds. | 1 |
| **sample** | Short recorded drum hits. | 1 |

**Every voice is monophonic.** No chords, ever. The most you can sound at one time is three
pitches — lead, harmony, bass — so voice your harmony in three parts at most, and think like
a string trio rather than a keyboard.

Two things about the bass voice:

- **It sounds one octave lower than you write it.** Write `o3 c` and you hear C2. This is
  worth remembering but you don't have to compensate: write the octave you want to *see* on
  the staff and the note below will be handled. Just be aware when reading the range table.
- **It has no volume or tone control at all.** It's always the same weight. You can't make
  the bass duck under the melody.

---

## Tempo

You must pick **one of seven tempos**. There is nothing in between.

| | | | | | | |
|---|---|---|---|---|---|---|
| **100** | **113** | **129** | **150** | **180** | **225** | **300** |

BPM here means quarter-note beats per minute. The game's own music uses 129, 150 and 180.

Tempo is set **per section**, so you can change it partway through a piece — but only
between sections, never within one, and only to another value on this list.

If 300 feels too fast for what you want, write it at 150 with doubled note values instead.

---

## Note lengths

This is the strictest limit in the whole engine. You may only use these:

| Length | Written |
|---|---|
| whole | `1` |
| dotted half | `2.` |
| half | `2` |
| dotted quarter | `4.` |
| quarter | `4` |
| dotted eighth | `8.` |
| eighth | `8` |
| sixteenth | `16` |
| thirty-second | `32` |
| half triplet | `3` |
| quarter triplet | `6` |
| eighth triplet | `12` |

**Not available**: dotted sixteenth, dotted whole, anything longer than a whole note, and
any tuplet other than triplets.

**Triplets are only exact at 100, 150 and 300 BPM.** At the other four tempos the engine
rounds them unevenly — a quarter triplet might come out 3% short — and because your voices
have to add up to the same length, that drift will pull the section out of alignment. If you
want triplets, pick 100 or 150.

**Thirty-seconds get unreliable above 180 BPM**, where they come out only one or two frames
long — too short to hear as a pitch. Use them at the slower tempos.

**There are no ties and no slurs.** A note is one length from the list. If you want something
longer than a whole note, write a whole note followed by another note — it will re-attack,
audibly. Plan phrases so this doesn't happen mid-line.

---

## Range

| Voice | Comfortable range | Full chromatic range |
|---|---|---|
| lead | B3 – C#6 | C2 – B8 |
| harmony | E3 – C6 | C2 – B8 |
| bass | G#3 – D#6 *as written* (sounds G#2 – D#5) | C2 – B8 written |

"Comfortable range" is what the game's own music actually uses, and it's what sits well on
this hardware. You can go outside it, but above roughly C7 the tone turns shrill and thin,
and the bottom of the range is buzzy and indistinct.

**C2 – B8 is a hard edge for a different reason**: the hardware tunes by dividing, and above
B8 there is no longer enough resolution to separate adjacent semitones — G9 and G#9 come out
as the same pitch. Everything up to B8 is properly in tune (within about 20 cents).

Middle C is `o4 c`.

---

## Dynamics and tone

**This is the limitation that will shape your writing most, so read it carefully.**

You cannot change volume note by note. There is no `mf`, no crescendo, no accent on a single
note. Instead, each of **lead** and **harmony** gets one *instrument* per section, chosen from
seven fixed presets. That preset governs both the tone colour and the volume shape of every
note in that section.

Each preset has a built-in attack-and-decay that plays out over about a quarter of a second
on every note, then holds. You cannot change it.

| Name | Character |
|---|---|
| `round` | Full, medium-loud, settles to a steady tone. The default lead sound. |
| `soft` | Same tone, noticeably quieter. Good for inner parts and accompaniment. |
| `blip` | Dies away almost instantly. Staccato and percussive — good for stabs, useless for melody. |
| `bright` | A thin click on the attack, then rounds out. Slightly more articulate than `round`. |
| `swell` | Dips then comes back up. Breathes on long notes; muddy on fast ones. |
| `reed` | Sharp attack, then a thin nasal sustain. Plucked or reedy. Cuts through well. |
| `accent` | Re-attacks partway through the note. Adds a bounce. Distracting on short notes. |

The bass voice takes no instrument.

**How to get dynamics anyway**: since the instrument is per section, a change in dynamics
means a new section. Writing a quiet second verse means writing it as its own section with
`soft` instead of `round`. This is normal practice for this kind of engine — build the shape
of the piece out of section-level contrast, not note-level shading.

---

## Sections and arrangement

You don't write one long timeline. You write **sections** — think of them as rehearsal
letters — and then an **arrangement** that plays them in order, with a **loop point**.

```
order: A B B C B B C D
loop:  B
```

That plays A once as an intro, then the body, and when it reaches the end it jumps back to
the first `B` and repeats forever. Game music loops indefinitely; there's no ending. Write
something that comes round cleanly.

Rules for a section:

- **lead, harmony and bass must all be exactly the same total length.** If they aren't, the
  section ends when the *lead* runs out and the other voices get cut off mid-note. Count your
  bars.
- **drums and sample may be shorter — they repeat automatically** to fill the section. Write
  a one-bar drum pattern for a four-bar section and it will loop four times. Only write it out
  in full if it actually varies.
- A voice can be left empty if it doesn't play in that section.
- Keep sections to **two to four bars**. This is a size limit, explained below.

Reusing sections is free and costs no space, so repetition in the arrangement is the cheapest
way to make a long piece.

---

## Drums

The **drums** voice has three sounds and a rest:

| Written | Sound |
|---|---|
| `h` | Short bright tick. A closed hi-hat. |
| `s` | Mid-range noise burst. A snare. |
| `t` | Lower, duller burst. A tom, or a soft kick. |
| `r` | Rest. |

There is no volume control and no accenting — every hit is identical.

### The sample kit

The **sample** voice plays short recorded hits. You have three slots — **`x1`, `x2` and
`x3`** — holding **two distinct recordings**, both about 0.13 seconds long:

| Written | Recording |
|---|---|
| `x1`, `x2` | A |
| `x3` | B |

`x1` and `x2` are the same recording, so use whichever reads better. (They're written with an
`x` rather than a `d` so they can't be confused with the note `d`.)

**Every hit takes a pitch**, written in brackets: `x3(15)`. The number runs 0 to 15, where 0
is lowest and 15 is highest. It works like a sampler transposing a one-shot, so a higher
number is also a shorter, snappier hit. Always write it — there's no default.

Pitch is the only real control you have on this voice, and the game leans on it completely.
Across the entire soundtrack — all 47 sections of all 23 pieces:

| | Hits | Share |
|---|---|---|
| `x3`, at pitches 12, 13, 14 and 15 | 676 | 98% |
| `x1`, always at pitch 15 | 15 | 2% |
| `x2`, once, at pitch 14 | 1 | — |

So the whole soundtrack is essentially **one recording, pitched** — mostly alternating
`x3(15)` and `x3(13)` to get a two-tone pattern out of a single hit. The appendix at the end
of this guide has the real drum lines from all three course themes if you want to see how
that's used in practice.

The noise voice is just as lean: `h` accounts for 83% of hits, `s` for 12%, and `t` appears
seven times in the whole game.

None of that is a rule. But a hi-hat, an occasional snare and one pitched sample is the
palette the original music was built from, and it's what sits most naturally on this hardware.

**Listen before you write.** `docs/drum_kit.nsf` opens in Mesen (or any NSF player); songs 1,
2 and 3 are slots `x1`, `x2` and `x3`, each repeating about twice a second. It's the game's
own sound code playing the game's own samples, so what you hear is exactly what you'll get.

Every hit is cut off after about 0.13 s whether or not the recording has finished — that
abrupt stop is part of how these sound.

Both drum voices loop within a section, so a groove costs almost nothing.

---

## How to write it down

Plain text. Anything after `#` on a line is a comment.

```
title: Course A Theme
tempo: 150
order: A B B C B B C
loop:  B

[A]
lead     round   o5 l8  | f4 g4 a a g4 | a4. g f2  | c4 d4 e e d4 | c4. d c2
harmony  soft    o4 l8  | c4 c4 c c c4 | c4. c a2  | a4 a4 g g g4 | g4. g e2
bass             o3 l4  | f c f c      | f c f2    | a e a e      | g g c2
drums            l8     | h h s h h h s h
sample           l4     | x3(15) r x3(13) r
```

**The commands**, in order of how often you'll use them:

| Written | Means |
|---|---|
| `c d e f g a b` | the note |
| `+` or `#` after a note | sharp — `f+` or `f#` |
| `-` after a note | flat — `b-` |
| a number after a note | its length — `c4` is a quarter note |
| `.` after the length | dotted — `c4.` |
| `r` | rest, with a length like a note — `r8` |
| `l8` | set the default length; notes with no number use it |
| `o4` | set the octave; middle C is `o4 c` |
| `>` / `<` | up / down one octave |
| `\|` | bar line — ignored, but please include them |

For **drums**, write `h`, `s`, `t` and `r` where notes would go. For **sample**, write `x1`,
`x2` or `x3` with a pitch in brackets, and `r`. Both take lengths the same way, and the length
goes last — so `x3(15)8` is slot 3 at pitch 15, an eighth note long.

The instrument name (`round`, `soft`, …) goes right after the voice name, on `lead` and
`harmony` only.

A voice line can wrap onto several lines; just start the continuation with whitespace.
Bar lines are ignored by the software but they let mistakes in bar length get caught before
anything is built, so please put them in.

---

## Size budget

Space in the game is very tight, so each piece has a byte budget. **Aim for 900 bytes of
section data per piece**, which is what the existing course themes use.

Counting is simple:

- every note, rest or drum hit = **1 byte**
- every time the length changes on a voice = **1 extra byte**
- reusing a section in the arrangement = **free**

So a section with 90 notes across all five voices and 20 length changes costs about 110 bytes.

Two hard rules:

- **No single section may exceed 255 bytes.** This is why sections should be two to four bars.
  If a section is too big, split it in half and put both letters in the arrangement.
- The total of all your *distinct* sections must fit the 900-byte budget. Repeats are free, so
  a piece built from five 150-byte sections arranged over three minutes is entirely fine.

If you go over, the usual fix is to find two similar sections and make them one.

---

## Before you send it back

- [ ] Tempo is one of: 100, 113, 129, 150, 180, 225, 300
- [ ] Every note length is on the allowed list
- [ ] Triplets only used at 100 or 150 BPM
- [ ] lead, harmony and bass are the **same total length** in every section
- [ ] No chords — one note at a time per voice
- [ ] No ties or slurs
- [ ] Pitches are within range, and you remembered the bass sounds an octave lower
- [ ] Each of lead and harmony has an instrument name in every section it plays in
- [ ] Every sample hit has a pitch in brackets, e.g. `x3(13)`
- [ ] Distinct sections total roughly 900 bytes or less; none exceeds 255
- [ ] The arrangement has a loop point and comes round cleanly

---

## What you can't do, in one list

No chords. No ties or slurs. No volume changes within a section, no crescendos, no accents.
No key changes except by writing the notes out transposed. No tempo change within a section.
No note lengths outside the list. No dotted sixteenths. No tuplets except triplets, and those
only at two of the seven tempos. No control at all over the bass tone. No ending — it loops.

What you *do* have is three clean independent melodic lines, a solid drum kit, and enough
range to write real counterpoint. The game's own soundtrack works within exactly these limits,
so listen to it first — it's the best guide to what sits well on this hardware.

---

## Appendix: how the game's own courses use the drums

These are the `drums` and `sample` lines of the three course themes, decoded from the
ROM into the notation above. They're the best evidence of what actually sits well on
this hardware.

Identical lines are listed once with the sections that use them. Where a line is shorter
than its section it repeats to fill it, as described under [Drums](#drums).

### US course

Arrangement: `A B C A B D E F E G`

**drums**

- sections **A** — written out in full
  ```
  h8 h h r h r h r h r h r h r h r h r h r h r h r h r h r h r h r
  ```
- sections **B C** — written out in full
  ```
  h8 r h r h r h r h r h r h r h r
  ```
- sections **D** — written out in full
  ```
  h8 r h r h r h r h r h r h r h h r
  ```
- sections **E** — written out in full
  ```
  h8 h r h r h r h r h
  ```
- sections **F** — written out in full
  ```
  r8 h r h r h r h r h r h r h r h r h r h r h
  ```
- sections **G** — written out in full
  ```
  r8 h r h r h r h r h r h r h r h r h r h h
  ```

**sample**

- sections **A** — written out in full
  ```
  x3(15)8 x3(15) x3(15) r x3(15)16 x3(15) r8 x3(13) r x3(15) r x3(13) r x3(15)16 x3(15)
  r8 x3(13) r x3(15) r x3(13) r x3(15)16 x3(15) r8 x3(13) r x3(15) r x3(13) r x3(15)16
  x3(15) r8 x3(13) r
  ```
- sections **B C** — written out in full
  ```
  x3(15)8 r x3(13) r x3(15)16 x3(15) r8 x3(13) r x3(15) r x3(13) r x3(15)16 x3(15) r8
  x3(13) r
  ```
- sections **D** — written out in full
  ```
  x3(15)8 r x3(13) r x3(15)16 x3(15) r8 x3(13) r x3(15) r x3(13) r x3(15)16 x3(15) r8
  x3(13) x3(15) r
  ```
- sections **E** — written out in full
  ```
  x3(13)8 x3(15) r x3(15)16 x3(15) r8 x3(13) r x3(15)16 x3(15) r8 x3(13)
  ```
- sections **F G** — repeats to fill each section
  ```
  r8 x3(15)16 x3(15) r8 x3(13)
  ```

### Japan course

Arrangement: `A B C A B D E F E G`

**drums**

- sections **A** — written out in full
  ```
  h16 h r8 h r h16 h r8 h r h16 h r8 h r h16 h r8 h r h16 h r8 h r h16 h r8 h r h16 h r8
  h r h16 h r8 h
  ```
- sections **B C D E F G** — repeats to fill each section
  ```
  r8 h16 h r8 h
  ```

**sample**

- sections **A** — written out in full
  ```
  x3(13)16 x3(13) x3(13)8 x3(13) x3(15) x3(13) x3(15) x3(13) x3(15) x3(13) x3(15) x3(13)
  x3(15) x3(13)16 x3(13) x3(15)8 x3(13) x3(15) x3(13) x3(15) x3(13) x3(15) x3(13) x3(15)
  x3(13) x3(15) x3(13) x3(15) x3(13) x3(15) x3(13)16 x3(13) x3(15)8 x3(13)
  ```
- sections **B** — written out in full
  ```
  x3(15)8 x3(13) x3(15) x3(13) x3(15) x3(13) x3(15) x3(13) x3(15) x3(13) x3(15) x3(13)
  x3(15) x3(13)16 x3(13) x3(15)8 x3(13) x3(15) x3(13) x3(15) x3(13)
  ```
- sections **C** — repeats to fill each section
  ```
  x3(15)8 x3(13) x3(15) x3(13) x3(15) x3(13) x3(15) x3(13) x3(15) x3(13)16 x3(13)
  x3(15)8 x3(13)
  ```
- sections **D** — written out in full
  ```
  x3(15)8 x3(13) x3(15) x3(13) x3(15) x3(13) x3(15) x3(13) x3(15) x3(13)16 x3(13)
  x3(15)8 x3(13) x3(15) x3(13) x3(15) x3(13)
  ```
- sections **E F** — written out in full
  ```
  x3(15)8 x3(13)16 x3(13) x3(15)8 x3(13) x3(15) x3(13) x3(15) x3(13) x3(15) x3(13)16
  x3(13) x3(15)8 x3(13) x3(15) x3(13) x3(15) x3(13)
  ```
- sections **G** — written out in full
  ```
  x3(15)8 x3(13)16 x3(13) x3(15)8 x3(13) x3(15) x3(13) x3(15) x3(13) x3(15) x3(13)16
  x3(13) x3(15)8 x3(13) x3(15)
  ```

### UK course

Arrangement: `A B A C D E D F G H`

**drums**

- sections **A B C D E F G H** — repeats to fill each section
  ```
  s8 s h s
  ```

**sample**

- sections **A B C** — repeats 2x per section
  ```
  r8 x3(15)16 x3(15) r8 x3(13) r x3(13) r x3(13)
  ```
- sections **D E F** — repeats 4x per section
  ```
  r8 x3(15)16 x3(15) r8 x3(13)
  ```
- sections **G H** — written out in full
  ```
  x3(15)16 x3(15) x3(15) x3(15) x3(13)8 x3(15)16 x3(15) x3(15) x3(15) x3(13)8 x3(15)16
  x3(15) x3(15) x3(15) x3(15) x3(15) x3(15) x3(15) x3(13)8 x3(15)16 x3(15) x3(15) x3(15)
  x3(13)8 x3(15)16 x3(15) x3(15) x3(15) r8 x3(15)16 x3(15) r8 x3(13) r x3(15)16 x3(15)
  r8 x3(13) r x3(15)16 x3(15) r8 x3(13) r x3(15)16 x3(15) r8 x3(13)
  ```
