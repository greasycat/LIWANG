from __future__ import annotations

import asyncio
import logging
from typing import Any

from fastapi import APIRouter, Form, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select

from .. import store
from ..config import settings
from ..deps import current_user, db, require_user, template_globals
from ..models import Chunk, Citation, Message

router = APIRouter()

log = logging.getLogger("liwang.chat")


def _tpl(request: Request) -> Jinja2Templates:
    return request.app.state.templates


def _ctx(request: Request, **extra) -> dict:
    base = template_globals(request)
    base.update(extra)
    return base


@router.get("/")
def home(request: Request):
    user = current_user(request)
    if not user:
        return RedirectResponse("/login", status_code=303)

    sessions = store.user_sessions(db(request), user.id)
    if sessions:
        return RedirectResponse(f"/c/{sessions[0].id}", status_code=303)

    s = store.create_session(db(request), user.id)
    return RedirectResponse(f"/c/{s.id}", status_code=303)


@router.get("/c/{sid}", response_class=HTMLResponse)
def view_session(request: Request, sid: str):
    user = require_user(request)
    d = db(request)
    s = store.get_session(d, sid)
    if not s or s.user_id != user.id:
        return HTMLResponse("not found", status_code=404)
    return _tpl(request).TemplateResponse(
        request,
        "chat.html",
        _ctx(
            request,
            session=s,
            messages=store.get_messages(d, sid),
            sessions=store.user_sessions(d, user.id),
            active_session_id=sid,
        ),
    )


@router.post("/c/{sid}/messages", response_class=HTMLResponse)
async def post_message(request: Request, sid: str, content: str = Form(...)):
    user = require_user(request)
    d = db(request)
    s = store.get_session(d, sid)
    if not s or s.user_id != user.id:
        return HTMLResponse("not found", status_code=404)

    user_msg = store.add_message(d, sid, "user", content.strip())

    citations = _retrieve_citations(d, user, content.strip())

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

    tpl = _tpl(request)
    user_html = tpl.get_template("_message.html").render(m=user_msg)
    assistant_html = (
        f'<div hx-ext="sse" sse-connect="/c/{sid}/messages/{pending.id}/stream" '
        f'sse-swap="content" sse-close="done" '
        f'hx-target="this" hx-swap="innerHTML" '
        f'class="streaming-msg">'
        f'<div class="flex gap-3">'
        f'  <div class="avatar placeholder shrink-0">'
        f'    <div class="bg-primary text-primary-content w-8 h-8 rounded-lg">'
        f'      <span class="text-[10px] font-semibold">LIWANG</span>'
        f'    </div>'
        f'  </div>'
        f'  <div class="flex-1 min-w-0">'
        f'    <div class="prose prose-sm max-w-none text-sm leading-relaxed whitespace-pre-wrap" id="stream-{pending.id}"></div>'
        f'    <div class="mt-2 flex items-center gap-2 text-xs opacity-50">'
        f'      <span class="loading loading-dots loading-xs"></span>'
        f'      <span>检索 + 生成中…</span>'
        f'    </div>'
        f'  </div>'
        f'</div>'
        f'</div>'
    )
    return HTMLResponse(user_html + assistant_html)


@router.get("/c/{sid}/messages/{mid}/stream")
async def stream_message(request: Request, sid: str, mid: str):
    from ..db import SessionLocal
    from ..services import llm

    user = require_user(request)
    d = db(request)
    s = store.get_session(d, sid)
    if not s or s.user_id != user.id:
        return Response(status_code=404)

    target = store.find_message(d, mid)
    if not target or target.session_id != sid:
        return Response(status_code=404)

    msgs = store.get_messages(d, sid)
    user_q = ""
    for i, m in enumerate(msgs):
        if m.id == mid and i > 0:
            user_q = msgs[i - 1].content
            break

    # Hydrate retrieved chunks for the LLM context block.
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

    # Trailing N turns of history (exclude the empty assistant placeholder).
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
            chunks = _split_for_stream(answer, n=22)
            for c in chunks:
                accumulated += c
                yield _wrap_sse(_render_assistant_streaming(target, accumulated, request))
                await asyncio.sleep(0.04)
        else:
            async for evt in llm.stream_chat(history, user_q, context_chunks):
                if evt.error:
                    error_note = evt.error
                    accumulated += f"\n\n⚠ {evt.error}"
                    yield _wrap_sse(
                        _render_assistant_streaming(target, accumulated, request)
                    )
                    break
                if evt.delta:
                    accumulated += evt.delta
                    yield _wrap_sse(
                        _render_assistant_streaming(target, accumulated, request)
                    )
                if evt.usage:
                    usage_obj = evt.usage

        # Persist final state in a fresh DB session (the request session
        # may be closing as we stream).
        with SessionLocal() as wdb:
            saved = wdb.get(Message, mid)
            if saved:
                saved.content = accumulated
                if usage_obj is not None:
                    saved.prompt_tokens = usage_obj.prompt_tokens
                    saved.completion_tokens = usage_obj.completion_tokens
                    saved.cost_cny = llm.estimate_cost_cny(usage_obj)
                if canned_fallback:
                    saved.model = "canned-stub"
                else:
                    saved.model = model_name
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
                # still bump query count so usage_monthly reflects activity
                store.add_usage(wdb, user_id, queries=1)

            final = wdb.get(Message, mid)
            final_html = _tpl(request).get_template("_message.html").render(m=final)
        yield _wrap_sse(final_html)
        yield "event: done\ndata: end\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


def _wrap_sse(html: str) -> str:
    return f"event: content\ndata: {_encode(html)}\n\n"


def _split_for_stream(text: str, n: int) -> list[str]:
    size = max(1, len(text) // n)
    return [text[i : i + size] for i in range(0, len(text), size)]


def _encode(html: str) -> str:
    return html.replace("\n", "")


def _render_assistant_streaming(msg: Message, partial: str, request: Request) -> str:
    snapshot = Message(
        id=msg.id,
        session_id=msg.session_id,
        role="assistant",
        content=partial,
        citations=[],
        prompt_tokens=0,
        completion_tokens=0,
        cost_cny=0.0,
        model=msg.model,
        created_at=msg.created_at,
    )
    return _tpl(request).get_template("_message.html").render(m=snapshot)


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


@router.post("/messages/{mid}/rating")
def rate_message(request: Request, mid: str, value: int = 0):
    require_user(request)
    if not store.set_message_rating(db(request), mid, value):
        return Response(status_code=404)
    return Response(status_code=204)
