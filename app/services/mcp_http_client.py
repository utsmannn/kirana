"""MCP HTTP/SSE client wrapper for per-channel MCP servers."""

import logging
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

import httpx
from anyio import EndOfStream
from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamable_http_client

logger = logging.getLogger(__name__)


def _format_mcp_error(error: BaseException) -> str:
    """Flatten nested MCP/anyio errors into a useful message for API responses."""
    if isinstance(error, ExceptionGroup):
        messages = [_format_mcp_error(e) for e in error.exceptions]
        messages = [m for m in messages if m]
        return "; ".join(messages) or str(error)

    if isinstance(error, httpx.HTTPStatusError):
        response = error.response
        detail = f"HTTP {response.status_code} from MCP server"
        try:
            body = response.text[:500] if response.is_closed and response.text else ""
        except httpx.ResponseNotRead:
            body = ""
        if body:
            detail += f": {body}"
        return detail

    if isinstance(error, httpx.HTTPError):
        return f"HTTP error connecting to MCP server: {error}"

    if isinstance(error, EndOfStream):
        return "MCP server closed the stream before completing initialization"

    return str(error)


class McpHttpConnection:
    """Connection to a single HTTP/SSE MCP server."""

    def __init__(
        self,
        server_url: str,
        transport: str = "sse",
        auth_type: str = "none",
        auth_config: Optional[Dict[str, Any]] = None,
    ):
        self.server_url = server_url
        self.transport = transport.lower()
        self.auth_type = auth_type.lower()
        self.auth_config = auth_config or {}
        self._headers = self._build_headers()

    def _build_headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {}
        if self.auth_type == "bearer":
            token = self.auth_config.get("token", "")
            if token:
                headers["Authorization"] = f"Bearer {token}"
        elif self.auth_type == "custom_header":
            for key, value in self.auth_config.get("headers", {}).items():
                if isinstance(value, str) and value:
                    headers[key] = value
        return headers

    def _httpx_client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            headers=self._headers,
            timeout=httpx.Timeout(30, read=300),
            follow_redirects=True,
        )

    @asynccontextmanager
    async def connect(self):
        """Yield an initialized ClientSession over HTTP/SSE."""
        parsed = urlparse(self.server_url)
        if parsed.scheme not in ("http", "https"):
            raise ValueError(f"Unsupported server URL scheme: {parsed.scheme}")

        if self.transport == "sse":
            async with sse_client(self.server_url, headers=self._headers) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    logger.info("[MCP HTTP] Connected to %s via SSE", self.server_url)
                    yield session
        elif self.transport == "http":
            client = self._httpx_client()
            async with client:
                async with streamable_http_client(self.server_url, http_client=client) as (
                    read,
                    write,
                    _,
                ):
                    async with ClientSession(read, write) as session:
                        await session.initialize()
                        logger.info("[MCP HTTP] Connected to %s via HTTP", self.server_url)
                        yield session
        else:
            raise ValueError(f"Unsupported MCP transport: {self.transport}")

    async def list_tools(self) -> List[Dict[str, Any]]:
        """List tools exposed by the MCP server."""
        async with self.connect() as session:
            result = await session.list_tools()
            return [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.inputSchema,
                }
                for tool in result.tools
            ]

    async def call_tool(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Call a tool on the MCP server and normalize the result."""
        async with self.connect() as session:
            logger.info("[MCP HTTP] Calling tool '%s' on %s", tool_name, self.server_url)
            result = await session.call_tool(tool_name, arguments=arguments)

            content_text = ""
            for content in result.content:
                if hasattr(content, "text"):
                    content_text += content.text
                elif hasattr(content, "data"):
                    content_text += f"[Binary content: {len(content.data)} bytes]"

            logger.info(
                "[MCP HTTP] Tool '%s' success=%s content_length=%d",
                tool_name,
                not result.isError,
                len(content_text),
            )

            return {
                "success": not result.isError,
                "content": content_text,
                "is_error": result.isError,
            }


async def test_mcp_connection(
    server_url: str,
    transport: str = "sse",
    auth_type: str = "none",
    auth_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Dry-run helper: connect, list tools, and return tool list without side effects."""
    conn = McpHttpConnection(server_url, transport, auth_type, auth_config)
    try:
        tools = await conn.list_tools()
        return {
            "success": True,
            "message": f"Connected and discovered {len(tools)} tool(s)",
            "tools": tools,
        }
    except Exception as e:
        message = _format_mcp_error(e)
        logger.warning("[MCP HTTP] Test connection failed: %s", message)
        return {
            "success": False,
            "message": message,
            "tools": [],
        }
