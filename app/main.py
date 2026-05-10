from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from alembic import command
from alembic.config import Config as AlembicConfig
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.middleware.sessions import SessionMiddleware

from .config import settings
from .db import SessionLocal, engine
from .routes import (
    admin,
    admin_files,
    auth,
    chat,
    docs,
    files,
    ocr_jobs,
    sessions,
    uploads,
)
from .seed import seed_if_empty

log = logging.getLogger("liwang.main")

BASE_DIR = Path(__file__).parent
ROOT_DIR = BASE_DIR.parent


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
    app = FastAPI(title="LIWANG 知识助手 API", lifespan=lifespan)

    app.add_middleware(
        SessionMiddleware,
        secret_key=settings.session_secret,
        max_age=86400 * 7,
        same_site="lax",
        https_only=False,
    )

    @app.middleware("http")
    async def db_session_middleware(request: Request, call_next):
        request.state.db = SessionLocal()
        try:
            response = await call_next(request)
        finally:
            request.state.db.close()
        return response

    api = "/api"
    app.include_router(auth.router, prefix=api)
    app.include_router(sessions.router, prefix=api)
    app.include_router(chat.router, prefix=api)
    app.include_router(docs.router, prefix=api)
    app.include_router(files.router, prefix=api)
    app.include_router(admin.router, prefix=f"{api}/admin")
    app.include_router(uploads.router, prefix=f"{api}/admin/upload")
    app.include_router(admin_files.router, prefix=f"{api}/admin/files")
    app.include_router(ocr_jobs.router, prefix=f"{api}/ocr-jobs")

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
