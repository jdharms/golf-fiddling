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
dependencies. The FastAPI app lives in the top-level `server/` package (`web/` is the
rangefinder; `site` would shadow the standard library module) and imports from `golf/`
only. `golf-site` (`tools/site.py`) runs it under uvicorn. A `golf-randomize` CLI drives the same code
so ROMs can be built and playtested from a manifest file offline; it lives at
`tools/randomize.py`.

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
  scorecard QR image with its credential placeholders unfilled. The manifest also carries
  the seed's SRAM magic, which only finishing writes. The result is stored as an IPS blob
  on the seed row. The server rejects QR code submissions with all-zero seed IDs, so an
  unfinished ROM cannot cause downstream problems.
- **Finished.** Run per download, in milliseconds: SRAM defaults for name, clubs and
  music under the seed's SRAM magic, so a save from vanilla or another seed is rebuilt
  with the player's choices, and one of two flavours.
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
and `qr_disable` rewrite bytes `scorecard_qr` wrote by design. An integration test
(`tests/integration/test_build_rom.py`) asserts those are the only overlaps between the
stages, and that one stack of both is refused at the QR finishing patch.

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
httpx calls (`server/auth.py`): the code is exchanged for a token, the token reads
`/users/@me`, and the token is thrown away. The session is a signed cookie through
Starlette's session middleware, SameSite=lax, and holds only the user's `users.id`, plus
the OAuth `state` and return path while a sign-in is under way. A development-only login
bypass, `GOLF_DEV_LOGIN`, keeps local work off Discord: `/auth/login?as=<name>` signs in as
the user `dev:<name>`, and the site refuses to start with it on unless the base URL is
localhost.

- Seed pages are public.
- Generating works signed out; the seed records its creator's `users.id` when there is
  one. Seed pages do not show it.
- Downloading works signed out and produces a guest ROM. Signed in, it creates or
  updates the user's entry and produces a ROM that can submit.
- The QR endpoint requires nothing: the phone doing the scan may not be signed in, and
  the MAC is the authentication.

Generation is rate limited, since it is the one request a stranger can use to make the
server do work and store bytes. A token bucket in process memory on `POST /generate`,
keyed `user:<users.id>` when signed in and `ip:<address>` otherwise, answered with a 429 page. A
bucket holds five seeds and gets one back a minute (`server/ratelimit.py`), and only a
submission the form accepts spends one. There is no global ceiling: a surge of real users
should queue on the generation semaphore, not be refused. The client IP is the last entry
of the forwarded header the reverse proxy sets, the address the proxy saw, or the socket's
peer when there is no header, as in development. Downloads are not limited: finishing takes milliseconds and
stores nothing for guests. Seeds are never expired or cleaned up, because seed pages are
the share link.

Stats are the carrot: the seed page tells a signed-out player what signing in gets
them, and the guest marker stops a league member playing a full round on a ROM that
cannot submit.

### Data model

| Table | Holds |
|---|---|
| `users` | Internal id, Discord id (`dev:<name>` for bypass users), Discord `username` and `global_name` (pages show `global_name`, falling back to `username`), avatar hash, a random unique nonzero uint32 `player_id` drawn at first sign-in, created_at, last_login. Names and avatar are refreshed on every sign-in |
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
| `GET /generate`, `POST /generate` | Settings form: par target, source ROMs, family repeats, music or random, and club rules in a section of their own. The mercy point and tag filters take their defaults. POST redirects to the seed page |
| `GET /h/<id>` | Seed page: the magic words, hole list with source, par and yards, totals, music, settings, required ROMs, the download form, the signed-in user's entry if any, recorded rounds |
| `GET /h/<id>.json` | The manifest |
| `POST /h/<id>/patch.ips` | Name, clubs, ROM hashes in; the finished IPS out. Signed in, upserts the entry and finishes with credentials; signed out, finishes as a guest. The page's script intercepts the form submit, fetches this, patches the ROM from IndexedDB and triggers the download |
| `GET /s/<48 chars>` | QR submission: decode, verify MAC, record, render the result or the rejection |
| `GET /auth/login`, `GET /auth/callback`, `POST /auth/logout` | Discord sign-in |
| `GET /me` | The player's entries and rounds |
| `GET /admin/...` | Seeds, submissions, flag, rebuild. Token gated |
| `GET /healthz` | For the reverse proxy |

