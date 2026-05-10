from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from .. import store
from ..deps import current_user, db
from ..schemas import LoginBody, MeOut, UserOut

router = APIRouter()


@router.post("/auth/login")
def login(request: Request, body: LoginBody) -> UserOut:
    user = store.authenticate(db(request), body.username, body.password)
    if not user:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    request.session["user_id"] = user.id
    return UserOut.model_validate(user)


@router.post("/auth/logout")
def logout(request: Request) -> dict:
    request.session.clear()
    return {"ok": True}


@router.get("/auth/me")
def me(request: Request) -> MeOut:
    user = current_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="not authenticated")
    from datetime import datetime, timezone

    ym = datetime.now(timezone.utc).strftime("%Y-%m")
    used = store.month_tokens(db(request), user.id, ym)
    cap = user.monthly_token_cap
    pct = (used / cap * 100) if cap else None
    return MeOut(
        user=UserOut.model_validate(user),
        month_tokens_used=used,
        month_tokens_cap=cap,
        month_tokens_pct=pct,
    )
