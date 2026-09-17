"""The FastAPI application factory and its routes. See docs/randomizer_devplan.md, "Routes"."""

import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.sessions import SessionMiddleware

from golf.randomizer.build import credentials_for
from golf.randomizer.generate import GenerationError
from golf.randomizer.manifest import required_roms
from golf.randomizer.roms import VANILLA_ROMS

from .auth import (
    DEV_DISCORD_PREFIX,
    DEV_NAME,
    SESSION_NEXT,
    SESSION_STATE,
    DiscordClient,
    DiscordError,
    current_user,
    safe_next,
    start_session,
)
from .builder import BuilderUnavailableError, SeedBuilder
from .config import Config
from .db import Database
from .entries import entries_for_user, upsert_entry
from .forms import (
    DownloadState,
    FormError,
    FormState,
    check_rom_hashes,
    player_options_from_state,
    settings_from_state,
)
from .ratelimit import (
    GENERATE_CAPACITY,
    GENERATE_REFILL_SECONDS,
    RateLimiter,
    client_key,
)
from .seeds import insert_seed, load_seed, load_unfinished_ips
from .strings import Strings
from .users import sign_in
from .views import download_stem, generate_options, seed_view

HERE = Path(__file__).resolve().parent
STATIC_DIR = HERE / "static"
TEMPLATES_DIR = HERE / "templates"

#: the catalog prefix whose strings the ROM setup page embeds for rom.js
ROM_SCRIPT_STRINGS = "rom.status"
#: the catalog prefix whose strings the seed page embeds for download.js
DOWNLOAD_SCRIPT_STRINGS = "seed.download.status"

#: generate.html shows one notice per value: a FormError reason, or one of these
RATE_LIMITED = "rate_limited"
UNAVAILABLE = "unavailable"
POOL_TOO_SMALL = "pool"

#: paths a missing resource answers with JSON rather than the not-found page
MACHINE_SUFFIXES = (".json", ".ips")

SESSION_COOKIE = "golf_session"
#: seconds a sign-in lasts
SESSION_MAX_AGE = 30 * 24 * 60 * 60
#: the name /auth/login?as= signs in as when it names none
DEFAULT_DEV_NAME = "dev"
#: sign_in_failed.html shows one notice per value
SIGN_IN_EXPIRED = "expired"
SIGN_IN_UNAVAILABLE = "unavailable"


def json_refusal(status_code: int, reason: str, values: dict | None = None) -> JSONResponse:
    """A download refusal: download.js shows the notice for `error`, filled from `values`."""
    return JSONResponse({"error": reason, "values": values or {}}, status_code=status_code)


