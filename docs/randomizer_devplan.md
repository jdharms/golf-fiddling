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
dependencies. The FastAPI app lives in the top-level `server/` package (`web/` held the
rangefinder at the time; `site` would shadow the standard library module) and imports from `golf/`
only. `golf-site` (`tools/site.py`) runs it under uvicorn. A `golf-randomize` CLI drives the same code
so ROMs can be built and playtested from a manifest file offline; it lives at
`tools/randomize.py`. The server's systemd unit, proxy and backup configuration are
`deploy/`, and `docs/deployment.md` is how they are installed and releases deployed.

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
without maintaining old versions. A fix is published as a new seed rather than changing
the ROM an existing seed produces.

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
- The admin pages under `/admin` admit the signed-in users whose Discord ids
  `GOLF_ADMIN_USERS` lists (`dev:<name>` under the bypass), checked on every request.
  Anyone else gets the not-found page, and nothing links to them. Admin actions are POSTs,
  which a cross-site form cannot make signed in under the SameSite=lax cookie.

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
| `seeds` | A 10-character base62 id for URLs and the same value as an integer, `qr_seed_id`, both unique; manifest JSON, generator and catalog versions, curation stamp, the immutable unfinished IPS blob, nullable creator and created_at |
| `seed_holes` | seed, position 1-18, catalog hole id, transforms, par, wind seed, pin index, wind direction anchor, wind speed anchor. Pure denormalization of the manifest for SQL stats; a migration can always backfill it |
| `entries` | One per (seed, user), unique. The player's choices at their latest download (name, clubs), one MAC key per slot, created_at, updated_at |
| `rounds` | A scan the server accepted: a unique `public_id`, the base62 id of its `/r/<id>` permalink; entry, slot, raw payload, total strokes, total putts, received_at, flagged, with an admin-only flag note. Unique on (entry, slot), which is the first-submission rule |
| `round_holes` | round, position, strokes, putts. Joins to `seed_holes` on (seed, position) |
| `voided_rounds` | A round an admin voided: its `public_id`, entry, slot, the payload (unique, and holding every hole, so no hole rows), received_at, its flag and note, voided_at, an admin-only note. A scan of a voided payload is refused; restoring moves it back while its slot is empty |
| `admin_actions` | The audit log: admin, action, target type and id, the admin's note, a JSON detail object, created_at. Who flagged, voided or restored a round, and its complete history, is read from here rather than from columns on the round itself |

An entry is the record that a signed-in player has entered a seed, in the tournament
sense. Downloading again updates the entry's choices and finishes with the same
credentials: the keys are drawn when the entry is created and never change. Settings lock
once the entry has a round.

An entry's name and clubs are the new-save defaults of the latest download, not a record of
the bag a round was played with. A save made before a re-download keeps its old defaults
under the seed's SRAM magic, an older ROM file still submits, and the club house's CHOOSE
CLUBS changes the bag in-game, so the bag is on the honour system.

A scan is submitted; a scan the server accepts becomes a round, and a rejected one is
stored nowhere. A round's `public_id` is drawn when it is recorded, moves to
`voided_rounds` on a void and back on a restore, and is never reused: a different round
filling a freed slot draws its own. It is the one id the site names a round by, in
`/r/<id>`, the admin pages and the audit log, so each follows one scorecard for good. The
row id stays internal, since a void and restore changes it and SQLite can hand it to a
later round.

The player ID is the user's, written to both ROM slots. The payload's slot flag tells the
two apart, so a slot 1 round is recorded against the same entry as the teammate's
round. Keys are per (entry, slot) so a leaked key is good for one seed only, and they
never appear in a manifest. Resolving a scan is: seed ID to seed, player ID to user, the
entry for that pair, the key for that slot.

#### The audit log

