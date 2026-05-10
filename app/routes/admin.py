from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, Response

from .. import store
from ..deps import db, require_admin, template_globals

router = APIRouter()


def _render(request: Request, template: str, **extra) -> HTMLResponse:
    base = template_globals(request)
    base.update(extra)
    base.setdefault("sessions", [])
    base.setdefault("active_session_id", None)
    return request.app.state.templates.TemplateResponse(request, template, base)


@router.get("", response_class=HTMLResponse)
def overview(request: Request):
    require_admin(request)
    d = db(request)
    ym = datetime.now(timezone.utc).strftime("%Y-%m")
    rows = [r for r in store.all_usage(d) if r.month == ym]
    return _render(
        request,
        "admin/overview.html",
        page="overview",
        month=ym,
        total_queries=sum(r.queries for r in rows),
        total_tokens=sum(r.prompt_tokens + r.completion_tokens for r in rows),
        total_cost=sum(r.cost_cny for r in rows),
        active_users=len(rows),
        failed_jobs=sum(1 for j in store.all_ocr_jobs(d) if j.status == "failed"),
        doc_count=len(store.all_docs(d)),
    )


@router.get("/users", response_class=HTMLResponse)
def users_page(request: Request):
    require_admin(request)
    d = db(request)
    ym = datetime.now(timezone.utc).strftime("%Y-%m")
    rows = [
        (u, store.month_tokens(d, u.id, ym), store.storage_used(d, u.id))
        for u in store.all_users(d)
    ]
    return _render(request, "admin/users.html", page="users", rows=rows, month=ym)


@router.get("/users/{user_id}/edit-form", response_class=HTMLResponse)
def user_edit_form(request: Request, user_id: int):
    require_admin(request)
    user = store.get_user(db(request), user_id)
    if not user:
        return Response(status_code=404)
    base = template_globals(request)
    base["user_row"] = user
    base["used_bytes"] = store.storage_used(db(request), user.id)
    return request.app.state.templates.TemplateResponse(
        request, "admin/_user_edit_modal.html", base
    )


@router.post("/users/{user_id}/quota", response_class=HTMLResponse)
async def update_user_quota(request: Request, user_id: int):
    require_admin(request)
    d = db(request)
    form = await request.form()
    user = store.get_user(d, user_id)
    if not user:
        return Response(status_code=404)

    if "monthly_token_cap" in form:
        raw = form.get("monthly_token_cap", "").strip()
        user.monthly_token_cap = int(raw) if raw else None

    if "storage_quota_mb" in form:
        raw = form.get("storage_quota_mb", "").strip()
        if raw:
            user.storage_quota_bytes = max(1, int(float(raw))) * 1024 * 1024

    if "acl_max" in form:
        acl = form.get("acl_max", "")
        if acl in ("public", "internal", "restricted"):
            user.acl_max = acl

    d.commit()
    return await users_page_partial(request)


@router.get("/docs/{doc_id}/acl-form", response_class=HTMLResponse)
def doc_acl_form(request: Request, doc_id: str):
    require_admin(request)
    d_obj = store.get_doc(db(request), doc_id)
    if not d_obj:
        return Response(status_code=404)
    base = template_globals(request)
    base["doc"] = d_obj
    return request.app.state.templates.TemplateResponse(
        request, "admin/_doc_acl_modal.html", base
    )


@router.post("/docs/{doc_id}/acl", response_class=HTMLResponse)
async def update_doc_acl(request: Request, doc_id: str):
    require_admin(request)
    form = await request.form()
    d = store.set_doc_acl(db(request), doc_id, form.get("acl", ""))
    if not d:
        return Response(status_code=404)
    base = template_globals(request)
    base["d"] = d
    return request.app.state.templates.TemplateResponse(
        request, "admin/_doc_row.html", base
    )


def _docs_table_response(request) -> HTMLResponse:
    return _render(
        request,
        "admin/_docs_table.html",
        page="docs",
        docs=store.all_docs(db(request)),
    )


@router.post("/docs/bulk", response_class=HTMLResponse)
async def docs_bulk(request: Request):
    require_admin(request)
    d = db(request)
    form = await request.form()
    action = form.get("action", "")
    ids = form.getlist("ids")
    if not action or not ids:
        return _docs_table_response(request)

    if action == "delete":
        for did in ids:
            store.delete_doc(d, did)
    elif action == "set_acl":
        v = form.get("value", "")
        for did in ids:
            store.set_doc_acl(d, did, v)
    elif action == "set_no_llm":
        v = form.get("value", "false") in ("true", "1", "on")
        for did in ids:
            store.update_doc(d, did, no_llm=v)
    elif action == "reembed":
        for did in ids:
            store.update_doc(d, did, embed_status="embedding")

    return _docs_table_response(request)


async def users_page_partial(request: Request) -> HTMLResponse:
    d = db(request)
    ym = datetime.now(timezone.utc).strftime("%Y-%m")
    rows = [
        (u, store.month_tokens(d, u.id, ym), store.storage_used(d, u.id))
        for u in store.all_users(d)
    ]
    return _render(request, "admin/_users_table.html", page="users", rows=rows, month=ym)


@router.get("/usage", response_class=HTMLResponse)
def usage_page(request: Request):
    require_admin(request)
    d = db(request)
    rows = store.all_usage(d)
    months = sorted({r.month for r in rows}, reverse=True)
    user_map = {u.id: u for u in store.all_users(d)}
    pivot: dict = {}
    for r in rows:
        pivot.setdefault(r.user_id, {})[r.month] = r
    return _render(
        request,
        "admin/usage.html",
        page="usage",
        months=months,
        user_map=user_map,
        pivot=pivot,
    )


@router.get("/docs", response_class=HTMLResponse)
def docs_page(request: Request):
    require_admin(request)
    return _render(request, "admin/docs.html", page="docs", docs=store.all_docs(db(request)))


@router.get("/ocr", response_class=HTMLResponse)
def ocr_page(request: Request):
    require_admin(request)
    return _render(request, "admin/ocr.html", page="ocr", jobs=store.all_ocr_jobs(db(request)))


@router.get("/eval", response_class=HTMLResponse)
def eval_page(request: Request):
    require_admin(request)
    return _render(request, "admin/eval.html", page="eval")


@router.get("/settings", response_class=HTMLResponse)
def settings_page(request: Request):
    require_admin(request)
    return _render(request, "admin/settings.html", page="settings")