def create_app(
    config: Config | None = None,
    strings: Strings | None = None,
    builder: SeedBuilder | None = None,
    rate_limiter: RateLimiter | None = None,
    discord: DiscordClient | None = None,
) -> FastAPI:
    """Build the app.

    With no config, reads it from the environment; with no strings, loads the catalog; with
    no builder, makes one from the config when the app starts; with no rate limiter, uses
    the generate limits in `server/ratelimit.py`; with no Discord client, makes one when
    the config has credentials. Raises ConfigError for settings the site refuses.
    """
    config = config if config is not None else Config.from_env()
    config.validate()
    if discord is None and config.discord_enabled:
        discord = DiscordClient(config.discord_client_id or "", config.discord_client_secret or "")
    strings = strings if strings is not None else Strings.load()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        db = Database(config.database)
        try:
            db.migrate()
            app.state.db = db
            app.state.builder = builder if builder is not None else SeedBuilder.from_config(config)
            yield
        finally:
            db.close()

    app = FastAPI(title="NES Open Randomizer", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.config = config
    app.state.strings = strings
    app.state.rate_limiter = (
        rate_limiter if rate_limiter is not None else RateLimiter(GENERATE_CAPACITY, GENERATE_REFILL_SECONDS)
    )
    app.state.discord = discord
    # Without a configured secret (development and tests; validate() insists on one for
    # Discord) sessions are signed with a secret that lasts as long as the process.
    app.add_middleware(
        SessionMiddleware,
        secret_key=config.session_secret or secrets.token_urlsafe(32),
        session_cookie=SESSION_COOKIE,
        max_age=SESSION_MAX_AGE,
        same_site="lax",
        https_only=config.base_url.startswith("https://"),
    )

    def sign_in_context(request: Request) -> dict:
        """What base.html's header needs on every page: the player, and where to come back to."""
        path = request.url.path
        here = path + (f"?{request.url.query}" if request.url.query else "")
        return {
            "user": current_user(request),
            "sign_in_enabled": config.sign_in_enabled,
            "return_path": "/" if path.startswith("/auth/") else here,
        }

    templates = Jinja2Templates(directory=TEMPLATES_DIR, context_processors=[sign_in_context])
    templates.env.globals["t"] = strings.html
    templates.env.globals["t_plain"] = strings.plain
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    def not_found() -> HTTPException:
        return HTTPException(status_code=404)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> Response:
        if exc.status_code == 404 and not request.url.path.endswith(MACHINE_SUFFIXES):
            return templates.TemplateResponse(
                request,
                "not_found.html",
                {"page": None},
                status_code=404
            )
        return await http_exception_handler(request, exc)

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request):
        return templates.TemplateResponse(request, "home.html", {"page": "home"})

    @app.get("/rom", response_class=HTMLResponse)
    def rom_setup(request: Request):
        return templates.TemplateResponse(
            request,
            "rom.html",
            {"page": "rom", "roms": VANILLA_ROMS, "rom_strings": strings.for_script(ROM_SCRIPT_STRINGS)},
        )

    def generate_page(
        request: Request,
        state: FormState,
        error: str | None = None,
        error_values: dict | None = None,
        status_code: int = 200,
    ):
        return templates.TemplateResponse(
            request,
            "generate.html",
            {
                "page": "generate",
                "options": generate_options(),
                "form": state,
                "error": error,
                "error_values": error_values or {},
            },
            status_code=status_code,
        )

    @app.get("/generate", response_class=HTMLResponse)
    def generate_form(request: Request):
        return generate_page(request, FormState.default())

    @app.post("/generate", response_class=HTMLResponse)
    async def generate_seed(request: Request):
        state = FormState.from_form(await request.form())
        try:
            settings = settings_from_state(state)
        except FormError as problem:
            return generate_page(request, state, problem.reason, problem.values, status_code=400)

        user = current_user(request)
        user_id = user.id if user is not None else None
        # Only a submission that would make the server work spends a token.
        if not request.app.state.rate_limiter.allow(client_key(request, user_id)):
            return generate_page(request, state, RATE_LIMITED, status_code=429)

        seed_builder: SeedBuilder = request.app.state.builder
        db: Database = request.app.state.db

        def create() -> str:
            manifest = seed_builder.generate(settings)
            unfinished_ips = seed_builder.build(manifest)
            return insert_seed(db, manifest, unfinished_ips, creator_id=user_id)

        try:
            seed_id = await run_in_threadpool(create)
        except GenerationError:
            return generate_page(request, state, POOL_TOO_SMALL, status_code=400)
        except BuilderUnavailableError:
            return generate_page(request, state, UNAVAILABLE, status_code=503)
        return RedirectResponse(f"/h/{seed_id}", status_code=303)

    # Registered before the seed page, whose {seed_id} would otherwise match "<id>.json".
    @app.get("/h/{seed_id}.json")
    def seed_manifest(request: Request, seed_id: str):
        row = load_seed(request.app.state.db, seed_id)
        if row is None:
            raise not_found()
        return Response(row.manifest_json, media_type="application/json")

    @app.get("/h/{seed_id}", response_class=HTMLResponse)
    def seed_page(request: Request, seed_id: str):
        row = load_seed(request.app.state.db, seed_id)
        if row is None:
            raise not_found()
        seed_builder: SeedBuilder = request.app.state.builder
        view = seed_view(row, seed_builder.catalog, seed_builder.curation)
        return templates.TemplateResponse(
            request,
            "seed.html",
            {"page": "seed", "seed": view, "download_strings": strings.for_script(DOWNLOAD_SCRIPT_STRINGS)},
        )

    @app.post("/h/{seed_id}/patch.ips")
    async def seed_patch(request: Request, seed_id: str):
        row = load_seed(request.app.state.db, seed_id)
        if row is None:
            raise not_found()
        seed_builder: SeedBuilder = request.app.state.builder
        manifest = row.manifest
        state = DownloadState.from_form(await request.form())
        try:
            check_rom_hashes(state, required_roms(manifest, seed_builder.catalog))
        except FormError as problem:
            return json_refusal(403, problem.reason, problem.values)
        try:
            options = player_options_from_state(state, manifest.course.clubs)
        except FormError as problem:
            return json_refusal(400, problem.reason, problem.values)

        db: Database = request.app.state.db
        unfinished_ips = load_unfinished_ips(db, seed_id)
        if unfinished_ips is None:  # pragma: no cover - seeds are never deleted
            raise not_found()
        # Signed in, the download enters the player in the seed and finishes with their
        # credentials; signed out, it finishes a guest ROM and records nothing.
        user = current_user(request)
        credentials = None
        if user is not None:
            entry = upsert_entry(db, row.id, user.id, options)
            credentials = credentials_for(row.qr_seed_id, user.player_id, entry.keys)
        try:
            patch = await run_in_threadpool(seed_builder.finish, manifest, unfinished_ips, options, credentials)
        except BuilderUnavailableError:
            return json_refusal(503, UNAVAILABLE)
        return Response(
            patch,
            media_type="application/octet-stream",
            headers={"Content-Disposition": f'attachment; filename="{download_stem(row)}.ips"'},
        )

    @app.get("/me", response_class=HTMLResponse)
    def me(request: Request):
        user = current_user(request)
        if user is None:
            if not config.sign_in_enabled:
                raise not_found()
            return RedirectResponse("/auth/login?next=/me", status_code=303)
        entries = entries_for_user(request.app.state.db, user.id)
        return templates.TemplateResponse(request, "me.html", {"page": "me", "entries": entries})

    def sign_in_failed(request: Request, reason: str, status_code: int):
        return templates.TemplateResponse(
            request, "sign_in_failed.html", {"page": None, "reason": reason}, status_code=status_code
        )

    def redirect_uri() -> str:
        return config.base_url.rstrip("/") + "/auth/callback"

    @app.get("/auth/login")
    def auth_login(request: Request, next: str | None = None, as_: str | None = Query(None, alias="as")):
        if not config.sign_in_enabled:
            raise not_found()
        return_to = safe_next(next)
        if config.dev_login:
            name = as_ if as_ is not None else DEFAULT_DEV_NAME
            if not DEV_NAME.fullmatch(name):
                raise HTTPException(status_code=400)
            user = sign_in(request.app.state.db, DEV_DISCORD_PREFIX + name, name, None, None)
            start_session(request, user)
            return RedirectResponse(return_to, status_code=303)
        state = secrets.token_urlsafe(32)
        request.session[SESSION_STATE] = state
        request.session[SESSION_NEXT] = return_to
        discord_client: DiscordClient = request.app.state.discord
        return RedirectResponse(discord_client.authorize_url(state, redirect_uri()), status_code=303)

    @app.get("/auth/callback")
    async def auth_callback(
        request: Request, code: str | None = None, state: str | None = None, error: str | None = None
    ):
        discord_client: DiscordClient | None = request.app.state.discord
        if config.dev_login or discord_client is None:
            raise not_found()
        expected = request.session.pop(SESSION_STATE, None)
        return_to = safe_next(request.session.pop(SESSION_NEXT, None))
        if not expected or not state or not secrets.compare_digest(expected, state):
            return sign_in_failed(request, SIGN_IN_EXPIRED, 400)
        if error is not None or not code:
            # The player turned Discord down: back where they were, still signed out.
            return RedirectResponse(return_to, status_code=303)
        try:
            identity = await discord_client.identify(code, redirect_uri())
        except DiscordError:
            return sign_in_failed(request, SIGN_IN_UNAVAILABLE, 502)
        user = sign_in(request.app.state.db, identity.id, identity.username, identity.global_name, identity.avatar)
        start_session(request, user)
        return RedirectResponse(return_to, status_code=303)

    @app.post("/auth/logout")
    async def auth_logout(request: Request):
        form = await request.form()
        next_value = form.get("next")
        request.session.clear()
        return RedirectResponse(safe_next(next_value if isinstance(next_value, str) else None), status_code=303)

    @app.get("/healthz")
    def healthz(request: Request) -> dict[str, str]:
        with request.app.state.db.transaction() as conn:
            conn.execute("SELECT 1").fetchone()
        return {"status": "ok"}

    return app
