from __future__ import annotations

import asyncio
import logging
from functools import lru_cache

from app.config import settings

logger = logging.getLogger(__name__)


@lru_cache(maxsize=1)
def _get_model():
    from fastembed import TextEmbedding

    logger.info("Loading embedding model: %s", settings.RAG_EMBED_MODEL)
    return TextEmbedding(model_name=settings.RAG_EMBED_MODEL)


def _embed_texts_sync(texts: tuple[str, ...]) -> list[list[float]]:
    model = _get_model()
    vectors = [list(vector) for vector in model.embed(list(texts))]
    for vector in vectors:
        if len(vector) != settings.RAG_EMBED_DIM:
            raise ValueError(
                f"Embedding dimension mismatch: got {len(vector)}, "
                f"expected {settings.RAG_EMBED_DIM}"
            )
    return vectors


async def embed_texts(texts: list[str]) -> list[list[float]]:
    if not texts:
        return []
    clean_texts = tuple(text or "" for text in texts)
    return await asyncio.to_thread(_embed_texts_sync, clean_texts)


async def embed_text(text: str) -> list[float]:
    vectors = await embed_texts([text])
    return vectors[0]
