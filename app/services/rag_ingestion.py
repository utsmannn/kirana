from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models.knowledge import Knowledge
from app.models.knowledge_chunk import KnowledgeChunk
from app.services.liteparse_parser import ParsedDocument
from app.services.rag_chunking import chunk_document, chunk_text
from app.services.rag_embeddings import embed_texts

logger = logging.getLogger(__name__)


async def index_knowledge(
    db: AsyncSession,
    knowledge: Knowledge,
    *,
    parsed_document: ParsedDocument | None = None,
) -> int:
    """Rebuild vector chunks for a knowledge row."""
    await db.execute(
        delete(KnowledgeChunk).where(KnowledgeChunk.knowledge_id == knowledge.id)
    )

    if not settings.RAG_ENABLED or not knowledge.is_active:
        logger.info("Skipping RAG indexing for knowledge %s", knowledge.id)
        return 0

    base_metadata = _base_metadata(knowledge)
    if parsed_document is not None:
        chunks = chunk_document(parsed_document, base_metadata=base_metadata)
    else:
        chunks = chunk_text(knowledge.content or "", base_metadata=base_metadata)

    if not chunks:
        logger.info("No chunks generated for knowledge %s", knowledge.id)
        return 0

    created = 0
    batch_size = settings.RAG_EMBED_BATCH_SIZE
    for start in range(0, len(chunks), batch_size):
        batch = chunks[start:start + batch_size]
        vectors = await embed_texts([chunk.text for chunk in batch])
        for chunk, vector in zip(batch, vectors):
            db.add(
                KnowledgeChunk(
                    knowledge_id=knowledge.id,
                    client_id=knowledge.client_id,
                    channel_id=knowledge.channel_id,
                    title=knowledge.title,
                    text=chunk.text,
                    content_type=knowledge.content_type,
                    source_type=knowledge.source_type,
                    source_url=knowledge.source_url,
                    chunk_index=chunk.chunk_index,
                    token_count=chunk.token_count,
                    embedding=vector,
                    extra_metadata=chunk.metadata,
                )
            )
            created += 1

    logger.info("Indexed %d chunks for knowledge %s", created, knowledge.id)
    return created


def _base_metadata(knowledge: Knowledge) -> dict[str, Any]:
    metadata = dict(knowledge.extra_metadata or {})
    metadata.update({
        "knowledge_id": str(knowledge.id),
        "channel_id": str(knowledge.channel_id) if knowledge.channel_id else None,
        "title": knowledge.title,
        "content_type": knowledge.content_type,
        "source_type": knowledge.source_type,
        "source_url": knowledge.source_url,
        "file_name": knowledge.file_name,
        "file_size": knowledge.file_size,
        "mime_type": knowledge.mime_type,
    })
    return metadata
