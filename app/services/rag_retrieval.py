from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass, field
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.knowledge import Knowledge
from app.models.knowledge_chunk import KnowledgeChunk
from app.services.rag_embeddings import embed_text

logger = logging.getLogger(__name__)


@dataclass
class RetrievedChunk:
    source_id: str
    knowledge_id: str
    chunk_id: str
    title: str
    text: str
    score: float
    chunk_index: int
    content_type: str | None = None
    source_type: str | None = None
    source_url: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RetrievalResult:
    chunks: list[RetrievedChunk]
    context: str
    citations: list[dict[str, Any]]


async def retrieve_context(
    db: AsyncSession,
    query: str,
    *,
    channel_context: str | None = None,
    channel_description: str | None = None,
    client_id: uuid.UUID | None = None,
    top_k: int | None = None,
    max_chars: int | None = None,
) -> RetrievalResult:
    if not settings.RAG_ENABLED or not query.strip():
        return RetrievalResult(chunks=[], context="", citations=[])

    top_k = top_k or settings.RAG_TOP_K
    max_chars = max_chars or settings.RAG_MAX_CONTEXT_CHARS
    retrieval_query = _build_query(query, channel_context, channel_description)
    query_vector = await embed_text(retrieval_query)
    distance = KnowledgeChunk.embedding.cosine_distance(query_vector)

    stmt = (
        select(KnowledgeChunk, Knowledge, distance.label("distance"))
        .join(Knowledge, Knowledge.id == KnowledgeChunk.knowledge_id)
        .where(Knowledge.is_active.is_(True))
        .order_by(distance)
        .limit(max(top_k * 3, top_k))
    )
    if client_id is not None:
        stmt = stmt.where(
            (KnowledgeChunk.client_id == client_id)
            | (KnowledgeChunk.client_id.is_(None))
        )

    result = await db.execute(stmt)
    rows = result.all()

    seen: set[tuple[str, int]] = set()
    chunks: list[RetrievedChunk] = []
    total_chars = 0

    for chunk, knowledge, raw_distance in rows:
        key = (str(chunk.knowledge_id), chunk.chunk_index)
        if key in seen:
            continue
        seen.add(key)

        text = chunk.text.strip()
        if not text:
            continue
        if chunks and total_chars + len(text) > max_chars:
            break

        source_id = f"S{len(chunks) + 1}"
        score = 1.0 - float(raw_distance or 0.0)
        chunks.append(
            RetrievedChunk(
                source_id=source_id,
                knowledge_id=str(chunk.knowledge_id),
                chunk_id=str(chunk.id),
                title=chunk.title or knowledge.title,
                text=text,
                score=score,
                chunk_index=chunk.chunk_index,
                content_type=chunk.content_type,
                source_type=chunk.source_type,
                source_url=chunk.source_url,
                metadata=chunk.extra_metadata or {},
            )
        )
        total_chars += len(text)
        if len(chunks) >= top_k:
            break

    return RetrievalResult(
        chunks=chunks,
        context=format_retrieved_context(chunks),
        citations=[citation_from_chunk(chunk) for chunk in chunks],
    )


def format_retrieved_context(chunks: list[RetrievedChunk]) -> str:
    if not chunks:
        return ""

    parts = ["## Retrieved Knowledge Context"]
    for chunk in chunks:
        citation = citation_from_chunk(chunk)
        parts.append(
            f"[{chunk.source_id}] citation={json.dumps(citation, ensure_ascii=False)}\n"
            f"{chunk.text}"
        )
    return "\n\n".join(parts)


def citation_from_chunk(chunk: RetrievedChunk) -> dict[str, Any]:
    metadata = chunk.metadata or {}
    citation: dict[str, Any] = {
        "source_id": chunk.source_id,
        "knowledge_id": chunk.knowledge_id,
        "chunk_id": chunk.chunk_id,
        "title": chunk.title,
        "chunk_index": chunk.chunk_index,
        "score": round(chunk.score, 4),
        "content_type": chunk.content_type,
        "source_type": chunk.source_type,
        "source_url": chunk.source_url,
    }
    for key in (
        "file_name",
        "mime_type",
        "page",
        "page_start",
        "page_end",
        "source_spans",
        "bboxes",
        "bbox_coordinate_system",
        "extraction",
    ):
        if metadata.get(key) is not None:
            value = metadata[key]
            if key == "source_spans" and isinstance(value, list):
                value = value[:3]
            if key == "bboxes" and isinstance(value, list):
                value = value[:40]
            citation[key] = value
    return citation


def _build_query(
    user_query: str,
    channel_context: str | None,
    channel_description: str | None,
) -> str:
    parts = []
    if channel_context:
        parts.append(f"Context: {channel_context}")
    if channel_description:
        parts.append(f"Description: {channel_description}")
    parts.append(f"User question: {user_query}")
    return "\n".join(parts)
