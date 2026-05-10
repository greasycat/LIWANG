from __future__ import annotations

from fastapi import APIRouter, Form, Request, Response
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from .. import store
from ..deps import db, require_user

router = APIRouter()


def _tpl(request: Request) -> Jinja2Templates:
    return request.app.state.templates


def _render_list(request: Request, active_session_id: str | None = None) -> HTMLResponse:
    user = require_user(request)
    return _tpl(request).TemplateResponse(
        request,
        "_session_list.html",
        {
            "sessions": store.user_sessions(db(request), user.id),
            "active_session_id": active_session_id,
        },
    )


@router.get("/sessions/search")
def search_sessions(request: Request, q: str = ""):
    user = require_user(request)
    items = store.user_sessions(db(request), user.id)
    if q:
        ql = q.lower()
        items = [s for s in items if ql in s.title.lower()]
    return _tpl(request).TemplateResponse(
        request,
        "_session_list.html",
        {"sessions": items, "active_session_id": None},
    )


@router.post("/sessions")
def create_session(request: Request):
    user = require_user(request)
    s = store.create_session(db(request), user.id)
    resp = Response(status_code=204)
    resp.headers["HX-Redirect"] = f"/c/{s.id}"
    return resp


@router.get("/sessions/{sid}/rename-form", response_class=HTMLResponse)
def rename_form(request: Request, sid: str):
    user = require_user(request)
    s = store.get_session(db(request), sid)
    if not s or s.user_id != user.id:
        return HTMLResponse("", status_code=404)
    return _tpl(request).TemplateResponse(
        request,
        "_rename_modal.html",
        {"session": s},
    )


@router.patch("/sessions/{sid}")
def rename(request: Request, sid: str, title: str = Form(...)):
    user = require_user(request)
    s = store.get_session(db(request), sid)
    if not s or s.user_id != user.id:
        return Response(status_code=404)
    store.rename_session(db(request), sid, title)
    return _render_list(request, active_session_id=sid)


@router.delete("/sessions/{sid}")
def delete(request: Request, sid: str):
    user = require_user(request)
    s = store.get_session(db(request), sid)
    if not s or s.user_id != user.id:
        return Response(status_code=404)
    store.delete_session(db(request), sid)
    resp = _render_list(request)
    resp.headers["HX-Redirect"] = "/"
    return resp