Each admin action inserts one `admin_actions` row through `audit.record`, on the connection
of the transaction that makes the change. Nothing records who acted in a column of its own,
so adding an action needs no migration, nothing overwrites an earlier action, and an action
whose transaction rolls back leaves no row. `detail` holds anything an action needs
remembered beyond its target.

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
10 characters. The alphabet and codec are `server/ids.py`, which a round's permalink id
shares; a round's is drawn as text, since nothing but the URL holds it. 62^10 is below 2^60, so every URL id converts to a seed ID the QR payload's
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
| `GET /pages/<slug>` | A checked-in Markdown page; enabled unlisted pages remain available by direct URL, while disabled pages answer 404 |
| `GET /rom` | ROM setup, pure client-side: pick files, hash, store in IndexedDB, show verified status |
| `GET /generate`, `POST /generate` | Settings form: par target, source ROMs, music or random, and club rules in a collapsed section of their own, open when a returned form has them set. The family repeats toggle is in the form but hidden until the families are mapped. The mercy point and tag filters take their defaults. POST redirects to the seed page |
| `GET /h/<id>` | Seed page: the magic words, hole list with source, par and yards, totals, music, settings, required ROMs, the download form, the signed-in user's entry if any, recorded rounds |
| `GET /h/<id>.json` | The manifest |
| `POST /h/<id>/patch.ips` | Name, clubs, ROM hashes in; the finished IPS out. Signed in, upserts the entry and finishes with credentials; signed out, finishes as a guest. The page's script intercepts the form submit, fetches this, patches the ROM from IndexedDB and triggers the download |
| `GET /s/<48 chars>` | QR submission: decode, verify MAC, record, then 303 to the round's permalink, with `?recorded` for the scan that recorded it. Uncached. A rejection has no round to point at, so it renders here |
| `GET /r/<id>` | A round's permalink: its scorecard, or 410 and a page of its own once an admin has voided it. An ordinary cacheable page, linked from the seed page, `/me` and a scan |
| `GET /auth/login`, `GET /auth/callback`, `POST /auth/logout` | Discord sign-in |
| `GET /me` | The player's entries and rounds. Signed out, redirects to sign-in |
| `GET /admin/...` | Counts, seeds, rounds (flagged filter), users, voided rounds, admin activity, and each seed, round and user. Admins only |
| `POST /admin/rounds/<id>/flag`, `.../unflag`, `.../void`, `.../restore` | Flag with a note, clear the flag, void with a note, restore into an empty slot. `<id>` is the round's `public_id` |
| `GET /healthz` | For the reverse proxy |

Everything is a form or a link. The only fetch from JavaScript is the IPS.

**Configuration** from the environment (`server/config.py`): the database path
`GOLF_DATABASE`, the server's vanilla ROM directory `GOLF_ROM_DIR` holding the ROMs under
the file names in `golf/randomizer/roms.py` (`nes_open_us.nes`, `mario_open_jp.nes`), the holes directory
`GOLF_HOLES_DIR` that `golf-rehydrate` fills from them, the rangefinder render directory
`GOLF_RANGEFINDER_DIR` it renders into, the public base URL `GOLF_BASE_URL` (also the OAuth redirect
base; the QR URL prefix is assembled into the port and fixed before the first public seed
ships), the Discord client id and secret `GOLF_DISCORD_CLIENT_ID` and
`GOLF_DISCORD_CLIENT_SECRET`, the session secret `GOLF_SESSION_SECRET`, the admin users
`GOLF_ADMIN_USERS`, and the development login bypass `GOLF_DEV_LOGIN`.

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
   `server/migrations.py`; migration 1 is the frozen version 1.0 baseline. The vanilla ROMs
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
10. **Discord sign-in.** Done: the 1.0 schema includes `users`; `server/users.py` is its only
    writer, with `sign_in` inserting or refreshing a user and drawing the `player_id`.
    `server/auth.py` has `DiscordClient`, `safe_next` and `current_user`. `/auth/login`,
    `/auth/callback` and `/auth/logout` sign in through Discord or the development bypass,
    and a failed Discord sign-in renders `sign_in_failed.html`. `Config.validate` refuses
    the bypass off localhost and Discord without a session secret. The page header shows
    sign-in, or the player's name and sign-out. `POST /generate` records the creator and
    rate-limits per user. `golf-site-screenshot --login` captures pages signed in.
    `tests/unit/test_server_users.py` and `test_server_auth.py` (the client against a mock
    transport), and the sign-in tests in `test_server_app.py`, run without Discord.