Everything is a form or a link. The only fetch from JavaScript is the IPS.

**Configuration** from the environment (`server/config.py`): the database path
`GOLF_DATABASE`, the server's vanilla ROM directory `GOLF_ROM_DIR` holding the ROMs under
the file names in `golf/randomizer/roms.py` (`nes_open_us.nes`, `mario_open_jp.nes`), the rehydrated holes
directory `GOLF_HOLES_DIR`, the public base URL `GOLF_BASE_URL` (also the OAuth redirect
base; the QR URL prefix is assembled into the port and fixed before the first public seed
ships), the Discord client id and secret `GOLF_DISCORD_CLIENT_ID` and
`GOLF_DISCORD_CLIENT_SECRET`, the session secret `GOLF_SESSION_SECRET`, the admin token
`GOLF_ADMIN_TOKEN`, and the development login bypass `GOLF_DEV_LOGIN`.

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
5. **Build stages.** Done: `golf/randomizer/build.py`. `build_unfinished` turns a manifest
   into the unfinished ROM and its IPS; `finish` applies that IPS to vanilla and runs the
   finishing stack for `PlayerOptions` (name, bag, music), checked against the seed's club
   rules, with `credentials_for` or as a guest. The manifest's course gained `sram_magic`,
   drawn per seed. NES Open themes use the new `course_theme` patch rather than an import.
   `tests/integration/test_build_rom.py` builds both flavours from generated manifests on
   the real ROM and checks the stages overlap only where `scorecard_qr` wrote.
6. **`golf-randomize` CLI.** Done: `tools/randomize.py`. `generate` turns settings flags
   into a manifest file, `build` turns a manifest into a finished guest ROM or IPS by
   running both stages, an unfinished one with `--unfinished` or a signed-in one with a
   `golf-qr-credentials` file, and `show` prints a manifest's course. See
   `docs/manifest.md`; `tests/unit/test_randomize_cli.py` and
   `tests/integration/test_randomize_cli_rom.py` check it against the library.
7. **Site skeleton.** Done: `server/`. `create_app` in `server/app.py` with the home page,
   the ROM setup page and `/healthz`; Jinja2 templates on vendored Pico CSS; `Config`
   from `GOLF_` environment variables; `Database` in `server/db.py`, one locked sqlite3
   connection in WAL mode, migrated by `PRAGMA user_version` from the ordered scripts in
   `server/migrations.py`, the first creating `seeds` and `seed_holes`. The vanilla ROMs
   and their SHA-1s are `golf/randomizer/roms.py`; `server/static/rom.js` hashes a chosen
   file with SubtleCrypto and stores verified bytes in IndexedDB. `golf-site` launches
   it. `tests/unit/test_server_app.py`, `test_server_db.py` and `test_server_config.py`
   run against an in-memory database. See `server/CLAUDE.md`.
8. **Generate and seed page.** Done: `/generate`, `/h/<id>` and `/h/<id>.json`.
   `server/forms.py` turns the form into `Settings`, refusing with a reason the page shows;
   `server/builder.py`'s `SeedBuilder` generates and builds the unfinished IPS behind a
   semaphore, reading the server's ROM on first use; `server/seeds.py` draws the base62
   id and writes the seed and its 18 `seed_holes` rows, with the pin and wind anchors from
   `predict_hole`; `server/ratelimit.py` is the token bucket; `server/views.py` shapes the
   form's choices and the seed page from the manifest and catalog. A missing page renders
   `not_found.html`. `tests/unit/test_server_app.py`, `test_server_forms.py`,
   `test_server_seeds.py`, `test_server_ratelimit.py` and `test_server_builder.py` run
   without a ROM; `tests/integration/test_server_generate_rom.py` checks the stored IPS
   against `build_unfinished`.
