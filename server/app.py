"""The FastAPI application factory and its routes. See docs/randomizer_devplan.md, "Routes"."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from golf.randomizer.roms import VANILLA_ROMS

from .config import Config
from .db import Database

HERE = Path(__file__).resolve().parent
STATIC_DIR = HERE / "static"
TEMPLATES_DIR = HERE / "templates"


def create_app(config: Config | None = None) -> FastAPI:
    """Build the app. With no config, reads it from the environment."""
    config = config if config is not None else Config.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        db = Database(config.database)
        try:
            db.migrate()
            app.state.db = db
            yield
        finally:
            db.close()

    app = FastAPI(title="NES Open Randomizer", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
    app.state.config = config
    templates = Jinja2Templates(directory=TEMPLATES_DIR)
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.get("/", response_class=HTMLResponse)
    def home(request: Request):
        return templates.TemplateResponse(request, "home.html", {"page": "home"})

    @app.get("/rom", response_class=HTMLResponse)
    def rom_setup(request: Request):
        return templates.TemplateResponse(request, "rom.html", {"page": "rom", "roms": VANILLA_ROMS})

    @app.get("/healthz")
    def healthz(request: Request) -> dict[str, str]:
        with request.app.state.db.transaction() as conn:
            conn.execute("SELECT 1").fetchone()
        return {"status": "ok"}

    return app
