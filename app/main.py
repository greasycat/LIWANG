from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from alembic import command
from alembic.config import Config as AlembicConfig
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from sqlalchemy import text
from starlette.middleware.sessions import SessionMiddleware

from .config import settings
from .db import SessionLocal, engine
from .deps import template_globals
from .routes import admin, admin_files, auth, chat, docs, files, ocr_jobs, sessions, uploads
from .seed import seed_if_empty

log = logging.getLogger("liwang.main")

BASE_DIR = Path(__file__).parent
ROOT_DIR = BASE_DIR.parent
TEMPLATES = Jinja2Templates(directory=str(BASE_DIR / "templates"))


def _date_bucket(dt: datetime) -> str:
    today = datetime.now(timezone.utc)
    delta = (today.date() - dt.date()).days
    if delta == 0:
        return "今天"
    if delta == 1:
        return "昨天"
    if delta < 7:
        return "本周"
    if delta < 30:
        return "本月"
    return "更早"


def _format_money(v: float) -> str:
    return f"¥{v:,.2f}"


def _format_int(v: int) -> str:
    return f"{v:,}"


def _filesize(v: int | None) -> str:
    if v is None or v <= 0:
        return "—"
    units = ["B", "KB", "MB", "GB", "TB"]
    i, f = 0, float(v)
    while f >= 1024 and i < len(units) - 1:
        f /= 1024
        i += 1
    return f"{f:.0f} {units[i]}" if f >= 10 or i == 0 else f"{f:.1f} {units[i]}"


TEMPLATES.env.filters["bucket"] = _date_bucket
TEMPLATES.env.filters["money"] = _format_money
TEMPLATES.env.filters["intcomma"] = _format_int
TEMPLATES.env.filters["filesize"] = _filesize


def _run_migrations() -> None:
    cfg = AlembicConfig(str(ROOT_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(ROOT_DIR / "alembic"))
    cfg.set_main_option("sqlalchemy.url", settings.database_url)
    command.upgrade(cfg, "head")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.run_migrations_on_startup:
        try:
            _run_migrations()
        except Exception:
            log.exception("alembic upgrade failed")
            raise
    with SessionLocal() as db:
        if seed_if_empty(db):
            log.info("seeded demo data")
    yield


def create_app() -> FastAPI:
    app = FastAPI(title="LIWANG 知识助手", lifespan=lifespan)
    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret,
        max_age=86400 * 7,
    )

    @app.middleware("http")
    async def db_session_middleware(request: Request, call_next):
        request.state.db = SessionLocal()
        try:
            response = await call_next(request)
        finally:
            request.state.db.close()
        return response

    static_dir = BASE_DIR / "static"
    static_dir.mkdir(exist_ok=True)
    app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    app.state.templates = TEMPLATES
    app.state.template_globals = template_globals

    app.include_router(auth.router)
    app.include_router(sessions.router)
    app.include_router(chat.router)
    app.include_router(docs.router)
    app.include_router(files.router, prefix="/files")
    app.include_router(admin.router, prefix="/admin")
    app.include_router(uploads.router, prefix="/admin/upload")
    app.include_router(admin_files.router, prefix="/admin/files")
    app.include_router(ocr_jobs.router, prefix="/ocr-jobs")

    @app.get("/healthz")
    def healthz():
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return {"ok": True}
        except Exception as ex:
            return JSONResponse(
                status_code=503, content={"ok": False, "error": str(ex)}
            )

    return app


app = create_app()
