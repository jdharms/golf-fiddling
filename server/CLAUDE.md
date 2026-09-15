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
  shared objects live on `app.state`: `config`, and `db` once the lifespan has started.
  Nothing is module-level state, so each test builds its own app.
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

## Pages

- Server-rendered Jinja2 in `server/templates/`, extending `base.html`, styled with the
  vendored Pico CSS green theme (`server/static/VENDORED.md`). Pass `page` in the context
  for the nav highlight. Reference static files by `/static/...` paths.
- `server/static/site.css` holds only rules Pico has no class for, and takes its colors
  from Pico's variables (`--pico-ins-color`, `--pico-del-color` and the like) so dark mode
  follows. Components that change look with script state carry a `data-state` attribute
  the stylesheet selects on, rather than the script toggling styles or `hidden`.
- JavaScript only where the browser must act: hashing and storing ROMs
  (`server/static/rom.js`) and, later, applying an IPS. Plain scripts, no build step, no
  frameworks. Everything else is a form or a link.
- The ROM store is IndexedDB database `golf-randomizer`, object store `roms`, records
  `{id, sha1, bytes}` keyed by catalog ROM id. It holds only files whose SHA-1 matched.

## Tests

`tests/unit/test_server_*.py`. Build the app with `create_app(Config(database=":memory:"))`
and use `TestClient` as a context manager so the lifespan opens and migrates the
database. Database tests use `Database(":memory:")` directly.
