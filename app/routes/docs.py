from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse, Response
from fastapi.templating import Jinja2Templates

from .. import store
from ..config import settings
from ..deps import db, require_user
from ..models import Doc, User

router = APIRouter()


_ACL_VISIBLE: dict[str, set[str]] = {
    "public": {"public"},
    "internal": {"public", "internal"},
    "restricted": {"public", "internal", "restricted"},
}


def _tpl(request: Request) -> Jinja2Templates:
    return request.app.state.templates


def _can_see(user: User, doc: Doc) -> bool:
    return doc.acl in _ACL_VISIBLE.get(user.acl_max, {"public"})


def _preview_kind(doc: Doc) -> str:
    name = (doc.source or "").lower()
    mime = (doc.mime or "").lower()
    if "pdf" in mime or name.endswith(".pdf"):
        return "pdf"
    if "wordprocessingml" in mime or name.endswith(".docx"):
        return "docx"
    if mime.startswith("text/") or name.endswith((".txt", ".md", ".markdown")):
        return "text"
    return "unsupported"


def _abs(rel: str | None) -> Path | None:
    if not rel:
        return None
    return (settings.files_root / rel).resolve()


@router.get("/docs/{doc_id}/view", response_class=HTMLResponse)
def view_doc(request: Request, doc_id: str):
    user = require_user(request)
    d = store.get_doc(db(request), doc_id)
    if not d:
        return HTMLResponse("<div class='p-4 text-sm opacity-60'>文档不存在</div>", status_code=404)
    if not _can_see(user, d):
        return HTMLResponse("<div class='p-4 text-sm opacity-60'>无权访问</div>", status_code=403)

    abs_path = _abs(d.file_path)
    has_file = bool(d.file_path) and abs_path is not None and abs_path.exists()
    kind = _preview_kind(d)

    body: str | None = None
    error: str | None = None
    if not has_file:
        error = "文档没有存档原文件 (legacy/seed entry)"
    elif kind in ("docx", "text"):
        try:
            if abs_path.stat().st_size > 5 * 1024 * 1024:
                error = "文件超过 5 MB 预览上限，请下载查看"
            else:
                from ..services.extraction import extract_text

                body, _ = extract_text(abs_path, d.mime, original_name=d.source)
                if not body.strip():
                    body = "(文件内容为空)"
        except Exception as ex:  # noqa: BLE001
            error = f"读取失败: {ex}"

    return _tpl(request).TemplateResponse(
        request,
        "_citations.html",
        {
            "doc": d,
            "kind": kind,
            "body": body,
            "error": error,
            "has_file": has_file,
            "raw_url": f"/docs/{d.id}/raw",
            "download_url": f"/docs/{d.id}/download",
        },
    )


@router.get("/docs/{doc_id}/raw")
def doc_raw(request: Request, doc_id: str):
    user = require_user(request)
    d = store.get_doc(db(request), doc_id)
    if not d or not _can_see(user, d):
        return Response(status_code=404)
    abs_path = _abs(d.file_path)
    if not abs_path or not abs_path.exists():
        return Response(status_code=404)
    return FileResponse(
        path=str(abs_path),
        media_type=d.mime or "application/octet-stream",
    )


@router.get("/docs/{doc_id}/download")
def doc_download(request: Request, doc_id: str):
    user = require_user(request)
    d = store.get_doc(db(request), doc_id)
    if not d or not _can_see(user, d):
        return Response(status_code=404)
    abs_path = _abs(d.file_path)
    if not abs_path or not abs_path.exists():
        return Response(status_code=404)
    return FileResponse(
        path=str(abs_path),
        media_type=d.mime or "application/octet-stream",
        filename=d.source,
        headers={"Content-Disposition": f'attachment; filename="{d.source}"'},
    )
