"""DashScope text-embedding-v3 singleton wrapped by LlamaIndex."""
from __future__ import annotations

import logging
from functools import lru_cache

from ..config import settings

log = logging.getLogger("liwang.embedding")


@lru_cache(maxsize=1)
def get_embedder():
    if not settings.dashscope_api_key:
        raise RuntimeError("DASHSCOPE_API_KEY is not configured")
    from llama_index.embeddings.dashscope import (
        DashScopeEmbedding,
        DashScopeTextEmbeddingModels,
    )

    model_enum = {
        "text-embedding-v3": DashScopeTextEmbeddingModels.TEXT_EMBEDDING_V3,
    }.get(settings.embed_model, DashScopeTextEmbeddingModels.TEXT_EMBEDDING_V3)

    return DashScopeEmbedding(
        model_name=model_enum,
        api_key=settings.dashscope_api_key,
        embed_batch_size=settings.embed_batch_size,
    )


def embed_batch(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    return get_embedder().get_text_embedding_batch(texts, show_progress=False)


def embed_query(text: str) -> list[float]:
    return get_embedder().get_query_embedding(text)
