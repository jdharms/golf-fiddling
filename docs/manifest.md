# Seed Manifests

> **Note**: This document was written by Claude.

A manifest is a randomized seed as JSON: everything that decides the seed's unfinished ROM,
and the settings it was generated from. The site stores it on the seed row and serves it
at `/h/<id>.json`; `golf-randomize` reads and writes it as a file.

Code: `golf/randomizer/manifest.py` (the model and its JSON), `golf/randomizer/generate.py`,
`golf/randomizer/pool.py`, `golf/randomizer/music.py` and `golf/randomizer/words.py`.

## Example

With the hole list trimmed to one of its 18 slots:

```json
{
  "schema": 1,
  "generator_version": 1,
  "catalog_version": 1,
  "curation_stamp": "f640f8d1…",
  "settings": {
    "prng_seed": "3f9a0c61d2e84b07",
    "par": 72,
    "sources": ["nes_open_us", "mario_open_jp"],
    "exclude_tags": [],
    "allow_family_repeats": false,
    "music": "random",
    "mercy_point": 9,
    "clubs": {"max": 14, "banned": [], "required_bag": null}
  },
  "course": {
    "holes": [
      {"id": "nes_uk/09", "par": 5, "transforms": [], "wind_seed": 32048}
    ],
    "music": "jp_france",
    "mercy_point": 9,
    "clubs": {"max": 14, "banned": [], "required_bag": null},
    "magic_words": ["DIVOT", "CADDY", "BOGEY"],
    "sram_magic": 21063
  }
}
```

## Structure

| Part | Holds | Read by |
|---|---|---|
| Version fields | `schema`, `generator_version`, `catalog_version`, `curation_stamp` | Loading and auditing |
| `settings` | Every input to generation, the PRNG seed included | The seed page, regeneration |
| `course` | Concrete values | The build |

A build reads only `course`, and nothing in `course` needs interpreting: hole ids rather
than filters, a music slug rather than "random", wind seeds rather than the string they
were derived from. Loading is strict: a missing or unknown field is an error.
`golf/randomizer/build.py` turns `course` into the seed's unfinished ROM, and finishes that
ROM per player (`docs/randomizer_devplan.md`).

**Versions.**

- `schema` fixes the manifest's shape and the patches every seed gets without the
  manifest naming them (WRAM expansion, multi-bank terrain, attribute streaming, the
  signpost banner, menu trim and the rest of the base ROM). A change to either that would
  make an existing manifest load or build differently bumps it. A loader reads only its
  own schema.
- `generator_version` is bumped whenever the same catalog, curation and settings would
  generate a different manifest.
- `catalog_version` and `curation_stamp` record what generation read, for auditing.
  Hole ids resolve through the frozen catalog forever (`docs/catalog.md`), so neither is
  needed to build.

### Settings

| Field | Default | Meaning |
|---|---|---|
| `prng_seed` | drawn | The string every random choice comes from |
| `par` | 72 | Course par: 72, 71 or 70 |
| `sources` | both ROMs | Which vanilla ROMs' holes the pool draws from |
| `exclude_tags` | none | Curation tags that keep a hole out of the pool |
| `allow_family_repeats` | false | Whether two holes of one family may share the course |
| `music` | `random` | A music slug, or `random` |
| `mercy_point` | 9 | The stroke a hole ends on with a tap-in; `null` leaves the patch out |
| `clubs` | no limits | Club rules, below |

Generation draws a `prng_seed` of 16 hex characters when the settings have none, and
records it. The web UI never exposes the PRNG seed, and does not offer a `null` mercy
point; the CLI accepts both.

### Course

| Field | Meaning |
|---|---|
| `holes` | 18 slots in play order |
| `music` | The course theme's slug |
| `mercy_point` | Copied from the settings |
| `clubs` | Copied from the settings |
| `magic_words` | Three words for the title menus, the scorecard title and the seed page |
| `sram_magic` | The 16-bit value that marks a save as this seed's, neither byte `$00` or `$FF` |

