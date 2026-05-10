from __future__ import annotations

import asyncio
import os
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import store
from ..config import settings
from ..deps import db, require_user, template_globals
from ..models import Doc, User, UserFile

router = APIRouter()


CHUNK_BYTES = 1024 * 1024  # 1 MB streaming write


def _abs_path(rel: str | None) -> Path | None:
    if not rel:
        return None
    return (settings.files_root / rel).resolve()


def _user_dir(user_id: int) -> Path:
    p = settings.files_root / "users" / str(user_id)
    p.mkdir(parents=True, exist_ok=True)
    return p


def _ctx(
    request: Request,
    target_user: User,
    link_base: str,
    api_base: str,
    **extra,
) -> dict:
    base = template_globals(request)
    base.setdefault("sessions", [])
    base.setdefault("active_session_id", None)
    base["target_user"] = target_user
    base["link_base"] = link_base
    base["api_base"] = api_base
    base["viewing_as_admin"] = (
        base.get("current_user") is not None
        and base["current_user"].id != target_user.id
        and base["current_user"].role == "admin"
    )
    d = db(request)
    base["storage_used"] = store.storage_used(d, target_user.id)
    base["storage_quota"] = target_user.storage_quota_bytes
    base["storage_pct"] = (
        (base["storage_used"] / base["storage_quota"] * 100)
        if base["storage_quota"]
        else 0
    )
    base["folder_tree"] = store.folder_tree(d, target_user.id)
    base.update(extra)
    return base


def render_listing(
    request: Request,
    target_user: User,
    parent_id: str | None,
    *,
    link_base: str,
    api_base: str,
) -> HTMLResponse:
    d = db(request)
    items = store.list_files(d, target_user.id, parent_id)
    crumbs = store.folder_path(d, parent_id)
    return request.app.state.templates.TemplateResponse(
        request,
        "_files_listing.html",
        _ctx(
            request, target_user, link_base, api_base,
            items=items,
            parent_id=parent_id,
            crumbs=crumbs,
            active_folder_id=parent_id,
        ),
    )


def render_page(
    request: Request,
    target_user: User,
    parent_id: str | None,
    *,
    link_base: str,
    api_base: str,
) -> HTMLResponse:
    d = db(request)
    items = store.list_files(d, target_user.id, parent_id)
    crumbs = store.folder_path(d, parent_id)
    return request.app.state.templates.TemplateResponse(
        request,
        "files.html",
        _ctx(
            request, target_user, link_base, api_base,
            items=items,
            parent_id=parent_id,
            crumbs=crumbs,
            active_folder_id=parent_id,
        ),
    )


def validate_folder(d: Session, target_user: User, parent_id: str | None) -> UserFile | None:
    if not parent_id:
        return None
    f = store.get_file(d, parent_id)
    if not f or f.user_id != target_user.id or not f.is_folder:
        return None
    return f


PREVIEW_LIMIT_BYTES = 5 * 1024 * 1024  # cap server-side text extract at 5 MB


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
    """Return one of: 'pdf', 'docx', 'text', 'unsupported'."""
    name = (f.name or "").lower()
    mime = (f.mime or "").lower()
    if "pdf" in mime or name.endswith(".pdf"):
        return "pdf"
    if "wordprocessingml" in mime or name.endswith(".docx"):
        return "docx"
    if mime.startswith("text/") or name.endswith((".txt", ".md", ".markdown")):
        return "text"
    return "unsupported"


def _render_preview(
    request: Request,
    f: UserFile,
    raw_url: str,
    download_url: str,
) -> HTMLResponse:
    """Build the preview modal payload for a file row."""
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

    base = template_globals(request)
    base.update(
        {
            "file": f,
            "kind": kind,
            "body": body,
            "error": error,
            "raw_url": raw_url,
            "download_url": download_url,
        }
    )
    return request.app.state.templates.TemplateResponse(
        request, "_files_preview_modal.html", base
    )


def _stream_file(f: UserFile, *, attachment: bool) -> Response:
    abs_path = _abs_path(f.file_path) if f.file_path else None
    if not abs_path or not abs_path.exists():
        return Response(status_code=404)
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
    """Delete Doc rows linked to deleted UserFiles. CASCADE removes chunks."""
    doc_ids = [r.doc_id for r in rows if r.doc_id]
    if not doc_ids:
        return
    for did in doc_ids:
        doc = d.get(Doc, did)
        if doc:
            d.delete(doc)
    d.commit()


