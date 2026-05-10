from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, Response

from .. import store
from ..config import settings
from ..deps import db, require_admin, template_globals

router = APIRouter()

log = logging.getLogger("liwang.uploads")
CHUNK_BYTES = 1024 * 1024


def _docs_dir() -> Path:
    p = settings.files_root / "docs"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _abs(rel: str | None) -> Path | None:
    if not rel:
        return None
    return (settings.files_root / rel).resolve()


def _render(request: Request, template: str, **extra) -> HTMLResponse:
    base = template_globals(request)
    base.update(extra)
    base.setdefault("sessions", [])
    base.setdefault("active_session_id", None)
    base["counts"] = store.upload_counts(db(request))
    base["status_labels"] = store.STATUS_LABELS
    return request.app.state.templates.TemplateResponse(request, template, base)


def _row(request: Request, item) -> HTMLResponse:
    base = template_globals(request)
    base["item"] = item
    base["status_labels"] = store.STATUS_LABELS
    return request.app.state.templates.TemplateResponse(
        request, "admin/_upload_row.html", base
    )


def _table(request: Request, status: str | None = None) -> HTMLResponse:
    return _render(
        request,
        "admin/_upload_table.html",
        items=store.filter_uploads(db(request), status),
        active_filter=status or "all",
    )


@router.get("", response_class=HTMLResponse)
def upload_page(request: Request, status: str | None = None):
    require_admin(request)
    flt = status if status in store.UPLOAD_STATUSES else None
    return _render(
        request,
        "admin/upload.html",
        page="upload",
        items=store.filter_uploads(db(request), flt),
        active_filter=status or "all",
    )


@router.get("/table", response_class=HTMLResponse)
def upload_table(request: Request, status: str | None = None):
    require_admin(request)
    flt = status if status in store.UPLOAD_STATUSES else None
    return _table(request, flt)


@router.post("/intake", response_class=HTMLResponse)
async def intake(
    request: Request,
    files: list[UploadFile] = File(...),
):
    user = require_admin(request)
    d = db(request)
    docs_dir = _docs_dir()

    for f in files:
        file_id = uuid4().hex
        abs_path = docs_dir / file_id
        written = 0
        with abs_path.open("wb") as out:
            while True:
                chunk = await f.read(CHUNK_BYTES)
                if not chunk:
                    break
                written += len(chunk)
                out.write(chunk)
        rel = f"docs/{file_id}"
        store.add_upload(
            d,
            filename=f.filename or "未命名",
            size=written,
            mime=f.content_type or "application/octet-stream",
            file_path=rel,
            uploaded_by=user.id,
        )
    return _table(request, None)


@router.delete("/{uid}", response_class=HTMLResponse)
def delete_one(request: Request, uid: str):
    require_admin(request)
    d = db(request)
    item = store.delete_upload(d, uid)
    if item and item.file_path:
        try:
            p = _abs(item.file_path)
            if p:
                os.unlink(p)
        except FileNotFoundError:
            pass
        except OSError:
            pass
    return _table(request, None)


@router.patch("/{uid}", response_class=HTMLResponse)
def patch_one(
    request: Request,
    uid: str,
    dept: str | None = Form(None),
    doc_type: str | None = Form(None),
    version: str | None = Form(None),
    acl: str | None = Form(None),
    no_llm: str | None = Form(None),
):
    require_admin(request)
    fields: dict = {}
    if dept is not None:
        fields["dept"] = dept
    if doc_type is not None:
        fields["doc_type"] = doc_type
    if version is not None:
        fields["version"] = version
    if acl in ("public", "internal", "restricted"):
        fields["acl"] = acl
    if no_llm is not None:
        fields["no_llm"] = no_llm in ("on", "true", "1")
    item = store.update_upload(db(request), uid, **fields)
    if not item:
        return Response(status_code=404)
    return _row(request, item)


@router.get("/{uid}/edit", response_class=HTMLResponse)
def edit_form(request: Request, uid: str):
    require_admin(request)
    item = store.get_upload(db(request), uid)
    if not item:
        return Response(status_code=404)
    base = template_globals(request)
    base["item"] = item
    return request.app.state.templates.TemplateResponse(
        request, "admin/_upload_edit_modal.html", base
    )


@router.post("/{uid}/start", response_class=HTMLResponse)
async def start_one(request: Request, uid: str):
    require_admin(request)
    d = db(request)
    item = store.get_upload(d, uid)
    if not item:
        return Response(status_code=404)
    if item.status not in ("queued", "failed"):
        return _row(request, item)
    _start_ingest(d, item)
    return _row(request, store.get_upload(d, uid))


def _start_ingest(d, item) -> None:
    """Promote a staged Upload to a Doc + schedule background ingest."""
    from ..services.ingest import ingest_upload  # local import to keep optional

    # mark as in-flight on the staging row so UI polling sees progress
    store.update_upload(
        d, item.id, status="parsing", progress=10, started_at=store.now(), error=None
    )
    asyncio.create_task(ingest_upload(item.id))


@router.post("/bulk", response_class=HTMLResponse)
async def bulk_action(request: Request):
    require_admin(request)
    d = db(request)
    form = await request.form()
    action = form.get("action")
    ids = form.getlist("ids")
    if not action or not ids:
        return _table(request, None)

    if action == "delete":
        for uid in ids:
            item = store.delete_upload(d, uid)
            if item and item.file_path:
                try:
                    p = _abs(item.file_path)
                    if p:
                        os.unlink(p)
                except FileNotFoundError:
                    pass
                except OSError:
                    pass
    elif action == "start":
        for uid in ids:
            item = store.get_upload(d, uid)
            if item and item.status in ("queued", "failed"):
                _start_ingest(d, item)
    elif action == "set_dept":
        v = form.get("value", "").strip()
        if v:
            for uid in ids:
                store.update_upload(d, uid, dept=v)
    elif action == "set_type":
        v = form.get("value", "").strip()
        if v:
            for uid in ids:
                store.update_upload(d, uid, doc_type=v)
    elif action == "set_acl":
        v = form.get("value", "")
        if v in ("public", "internal", "restricted"):
            for uid in ids:
                store.update_upload(d, uid, acl=v)
    elif action == "set_no_llm":
        v = form.get("value", "false") in ("true", "1", "on")
        for uid in ids:
            store.update_upload(d, uid, no_llm=v)
    return _table(request, None)
