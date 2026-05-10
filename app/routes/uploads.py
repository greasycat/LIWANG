from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, HTTPException, Request, UploadFile

from .. import store
from ..config import settings
from ..deps import db, require_admin
from ..schemas import BulkAction, UploadOut, UploadPatch, UploadTable

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


def _table(request: Request, status: str | None) -> UploadTable:
    d = db(request)
    return UploadTable(
        items=[UploadOut.model_validate(x) for x in store.filter_uploads(d, status)],
        counts=store.upload_counts(d),
        status_labels=store.STATUS_LABELS,
        active_filter=status or "all",
    )


@router.get("")
def upload_table(request: Request, status: str | None = None) -> UploadTable:
    require_admin(request)
    flt = status if status in store.UPLOAD_STATUSES else None
    return _table(request, flt)


@router.post("/intake", status_code=201)
async def intake(
    request: Request, files: list[UploadFile] = File(...)
) -> UploadTable:
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


@router.delete("/{uid}")
def delete_one(request: Request, uid: str) -> UploadTable:
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


@router.patch("/{uid}")
def patch_one(request: Request, uid: str, body: UploadPatch) -> UploadOut:
    require_admin(request)
    fields = body.model_dump(exclude_unset=True, exclude_none=True)
    item = store.update_upload(db(request), uid, **fields)
    if not item:
        raise HTTPException(status_code=404)
    return UploadOut.model_validate(item)


@router.post("/{uid}/start")
def start_one(request: Request, uid: str) -> UploadOut:
    require_admin(request)
    d = db(request)
    item = store.get_upload(d, uid)
    if not item:
        raise HTTPException(status_code=404)
    if item.status not in ("queued", "failed"):
        return UploadOut.model_validate(item)
    _start_ingest(d, item)
    return UploadOut.model_validate(store.get_upload(d, uid))


def _start_ingest(d, item) -> None:
    from ..services.ingest import ingest_upload

    store.update_upload(
        d, item.id, status="parsing", progress=10, started_at=store.now(), error=None
    )
    asyncio.create_task(ingest_upload(item.id))


@router.post("/bulk")
def bulk_action(request: Request, body: BulkAction) -> UploadTable:
    require_admin(request)
    d = db(request)
    if not body.action or not body.ids:
        return _table(request, None)

    if body.action == "delete":
        for uid in body.ids:
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
    elif body.action == "start":
        for uid in body.ids:
            item = store.get_upload(d, uid)
            if item and item.status in ("queued", "failed"):
                _start_ingest(d, item)
    elif body.action == "set_dept" and body.value:
        for uid in body.ids:
            store.update_upload(d, uid, dept=body.value)
    elif body.action == "set_type" and body.value:
        for uid in body.ids:
            store.update_upload(d, uid, doc_type=body.value)
    elif body.action == "set_acl" and body.value in (
        "public",
        "internal",
        "restricted",
    ):
        for uid in body.ids:
            store.update_upload(d, uid, acl=body.value)
    elif body.action == "set_no_llm":
        v = (body.value or "false") in ("true", "1", "on")
        for uid in body.ids:
            store.update_upload(d, uid, no_llm=v)
    return _table(request, None)