9. **Download flow.** Done: the seed page's download form and `POST /h/<id>/patch.ips`.
   `server/forms.py`'s `DownloadState` reads the player's name and clubs and a `rom_<id>`
   field per stored ROM holding its SHA-1; `check_rom_hashes` refuses a download missing any
   of the manifest's required ROMs, and `player_options_from_state` checks the bag against
   the seed's club rules, a locked bag replacing whatever was sent. `SeedBuilder.finish`
   finishes the stored IPS as a guest. Refusals are JSON reasons the page's script shows.
   `server/static/romstore.js` is the ROM store and string lookup both page scripts share;
   `server/static/download.js` gates the form on the store, fetches the IPS, applies it to
   the stored US ROM and saves it as `notgr_par<par>_<id>.nes`, a name that marks a
   randomizer ROM, tells seeds apart by par and leads back to the seed page (`download_stem`
   in `server/views.py`). `tests/unit/test_server_app.py` and `test_server_forms.py` run
   without a ROM; `tests/integration/test_server_download_rom.py` checks the served IPS
   against `finish`, and `tests/integration/test_site_download.py` downloads in headless
   Chromium and compares the saved ROM with the library's. The site can now run a league
   of guest ROMs. Playtest a downloaded ROM.
10. **Discord sign-in.** Done: migration 2 adds `users`; `server/users.py` is its only
    writer, with `sign_in` inserting or refreshing a user and drawing the `player_id`.
    `server/auth.py` has `DiscordClient`, `safe_next` and `current_user`. `/auth/login`,
    `/auth/callback` and `/auth/logout` sign in through Discord or the development bypass,
    and a failed Discord sign-in renders `sign_in_failed.html`. `Config.validate` refuses
    the bypass off localhost and Discord without a session secret. The page header shows
    sign-in, or the player's name and sign-out. `POST /generate` records the creator and
    rate-limits per user. `golf-site-screenshot --login` captures pages signed in.
    `tests/unit/test_server_users.py` and `test_server_auth.py` (the client against a mock
    transport), and the sign-in tests in `test_server_app.py`, run without Discord.
11. **Entries.** Entries created and updated by the download form, signed-in finishing
    with credentials, settings locked once a submission exists, `/me` listing entries.
    `sram_defaults` has one default name shared by both players, so a player 2 name
    needs a patch before the form can offer it.
12. **Submissions.** The QR endpoint reusing `golf.qr.payload` for decoding and MAC
    verification, submissions and submission_holes rows, rounds on the seed page and
    `/me`, the teammate slot rule. Playtest a round through to a recorded scan.
13. **Admin.** Token-gated views of seeds and submissions, flag, and rebuild a seed.
14. **Vanilla data out of the repository.** The ROM rehydration script that regenerates
    the course directories from the server's vanilla ROMs, verified against the index's
    content hashes with `golf-catalog-sync --check`, then strip the course data from the
    repository and point the tests at rehydrated data.
15. **Deployment.** A systemd unit or container, reverse proxy configuration,
    Litestream, and a deployment note under `docs/`. Configuration reaches the service
    as environment variables from a root-owned, mode 0600 file the unit names with
    `EnvironmentFile=` (such as `/etc/golf-site/env`), so the service account never reads
    the secrets file. `GOLF_DEV_LOGIN` is never set there, and `GOLF_SESSION_SECRET` stays
    fixed, since changing it signs everyone out. Litestream's storage credentials get a
    file of their own.
16. **Polish.** The guest menu marker once its wording is settled, difficulty filters,
    mirrored holes and the transforms column, hole thumbnails, multi-course generation.
