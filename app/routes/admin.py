from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request

from .. import store
from ..deps import db, require_admin
from ..schemas import (
    AdminOverview,
    AdminUserRow,
    BulkAction,
    DocOut,
    QuotaBody,
    UsageGrid,
    UsageRow,
    UserOut,
)

router = APIRouter()


def _ym() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m")


@router.get("/overview")
def overview(request: Request) -> AdminOverview:
    require_admin(request)
    d = db(request)
    ym = _ym()
    rows = [r for r in store.all_usage(d) if r.month == ym]
    return AdminOverview(
        month=ym,
        total_queries=sum(r.queries for r in rows),
        total_tokens=sum(r.prompt_tokens + r.completion_tokens for r in rows),
        total_cost=sum(r.cost_cny for r in rows),
        active_users=len(rows),
        failed_jobs=sum(1 for j in store.all_ocr_jobs(d) if j.status == "failed"),
        doc_count=len(store.all_docs(d)),
    )


@router.get("/users")
def users_page(request: Request) -> list[AdminUserRow]:
    require_admin(request)
    d = db(request)
    ym = _ym()
    return [
        AdminUserRow(
            user=UserOut.model_validate(u),
            month_tokens=store.month_tokens(d, u.id, ym),
            storage_used=store.storage_used(d, u.id),
        )
        for u in store.all_users(d)
    ]


@router.get("/users/{user_id}")
def user_detail(request: Request, user_id: int) -> AdminUserRow:
    require_admin(request)
    d = db(request)
    user = store.get_user(d, user_id)
    if not user:
        raise HTTPException(status_code=404)
    return AdminUserRow(
        user=UserOut.model_validate(user),
        month_tokens=store.month_tokens(d, user.id, _ym()),
        storage_used=store.storage_used(d, user.id),
    )


@router.patch("/users/{user_id}/quota")
def update_user_quota(request: Request, user_id: int, body: QuotaBody) -> UserOut:
    require_admin(request)
    d = db(request)
    user = store.get_user(d, user_id)
    if not user:
        raise HTTPException(status_code=404)

    if body.monthly_token_cap is not None:
        user.monthly_token_cap = body.monthly_token_cap or None
    if body.storage_quota_mb is not None:
        user.storage_quota_bytes = max(1, body.storage_quota_mb) * 1024 * 1024
    if body.acl_max is not None:
        user.acl_max = body.acl_max

    d.commit()
    return UserOut.model_validate(user)


@router.get("/docs")
def docs_page(request: Request) -> list[DocOut]:
    require_admin(request)
    return [DocOut.model_validate(x) for x in store.all_docs(db(request))]


@router.post("/docs/{doc_id}/acl")
def update_doc_acl(request: Request, doc_id: str, body: dict) -> DocOut:
    require_admin(request)
    acl = body.get("acl", "")
    d_obj = store.set_doc_acl(db(request), doc_id, acl)
    if not d_obj:
        raise HTTPException(status_code=404)
    return DocOut.model_validate(d_obj)


@router.post("/docs/bulk")
def docs_bulk(request: Request, body: BulkAction) -> list[DocOut]:
    require_admin(request)
    d = db(request)
    if body.action == "delete":
        for did in body.ids:
            store.delete_doc(d, did)
    elif body.action == "set_acl":
        for did in body.ids:
            store.set_doc_acl(d, did, body.value or "")
    elif body.action == "set_no_llm":
        v = (body.value or "false") in ("true", "1", "on")
        for did in body.ids:
            store.update_doc(d, did, no_llm=v)
    elif body.action == "reembed":
        for did in body.ids:
            store.update_doc(d, did, embed_status="embedding")
    return [DocOut.model_validate(x) for x in store.all_docs(d)]


@router.get("/usage")
def usage_grid(request: Request) -> UsageGrid:
    require_admin(request)
    d = db(request)
    rows = store.all_usage(d)
    months = sorted({r.month for r in rows}, reverse=True)
    user_list = store.all_users(d)
    cells: dict[int, dict[str, UsageRow]] = {}
    for r in rows:
        cells.setdefault(r.user_id, {})[r.month] = UsageRow.model_validate(r)
    return UsageGrid(
        months=months,
        users=[UserOut.model_validate(u) for u in user_list],
        cells=cells,
    )


@router.get("/ocr")
def ocr_page(request: Request):
    from ..schemas import OcrJobOut

    require_admin(request)
    return [OcrJobOut.model_validate(j) for j in store.all_ocr_jobs(db(request))]
