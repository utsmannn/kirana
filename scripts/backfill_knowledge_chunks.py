#!/usr/bin/env python
from __future__ import annotations

import argparse
import asyncio
import logging
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402

from app.db.session import async_session  # noqa: E402
from app.models.knowledge import Knowledge  # noqa: E402
from app.services.liteparse_parser import (  # noqa: E402
    parse_document_generic,
    parse_document_smart,
)
from app.services.rag_ingestion import index_knowledge  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Backfill RAG chunks for existing knowledge"
    )
    parser.add_argument(
        "--only-active", action="store_true", help="Only index active knowledge"
    )
    parser.add_argument("--knowledge-id", help="Only index one knowledge UUID")
    parser.add_argument("--limit", type=int, help="Limit number of rows to process")
    parser.add_argument(
        "--reparse-files",
        action="store_true",
        help="Reparse file-backed knowledge with LiteParse when possible",
    )
    return parser.parse_args()


def _try_reparse(knowledge: Knowledge):
    if not knowledge.file_path:
        return None
    path = Path(knowledge.file_path)
    if not path.exists():
        return None
    try:
        return parse_document_smart(path)
    except Exception as e:
        logger.warning("LiteParse smart failed for %s: %s", knowledge.id, e)
    try:
        return parse_document_generic(path)
    except Exception as e:
        logger.warning("LiteParse generic failed for %s: %s", knowledge.id, e)
    return None


async def main() -> None:
    args = _parse_args()
    async with async_session() as db:
        stmt = select(Knowledge).order_by(Knowledge.created_at)
        if args.only_active:
            stmt = stmt.where(Knowledge.is_active.is_(True))
        if args.knowledge_id:
            stmt = stmt.where(Knowledge.id == uuid.UUID(args.knowledge_id))
        if args.limit:
            stmt = stmt.limit(args.limit)

        result = await db.execute(stmt)
        knowledge_items = result.scalars().all()
        logger.info("Backfilling %d knowledge rows", len(knowledge_items))

        total_chunks = 0
        for knowledge in knowledge_items:
            parsed_document = _try_reparse(knowledge) if args.reparse_files else None
            if parsed_document is not None:
                knowledge.content = parsed_document.text
                knowledge.extra_metadata = {
                    **(knowledge.extra_metadata or {}),
                    "parser": parsed_document.parser,
                    "parsing_status": parsed_document.parsing_status,
                    "pages": len(parsed_document.pages),
                    "raw_text_length": len(parsed_document.text),
                }
            chunks = await index_knowledge(
                db, knowledge, parsed_document=parsed_document
            )
            total_chunks += chunks
            logger.info("Indexed %s: %d chunks", knowledge.id, chunks)

        await db.commit()
        logger.info("Backfill complete: %d chunks", total_chunks)


if __name__ == "__main__":
    asyncio.run(main())
