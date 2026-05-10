"""Admin browses + edits any user's personal file space."""
from __future__ import annotations

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response

from .. import store
from ..deps import db, require_admin, template_globals
from ..models import User
from sqlalchemy import select

from ..models import UserFile
from .files import (
    _do_upload,
    _is_ingestable,
    _kick_embed,
    _purge_disk,
    _purge_docs,
    _render_preview,
    _stream_file,
    render_listing,
    render_page,
    validate_folder,
)

router = APIRouter()


def _bases(user_id: int) -> tuple[str, str]:
    base = f"/admin/files/{user_id}"
    return base, base


def _resolve(request: Request, user_id: int) -> User | None:
    return store.get_user(db(request), user_id)


@router.get("/{user_id}", response_class=HTMLResponse)
@router.get("/{user_id}/", response_class=HTMLResponse)
def root(request: Request, user_id: int):
    require_admin(request)
    target = _resolve(request, user_id)
    if not target:
        return Response(status_code=404)
    link_base, api_base = _bases(user_id)
    return render_page(request, target, None, link_base=link_base, api_base=api_base)


@router.get("/{user_id}/folder/{folder_id}", response_class=HTMLResponse)
def folder(request: Request, user_id: int, folder_id: str):
    require_admin(request)
    target = _resolve(request, user_id)
    if not target:
        return Response(status_code=404)
    f = validate_folder(db(request), target, folder_id)
    if not f:
        return RedirectResponse(f"/admin/files/{user_id}", status_code=303)
    link_base, api_base = _bases(user_id)
    return render_page(request, target, folder_id, link_base=link_base, api_base=api_base)


@router.post("/{user_id}/folder", response_class=HTMLResponse)
def create_folder(
    request: Request,
    user_id: int,
    name: str = Form(...),
    parent_id: str | None = Form(None),
):
    require_admin(request)
    target = _resolve(request, user_id)
    if not target:
        return Response(status_code=404)
    d = db(request)
    parent = validate_folder(d, target, parent_id) if parent_id else None
    parent_pk = parent.id if parent else None
    store.create_folder(d, target.id, name, parent_pk)
    link_base, api_base = _bases(user_id)
    return render_listing(request, target, parent_pk, link_base=link_base, api_base=api_base)


@router.post("/{user_id}/upload")
async def upload_files(
    request: Request,
    user_id: int,
    files: list[UploadFile] = File(...),
    parent_id: str | None = Form(None),
):
    require_admin(request)
    target = _resolve(request, user_id)
    if not target:
        return Response(status_code=404)
    parent = validate_folder(db(request), target, parent_id) if parent_id else None
    parent_pk = parent.id if parent else None
    link_base, api_base = _bases(user_id)
    return await _do_upload(request, target, parent_pk, files,
                            link_base=link_base, api_base=api_base)


@router.get("/{user_id}/{file_id}/raw")
def raw_file(request: Request, user_id: int, file_id: str):
    require_admin(request)
    target = _resolve(request, user_id)
    if not target:
        return Response(status_code=404)
    f = store.get_file(db(request), file_id)
    if not f or f.user_id != target.id or f.is_folder:
        return Response(status_code=404)
    return _stream_file(f, attachment=False)


@router.get("/{user_id}/{file_id}/download")
def download_file(request: Request, user_id: int, file_id: str):
    require_admin(request)
    target = _resolve(request, user_id)
    if not target:
        return Response(status_code=404)
    f = store.get_file(db(request), file_id)
    if not f or f.user_id != target.id or f.is_folder:
        return Response(status_code=404)
    return _stream_file(f, attachment=True)


@router.post("/{user_id}/{file_id}/embed", response_class=HTMLResponse)
async def embed_one(request: Request, user_id: int, file_id: str):
    require_admin(request)
    target = _resolve(request, user_id)
    if not target:
        return Response(status_code=404)
    d = db(request)
    f = store.get_file(d, file_id)
    if not f or f.user_id != target.id:
        return Response(status_code=404)
    _kick_embed(d, target, f)
    link_base, api_base = _bases(user_id)
    return render_listing(request, target, f.parent_id, link_base=link_base, api_base=api_base)


@router.post("/{user_id}/embed-all", response_class=HTMLResponse)
async def embed_all(request: Request, user_id: int):
    require_admin(request)
    target = _resolve(request, user_id)
    if not target:
        return Response(status_code=404)
    d = db(request)
    parent_id_raw = request.query_params.get("parent_id")
    parent_id = parent_id_raw if parent_id_raw else None
    files = d.scalars(
        select(UserFile).where(
            UserFile.user_id == target.id,
            UserFile.is_folder.is_(False),
        )
    ).all()
    for uf in files:
        if not uf.file_path or not _is_ingestable(uf.mime or "", uf.name):
            continue
        if uf.doc and uf.doc.embed_status == "done":
            continue
        _kick_embed(d, target, uf)
    link_base, api_base = _bases(user_id)
    return render_listing(request, target, parent_id, link_base=link_base, api_base=api_base)