def _kick_embed(d: Session, target_user: User, uf: UserFile) -> str:
    """Ensure the UserFile has a Doc + schedule (re-)ingest. Returns one of:
    'started' / 'skipped:not-ingestable' / 'skipped:no-file' / 'skipped:running'."""
    if uf.is_folder:
        return "skipped:not-ingestable"
    if not uf.file_path:
        return "skipped:no-file"
    if not _is_ingestable(uf.mime or "", uf.name):
        return "skipped:not-ingestable"

    if uf.doc_id:
        doc = d.get(Doc, uf.doc_id)
    else:
        doc = None

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
        # ensure file_path is current (in case file was renamed/moved)
        doc.file_path = uf.file_path
        doc.mime = uf.mime
        doc.embed_status = "pending"
    d.commit()

    from ..services.ingest import ingest_doc
    asyncio.create_task(ingest_doc(doc.id))
    return "started"


# ---------- user-facing routes ----------


@router.get("", response_class=HTMLResponse)
@router.get("/", response_class=HTMLResponse)
def files_root(request: Request):
    user = require_user(request)
    return render_page(request, user, None, link_base="/files", api_base="/files")


@router.get("/folder/{folder_id}", response_class=HTMLResponse)
def files_folder(request: Request, folder_id: str):
    user = require_user(request)
    folder = validate_folder(db(request), user, folder_id)
    if folder is None:
        return RedirectResponse("/files", status_code=303)
    return render_page(request, user, folder_id, link_base="/files", api_base="/files")


@router.post("/folder", response_class=HTMLResponse)
def create_folder(
    request: Request,
    name: str = Form(...),
    parent_id: str | None = Form(None),
):
    user = require_user(request)
    d = db(request)
    parent = validate_folder(d, user, parent_id) if parent_id else None
    parent_pk = parent.id if parent else None
    store.create_folder(d, user.id, name, parent_pk)
    return render_listing(request, user, parent_pk, link_base="/files", api_base="/files")


@router.post("/upload")
async def upload_files(
    request: Request,
    files: list[UploadFile] = File(...),
    parent_id: str | None = Form(None),
):
    user = require_user(request)
    d = db(request)
    parent = validate_folder(d, user, parent_id) if parent_id else None
    parent_pk = parent.id if parent else None
    return await _do_upload(request, user, parent_pk, files,
                            link_base="/files", api_base="/files")


async def _do_upload(
    request: Request,
    target_user: User,
    parent_pk: str | None,
    files: list[UploadFile],
    *,
    link_base: str,
    api_base: str,
) -> Response:
    d = db(request)

    # Stream each upload to a temp path in the user dir, tracking total bytes.
    user_dir = _user_dir(target_user.id)
    tmp_paths: list[tuple[Path, str, int, str]] = []  # (abs, name, size, mime)
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
                        # over quota — abort and clean up
                        out.close()
                        abs_path.unlink(missing_ok=True)
                        for ap, _, _, _ in tmp_paths:
                            ap.unlink(missing_ok=True)
                        used = store.storage_used(d, target_user.id)
                        return JSONResponse(
                            status_code=413,
                            content={
                                "error": "quota_exceeded",
                                "message": "存储配额不足",
                                "needed": total_new,
                                "remaining": max(0, quota - used),
                                "quota": quota,
                            },
                        )
                    out.write(chunk)
            tmp_paths.append(
                (abs_path, f.filename or "未命名", written,
                 f.content_type or "application/octet-stream")
            )
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

    return render_listing(request, target_user, parent_pk,
                          link_base=link_base, api_base=api_base)


@router.get("/{file_id}/rename-form", response_class=HTMLResponse)
def rename_form(request: Request, file_id: str):
    user = require_user(request)
    f = store.get_file(db(request), file_id)
    if not f or f.user_id != user.id:
        return Response(status_code=404)
    base = template_globals(request)
    base["file"] = f
    base["api_base"] = "/files"
    return request.app.state.templates.TemplateResponse(
        request, "_files_rename_modal.html", base
    )


