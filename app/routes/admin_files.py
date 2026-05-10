"""Admin browses + edits any user's personal file space."""
from __future__ import annotations

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from sqlalchemy import select

from .. import store
from ..deps import db, require_admin
from ..models import User, UserFile
from ..schemas import (
    AclBody,
    BulkAction,
    CreateFolderBody,
    FilePreviewOut,
    FilesListing,
    RenameBody,
)
from .files import (
    _do_upload,
    _is_ingestable,
    _kick_embed,
    _purge_disk,
    _purge_docs,
    _render_preview,
    _stream_file,
    build_listing,
    validate_folder,
)

router = APIRouter()


def _resolve(request: Request, user_id: int) -> User:
    target = store.get_user(db(request), user_id)
    if not target:
        raise HTTPException(status_code=404, detail="user not found")
    return target


@router.get("/{user_id}")
def root(
    request: Request, user_id: int, parent_id: str | None = None
) -> FilesListing:
    require_admin(request)
    target = _resolve(request, user_id)
    parent = (
        validate_folder(db(request), target, parent_id) if parent_id else None
    )
    return build_listing(request, target, parent.id if parent else None)


@router.post("/{user_id}/folder", status_code=201)
def create_folder(
    request: Request, user_id: int, body: CreateFolderBody
) -> FilesListing:
    require_admin(request)
    target = _resolve(request, user_id)
    d = db(request)
    parent = validate_folder(d, target, body.parent_id) if body.parent_id else None
    parent_pk = parent.id if parent else None
    store.create_folder(d, target.id, body.name, parent_pk)
    return build_listing(request, target, parent_pk)


@router.post("/{user_id}/upload", status_code=201)
async def upload_files(
    request: Request,
    user_id: int,
    files: list[UploadFile] = File(...),
    parent_id: str | None = Form(None),
) -> FilesListing:
    require_admin(request)
    target = _resolve(request, user_id)
    parent = validate_folder(db(request), target, parent_id) if parent_id else None
    parent_pk = parent.id if parent else None
    return await _do_upload(request, target, parent_pk, files)


@router.get("/{user_id}/{file_id}/raw")
def raw_file(request: Request, user_id: int, file_id: str):
    require_admin(request)
    target = _resolve(request, user_id)
    f = store.get_file(db(request), file_id)
    if not f or f.user_id != target.id or f.is_folder:
        raise HTTPException(status_code=404)
    return _stream_file(f, attachment=False)


@router.get("/{user_id}/{file_id}/download")
def download_file(request: Request, user_id: int, file_id: str):
    require_admin(request)
    target = _resolve(request, user_id)
    f = store.get_file(db(request), file_id)
    if not f or f.user_id != target.id or f.is_folder:
        raise HTTPException(status_code=404)
    return _stream_file(f, attachment=True)


@router.get("/{user_id}/{file_id}/preview")
def preview(
    request: Request, user_id: int, file_id: str
) -> FilePreviewOut:
    require_admin(request)
    target = _resolve(request, user_id)
    f = store.get_file(db(request), file_id)
    if not f or f.user_id != target.id or f.is_folder:
        raise HTTPException(status_code=404)
    base = f"/api/admin/files/{user_id}/{file_id}"
    return _render_preview(f, raw_url=f"{base}/raw", download_url=f"{base}/download")


@router.post("/{user_id}/{file_id}/embed")
def embed_one(request: Request, user_id: int, file_id: str) -> FilesListing:
    require_admin(request)
    target = _resolve(request, user_id)
    d = db(request)
    f = store.get_file(d, file_id)
    if not f or f.user_id != target.id:
        raise HTTPException(status_code=404)
    _kick_embed(d, target, f)
    return build_listing(request, target, f.parent_id)


@router.post("/{user_id}/embed-all")
def embed_all(
    request: Request, user_id: int, parent_id: str | None = None
) -> FilesListing:
    require_admin(request)
    target = _resolve(request, user_id)
    d = db(request)
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
    return build_listing(request, target, parent_id)


@router.post("/{user_id}/{file_id}/acl")
def set_acl(
    request: Request, user_id: int, file_id: str, body: AclBody
) -> FilesListing:
    require_admin(request)
    target = _resolve(request, user_id)
    d = db(request)
    f = store.get_file(d, file_id)
    if not f or f.user_id != target.id:
        raise HTTPException(status_code=404)
    store.set_user_file_acl(d, file_id, body.acl, recursive=body.recursive)
    return build_listing(request, target, f.parent_id)


@router.patch("/{user_id}/{file_id}")
def rename(
    request: Request, user_id: int, file_id: str, body: RenameBody
) -> FilesListing:
    require_admin(request)
    target = _resolve(request, user_id)
    d = db(request)
    f = store.get_file(d, file_id)
    if not f or f.user_id != target.id:
        raise HTTPException(status_code=404)
    store.rename_file(d, file_id, body.name)
    return build_listing(request, target, f.parent_id)


@router.delete("/{user_id}/{file_id}")
def delete(request: Request, user_id: int, file_id: str) -> FilesListing:
    require_admin(request)
    target = _resolve(request, user_id)
    d = db(request)
    f = store.get_file(d, file_id)
    if not f or f.user_id != target.id:
        raise HTTPException(status_code=404)
    parent_id = f.parent_id
    removed = store.delete_file(d, file_id)
    _purge_disk(removed)
    _purge_docs(d, removed)
    return build_listing(request, target, parent_id)


@router.post("/{user_id}/bulk")
def bulk(request: Request, user_id: int, body: BulkAction) -> FilesListing:
    require_admin(request)
    target = _resolve(request, user_id)
    d = db(request)
    parent_pk: str | None = None
    if body.action == "delete":
        for fid in body.ids:
            f = store.get_file(d, fid)
            if f and f.user_id == target.id:
                if parent_pk is None:
                    parent_pk = f.parent_id
                removed = store.delete_file(d, fid)
                _purge_disk(removed)
                _purge_docs(d, removed)
    return build_listing(request, target, parent_pk)
