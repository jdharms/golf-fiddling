# Randomizer Site: Architecture and Development Plan

> **Note**: This document was written by Claude and edited by jdharms.
> It records the decisions as they stand and the order of work. `randomizer.md` is the
> feature design; `scorecard_qr.md` is the submission format.

## Architecture

**Stack.** Python, FastAPI, server-rendered Jinja2 templates, Pico CSS, hand-written
JavaScript only where the browser has to do something (hash and store the ROM, apply an
IPS patch). SQLite for persistence through the standard library `sqlite3` module in WAL
mode, with a small migrations file and no ORM. Litestream replicates the database to
object storage and sits outside the app.

**Code layout.** Generation logic lives in a new `golf/randomizer/` package with no web
dependencies. The FastAPI app lives in a new top-level `site/` package (`web/` is the
rangefinder) and imports from `golf/` only. A `golf-randomize` CLI drives the same code
so ROMs can be built and playtested from a manifest file offline. The `tools/randomize.py`
spike is deleted once the package exists.

**The catalog** is two checked-in files (`docs/catalog.md`). The frozen, append-only
index holds versioned hole ids such as `jp_hawaii/07` or `dharms/cliffside@2`, each with
its source, a content hash, par and yardage. The curation file holds what steers
generation, keyed by lineage: tags, drawability and hand-assigned families. Hole data
lives in a directory the server rehydrates from its vanilla ROMs. Manifests reference hole
ids, the catalog version and the curation stamp, never hole data.

### Two-stage build

Warm, a full randomized ROM builds in under half a second, and most of that is course
compression, which depends only on the 18 holes. Nothing a player chooses at download
time touches it. So the build is split at the manifest boundary and no job queue is
needed:

- **Unfinished.** Run once at generation time: the base patches, the course, seeded
  wind, music, mercy tap-in, the magic words on the menus and scorecard, signpost, and the
  scorecard QR image with its credential placeholders unfilled. The result is stored as an IPS blob
  on the seed row. The server rejects QR code submissions with all-zero seed IDs, so an
  unfinished ROM cannot cause downstream problems.
- **Finished.** Run per download, in milliseconds: SRAM defaults for name and clubs
  and one of two flavours.
  - *Signed in*: a credentials patch of three byte patches writing the seed's `qr_seed_id` as
    the seed ID, the player ID and the MAC keys into the placeholders. Their expected original bytes are the
    placeholder fill, so finishing can only land on an unfinished image.
  - *Guest*: a two-byte patch reverting the round-end splice to the vanilla scorecard
    wait, so the QR screen never appears. A guest ROM also carries a visible marker on
    the main menu; menu text is table data, so this is a finishing byte patch, and
    the wording and placement are still being decided with league members.

Finishing applies the stored IPS to the vanilla bytes in memory, runs the finishing
`PatchStack` on that unfinished ROM with the stack's vanilla hash check disabled
(`base_sha1=None`), and diffs the result against vanilla to produce the finished IPS. Overlap tracking is per stack,
so a finishing patch rewriting bytes the unfinished stage wrote is allowed. `qr_credentials`
and `qr_disable` rewrite bytes `scorecard_qr` wrote by design; one unit test builds both
stages as a single stack and asserts those are the only overlaps.

Generation runs in a threadpool behind a semaphore so a burst of requests serializes
instead of piling up. One uvicorn worker is enough to start.

Storing the unfinished IPS means everything upstream of it, the hole data, transforms and
seed-level patches, is fixed for the life of the seed regardless of later changes to the
catalog or the patches. That is the catalog immutability of `randomizer.md` Appendix C
without maintaining old versions. An admin action rebuilds a seed when a fix should be
applied.

### ROM gating

The ROM never leaves the browser. The ROM setup page reads the file, hashes it with
SubtleCrypto, and keeps the bytes in IndexedDB so players upload once. The download
request carries the hashes, and the server refuses a finished IPS for a manifest whose
holes or music come from Mario Open unless the JP hash is present. The seed page says up
front which ROMs a seed needs, from `required_roms` (`docs/manifest.md`). This is a speed bump, as `randomizer.md` accepts.

### Users and access

Nothing requires sign-in. Discord OAuth2 with the `identify` scope, hand-rolled with two
httpx calls, and a signed session cookie through Starlette's session middleware. A
development-only login bypass behind an environment flag keeps local work off Discord.

- Seed pages are public.
- Generating works signed out; the seed records its creator when there is one.
- Downloading works signed out and produces a guest ROM. Signed in, it creates or
  updates the user's entry and produces a ROM that can submit.
- The QR endpoint requires nothing: the phone doing the scan may not be signed in, and
  the MAC is the authentication.

