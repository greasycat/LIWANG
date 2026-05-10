from __future__ import annotations

from fastapi import HTTPException, Request

from sqlalchemy.orm import Session

from . import store
from .models import User


def db(request: Request) -> Session:
    return request.state.db


def current_user(request: Request) -> User | None:
    uid = request.session.get("user_id")
    if uid is None:
        return None
    return store.get_user(db(request), int(uid))


def require_user(request: Request) -> User:
    u = current_user(request)
    if u is None:
        raise HTTPException(status_code=401, detail="not authenticated")
    return u


def require_admin(request: Request) -> User:
    u = require_user(request)
    if u.role != "admin":
        raise HTTPException(status_code=403, detail="admin only")
    return u
