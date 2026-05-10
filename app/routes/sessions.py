from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from .. import store
from ..deps import db, require_user
from ..schemas import ChatSessionOut, RenameSessionBody

router = APIRouter()


@router.get("/sessions")
def list_sessions(request: Request, q: str | None = None) -> list[ChatSessionOut]:
    user = require_user(request)
    items = store.user_sessions(db(request), user.id)
    if q:
        ql = q.lower()
        items = [s for s in items if ql in s.title.lower()]
    return [ChatSessionOut.model_validate(s) for s in items]


@router.post("/sessions", status_code=201)
def create_session(request: Request) -> ChatSessionOut:
    user = require_user(request)
    s = store.create_session(db(request), user.id)
    return ChatSessionOut.model_validate(s)


def _owned(request: Request, sid: str):
    user = require_user(request)
    s = store.get_session(db(request), sid)
    if not s or s.user_id != user.id:
        raise HTTPException(status_code=404, detail="session not found")
    return s


@router.get("/sessions/{sid}")
def get_session(request: Request, sid: str) -> ChatSessionOut:
    return ChatSessionOut.model_validate(_owned(request, sid))


@router.patch("/sessions/{sid}")
def rename(request: Request, sid: str, body: RenameSessionBody) -> ChatSessionOut:
    s = _owned(request, sid)
    store.rename_session(db(request), sid, body.title)
    return ChatSessionOut.model_validate(store.get_session(db(request), sid) or s)


@router.delete("/sessions/{sid}", status_code=204)
def delete(request: Request, sid: str) -> None:
    _owned(request, sid)
    store.delete_session(db(request), sid)
