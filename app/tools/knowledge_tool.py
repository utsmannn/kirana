import logging
from typing import Any, Dict

from app.db.session import get_db
from app.services.rag_retrieval import retrieve_context
from app.tools.base import BaseTool

logger = logging.getLogger(__name__)


class KnowledgeTool(BaseTool):
    """Tool for querying knowledge base to retrieve relevant information."""

    @property
    def name(self) -> str:
        return "query_knowledge"

    @property
    def description(self) -> str:
        return (
            "Search the knowledge base for relevant information. "
            "Use this when you need to answer questions about specific topics, "
            "retrieve facts, or access stored knowledge documents. "
            "Returns relevant knowledge chunks with citations."
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query to find relevant knowledge",
                },
                "top_k": {
                    "type": "integer",
                    "description": (
                        "Maximum number of knowledge chunks to return (default: 3)"
                    ),
                    "minimum": 1,
                    "maximum": 10,
                },
            },
            "required": ["query"],
        }

    async def execute(self, query: str, top_k: int = 3) -> Dict[str, Any]:
        """Execute semantic knowledge retrieval and return relevant chunks."""
        try:
            async for db in get_db():
                result = await retrieve_context(db, query, top_k=min(max(top_k, 1), 10))
                if not result.chunks:
                    return {
                        "found": False,
                        "query": query,
                        "results": [],
                        "message": "No relevant knowledge found for this query.",
                    }

                return {
                    "found": True,
                    "query": query,
                    "results": [
                        {
                            "source_id": chunk.source_id,
                            "title": chunk.title,
                            "content": chunk.text,
                            "score": chunk.score,
                            "citation": result.citations[index],
                        }
                        for index, chunk in enumerate(result.chunks)
                    ],
                    "context": result.context,
                }

        except Exception as e:
            logger.exception("[KNOWLEDGE TOOL] Error querying knowledge: %s", e)
            return {
                "found": False,
                "query": query,
                "error": "Failed to query knowledge base",
                "results": [],
            }
