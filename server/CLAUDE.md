# server/ - the randomizer website

The FastAPI app for the randomizer site. Architecture, data model, routes and the ordered
work items are in `docs/randomizer_devplan.md`; this file holds the conventions for code
in this package.

## Layering

- `server/` imports from `golf/` and never from `tools/`. Generation, builds and anything
  a test or CLI would also want (such as the vanilla ROM list in
  `golf/randomizer/roms.py`) belongs in `golf/`, with no web dependency.
- `tools/site.py` (`golf-site`) is only a uvicorn launcher.

## App

- `server/app.py` has `create_app(config)`, a factory. Routes are defined inside it, and
  shared objects live on `app.state`: `config`, `strings` and `rate_limiter`, and `db` and
  `builder` once the lifespan has started. Nothing is module-level state, so each test
  builds its own app.
- `server/builder.py`'s `SeedBuilder` is the only thing a route calls to generate or build.
  It holds the catalog and curation the seed page also reads, and reads the server's ROM
  on first build. Builds run in the threadpool (`run_in_threadpool`), never on the event
  loop.
- Route helpers with no web types live beside the app: `server/forms.py` (form to
  `Settings`), `server/views.py` (what a page shows, as dataclasses) and
  `server/ratelimit.py`.
- Configuration is `server/config.py`, read from `GOLF_`-prefixed environment variables.
  A new setting is a field there, a variable in the README's "Running the site" list, and
  a line in the devplan's configuration paragraph.

## Database

- `server/db.py` keeps one `sqlite3` connection in autocommit mode behind a lock. Every
  read or write goes through `db.transaction()`, which holds the lock for its duration:
  keep work inside it short, and never build a ROM while holding it.
- The schema is `server/migrations.py`, ordered SQL scripts applied by `PRAGMA
  user_version`. A committed script is never edited; a schema change appends a script.
  A table arrives with the work item that first writes to it.
- `server/seeds.py` is the only code that writes `seeds` and `seed_holes`, and the only
  place seed ids are drawn or converted.

## Pages

- Server-rendered Jinja2 in `server/templates/`, extending `base.html`, styled with the
  vendored Pico CSS green theme (`server/static/VENDORED.md`). Pass `page` in the context
  for the nav highlight. Reference static files by `/static/...` paths.
- `server/static/site.css` holds only rules Pico has no class for, and takes its colors
  from Pico's variables (`--pico-ins-color`, `--pico-del-color` and the like) so dark mode
  follows. Components that change look with script state carry a `data-state` attribute
  the stylesheet selects on, rather than the script toggling styles or `hidden`.
- No English in templates or scripts: see "Player-facing text" below.
- A page that shows one of several messages, such as the generate form's refusal notices,
  picks each in an `if` chain calling `t()` with its literal key, never a key built from
  a variable, so the strings test can find every key.
- JavaScript only where the browser must act: hashing and storing ROMs
  (`server/static/rom.js`) and, later, applying an IPS. Plain scripts, no build step, no
  frameworks. Everything else is a form or a link.
- The ROM store is IndexedDB database `golf-randomizer`, object store `roms`, records
  `{id, sha1, bytes}` keyed by catalog ROM id. It holds only files whose SHA-1 matched.

## Player-facing text

A trial begun 2026-09-15. jdharms composes every English word a player sees, and Claude
writes none of it, not even as a draft to be rewritten.

- Every visible string, including tab titles, nav labels, button labels, accessible names
  and script status messages, comes from `server/strings.toml` by key. No English goes in
  a template or script. Proper nouns and data are not strings: ROM titles, hole ids, magic
  words.
- An entry is a `note` and a `text`. Claude adds keys and notes and never writes or edits
  `text`. A note is terse fragments of what the string has to get across and the values it
  receives, never wording that could be kept. Notes starting `plain:` mark strings that
  take no HTML.
- Templates call `t("key", name=value)`, whose text may hold inline HTML with values
  escaped, or `t_plain(...)` for tab titles, attributes and anything else HTML would break.
  Empty text renders as a marked placeholder showing the key, with the note on hover.
- A script gets its entries as JSON: the route passes `strings.for_script(prefix)` and the
  template embeds it in a `<script type="application/json">` element. The script's own
  `t()` reads it, and calls it with literal keys so the tests can find them. Script
  strings may hold inline HTML like any other: `t()` escapes the values it inserts and
  returns HTML, which the script sets with `innerHTML`.
- `tests/unit/test_server_strings.py` checks that every key a template or script uses is
  in the catalog, and that every entry is used.
- `golf-site --reload` restarts on changes to the catalog, since the app loads it once.

## Seeing pages

After changing a template, `site.css` or a page script, render the pages and look at the
PNGs before reporting the change done:

```bash
uv run golf-site-screenshot / /rom /generate --generate -o <scratchpad>/shots \
  --rom nes_open_us=nes_open_us.nes --rom mario_open_jp=mario_open_jp.nes
```

It serves the app on an in-memory database, captures each page at desktop and phone
widths in light and dark, and exits 1 on a browser console error or a failed request. With
`--rom`, the ROM setup page is captured again after loading those files, and the final card
states are printed. Pass a patched ROM to capture the mismatch state. With `--generate`,
the generate form is submitted and the seed page it lands on is captured as
`<name>-seed.png`; that builds a real seed from the ROM in `GOLF_ROM_DIR`. The tool is
`tools/site_screenshot.py`; `tests/integration/test_site_screenshot.py` skips without a
Playwright browser.

## Tests

`tests/unit/test_server_*.py`. Build the app with `create_app(Config(database=":memory:"))`
and use `TestClient` as a context manager so the lifespan opens and migrates the
database. Database tests use `Database(":memory:")` directly.

Posting to `/generate` builds a ROM, so unit tests pass `builder=` a `SeedBuilder` subclass
whose `build` returns a fixed blob, and `rate_limiter=` a small `RateLimiter` to test
refusals (`tests/unit/test_server_app.py`). `tests/integration/test_server_generate_rom.py`
runs the real builder.

A test that checks *which* refusal notice a page shows names it by string key and builds the
app with `strings=UNWRITTEN`, a catalog with nothing written, in which every string renders
as the placeholder naming its key and the values passed to it. The assertion then holds
whatever `strings.toml` says.