11. **Entries.** Done: the 1.0 schema includes `entries`; `server/entries.py` is its only writer,
    with `upsert_entry` creating a player's entry for a seed with two drawn keys or updating
    its name and clubs, and `entries_for_user` listing them. A signed-in download upserts the
    entry and finishes through `SeedBuilder.finish` with `credentials_for` the seed's
    `qr_seed_id`, the user's `player_id` and the entry's keys; a signed-out one is still a
    guest ROM and records nothing. The seed page tells a signed-out player the download is
    a guest ROM and links to sign-in. `/me` lists the player's entries, and the signed-in
    name in the header links to it. `tests/unit/test_server_entries.py` and the entry tests
    in `test_server_app.py` and `test_server_db.py` run without a ROM;
    `tests/integration/test_server_download_rom.py` checks a signed-in download against
    `finish` with the entry's credentials.
12. **Submissions.** Done: the 1.0 schema includes `rounds` and `round_holes`, which
    `server/rounds.py` alone writes. `server/submissions.py`'s `submit_scan` decodes a scan
    with `golf.qr.payload`, rejects it as malformed (length, alphabet, protocol version, reserved
    flags, a slot past 1), unfinished (an all-zero seed or player ID) or unrecognized (no
    entry for the seed and player, or a MAC its slot's key does not verify, one reason for
    all of them), and records it against (entry, slot). A later scan for a recorded entry and
    slot that verifies, identical or not, records nothing and shows the first round.
    `GET /s/<48 chars>` redirects to the round's `/r/<id>`
    permalink, uncached, with `?recorded` on the scan that recorded it, which
    `round.html` turns into its confirmation heading before an inline `replaceState`
    leaves the address bar on the bare permalink. A rejection has no round to point at, so
    it renders in place as `scan_rejected.html`. `GET /r/<id>` renders the round, or
    `round_voided.html` with a 410 once an admin has voided it; the id is drawn from
    `server/ids.py` when the round is recorded and carried through a void and restore.
    The seed page lists the seed's rounds under Discord display names, fewest strokes first,
    each linking to its permalink, and `/me` lists the player's rounds. Once an entry has a round, `upsert_entry` leaves it
    alone: a later download still finishes with the choices it posts and the entry's keys.
    `tests/unit/test_server_submissions.py`, `tests/unit/test_server_rounds.py` and the
    submission tests in `test_server_app.py` and `test_server_db.py` run without a ROM;
    `tests/integration/test_server_submission_rom.py` downloads a signed-in ROM, builds both
    players' URLs by running its QR routine in the simulator, and records them. Playtest a
    round through to a recorded scan.
13. **Admin.** Done: the 1.0 schema includes the flag note and the voided rounds table.
    `Config.admin_users` (`GOLF_ADMIN_USERS`) replaces
    the token. `server/admin.py` holds the admin pages' queries and `server/admin_routes.py`
    their router, behind `require_admin`; the templates in `server/templates/admin/` write
    their own English. `server/rounds.py` holds `flag_round`, `unflag_round`, `void_round` and
    `restore_round`, and `server/submissions.py` refuses a voided payload as unrecognized
    and logs every rejection's exact cause at WARNING. Every action logs itself through
    `server/audit.py`, the only writer of `admin_actions`, inside the transaction that
    makes the change; the admin pages read who acted and each round's history from that
    log, and `/admin/activity` lists it. A round is logged by its `public_id`, so one
    history follows a round through being voided and restored. The seed page and `/me`
    mark flagged rounds. `tests/unit/test_server_admin.py` and the admin tests in
    `test_server_rounds.py`, `test_server_seeds.py`, `test_server_db.py` and
    `test_server_config.py` run without a ROM.
