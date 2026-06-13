"""Image analyzer tool — uses Z.AI Vision MCP with automatic fallback to LLM provider."""

import base64
import logging
import mimetypes
import os
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from PIL import Image

from app.config import settings
from app.services.mcp_client import mcp_manager
from app.tools.base import BaseTool

logger = logging.getLogger(__name__)

UPLOAD_DIR = Path(settings.UPLOAD_DIR) / "knowledge"


class ImageAnalyzerTool(BaseTool):
    """Tool for analyzing images.

    Internal tool — not exposed to users in system prompts. The system
    uses it for processing uploaded images in the knowledge base.

    Priority: Z.AI Vision MCP → LLM provider fallback.
    """

    internal: bool = True

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
                    "description": "Base64-encoded image data (without data URI prefix)",
                },
                "image_file": {
                    "type": "string",
                    "description": "Path to local image file",
                },
                "image_url": {
                    "type": "string",
                    "description": "Public URL of the image",
                },
                "prompt": {
                    "type": "string",
                    "description": "Specific question or instruction about the image",
                },
            },
            "required": [],
        }

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_mime_type(self, file_path: str) -> str:
        mime_type, _ = mimetypes.guess_type(file_path)
        return mime_type or "image/jpeg"

    def _resolve_file_path(self, file_path: str) -> str:
        if not file_path.startswith("/"):
            file_path = str(UPLOAD_DIR / file_path)
        if file_path.startswith("/uploads/knowledge/"):
            file_path = str(UPLOAD_DIR / file_path.replace("/uploads/knowledge/", ""))
        return file_path

    def _read_file_as_base64(self, file_path: str) -> Tuple[str, str]:
        """Read a local file; return (base64_data, mime_type)."""
        path = Path(self._resolve_file_path(file_path))
        if not path.exists():
            raise FileNotFoundError(f"Image file not found: {file_path}")
        with open(path, "rb") as f:
            image_data = f.read()
        return base64.b64encode(image_data).decode("utf-8"), self._get_mime_type(str(path))

    # ------------------------------------------------------------------
    # Fallback: direct LLM multimodal call
    # ------------------------------------------------------------------

    async def _analyze_via_fallback(
        self,
        data_uri: str,
        prompt: str,
        source_type: str,
    ) -> Dict[str, Any]:
        """Call the configured LLM provider directly for image analysis."""
        from openai import AsyncOpenAI

        if not settings.OPENAI_API_KEY:
            return {
                "success": False,
                "error": (
                    "No vision backend available. "
                    "Set ZAI_API_KEY for Z.AI Vision or OPENAI_API_KEY for LLM-based analysis."
                ),
                "analysis": None,
            }

        kwargs: Dict[str, Any] = {"api_key": settings.OPENAI_API_KEY}
        if settings.OPENAI_BASE_URL:
            kwargs["base_url"] = settings.OPENAI_BASE_URL
        client = AsyncOpenAI(**kwargs)

        logger.info("[IMAGE ANALYZER] Fallback LLM: model=%s", settings.DEFAULT_MODEL)

        response = await client.chat.completions.create(
            model=settings.DEFAULT_MODEL,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": data_uri}},
                    {"type": "text", "text": prompt},
                ],
            }],
        )

        content = response.choices[0].message.content if response.choices else ""
        return {
            "success": True,
            "analysis": content or "",
            "source_type": source_type,
            "prompt": prompt,
            "backend": "fallback_llm",
            "model": settings.DEFAULT_MODEL,
        }

    # ------------------------------------------------------------------
    # MCP (Z.AI Vision) path
    # ------------------------------------------------------------------

    async def _analyze_via_mcp(
        self,
        data_uri: str,
        base64_data: str,
        mime_type: str,
        prompt: str,
    ) -> Optional[Dict[str, Any]]:
        """Try Z.AI Vision via MCP. Returns None if MCP is unavailable."""
        available_servers = mcp_manager.get_available_servers()
        if not available_servers:
            return None

        logger.info("[IMAGE ANALYZER] Trying MCP/zai backend…")

        # Try multiple parameter-name variants (different MCP servers differ)
        for args in (
            {"image": data_uri, "prompt": prompt},
            {"image_url": data_uri, "prompt": prompt},
            {"image_base64": base64_data, "mime_type": mime_type, "prompt": prompt},
        ):
            result = await mcp_manager.call_tool(
                tool_name="analyze_image",
                arguments=args,
                server_name="zai",
            )
            if result["success"]:
                return {
                    "success": True,
                    "analysis": result["content"],
                    "structured_content": result["structured_content"],
                    "source_type": "mcp_zai",
                    "prompt": prompt,
                    "backend": "zai_mcp",
                }
            if "parameter" not in result.get("content", "").lower():
                break  # not a parameter-name issue — stop trying

        logger.warning("[IMAGE ANALYZER] MCP/zai failed: %s", result.get("content", "unknown"))
        return None  # MCP available but failed — caller decides whether to fallback

    # ------------------------------------------------------------------
    # Execute
    # ------------------------------------------------------------------

    async def execute(
        self,
        image_base64: str = None,
        image_file: str = None,
        image_url: str = None,
        prompt: str = "Describe this image in detail.",
    ) -> Dict[str, Any]:
        try:
            if not image_base64 and not image_file and not image_url:
                return {
                    "success": False,
                    "error": "Must provide one of: image_base64, image_file, or image_url",
                    "analysis": None,
                }

            # --- Resolve image source into data URI + base64 ---
            mime_type = "image/jpeg"
            source_type: Optional[str] = None

            if image_base64:
                base64_data = image_base64
                source_type = "base64"
            elif image_file:
                try:
                    base64_data, mime_type = self._read_file_as_base64(image_file)
                    source_type = "file"
                except FileNotFoundError as e:
                    return {"success": False, "error": str(e), "analysis": None}
            elif image_url:
                try:
                    import httpx
                    async with httpx.AsyncClient() as client:
                        resp = await client.get(image_url, follow_redirects=True, timeout=30)
                        resp.raise_for_status()
                        base64_data = base64.b64encode(resp.content).decode("utf-8")
                        mime_type = resp.headers.get("content-type", "image/jpeg")
                        source_type = "url"
                except Exception as e:
                    return {
                        "success": False,
                        "error": f"Failed to fetch image from URL: {e}",
                        "analysis": None,
                    }

            data_uri = f"data:{mime_type};base64,{base64_data}"

            # --- Try MCP (Z.AI Vision) first ---
            mcp_result = await self._analyze_via_mcp(data_uri, base64_data, mime_type, prompt)
            if mcp_result:
                return mcp_result

            # --- Fallback to direct LLM ---
            logger.info("[IMAGE ANALYZER] MCP/zai unavailable — falling back to LLM provider")
            return await self._analyze_via_fallback(data_uri, prompt, source_type or "unknown")

        except Exception as e:
            logger.exception("[IMAGE ANALYZER] Error: %s", e)
            return {
                "success": False,
                "error": f"Failed to analyze image: {e}",
                "analysis": None,
            }
