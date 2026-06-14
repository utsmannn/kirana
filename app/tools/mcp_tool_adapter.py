"""Adapter that exposes an MCP server tool as a BaseTool."""

from typing import Any, Dict

from app.services.mcp_http_client import McpHttpConnection
from app.tools.base import BaseTool


class McpToolAdapter(BaseTool):
    """Wraps a tool discovered from an MCP server so it can be used by ChatService."""

    def __init__(
        self,
        connection: McpHttpConnection,
        name: str,
        description: str,
        parameters: Dict[str, Any],
    ):
        self._connection = connection
        self._name = name
        self._description = description
        self._parameters = parameters

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return self._description

    @property
    def parameters(self) -> Dict[str, Any]:
        return self._parameters

    async def execute(self, **kwargs: Any) -> Any:
        result = await self._connection.call_tool(self._name, kwargs)
        return result
