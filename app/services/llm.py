"""DeepSeek streaming chat via LlamaIndex.

Wraps `llama_index.llms.deepseek.DeepSeek` (OpenAI-compatible). The same
LLM instance is registered on `llama_index.core.Settings.llm` so any future
ChatEngine / agent / query engine picks it up without re-config.
"""
from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from ..config import settings

log = logging.getLogger("liwang.llm")


@dataclass
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_tokens: int = 0


@dataclass
class StreamChunk:
    delta: str | None = None
    usage: TokenUsage | None = None
    error: str | None = None


def is_configured() -> bool:
    key = settings.deepseek_api_key
    return bool(key) and not key.startswith(("sk-replace", "sk-xxx"))


def estimate_cost_cny(usage: TokenUsage) -> float:
    return (
        usage.prompt_tokens * settings.deepseek_input_cny_per_1k / 1000
        + usage.completion_tokens * settings.deepseek_output_cny_per_1k / 1000
    )


@lru_cache(maxsize=1)
def get_llm():
    if not is_configured():
        raise RuntimeError("DEEPSEEK_API_KEY not configured")
    from llama_index.core import Settings as LISettings
    from llama_index.llms.deepseek import DeepSeek

    llm = DeepSeek(
        model=settings.deepseek_model,
        api_key=settings.deepseek_api_key,
        api_base=settings.deepseek_base_url.rstrip("/v1").rstrip("/"),
        temperature=0.3,
        # Ask the OpenAI-compatible client to include usage in the final stream chunk
        additional_kwargs={"stream_options": {"include_usage": True}},
    )
    LISettings.llm = llm
    return llm


SYSTEM_PROMPT = (
    "你是LIWANG公司内部知识助手。基于下面提供的「检索片段」回答员工问题。\n"
    "硬性要求：\n"
    "1. 只用中文回答，语气专业、准确。\n"
    "2. 答案必须来源于检索片段；如片段不足以回答，明确说明「检索资料不足」并建议补充上传文档。\n"
    "3. 在引用具体事实时，用方括号编号 [1] [2] 标注片段来源；编号必须与片段标题一致。\n"
    "4. 不要编造事实、版本号、日期或人员姓名。\n"
)


def build_context_block(chunks: list[dict[str, Any]]) -> str:
    if not chunks:
        return "(本次未检索到相关资料)"
    lines: list[str] = []
    for c in chunks:
        page_part = f" 第 {c['page']} 页" if c.get("page") else ""
        lines.append(f"{c['label']} 来源: {c['source']}{page_part}")
        lines.append(c["content"].strip())
        lines.append("")
    return "\n".join(lines).rstrip()


def _chat_messages(history, user_q, chunks):
    """Build a list[ChatMessage] for LlamaIndex."""
    from llama_index.core.llms import ChatMessage, MessageRole

    msgs = [ChatMessage(role=MessageRole.SYSTEM, content=SYSTEM_PROMPT)]
    for role, content in history:
        if not content.strip():
            continue
        mr = MessageRole.ASSISTANT if role == "assistant" else MessageRole.USER
        msgs.append(ChatMessage(role=mr, content=content))
    context = build_context_block(chunks)
    msgs.append(
        ChatMessage(
            role=MessageRole.USER,
            content=f"# 检索片段\n{context}\n\n# 用户问题\n{user_q}",
        )
    )
    return msgs


def _extract_usage(raw: Any) -> TokenUsage | None:
    """Pull token counts from the underlying OpenAI stream chunk if present."""
    if not raw:
        return None
    # raw is an openai ChatCompletionChunk-like object or dict
    usage = None
    if hasattr(raw, "usage"):
        usage = getattr(raw, "usage", None)
    elif isinstance(raw, dict):
        usage = raw.get("usage")
    if not usage:
        return None
    if hasattr(usage, "model_dump"):
        u = usage.model_dump()
    elif hasattr(usage, "__dict__"):
        u = {k: getattr(usage, k) for k in ("prompt_tokens", "completion_tokens")}
        cd = getattr(usage, "prompt_tokens_details", None) or getattr(
            usage, "prompt_cache_hit_tokens", None
        )
        if cd:
            u["prompt_tokens_details"] = (
                cd if isinstance(cd, dict) else getattr(cd, "__dict__", {})
            )
    else:
        u = dict(usage)

    cached = 0
    details = u.get("prompt_tokens_details") or {}
    if isinstance(details, dict):
        cached = int(details.get("cached_tokens", 0) or 0)
    cached = cached or int(u.get("prompt_cache_hit_tokens", 0) or 0)

    return TokenUsage(
        prompt_tokens=int(u.get("prompt_tokens", 0) or 0),
        completion_tokens=int(u.get("completion_tokens", 0) or 0),
        cached_tokens=cached,
    )


async def stream_chat(
    history: list[tuple[str, str]],
    user_q: str,
    chunks: list[dict[str, Any]],
) -> AsyncIterator[StreamChunk]:
    try:
        llm = get_llm()
    except Exception as ex:  # noqa: BLE001
        yield StreamChunk(error=f"LLM 未配置: {ex}")
        return

    messages = _chat_messages(history, user_q, chunks)
    last_raw: Any = None
    last_text = ""
    try:
        gen = await llm.astream_chat(messages)
        async for resp in gen:
            # ChatResponse: .delta (new piece) + .message.content (cumulative)
            delta = getattr(resp, "delta", None)
            if delta is None:
                cur = resp.message.content or ""
                delta = cur[len(last_text) :]
                last_text = cur
            else:
                last_text += delta
            if delta:
                yield StreamChunk(delta=delta)
            last_raw = getattr(resp, "raw", None) or last_raw
        usage = _extract_usage(last_raw)
        if usage:
            yield StreamChunk(usage=usage)
    except Exception as ex:  # noqa: BLE001
        log.exception("DeepSeek stream failed")
        yield StreamChunk(error=f"DeepSeek 调用失败: {ex}")