@router.get("/{file_id}/raw")
def raw_file(request: Request, file_id: str):
    user = require_user(request)
    f = store.get_file(db(request), file_id)
    if not f or f.user_id != user.id or f.is_folder:
        return Response(status_code=404)
    return _stream_file(f, attachment=False)


@router.get("/{file_id}/download")
def download_file(request: Request, file_id: str):
    user = require_user(request)
    f = store.get_file(db(request), file_id)
    if not f or f.user_id != user.id or f.is_folder:
        return Response(status_code=404)
    return _stream_file(f, attachment=True)


@router.get("/{file_id}/preview", response_class=HTMLResponse)
def preview(request: Request, file_id: str):
    user = require_user(request)
    f = store.get_file(db(request), file_id)
    if not f or f.user_id != user.id or f.is_folder:
        return Response(status_code=404)
    return _render_preview(
        request,
        f,
        raw_url=f"/files/{f.id}/raw",
        download_url=f"/files/{f.id}/download",
    )


@router.post("/{file_id}/embed", response_class=HTMLResponse)
async def embed_one(request: Request, file_id: str):
    user = require_user(request)
    d = db(request)
    f = store.get_file(d, file_id)
    if not f or f.user_id != user.id:
        return Response(status_code=404)
    _kick_embed(d, user, f)
    return render_listing(request, user, f.parent_id,
                          link_base="/files", api_base="/files")


@router.post("/embed-all", response_class=HTMLResponse)
async def embed_all(request: Request):
    user = require_user(request)
    d = db(request)
    parent_id_raw = request.query_params.get("parent_id")
    parent_id = parent_id_raw if parent_id_raw else None
    # everything under this user that needs embedding (skip folders, missing
    # files, unsupported mimes, and rows already embedded)
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
    return render_listing(request, user, parent_id,
                          link_base="/files", api_base="/files")


@router.get("/{file_id}/acl-form", response_class=HTMLResponse)
def acl_form(request: Request, file_id: str):
    user = require_user(request)
    f = store.get_file(db(request), file_id)
    if not f or f.user_id != user.id:
        return Response(status_code=404)
    base = template_globals(request)
    base["file"] = f
    base["api_base"] = "/files"
    return request.app.state.templates.TemplateResponse(
        request, "_files_acl_modal.html", base
    )


@router.post("/{file_id}/acl", response_class=HTMLResponse)
def set_acl(
    request: Request,
    file_id: str,
    acl: str = Form(...),
    recursive: str | None = Form(None),
):
    user = require_user(request)
    d = db(request)
    f = store.get_file(d, file_id)
    if not f or f.user_id != user.id:
        return Response(status_code=404)
    store.set_user_file_acl(d, file_id, acl, recursive=(recursive in ("on", "1", "true")))
    return render_listing(request, user, f.parent_id, link_base="/files", api_base="/files")


@router.patch("/{file_id}", response_class=HTMLResponse)
def rename(request: Request, file_id: str, name: str = Form(...)):
    user = require_user(request)
    d = db(request)
    f = store.get_file(d, file_id)
    if not f or f.user_id != user.id:
        return Response(status_code=404)
    store.rename_file(d, file_id, name)
    return render_listing(request, user, f.parent_id,
                          link_base="/files", api_base="/files")


@router.delete("/{file_id}", response_class=HTMLResponse)
def delete(request: Request, file_id: str):
    user = require_user(request)
    d = db(request)
    f = store.get_file(d, file_id)
    if not f or f.user_id != user.id:
        return Response(status_code=404)
    parent_id = f.parent_id
    removed = store.delete_file(d, file_id)
    _purge_disk(removed)
    _purge_docs(d, removed)
    return render_listing(request, user, parent_id,
                          link_base="/files", api_base="/files")


@router.post("/bulk", response_class=HTMLResponse)
async def bulk(request: Request):
    user = require_user(request)
    d = db(request)
    form = await request.form()
    action = form.get("action")
    ids = form.getlist("ids")
    parent_id = form.get("parent_id") or None
    parent = validate_folder(d, user, parent_id) if parent_id else None
    parent_pk = parent.id if parent else None

    if action == "delete":
        for fid in ids:
            f = store.get_file(d, fid)
            if f and f.user_id == user.id:
                removed = store.delete_file(d, fid)
                _purge_disk(removed)
                _purge_docs(d, removed)

    return render_listing(request, user, parent_pk,
                          link_base="/files", api_base="/files")