Generation is rate limited, since it is the one request a stranger can use to make the
server do work and store bytes. A token bucket in process memory on `POST /generate`,
keyed by user id when signed in and by client IP otherwise, answered with a 429 page.
There is no global ceiling: a surge of real users should queue on the generation
semaphore, not be refused. The client IP is read from the forwarded header the reverse
proxy sets and nothing else. Downloads are not limited: finishing takes milliseconds and
stores nothing for guests. Seeds are never expired or cleaned up, because seed pages are
the share link.

Stats are the carrot: the seed page tells a signed-out player what signing in gets
them, and the guest marker stops a league member playing a full round on a ROM that
cannot submit.

### Data model

| Table | Holds |
|---|---|
| `users` | Discord id, username (use Discord "global_name", update on log-in as needed), avatar, a random unique uint32 `player_id` generated at first login, created_at, last_login |
| `seeds` | A 10-character base62 id for URLs and the same value as an integer, `qr_seed_id`, both unique; manifest JSON, generator and catalog versions, curation stamp, the unfinished IPS blob, nullable creator, created_at |
| `seed_holes` | seed, position 1-18, catalog hole id, transforms, par, wind seed, pin index, wind direction anchor, wind speed anchor. Pure denormalization of the manifest for SQL stats; a migration can always backfill it |
| `entries` | One per (seed, user), unique. The player's choices for this seed (name, clubs, optional player 2 name), one MAC key per slot, created_at |
| `submissions` | entry, slot, raw payload, total strokes, total putts, received_at, flagged. Unique on (entry, slot), which is the first-submission rule |
| `submission_holes` | submission, position, strokes, putts. Joins to `seed_holes` on (seed, position) |

An entry is the record that a signed-in player has entered a seed, in the tournament
sense. Downloading again reads the entry and finishes the same ROM with the same
credentials; it creates nothing. Settings lock once the entry has a submission.

The player ID is the user's, written to both ROM slots. The payload's slot flag tells the
two apart, so a slot 1 submission is recorded against the same entry as the teammate's
round. Keys are per (entry, slot) so a leaked key is good for one seed only, and they
never appear in a manifest. Resolving a scan is: seed ID to seed, player ID to user, the
entry for that pair, the key for that slot.

#### Generating player_id

In Python, on first login:

```python
import secrets, sqlite3

def new_player_id() -> int:
    while True:
        value = secrets.randbits(32)
        if value != 0:
            return value

for _ in range(10):
    try:
        db.execute("INSERT INTO users (discord_id, player_id, ...) VALUES (?, ?, ...)",
                   (discord_id, new_player_id(), ...))
        break
    except sqlite3.IntegrityError:
        continue  # player_id collision; draw again
```

with the column declared as:

```sql
player_id INTEGER NOT NULL UNIQUE CHECK (player_id BETWEEN 1 AND 4294967295)
```

#### Generating seed ids

A seed's `qr_seed_id` is drawn uniformly from 1 to 62^10 - 1 when the row is inserted, and
its URL id is that integer in base62 (`0-9A-Za-z`, most significant digit first), padded to
10 characters. 62^10 is below 2^60, so every URL id converts to a seed ID the QR payload's
8 bytes hold and SQLite's signed `INTEGER` stores, and zero, which the server rejects as a
seed ID, is never drawn. A collision on either unique column draws again, as for
`player_id`:

```sql
qr_seed_id INTEGER NOT NULL UNIQUE CHECK (qr_seed_id BETWEEN 1 AND 839299365868340223)
```

### Routes

| Route | Purpose |
|---|---|
| `GET /` | What this is, links to ROM setup and generate |
| `GET /rom` | ROM setup, pure client-side: pick files, hash, store in IndexedDB, show verified status |
| `GET /generate`, `POST /generate` | Settings form: pool filters, par target, mercy point, club rules, music or random. POST redirects to the seed page |
| `GET /h/<id>` | Seed page: the magic words, hole list with source, par and yards, totals, music, settings, required ROMs, the download form, the signed-in user's entry if any, recorded rounds |
| `GET /h/<id>.json` | The manifest |
| `POST /h/<id>/patch.ips` | Name, clubs, ROM hashes in; the finished IPS out. Signed in, upserts the entry and finishes with credentials; signed out, finishes as a guest. The page's script intercepts the form submit, fetches this, patches the ROM from IndexedDB and triggers the download |
| `GET /s/<48 chars>` | QR submission: decode, verify MAC, record, render the result or the rejection |
| `GET /auth/login`, `GET /auth/callback`, `POST /auth/logout` | Discord sign-in |
| `GET /me` | The player's entries and rounds |
| `GET /admin/...` | Seeds, submissions, flag, rebuild. Token gated |
| `GET /healthz` | For the reverse proxy |

