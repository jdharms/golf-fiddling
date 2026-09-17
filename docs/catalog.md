# The Hole Catalog

> **Note**: This document was written by Claude and edited by jdharms.

The catalog is every hole a randomizer seed can reference. It lives in two files with
different contracts:

| File | Holds | Changes |
|---|---|---|
| `data/catalog/holes.json` | Ids, provenance and a content hash per hole | Append-only |
| `data/catalog/curation.json` | Tags, drawability, families and display names | Freely edited |

Everything that can reach a ROM is in the frozen index. Everything that only decides
which holes get drawn is curation. A manifest stores resolved hole ids, never filters, so
editing curation never changes what an existing seed builds.

Code: `golf/randomizer/catalog.py` and `golf/randomizer/curation.py`.

## Ids and versions

An id is a lineage and a version: `nes_uk/01`, `jp_hawaii/07`, `dharms/cliffside@2`.
Version 1 is written without a suffix, and `nes_uk/01@1` parses to the same id.

- **Vanilla lineages** are `nes_<course>/<hole>` for NES Open (`nes_us`, `nes_uk`,
  `nes_japan`) and the Mario Open dump names for Mario Open (`jp_japan`, `jp_australia`,
  `jp_france`, `jp_hawaii`, `jp_uk`).
- **Community lineages** are `<author>/<slug>`.
- **A changed hole is a new version.** This applies to vanilla holes too: a corrected
  extraction of `nes_uk/01` is `nes_uk/01@2`.
- **Only the highest version of a lineage is drawable.** Supersession never rolls back:
  to undo version 2, publish version 3 with version 1's content.

## The index

Each entry holds its source, content hash, par, distance and author:

```json
"nes_uk/01": {
  "source": {"rom": "nes_open_us", "course": "uk", "hole": 1},
  "content_hash": "1dcf8587…",
  "par": 4,
  "distance": 418,
  "author": "Nintendo"
}
```

A source is either a vanilla ROM location or, for a community hole, `{"file": "<path>"}`
relative to the hole store root. Par and distance are copies for the pool builder and the
seed page; the hash covers them.

Guarantees, enforced by `tests/meta/test_catalog_frozen.py` and the loader:

1. **An id resolves to the same hole data forever.** `HoleStore.load` recomputes the hash
   and refuses data that does not match.
2. **No committed entry is ever removed or changed**, across the index's whole git
   history, and the index version never decreases.
3. **Withdrawal is the one permitted mutation.** `"withdrawn": true` retires an entry for
   a takedown. Its id stays reserved and seeds that used it keep their stored unfinished
   IPS; only rebuilding such a seed fails. A lineage whose highest version is withdrawn
   has nothing drawable.

## The content hash

`content_hash` is SHA-256 over the canonical JSON (sorted keys, no whitespace) of the
fields of `HoleData.to_dict()` that reach the ROM: par, distance, handicap, scroll limit,
green, tee, flag positions, attributes, greens, and terrain cut to its visible height.
The hole number, the `_debug` block and hidden terrain rows are excluded. Reformatting a
hole file or re-dumping identical data leaves the hash unchanged.

## Curation

Curation is keyed by lineage, never by versioned id, so a record carries forward when a
new version is published:

```json
{
  "jp_japan/01": {"family": "nes_uk_01"},
  "nes_uk/01": {"family": "nes_uk_01", "tags": ["dogleg"]}
}
```

| Field | Default | Meaning |
|---|---|---|
| `tags` | none | Labels pool filters match on |
| `drawable` | true | False retires the lineage from new seeds |
| `family` | none | Holes judged to be the same hole |
| `display_name` | none | Name for the seed page |

An uncurated lineage gets the defaults, so a new catalog entry is drawable with no tags.
Unknown fields and versioned keys are load errors, and a test checks that every curated
lineage exists in the index.

**Families** are assigned by hand, never computed. Every lineage with the same label is in
the same family, and a lineage is in at most one. Examples are a vanilla hole and its
Mario Open twin, or a par 5 and its forward-tee par 3. The label is a plain string; by
convention a family containing an NES Open hole is named after it, as in `nes_uk_01`.
Whether two holes from one family may share a course is the `allow_family_repeats`
generation setting ([manifest.md](manifest.md)).

**Transforms** such as mirroring are applied to a manifest slot after the draw. They
create no catalog entry and have no family of their own.

Generation reads a `CurationSnapshot`: the curation file as loaded, with a `stamp` that
identifies its content and is recorded in the manifest for auditing. The site builds its
snapshot from the same file and will layer player statistics from its database onto the
same record type.

## Syncing vanilla holes

`golf-catalog-sync` walks the dumped course directories (NES Open under `courses/`, Mario
Open under `courses/jp/`) and, for each hole:

- **Adds** a version 1 entry when the index lacks the id, and bumps the index version.
- **Verifies** an existing entry against the data, and reports a mismatch without writing
  anything.
- **Skips** entries whose data is not present, such as Mario Open holes on a checkout
  without the JP dump.

It never removes or rewrites an entry, and never mints a version above 1. `--check`
reports without writing and exits 1 if anything would be added or does not match.
