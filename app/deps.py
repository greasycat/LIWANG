from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException, Request, status
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
        raise HTTPException(
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            headers={"Location": "/login"},
        )
    return u


def require_admin(request: Request) -> User:
    u = require_user(request)
    if u.role != "admin":
        raise HTTPException(status_code=403, detail="admin only")
    return u


def template_globals(request: Request) -> dict:
    user = current_user(request)
    if user:
        ym = datetime.now(timezone.utc).strftime("%Y-%m")
        used = store.month_tokens(db(request), user.id, ym)
        cap = user.monthly_token_cap
    else:
        used, cap = 0, None
    return {
        "current_user": user,
        "month_tokens_used": used,
        "month_tokens_cap": cap,
        "month_tokens_pct": (used / cap * 100) if cap else None,
    }