Everything is a form or a link. The only fetch from JavaScript is the IPS.

**Configuration** from the environment: database path, the server's vanilla ROM
directory, the rehydrated holes directory, the public base URL (also the OAuth redirect
base; the QR URL prefix is assembled into the port and fixed before the first public seed
ships), Discord client id and secret, session secret, admin token, and the development
login bypass.

## Development plan

Each item is about one pull request of work and ends with tests passing and, where it
says so, a ROM playtested. Items 1 to 6 build the library; 7 onward build the site.

1. **Catalog.** Done: `golf/randomizer/catalog.py` and `golf/randomizer/curation.py`, the
   index at `data/catalog/holes.json`, the curation file, and `golf-catalog-sync`, which
   adds and verifies vanilla entries without ever rewriting one. See `docs/catalog.md`.
2. **Layout generation.** Done: `golf/randomizer/layout.py`. Distinct permutations of
   par counts, built a nine at a time and joined, filtered by the predicates in
   `randomizer.md`. Par 72 is four par 3s, ten par 4s and four par 5s; par 71 and 70 drop
   par 5s. Each par value splits evenly across the nines, an odd count putting its extra
   hole in either nine, and no par 3s or par 5s are consecutive, including holes 9 and 10.
   That leaves 188,802 layouts at par 72, 165,564 at 71 and 35,574 at 70.
3. **Manifest and generation.** Done: `golf/randomizer/manifest.py`, `pool.py`,
   `generate.py`, `music.py` and `words.py`. The manifest's version fields, settings and
   concrete course with club rules and magic words, and its strict JSON; the pool from
   sources, curation tags, the newest drawable version of each lineage and families;
   `generate(catalog, curation, settings) -> Manifest`, which draws a family per slot into
   a layout, chooses the music, derives the wind seeds and draws the magic words, each from
   its own stream of the PRNG seed. See `docs/manifest.md`.
4. **QR patch split.** Done: `scorecard_qr` (`golf/core/patches/scorecard_qr.py`) writes
   the image with its placeholders at the fill; `qr_credentials`
   (`golf/core/patches/qr_credentials.py`) is three byte patches that fill them, expecting
   the fill; `qr_disable` reverts the splice for guest ROMs. All three are registered, and
   `tests/integration/test_qr_patch_rom.py` covers them on the real ROM. See
   `docs/scorecard_qr.md`.
5. **Build stages.** The unfinished stack from a manifest and the finishing stack from
   player options in both flavours, in `golf/randomizer/`. The unit test that builds
   both stages as a single stack to prove no overlap, and an integration test that
   builds a finished ROM from a manifest on the real ROM. Playtest that ROM.
6. **`golf-randomize` CLI.** Settings in, manifest out; manifest in, unfinished or
   finished ROM or IPS out. Registered in `pyproject.toml` and the `README.md` command
   index. Delete `tools/randomize.py`.
7. **Site skeleton.** `site/`: FastAPI app, Jinja2, vendored Pico, sqlite3 with
   migrations, configuration from the environment, health check, home page, and the
   ROM setup page with its hashing and IndexedDB script. Tests against the app with
   an in-memory database.
8. **Generate and seed page.** The settings form, the seed and seed_holes rows, the
   unfinished IPS built in the threadpool and stored, the rate limiter, the seed page
   and manifest JSON rendered from the manifest and catalog.
9. **Download flow.** The download form gated on the ROM store, the IPS endpoint with
   hash gating on the manifest's required ROMs and guest finishing, the JavaScript patcher. The site can now run a
   league of guest ROMs. Playtest a downloaded ROM.
10. **Discord sign-in.** The OAuth flow, sessions, the development bypass, the users
    table with its player ID, sign-in and sign-out in the page header.
11. **Entries.** Entries created and updated by the download form, signed-in finishing
    with credentials, settings locked once a submission exists, `/me` listing entries.
12. **Submissions.** The QR endpoint reusing `golf.qr.payload` for decoding and MAC
    verification, submissions and submission_holes rows, rounds on the seed page and
    `/me`, the teammate slot rule. Playtest a round through to a recorded scan.
13. **Admin.** Token-gated views of seeds and submissions, flag, and rebuild a seed.
14. **Vanilla data out of the repository.** The ROM rehydration script that regenerates
    the course directories from the server's vanilla ROMs, verified against the index's
    content hashes with `golf-catalog-sync --check`, then strip the course data from the
    repository and point the tests at rehydrated data.
15. **Deployment.** A systemd unit or container, reverse proxy configuration,
    Litestream, and a deployment note under `docs/`.
16. **Polish.** The guest menu marker once its wording is settled, difficulty filters,
    mirrored holes and the transforms column, hole thumbnails, multi-course generation.
