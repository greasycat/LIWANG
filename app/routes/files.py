from __future__ import annotations

import asyncio
import os
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import store
from ..config import settings
from ..deps import db, require_user
from ..models import Doc, User, UserFile
from ..schemas import (
    AclBody,
    BulkAction,
    CreateFolderBody,
    FilePreviewOut,
    FilesListing,
    FolderCrumb,
    FolderTreeNode,
    RenameBody,
    UserFileOut,
    UserOut,
)

router = APIRouter()


CHUNK_BYTES = 1024 * 1024  # 1 MB streaming write
PREVIEW_LIMIT_BYTES = 5 * 1024 * 1024


def _abs_path(rel: str | None) -> Path | None:
    if not rel:
        return None
    return (settings.files_root / rel).resolve()


def _user_dir(user_id: int) -> Path:
    p = settings.files_root / "users" / str(user_id)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _is_ingestable(mime: str, name: str) -> bool:
    m = (mime or "").lower()
    n = (name or "").lower()
    return (
        m.startswith("text/")
        or "pdf" in m
        or "wordprocessingml" in m
        or n.endswith((".pdf", ".docx", ".txt", ".md", ".markdown"))
    )


def _preview_kind(f: UserFile) -> str:
    name = (f.name or "").lower()
    mime = (f.mime or "").lower()
    if "pdf" in mime or name.endswith(".pdf"):
        return "pdf"
    if "wordprocessingml" in mime or name.endswith(".docx"):
        return "docx"
    if mime.startswith("text/") or name.endswith((".txt", ".md", ".markdown")):
        return "text"
    return "unsupported"


def _user_file_out(f: UserFile) -> UserFileOut:
    base = UserFileOut.model_validate(f)
    base.embed_status = f.doc.embed_status if f.doc_id and f.doc else None
    return base


def _file_preview_url(api_base: str, fid: str, kind: str) -> tuple[str, str]:
    return f"{api_base}/{fid}/raw", f"{api_base}/{fid}/download"


def build_listing(
    request: Request,
    target_user: User,
    parent_id: str | None,
) -> FilesListing:
    d = db(request)
    items = store.list_files(d, target_user.id, parent_id)
    crumbs = store.folder_path(d, parent_id)
    tree = store.folder_tree(d, target_user.id)
    used = store.storage_used(d, target_user.id)
    quota = target_user.storage_quota_bytes
    return FilesListing(
        items=[_user_file_out(f) for f in items],
        crumbs=[FolderCrumb(id=c.id, name=c.name) for c in crumbs],
        parent_id=parent_id,
        folder_tree=[
            FolderTreeNode(
                id=f.id, name=f.name, depth=depth, parent_id=f.parent_id
            )
            for f, depth in tree
        ],
        storage_used=used,
        storage_quota=quota,
        storage_pct=(used / quota * 100) if quota else 0.0,
        target_user=UserOut.model_validate(target_user),
    )


def validate_folder(
    d: Session, target_user: User, parent_id: str | None
) -> UserFile | None:
    if not parent_id:
        return None
    f = store.get_file(d, parent_id)
    if not f or f.user_id != target_user.id or not f.is_folder:
        return None
    return f


def _stream_file(f: UserFile, *, attachment: bool) -> Response:
    abs_path = _abs_path(f.file_path) if f.file_path else None
    if not abs_path or not abs_path.exists():
        raise HTTPException(status_code=404)
    headers = {}
    if attachment:
        headers["Content-Disposition"] = f'attachment; filename="{f.name}"'
    return FileResponse(
        path=str(abs_path),
        media_type=f.mime or "application/octet-stream",
        filename=f.name if attachment else None,
        headers=headers,
    )


def _purge_disk(rows: list[UserFile]) -> None:
    for r in rows:
        if r.file_path:
            try:
                p = _abs_path(r.file_path)
                if p:
                    os.unlink(p)
            except FileNotFoundError:
                pass
            except OSError:
                pass


def _purge_docs(d: Session, rows: list[UserFile]) -> None:
    doc_ids = [r.doc_id for r in rows if r.doc_id]
    if not doc_ids:
        return
    for did in doc_ids:
        doc = d.get(Doc, did)
        if doc:
            d.delete(doc)
    d.commit()


