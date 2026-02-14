"""MCP Client Manager for connecting to external MCP servers."""

import asyncio
import base64
import logging
import mimetypes
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

logger = logging.getLogger(__name__)


class MCPClientManager:
    """
    Manager for connecting to MCP servers and calling their tools.

    Supports multiple MCP server configurations via environment variables.
    """

    def __init__(self):
        self._sessions: Dict[str, ClientSession] = {}
        self._server_configs: Dict[str, StdioServerParameters] = {}
        self._initialized = False

    def _load_configs(self):
        """Load MCP server configurations from environment."""
        # Z.AI MCP Server (GLM Vision)
        # Support both ZAI_API_KEY and Z_AI_API_KEY for flexibility
        zai_api_key = os.getenv("ZAI_API_KEY") or os.getenv("Z_AI_API_KEY")
        zai_mode = os.getenv("ZAI_MODE") or os.getenv("Z_AI_MODE", "ZAI")

        if zai_api_key:
            self._server_configs["zai"] = StdioServerParameters(
                command="npx",
                args=["-y", "@z_ai/mcp-server"],
                env={
                    "ZAI_API_KEY": zai_api_key,
                    "ZAI_MODE": zai_mode,
                    **os.environ,  # Pass through existing env vars
                },
            )
            logger.info("[MCP] Configured Z.AI MCP server with API key (len=%d)", len(zai_api_key))
        else:
            logger.warning("[MCP] ZAI_API_KEY not found in environment. Image analysis will not work.")

        # Add more MCP servers here as needed
        # Example:
        # if os.getenv("OTHER_MCP_API_KEY"):
        #     self._server_configs["other"] = StdioServerParameters(...)

        self._initialized = True

    def get_available_servers(self) -> List[str]:
        """Get list of configured MCP server names."""
        if not self._initialized:
            self._load_configs()
        return list(self._server_configs.keys())

    def _prepare_image_arguments(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Convert image_file path to base64 if present."""
        args = arguments.copy()

        # Handle image_file parameter - convert to base64
        if "image_file" in args and args["image_file"]:
            file_path = Path(args["image_file"])

            if not file_path.exists():
                raise FileNotFoundError(f"Image file not found: {file_path}")

            # Read and encode to base64
            with open(file_path, "rb") as f:
                image_data = f.read()

            mime_type, _ = mimetypes.guess_type(str(file_path))
            mime_type = mime_type or "image/jpeg"

            base64_data = base64.b64encode(image_data).decode("utf-8")
            data_uri = f"data:{mime_type};base64,{base64_data}"

            # Replace image_file with image (data URI)
            del args["image_file"]
            args["image"] = data_uri

            logger.info("[MCP] Converted image_file to base64 data URI (%d bytes -> %d chars)",
                       len(image_data), len(data_uri))

        return args

    @asynccontextmanager
    async def connect(self, server_name: str = "zai"):
        """
        Connect to an MCP server and yield the session.

        Usage:
            async with mcp_manager.connect("zai") as session:
                tools = await session.list_tools()
                result = await session.call_tool("analyze_image", {...})
        """
        if not self._initialized:
            self._load_configs()

        if server_name not in self._server_configs:
            raise ValueError(f"MCP server '{server_name}' not configured. Available: {self.get_available_servers()}")

        server_params = self._server_configs[server_name]

        async with stdio_client(server_params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                logger.info("[MCP] Connected to server: %s", server_name)
                yield session

    async def list_tools(self, server_name: str = "zai") -> List[Dict[str, Any]]:
        """List available tools from an MCP server."""
        async with self.connect(server_name) as session:
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
        server_name: str = "zai",
    ) -> Dict[str, Any]:
        """
        Call a tool on an MCP server.

        Returns:
            Dict with 'success', 'content', and 'structured_content' keys.
        """
        try:
            # Prepare arguments (convert image_file to base64 if present)
            prepared_args = self._prepare_image_arguments(arguments)

            async with self.connect(server_name) as session:
                logger.info("[MCP] Calling tool '%s'", tool_name)
                logger.debug("[MCP] Prepared args keys: %s", list(prepared_args.keys()))

                result = await session.call_tool(tool_name, arguments=prepared_args)

                # Extract content from result
                content_text = ""
                structured_content = None

                if result.content:
                    for content in result.content:
                        if hasattr(content, "text"):
                            content_text += content.text
                        elif hasattr(content, "data"):
                            # Binary/image content
                            content_text += f"[Binary content: {len(content.data)} bytes]"

                if hasattr(result, "structuredContent") and result.structuredContent:
                    structured_content = result.structuredContent

                logger.info("[MCP] Tool '%s' result: success=%s, content_length=%d",
                           tool_name, not result.isError, len(content_text))

                return {
                    "success": not result.isError,
                    "content": content_text,
                    "structured_content": structured_content,
                    "is_error": result.isError,
                }

        except FileNotFoundError as e:
            logger.error("[MCP] File not found: %s", e)
            return {
                "success": False,
                "content": f"File not found: {str(e)}",
                "structured_content": None,
                "is_error": True,
            }
        except Exception as e:
            logger.exception("[MCP] Error calling tool '%s': %s", tool_name, e)
            return {
                "success": False,
                "content": f"Error: {str(e)}",
                "structured_content": None,
                "is_error": True,
            }


# Global singleton
mcp_manager = MCPClientManager()