@router.get("/{user_id}/{file_id}/preview", response_class=HTMLResponse)
def preview(request: Request, user_id: int, file_id: str):
    require_admin(request)
    target = _resolve(request, user_id)
    if not target:
        return Response(status_code=404)
    f = store.get_file(db(request), file_id)
    if not f or f.user_id != target.id or f.is_folder:
        return Response(status_code=404)
    base_url = f"/admin/files/{user_id}/{file_id}"
    return _render_preview(
        request, f, raw_url=f"{base_url}/raw", download_url=f"{base_url}/download"
    )


@router.get("/{user_id}/{file_id}/rename-form", response_class=HTMLResponse)
def rename_form(request: Request, user_id: int, file_id: str):
    require_admin(request)
    target = _resolve(request, user_id)
    if not target:
        return Response(status_code=404)
    f = store.get_file(db(request), file_id)
    if not f or f.user_id != target.id:
        return Response(status_code=404)
    base = template_globals(request)
    base["file"] = f
    base["api_base"] = f"/admin/files/{user_id}"
    return request.app.state.templates.TemplateResponse(
        request, "_files_rename_modal.html", base
    )


@router.get("/{user_id}/{file_id}/acl-form", response_class=HTMLResponse)
def acl_form(request: Request, user_id: int, file_id: str):
    require_admin(request)
    target = _resolve(request, user_id)
    if not target:
        return Response(status_code=404)
    f = store.get_file(db(request), file_id)
    if not f or f.user_id != target.id:
        return Response(status_code=404)
    base = template_globals(request)
    base["file"] = f
    base["api_base"] = f"/admin/files/{user_id}"
    return request.app.state.templates.TemplateResponse(
        request, "_files_acl_modal.html", base
    )


@router.post("/{user_id}/{file_id}/acl", response_class=HTMLResponse)
def set_acl(
    request: Request,
    user_id: int,
    file_id: str,
    acl: str = Form(...),
    recursive: str | None = Form(None),
):
    require_admin(request)
    target = _resolve(request, user_id)
    if not target:
        return Response(status_code=404)
    d = db(request)
    f = store.get_file(d, file_id)
    if not f or f.user_id != target.id:
        return Response(status_code=404)
    store.set_user_file_acl(d, file_id, acl, recursive=(recursive in ("on", "1", "true")))
    link_base, api_base = _bases(user_id)
    return render_listing(request, target, f.parent_id, link_base=link_base, api_base=api_base)


@router.patch("/{user_id}/{file_id}", response_class=HTMLResponse)
def rename(
    request: Request,
    user_id: int,
    file_id: str,
    name: str = Form(...),
):
    require_admin(request)
    target = _resolve(request, user_id)
    if not target:
        return Response(status_code=404)
    d = db(request)
    f = store.get_file(d, file_id)
    if not f or f.user_id != target.id:
        return Response(status_code=404)
    store.rename_file(d, file_id, name)
    link_base, api_base = _bases(user_id)
    return render_listing(request, target, f.parent_id, link_base=link_base, api_base=api_base)


@router.delete("/{user_id}/{file_id}", response_class=HTMLResponse)
def delete(request: Request, user_id: int, file_id: str):
    require_admin(request)
    target = _resolve(request, user_id)
    if not target:
        return Response(status_code=404)
    d = db(request)
    f = store.get_file(d, file_id)
    if not f or f.user_id != target.id:
        return Response(status_code=404)
    parent_id = f.parent_id
    removed = store.delete_file(d, file_id)
    _purge_disk(removed)
    _purge_docs(d, removed)
    link_base, api_base = _bases(user_id)
    return render_listing(request, target, parent_id, link_base=link_base, api_base=api_base)


@router.post("/{user_id}/bulk", response_class=HTMLResponse)
async def bulk(request: Request, user_id: int):
    require_admin(request)
    target = _resolve(request, user_id)
    if not target:
        return Response(status_code=404)
    d = db(request)
    form = await request.form()
    action = form.get("action")
    ids = form.getlist("ids")
    parent_id = form.get("parent_id") or None
    parent = validate_folder(d, target, parent_id) if parent_id else None
    parent_pk = parent.id if parent else None

    if action == "delete":
        for fid in ids:
            f = store.get_file(d, fid)
            if f and f.user_id == target.id:
                removed = store.delete_file(d, fid)
                _purge_disk(removed)
                _purge_docs(d, removed)

    link_base, api_base = _bases(user_id)
    return render_listing(request, target, parent_pk, link_base=link_base, api_base=api_base)