def _kick_embed(d: Session, target_user: User, uf: UserFile) -> str:
    if uf.is_folder:
        return "skipped:not-ingestable"
    if not uf.file_path:
        return "skipped:no-file"
    if not _is_ingestable(uf.mime or "", uf.name):
        return "skipped:not-ingestable"

    doc = d.get(Doc, uf.doc_id) if uf.doc_id else None

    if doc and doc.embed_status == "embedding":
        return "skipped:running"

    if not doc:
        doc = Doc(
            id=str(uuid4()),
            source=uf.name,
            dept="个人空间",
            doc_type="私有",
            version="v1",
            effective_date=store.now().strftime("%Y-%m-%d"),
            acl="private",
            no_llm=False,
            chunks=0,
            embed_status="pending",
            uploaded_by=target_user.username,
            uploaded_at=store.now(),
            file_path=uf.file_path,
            mime=uf.mime,
            owner_user_id=target_user.id,
        )
        d.add(doc)
        uf.doc_id = doc.id
    else:
        doc.file_path = uf.file_path
        doc.mime = uf.mime
        doc.embed_status = "pending"
    d.commit()

    from ..services.ingest import ingest_doc

    asyncio.create_task(ingest_doc(doc.id))
    return "started"


async def _do_upload(
    request: Request,
    target_user: User,
    parent_pk: str | None,
    files: list[UploadFile],
) -> FilesListing:
    d = db(request)
    user_dir = _user_dir(target_user.id)
    tmp_paths: list[tuple[Path, str, int, str]] = []
    total_new = 0
    quota = target_user.storage_quota_bytes

    try:
        for f in files:
            file_id = uuid4().hex
            abs_path = user_dir / file_id
            written = 0
            with abs_path.open("wb") as out:
                while True:
                    chunk = await f.read(CHUNK_BYTES)
                    if not chunk:
                        break
                    written += len(chunk)
                    total_new += len(chunk)
                    if not store.can_store(d, target_user.id, total_new, quota):
                        out.close()
                        abs_path.unlink(missing_ok=True)
                        for ap, _, _, _ in tmp_paths:
                            ap.unlink(missing_ok=True)
                        used = store.storage_used(d, target_user.id)
                        raise HTTPException(
                            status_code=413,
                            detail={
                                "error": "quota_exceeded",
                                "message": "存储配额不足",
                                "needed": total_new,
                                "remaining": max(0, quota - used),
                                "quota": quota,
                            },
                        )
                    out.write(chunk)
            tmp_paths.append(
                (
                    abs_path,
                    f.filename or "未命名",
                    written,
                    f.content_type or "application/octet-stream",
                )
            )
    except HTTPException:
        raise
    except Exception:
        for ap, _, _, _ in tmp_paths:
            ap.unlink(missing_ok=True)
        raise

    for abs_path, name, size, mime in tmp_paths:
        rel = f"users/{target_user.id}/{abs_path.name}"
        uf = store.add_user_file(
            d, target_user.id, name, parent_pk, size, mime, file_path=rel
        )
        if _is_ingestable(mime, name):
            doc = Doc(
                id=str(uuid4()),
                source=name,
                dept="个人空间",
                doc_type="私有",
                version="v1",
                effective_date=store.now().strftime("%Y-%m-%d"),
                acl="private",
                no_llm=False,
                chunks=0,
                embed_status="pending",
                uploaded_by=target_user.username,
                uploaded_at=store.now(),
                file_path=rel,
                mime=mime,
                owner_user_id=target_user.id,
            )
            d.add(doc)
            uf.doc_id = doc.id
            d.commit()
            from ..services.ingest import ingest_doc

            asyncio.create_task(ingest_doc(doc.id))

    return build_listing(request, target_user, parent_pk)


def _render_preview(
    f: UserFile, raw_url: str, download_url: str
) -> FilePreviewOut:
    kind = _preview_kind(f)
    body: str | None = None
    error: str | None = None
    abs_path = _abs_path(f.file_path) if f.file_path else None

    if not f.file_path or not abs_path or not abs_path.exists():
        error = "文件未持久化（演示数据，无原始内容）"
    elif kind in ("docx", "text"):
        try:
            if abs_path.stat().st_size > PREVIEW_LIMIT_BYTES:
                error = "文件超过 5 MB 预览上限，请下载查看"
            else:
                from ..services.extraction import extract_text

                body, _ = extract_text(abs_path, f.mime, original_name=f.name)
                if not body.strip():
                    body = "(文件内容为空)"
        except Exception as ex:  # noqa: BLE001
            error = f"读取失败: {ex}"

    return FilePreviewOut(
        file=_user_file_out(f),
        kind=kind,  # type: ignore[arg-type]
        body=body,
        error=error,
        raw_url=raw_url,
        download_url=download_url,
    )


# ---------- routes ----------


@router.get("/files")
def files_root(request: Request, parent_id: str | None = None) -> FilesListing:
    user = require_user(request)
    parent = validate_folder(db(request), user, parent_id) if parent_id else None
    return build_listing(request, user, parent.id if parent else None)


