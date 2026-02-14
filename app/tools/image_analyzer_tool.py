"""Image analyzer tool using MCP server (Z.AI GLM Vision)."""

import base64
import logging
import mimetypes
import os
from pathlib import Path
from typing import Any, Dict

from app.services.mcp_client import mcp_manager
from app.tools.base import BaseTool

logger = logging.getLogger(__name__)

# Upload directory for local files
UPLOAD_DIR = Path("/app/uploads/knowledge")


class ImageAnalyzerTool(BaseTool):
    """Tool for analyzing images using MCP server (Z.AI GLM Vision)."""

    @property
    def name(self) -> str:
        return "analyze_image"

    @property
    def description(self) -> str:
        return (
            "Analyze an image using AI vision capabilities. "
            "Use this when you need to understand what's in an image, "
            "extract text from images (OCR), identify objects, describe scenes, "
            "or answer questions about visual content. "
            "Provide image as base64 data or file path."
        )

    @property
    def parameters(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "image_base64": {
                    "type": "string",
                    "description": "Base64-encoded image data (without data URI prefix)"
                },
                "image_file": {
                    "type": "string",
                    "description": "Path to local image file (e.g., /uploads/knowledge/filename.jpg)"
                },
                "image_url": {
                    "type": "string",
                    "description": "Public URL of the image (must be accessible from internet)"
                },
                "prompt": {
                    "type": "string",
                    "description": "Specific question or instruction about the image (e.g., 'What objects are in this image?', 'Extract all text from this image', 'Describe the layout and colors')"
                }
            },
            "required": []  # At least one of image_base64, image_file, or image_url required
        }

    def _get_mime_type(self, file_path: str) -> str:
        """Get MIME type from file extension."""
        mime_type, _ = mimetypes.guess_type(file_path)
        return mime_type or "image/jpeg"

    def _read_file_as_base64(self, file_path: str) -> tuple[str, str]:
        """Read local file and return base64 data with MIME type."""
        # Handle relative paths
        if not file_path.startswith("/"):
            file_path = str(UPLOAD_DIR / file_path)

        # Also handle /uploads/knowledge/ prefix
        if file_path.startswith("/uploads/knowledge/"):
            file_path = str(UPLOAD_DIR / file_path.replace("/uploads/knowledge/", ""))

        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Image file not found: {file_path}")

        with open(path, "rb") as f:
            image_data = f.read()

        mime_type = self._get_mime_type(str(path))
        base64_data = base64.b64encode(image_data).decode("utf-8")

        return base64_data, mime_type

    async def execute(
        self,
        image_base64: str = None,
        image_file: str = None,
        image_url: str = None,
        prompt: str = "Describe this image in detail.",
    ) -> Dict[str, Any]:
        """Analyze image using MCP server (Z.AI GLM Vision)."""
        try:
            # Check if MCP server is configured
            available_servers = mcp_manager.get_available_servers()
            if not available_servers:
                return {
                    "success": False,
                    "error": "No MCP server configured. Set Z_AI_API_KEY environment variable to enable image analysis.",
                    "analysis": None
                }

            # Validate input - need at least one image source
            if not image_base64 and not image_file and not image_url:
                return {
                    "success": False,
                    "error": "Must provide one of: image_base64, image_file, or image_url",
                    "analysis": None
                }

            # Prepare image data
            mime_type = "image/jpeg"  # default
            source_type = None

            if image_base64:
                # Use base64 directly
                base64_data = image_base64
                source_type = "base64"
                logger.info("[IMAGE ANALYZER] Using provided base64 image data")

            elif image_file:
                # Read local file and convert to base64
                try:
                    base64_data, mime_type = self._read_file_as_base64(image_file)
                    source_type = "file"
                    logger.info("[IMAGE ANALYZER] Read local file: %s (%s)", image_file, mime_type)
                except FileNotFoundError as e:
                    return {
                        "success": False,
                        "error": str(e),
                        "analysis": None
                    }

            elif image_url:
                # For public URLs, we still might need to fetch and convert to base64
                # since Z.AI MCP server likely expects base64
                try:
                    import httpx
                    async with httpx.AsyncClient() as client:
                        response = await client.get(image_url, follow_redirects=True, timeout=30)
                        response.raise_for_status()
                        image_data = response.content
                        base64_data = base64.b64encode(image_data).decode("utf-8")
                        mime_type = response.headers.get("content-type", "image/jpeg")
                        source_type = "url"
                        logger.info("[IMAGE ANALYZER] Fetched URL: %s (%s)", image_url, mime_type)
                except Exception as e:
                    return {
                        "success": False,
                        "error": f"Failed to fetch image from URL: {str(e)}",
                        "analysis": None
                    }

            # Build data URI
            data_uri = f"data:{mime_type};base64,{base64_data}"

            logger.info("[IMAGE ANALYZER] Analyzing image (source: %s)", source_type)

            # Call MCP tool - try different possible parameter names
            # Different MCP servers might use different parameter names
            result = await mcp_manager.call_tool(
                tool_name="analyze_image",
                arguments={
                    "image": data_uri,  # Common parameter name
                    "prompt": prompt,
                },
                server_name="zai",
            )

            # If first attempt fails, try with alternative parameter names
            if not result["success"] and "parameter" in result["content"].lower():
                result = await mcp_manager.call_tool(
                    tool_name="analyze_image",
                    arguments={
                        "image_url": data_uri,
                        "prompt": prompt,
                    },
                    server_name="zai",
                )

            if not result["success"] and "parameter" in result["content"].lower():
                result = await mcp_manager.call_tool(
                    tool_name="analyze_image",
                    arguments={
                        "image_base64": base64_data,
                        "mime_type": mime_type,
                        "prompt": prompt,
                    },
                    server_name="zai",
                )

            if result["success"]:
                logger.info("[IMAGE ANALYZER] Analysis complete")
                return {
                    "success": True,
                    "analysis": result["content"],
                    "structured_content": result["structured_content"],
                    "source_type": source_type,
                    "prompt": prompt
                }
            else:
                logger.error("[IMAGE ANALYZER] MCP tool failed: %s", result["content"])
                return {
                    "success": False,
                    "error": result["content"],
                    "analysis": None
                }

        except Exception as e:
            logger.exception("[IMAGE ANALYZER] Error: %s", e)
            return {
                "success": False,
                "error": f"Failed to analyze image: {str(e)}",
                "analysis": None
            }