A slot is a catalog hole `id`, its `par` (a copy of the catalog's, for readability),
`transforms` and a `wind_seed`. Schema 1 defines no transforms, so the list is always
empty. The wind seed is the 16-bit state the ROM's own RNG starts the hole from
(`docs/seeded_wind.md`), not a seed for generation. No hole id appears twice.

The SRAM magic is what the ROM's save initialisation compares a save against at boot
(`sram_defaults`). A save holding any other magic, from the vanilla game or another seed,
is wiped and rebuilt with the name and bag the player chose at download, so those choices
always land. Neither byte may be `$00` or `$FF`, what blank SRAM holds, or blank SRAM would
pass the check. The model refuses any other value when a course is built or loaded, so a
manifest that would fail at patch time cannot exist.

### Club rules

| Field | Default | Meaning |
|---|---|---|
| `max` | 14 | The most clubs a bag may hold, putter included, 1-14 |
| `banned` | none | Clubs no bag may hold. Never the putter |
| `required_bag` | `null` | The one bag every player carries |

Clubs are written with the choose-clubs labels `1W`-`4W`, `1I`-`9I`, `PW`, `SW` and `PT`,
in that order. The putter is always allowed: a required bag gains it if missing, must fit
within `max`, and holds no banned club. The ROM does not yet enforce these rules; the club
house's CHOOSE CLUBS menu stays reachable.

### Music slugs

A slug names the course a theme belongs to, with the catalog's lineage prefixes:

| Slug | ROM | Music id |
|---|---|---|
| `nes_japan` | NES Open | $03 |
| `nes_us` | NES Open | $02 |
| `nes_uk` | NES Open | $04 |
| `jp_japan` | Mario Open | $04 |
| `jp_australia` | Mario Open | $03 |
| `jp_france` | Mario Open | $0B |
| `jp_hawaii` | Mario Open | $02 |
| `jp_uk` | Mario Open | $0C |

The ids are those in each ROM's `data/music/` dump, and collide between the two ROMs.
A build plays a NES Open theme by pointing every course at it (`course_theme`), since its
data is already in the ROM, and imports a Mario Open theme from its dump (`music_import`).

### What is not in a manifest

- **The seed's identity.** Its URL id and QR seed ID live on the seed row
  (`docs/randomizer_devplan.md`). Two identical manifests can be two seeds.
- **Download-time choices.** Player names, bags, player IDs and MAC keys belong to the
  player's entry and the finishing stage.
- **Required ROMs.** `required_roms` computes them from the holes and the music: the US
  ROM always, and the Mario Open ROM when any hole or the theme comes from it.

## Generation

`generate(catalog, curation, settings)`:

1. **PRNG seed.** The settings' seed, or a fresh one.
2. **Pool.** Each lineage's newest version that is not withdrawn, is drawable, comes from
   one of the `sources` and has no excluded tag. Community holes have no source ROM and
   are not drawn. Holes sharing a curation family form one family; every other hole is a
   family of its own, as is every hole when `allow_family_repeats` is on.
3. **Layout.** A uniform draw from the layouts for the par (`golf/randomizer/layout.py`).
4. **Holes.** Slot by slot: shuffle the unused families that have a member of the slot's
   par, take the first that leaves the remaining slots fillable, then one of its members
   with that par. Drawing a family before a hole keeps a hole with a twin from being twice
   as likely. The fillability check is a bipartite matching of slots to families, which
   finds the fill a backtracking search would, and a pool that no fill exists for raises
   `GenerationError` before anything is drawn. A family holding holes of different pars,
   such as a par 5 and its forward-tee par 3, can fill either kind of slot but only one.
5. **Music.** A named slug is used as given. `random` draws from the NES Open themes, or
   from all eight when at least one hole comes from Mario Open.
6. **Wind.** `derive_hole_seeds(prng_seed)` gives the 18 wind seeds.
7. **Magic words.** Three distinct words from `golf/randomizer/data/word_bank.txt`.
8. **SRAM magic.** Two bytes, each uniform over `$01`-`$FE`, high byte first.

The layout, holes, music, magic words and SRAM magic each draw from their own generator,
`random.Random(f"{purpose}\0{prng_seed}")`, and the wind seeds from their own hash, so a
change to one draw leaves the others as they were.

The same catalog, curation and settings give the same manifest under one generator
version, and the tests hold generation to that. It is not a promise across generator
versions: the stored manifest, not its inputs, is what a seed is.

### The word bank

One word per line, in any case, uppercased on load. Every word is 4 to 6 characters of
A-Z and 0-9, the characters both the menu header (`menu_trim`) and the scorecard title
(`scorecard_course_name`) can draw, and no word appears twice; a unit test loads the
checked-in bank. Three words joined by spaces are at most 20 characters, within the
scorecard title's 26. The words tell a player at a glance that they have the right ROM;
they do not identify a seed uniquely.