@router.post("/files/folder", status_code=201)
def create_folder(request: Request, body: CreateFolderBody) -> FilesListing:
    user = require_user(request)
    d = db(request)
    parent = validate_folder(d, user, body.parent_id) if body.parent_id else None
    parent_pk = parent.id if parent else None
    store.create_folder(d, user.id, body.name, parent_pk)
    return build_listing(request, user, parent_pk)


@router.post("/files/upload", status_code=201)
async def upload_files(
    request: Request,
    files: list[UploadFile] = File(...),
    parent_id: str | None = Form(None),
) -> FilesListing:
    user = require_user(request)
    parent = validate_folder(db(request), user, parent_id) if parent_id else None
    parent_pk = parent.id if parent else None
    return await _do_upload(request, user, parent_pk, files)


@router.get("/files/{file_id}")
def get_file(request: Request, file_id: str) -> UserFileOut:
    user = require_user(request)
    f = store.get_file(db(request), file_id)
    if not f or f.user_id != user.id:
        raise HTTPException(status_code=404)
    return _user_file_out(f)


@router.get("/files/{file_id}/raw")
def raw_file(request: Request, file_id: str):
    user = require_user(request)
    f = store.get_file(db(request), file_id)
    if not f or f.user_id != user.id or f.is_folder:
        raise HTTPException(status_code=404)
    return _stream_file(f, attachment=False)


@router.get("/files/{file_id}/download")
def download_file(request: Request, file_id: str):
    user = require_user(request)
    f = store.get_file(db(request), file_id)
    if not f or f.user_id != user.id or f.is_folder:
        raise HTTPException(status_code=404)
    return _stream_file(f, attachment=True)


@router.get("/files/{file_id}/preview")
def preview(request: Request, file_id: str) -> FilePreviewOut:
    user = require_user(request)
    f = store.get_file(db(request), file_id)
    if not f or f.user_id != user.id or f.is_folder:
        raise HTTPException(status_code=404)
    return _render_preview(
        f,
        raw_url=f"/api/files/{f.id}/raw",
        download_url=f"/api/files/{f.id}/download",
    )


@router.post("/files/{file_id}/embed")
def embed_one(request: Request, file_id: str) -> FilesListing:
    user = require_user(request)
    d = db(request)
    f = store.get_file(d, file_id)
    if not f or f.user_id != user.id:
        raise HTTPException(status_code=404)
    _kick_embed(d, user, f)
    return build_listing(request, user, f.parent_id)


@router.post("/files/embed-all")
def embed_all(request: Request, parent_id: str | None = None) -> FilesListing:
    user = require_user(request)
    d = db(request)
    files = d.scalars(
        select(UserFile).where(
            UserFile.user_id == user.id,
            UserFile.is_folder.is_(False),
        )
    ).all()
    for uf in files:
        if not uf.file_path or not _is_ingestable(uf.mime or "", uf.name):
            continue
        if uf.doc and uf.doc.embed_status == "done":
            continue
        _kick_embed(d, user, uf)
    return build_listing(request, user, parent_id)


@router.post("/files/{file_id}/acl")
def set_acl(request: Request, file_id: str, body: AclBody) -> FilesListing:
    user = require_user(request)
    d = db(request)
    f = store.get_file(d, file_id)
    if not f or f.user_id != user.id:
        raise HTTPException(status_code=404)
    store.set_user_file_acl(d, file_id, body.acl, recursive=body.recursive)
    return build_listing(request, user, f.parent_id)


@router.patch("/files/{file_id}")
def rename(request: Request, file_id: str, body: RenameBody) -> FilesListing:
    user = require_user(request)
    d = db(request)
    f = store.get_file(d, file_id)
    if not f or f.user_id != user.id:
        raise HTTPException(status_code=404)
    store.rename_file(d, file_id, body.name)
    return build_listing(request, user, f.parent_id)


@router.delete("/files/{file_id}")
def delete(request: Request, file_id: str) -> FilesListing:
    user = require_user(request)
    d = db(request)
    f = store.get_file(d, file_id)
    if not f or f.user_id != user.id:
        raise HTTPException(status_code=404)
    parent_id = f.parent_id
    removed = store.delete_file(d, file_id)
    _purge_disk(removed)
    _purge_docs(d, removed)
    return build_listing(request, user, parent_id)


@router.post("/files/bulk")
def bulk(request: Request, body: BulkAction) -> FilesListing:
    user = require_user(request)
    d = db(request)
    parent_pk: str | None = None
    if body.action == "delete":
        for fid in body.ids:
            f = store.get_file(d, fid)
            if f and f.user_id == user.id:
                if parent_pk is None:
                    parent_pk = f.parent_id
                removed = store.delete_file(d, fid)
                _purge_disk(removed)
                _purge_docs(d, removed)
    return build_listing(request, user, parent_pk)