14. **Vanilla data out of the repository.** Done: `golf-rehydrate` (`tools/rehydrate.py`,
    logic in `golf/randomizer/rehydrate.py`) finds the ROMs by name in `GOLF_ROM_DIR`,
    checks their SHA-1s, dumps them through `golf/core/course_dump.py` into a scratch
    directory, verifies every live catalog entry sourced from them, and only then moves
    the hole files into `GOLF_HOLES_DIR`; it then renders the rangefinder through
    `golf/rendering/rangefinder.py`. The US ROM is required and the JP ROM optional.
    `--check` verifies without writing. The course JSON and rangefinder renders are out of
    the repository, with `.gitkeep` markers holding the course directories; `golf-site`
    refuses to start until `check_site_data` passes. Tests read vanilla data through the
    `vanilla_courses`, `vanilla_jp_courses` and `rangefinder_assets` fixtures in
    `tests/conftest.py`, which skip without the ROM and fail with it if the data is
    missing or stale. `tests/unit/test_rehydrate.py` runs without a ROM;
    `tests/integration/test_rehydrate_rom.py` rehydrates from the real ROMs.
15. **Deployment.** `deploy/` and `docs/deployment.md`. The site runs under systemd
    (`deploy/golf-site.service`) as the system user `golf`, one uvicorn worker on
    `127.0.0.1:8000` behind Caddy (`deploy/Caddyfile`), which holds the certificates and
    redirects `www` and HTTP to `https://nesopengolf.com`, the host the QR prefix names.
    `golf-site` trusts the forwarded headers from the loopback address only.
    Configuration reaches the service as environment variables from the root-owned, mode
    0600 `/etc/golf-site/env` the unit names with `EnvironmentFile=`, so the service
    account never reads the secrets file; `deploy/golf-site.env.example` is its template.
    `GOLF_DEV_LOGIN` is never set there, and `GOLF_SESSION_SECRET` stays fixed, since
    changing it signs everyone out. The service can write only `/var/lib/golf-site`, which
    holds the database, the ROMs, the hole store and `GOLF_RANGEFINDER_DIR`, the renders
    the site serves at `/rangefinder-data/`, apart from the checked-in static files. Its
    `ExecStartPre=` runs `golf-rehydrate --check` and a full `golf-rehydrate` only when
    that fails, so every start serves verified data. Litestream (`deploy/litestream.yml`)
    replicates the database with a daily snapshot kept three weeks, its storage credentials in
    a file of their own. A release is a git tag: `deploy/deploy.sh <tag>` checks it out in
    `/opt/golf-site`, runs `uv sync --frozen --no-dev`, restarts and waits for
    `/healthz`, and rolling back is deploying the previous tag. Templates link static files
    through `static_url` (`server/static_files.py`), which versions each URL with a hash
    of the file's contents; versioned responses are immutable and the rest `no-cache`, so
    no browser keeps an old script or stylesheet past a deploy.
    `tests/unit/test_server_static_files.py` covers the versioning.
16. **Polish.** The guest menu marker once its wording is settled, difficulty filters,
    mirrored holes and the transforms column, hole thumbnails, multi-course generation.
    - **Player 2's account.** Both ROM slots carry the downloader's `player_id`, so a
      player 2 round counts toward the downloader's entry. Crediting it to a second
      account is undecided; candidates are a share code shown on `/me` that the teammate
      gives the downloader, and an invite link the teammate opens signed in to join the
      entry.
    - **Bag from ROM.** Repointing the bag reads at a table in PRG ROM (see
      `golf/core/patches/sram_defaults.py`) so no save can change the bag, with CHOOSE
      CLUBS out of the club house. With that in place, SRAM magic derived from the
      player's choices, and keys that change when the choices do, would make an entry's
      bag the bag played.
    - **Phone header.** The site has been laid out for desktop, where seeds are downloaded,
      but the scan page (`/s/`) opens on the phone that scanned the QR code. At phone width
      the header wraps into the site name, the nav links and the sign-in row, taking the
      top 220px or so before the round shows. A compact header on narrow screens, or a
      pared-down header on the scan page alone, would put the result on screen first.
