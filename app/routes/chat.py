from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import select

from .. import store
from ..config import settings
from ..deps import db, require_user
from ..models import Chunk, Citation, Message
from ..schemas import MessageOut, PostMessageOut, RatingBody

router = APIRouter()
log = logging.getLogger("liwang.chat")


class SendMessageBody(BaseModel):
    content: str


def _owned(request: Request, sid: str):
    user = require_user(request)
    s = store.get_session(db(request), sid)
    if not s or s.user_id != user.id:
        raise HTTPException(status_code=404, detail="session not found")
    return user, s


@router.get("/sessions/{sid}/messages")
def list_messages(request: Request, sid: str) -> list[MessageOut]:
    _owned(request, sid)
    return [MessageOut.model_validate(m) for m in store.get_messages(db(request), sid)]


@router.post("/sessions/{sid}/messages")
async def post_message(
    request: Request, sid: str, body: SendMessageBody
) -> PostMessageOut:
    user, s = _owned(request, sid)
    d = db(request)

    content = body.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="empty message")

    user_msg = store.add_message(d, sid, "user", content)
    citations = _retrieve_citations(d, user, content)
    pending = store.add_message(
        d,
        sid,
        "assistant",
        "",
        citations=citations,
        prompt_tokens=0,
        completion_tokens=0,
        cost_cny=0.0,
        model=settings.deepseek_model,
    )
    return PostMessageOut(
        user_message=MessageOut.model_validate(user_msg),
        pending_message=MessageOut.model_validate(pending),
        stream_url=f"/api/messages/{pending.id}/stream",
    )


@router.get("/messages/{mid}/stream")
async def stream_message(request: Request, mid: str):
    """SSE stream that emits JSON deltas for a pending assistant message.

    Events:
      - event: delta   data: {"content": "<full accumulated text>"}
      - event: done    data: {"message": <MessageOut>}
      - event: error   data: {"error": "..."}
    """
    from ..db import SessionLocal
    from ..services import llm

    user = require_user(request)
    d = db(request)

    target = store.find_message(d, mid)
    if not target:
        raise HTTPException(status_code=404, detail="message not found")
    s = store.get_session(d, target.session_id)
    if not s or s.user_id != user.id:
        raise HTTPException(status_code=404, detail="message not found")

    sid = target.session_id
    msgs = store.get_messages(d, sid)
    user_q = ""
    for i, m in enumerate(msgs):
        if m.id == mid and i > 0:
            user_q = msgs[i - 1].content
            break

    chunk_ids = [c.chunk_id for c in (target.citations or [])]
    chunk_map: dict[str, Chunk] = {}
    if chunk_ids:
        rows = d.scalars(select(Chunk).where(Chunk.id.in_(chunk_ids))).all()
        chunk_map = {c.id: c for c in rows}
    context_chunks = []
    for cit in target.citations or []:
        ch = chunk_map.get(cit.chunk_id)
        if not ch:
            continue
        context_chunks.append(
            {
                "label": cit.label,
                "source": cit.source,
                "page": cit.page,
                "content": ch.content,
            }
        )

    history: list[tuple[str, str]] = []
    for m in msgs:
        if m.id == mid:
            break
        history.append((m.role, m.content))
    history = history[-settings.chat_max_history :]

    user_id = user.id
    model_name = settings.deepseek_model
    canned_fallback = not llm.is_configured()

    async def gen():
        accumulated = ""
        usage_obj = None
        error_note: str | None = None

        if canned_fallback:
            answer = store._canned_answer(user_q[:24] or "您的问题")
            for c in _split_for_stream(answer, n=22):
                accumulated += c
                yield _sse("delta", {"content": accumulated})
                await asyncio.sleep(0.04)
        else:
            async for evt in llm.stream_chat(history, user_q, context_chunks):
                if evt.error:
                    error_note = evt.error
                    accumulated += f"\n\n⚠ {evt.error}"
                    yield _sse("delta", {"content": accumulated})
                    break
                if evt.delta:
                    accumulated += evt.delta
                    yield _sse("delta", {"content": accumulated})
                if evt.usage:
                    usage_obj = evt.usage

        with SessionLocal() as wdb:
            saved = wdb.get(Message, mid)
            if saved:
                saved.content = accumulated
                if usage_obj is not None:
                    saved.prompt_tokens = usage_obj.prompt_tokens
                    saved.completion_tokens = usage_obj.completion_tokens
                    saved.cost_cny = llm.estimate_cost_cny(usage_obj)
                saved.model = "canned-stub" if canned_fallback else model_name
                wdb.commit()
            if usage_obj is not None and not canned_fallback:
                store.add_usage(
                    wdb,
                    user_id,
                    queries=1,
                    prompt_tokens=usage_obj.prompt_tokens,
                    completion_tokens=usage_obj.completion_tokens,
                    cached_tokens=usage_obj.cached_tokens,
                    cost_cny=llm.estimate_cost_cny(usage_obj),
                )
            elif canned_fallback:
                store.add_usage(wdb, user_id, queries=1)

            final = wdb.get(Message, mid)
            payload = MessageOut.model_validate(final).model_dump(mode="json")
        yield _sse("done", {"message": payload, "error": error_note})

    return StreamingResponse(
        gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _split_for_stream(text: str, n: int) -> list[str]:
    size = max(1, len(text) // n)
    return [text[i : i + size] for i in range(0, len(text), size)]


def _retrieve_citations(d, user, query: str) -> list[Citation]:
    try:
        from ..services.retrieval import retrieve_citations
    except Exception:
        return []
    try:
        return retrieve_citations(d, user, query, k=settings.chat_top_k)
    except Exception:
        log.exception("retrieval failed")
        return []


@router.post("/messages/{mid}/rating", status_code=204)
def rate_message(request: Request, mid: str, body: RatingBody) -> None:
    require_user(request)
    if not store.set_message_rating(db(request), mid, body.value):
        raise HTTPException(status_code=404, detail="message not found")
