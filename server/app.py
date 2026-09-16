"""The FastAPI application factory and its routes. See docs/randomizer_devplan.md, "Routes"."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException

from golf.randomizer.generate import GenerationError
from golf.randomizer.roms import VANILLA_ROMS

from .builder import BuilderUnavailableError, SeedBuilder
from .config import Config
from .db import Database
from .forms import FormError, FormState, settings_from_state
from .ratelimit import (
    GENERATE_CAPACITY,
    GENERATE_REFILL_SECONDS,
    RateLimiter,
    client_key,
)
from .seeds import insert_seed, load_seed
from .strings import Strings
from .views import generate_options, seed_view

HERE = Path(__file__).resolve().parent
STATIC_DIR = HERE / "static"
TEMPLATES_DIR = HERE / "templates"

#: the catalog prefix whose strings the ROM setup page embeds for rom.js
ROM_SCRIPT_STRINGS = "rom.status"

#: generate.html shows one notice per value: a FormError reason, or one of these
RATE_LIMITED = "rate_limited"
UNAVAILABLE = "unavailable"
POOL_TOO_SMALL = "pool"


def create_app(
    config: Config | None = None,
    strings: Strings | None = None,
    builder: SeedBuilder | None = None,
    rate_limiter: RateLimiter | None = None,
) -> FastAPI:
    """Build the app.

    With no config, reads it from the environment; with no strings, loads the catalog; with
    no builder, makes one from the config when the app starts; with no rate limiter, uses
    the generate limits in `server/ratelimit.py`.
    """
    config = config if config is not None else Config.from_env()
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
    templates = Jinja2Templates(directory=TEMPLATES_DIR)
    templates.env.globals["t"] = strings.html
    templates.env.globals["t_plain"] = strings.plain
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    def not_found() -> HTTPException:
        return HTTPException(status_code=404)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> Response:
        if exc.status_code == 404 and not request.url.path.endswith(".json"):
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

        # Only a submission that would make the server work spends a token.
        if not request.app.state.rate_limiter.allow(client_key(request)):
            return generate_page(request, state, RATE_LIMITED, status_code=429)

        seed_builder: SeedBuilder = request.app.state.builder
        db: Database = request.app.state.db

        def create() -> str:
            manifest = seed_builder.generate(settings)
            unfinished_ips = seed_builder.build(manifest)
            return insert_seed(db, manifest, unfinished_ips)

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
        return templates.TemplateResponse(request, "seed.html", {"page": "seed", "seed": view})

    @app.get("/healthz")
    def healthz(request: Request) -> dict[str, str]:
        with request.app.state.db.transaction() as conn:
            conn.execute("SELECT 1").fetchone()
        return {"status": "ok"}

    return app
