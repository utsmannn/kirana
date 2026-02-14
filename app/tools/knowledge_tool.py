import logging
from typing import Any, Dict, List, Optional

from sqlalchemy import select, text

from app.db.session import get_db
from app.models.knowledge import Knowledge
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
            "Returns relevant knowledge entries with titles and content."
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search query to find relevant knowledge (e.g., 'project setup instructions', 'API authentication')"
                },
                "top_k": {
                    "type": "integer",
                    "description": "Maximum number of knowledge entries to return (default: 3)",
                    "minimum": 1,
                    "maximum": 10
                }
            },
            "required": ["query"]
        }

    async def execute(self, query: str, top_k: int = 3) -> Dict[str, Any]:
        """Execute knowledge query and return relevant results."""
        try:
            # Get async DB session
            async for db in get_db():
                try:
                    # Search for knowledge entries
                    # Use text search with ILIKE for now (can be enhanced with vector search)
                    search_terms = query.lower().split()

                    # Build query for active knowledge
                    stmt = select(Knowledge).where(
                        Knowledge.is_active.is_(True)
                    ).order_by(Knowledge.updated_at.desc())

                    result = await db.execute(stmt)
                    all_items = result.scalars().all()

                    # Simple relevance scoring based on term frequency
                    scored_items: List[tuple] = []
                    for item in all_items:
                        score = 0
                        content_lower = (item.title + " " + item.content).lower()
                        for term in search_terms:
                            score += content_lower.count(term)
                        if score > 0:
                            scored_items.append((score, item))

                    # Sort by score and take top_k
                    scored_items.sort(key=lambda x: x[0], reverse=True)
                    top_items = scored_items[:top_k]

                    if not top_items:
                        return {
                            "found": False,
                            "query": query,
                            "results": [],
                            "message": "No relevant knowledge found for this query."
                        }

                    # Format results
                    results = []
                    for score, item in top_items:
                        results.append({
                            "title": item.title,
                            "content": item.content[:2000] if len(item.content) > 2000 else item.content,
                            "content_type": item.content_type,
                            "relevance_score": score
                        })

                    return {
                        "found": True,
                        "query": query,
                        "results": results,
                        "total_available": len(scored_items)
                    }

                finally:
                    await db.close()

        except Exception as e:
            logger.exception("[KNOWLEDGE TOOL] Error querying knowledge: %s", e)
            return {
                "found": False,
                "query": query,
                "error": "Failed to query knowledge base",
                "results": []
            }
