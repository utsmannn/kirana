"""Z.AI Vision Service for image analysis using direct API."""

import base64
import logging
import mimetypes
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Optional

from openai import AsyncOpenAI
from PIL import Image

logger = logging.getLogger(__name__)

# Z.AI Vision API configuration
ZAI_VISION_BASE_URL = "https://api.z.ai/api/coding/paas/v4"
ZAI_VISION_MODEL = "glm-4.6v"


class ZaiVisionService:
    """
    Service for analyzing images using Z.AI Vision API (GLM-4.6V).

    Uses OpenAI SDK with custom base URL for compatibility.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self._api_key = api_key
        self._base_url = base_url or ZAI_VISION_BASE_URL
        self._model = model or ZAI_VISION_MODEL
        self._client: Optional[AsyncOpenAI] = None

    def _get_client(self) -> AsyncOpenAI:
        """Get or create OpenAI client."""
        if self._client is None:
            if not self._api_key:
                raise ValueError("ZAI_API_KEY not configured")
            self._client = AsyncOpenAI(
                api_key=self._api_key,
                base_url=self._base_url,
            )
        return self._client

    def _encode_image_to_base64(self, image_source: str | Path | bytes, mime_type: Optional[str] = None) -> tuple[str, str]:
        """
        Encode image to base64 data URI.

        Args:
            image_source: File path (str/Path) or raw bytes
            mime_type: MIME type (auto-detected if not provided)

        Returns:
            Tuple of (data_uri, mime_type)
        """
        if isinstance(image_source, bytes):
            # Raw bytes
            image_data = image_source
            if not mime_type:
                # Try to detect from image content
                try:
                    img = Image.open(BytesIO(image_data))
                    mime_type = Image.MIME.get(img.format, "image/jpeg")
                except Exception:
                    mime_type = "image/jpeg"
        else:
            # File path
            file_path = Path(image_source)
            if not file_path.exists():
                raise FileNotFoundError(f"Image file not found: {file_path}")

            with open(file_path, "rb") as f:
                image_data = f.read()

            if not mime_type:
                mime_type, _ = mimetypes.guess_type(str(file_path))
                if not mime_type:
                    # Try PIL
                    try:
                        img = Image.open(file_path)
                        mime_type = Image.MIME.get(img.format, "image/jpeg")
                    except Exception:
                        mime_type = "image/jpeg"

        base64_data = base64.b64encode(image_data).decode("utf-8")
        data_uri = f"data:{mime_type};base64,{base64_data}"

        return data_uri, mime_type

    async def analyze_image(
        self,
        image_source: str | Path | bytes,
        prompt: str,
        mime_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Analyze an image using Z.AI Vision API.

        Args:
            image_source: File path (str/Path) or raw bytes of the image
            prompt: The analysis prompt/question
            mime_type: MIME type (auto-detected if not provided)

        Returns:
            Dict with 'success', 'content', 'error' keys
        """
        try:
            # Encode image
            data_uri, detected_mime = self._encode_image_to_base64(image_source, mime_type)
            logger.info("[ZAI_VISION] Image encoded: mime_type=%s, data_uri_length=%d",
                       detected_mime, len(data_uri))

            client = self._get_client()

            logger.info("[ZAI_VISION] Calling API: model=%s, prompt_length=%d",
                       self._model, len(prompt))

            # Call Z.AI Vision API
            response = await client.chat.completions.create(
                model=self._model,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": data_uri,
                                },
                            },
                            {
                                "type": "text",
                                "text": prompt,
                            },
                        ],
                    }
                ],
                max_tokens=2000,
            )

            # Extract response
            content = response.choices[0].message.content if response.choices else ""
            usage = response.usage

            logger.info("[ZAI_VISION] API success: content_length=%d, tokens_used=%s",
                       len(content) if content else 0,
                       f"{usage.prompt_tokens}/{usage.completion_tokens}" if usage else "N/A")

            return {
                "success": True,
                "content": content,
                "error": None,
                "usage": {
                    "prompt_tokens": usage.prompt_tokens if usage else 0,
                    "completion_tokens": usage.completion_tokens if usage else 0,
                    "total_tokens": usage.total_tokens if usage else 0,
                } if usage else None,
            }

        except FileNotFoundError as e:
            logger.error("[ZAI_VISION] File not found: %s", e)
            return {
                "success": False,
                "content": None,
                "error": f"File not found: {str(e)}",
            }

        except ValueError as e:
            logger.error("[ZAI_VISION] Configuration error: %s", e)
            return {
                "success": False,
                "content": None,
                "error": f"Configuration error: {str(e)}",
            }

        except Exception as e:
            logger.exception("[ZAI_VISION] API error: %s", e)
            return {
                "success": False,
                "content": None,
                "error": f"API error: {str(e)}",
            }


# Global singleton instance
_zai_vision_service: Optional[ZaiVisionService] = None


def get_zai_vision_service() -> ZaiVisionService:
    """Get or create Z.AI Vision service instance."""
    global _zai_vision_service

    if _zai_vision_service is None:
        import os

        # Support both ZAI_API_KEY and Z_AI_API_KEY for flexibility
        api_key = os.getenv("ZAI_API_KEY") or os.getenv("Z_AI_API_KEY")
        base_url = os.getenv("ZAI_VISION_BASE_URL", ZAI_VISION_BASE_URL)
        model = os.getenv("ZAI_VISION_MODEL", ZAI_VISION_MODEL)

        _zai_vision_service = ZaiVisionService(
            api_key=api_key,
            base_url=base_url,
            model=model,
        )

        if api_key:
            logger.info("[ZAI_VISION] Service initialized with API key (len=%d)", len(api_key))
        else:
            logger.warning("[ZAI_VISION] No API key configured. Image analysis will not work.")

    return _zai_vision_service


def is_zai_vision_configured() -> bool:
    """Check if Z.AI Vision is configured with an API key."""
    import os
    return bool(os.getenv("ZAI_API_KEY") or os.getenv("Z_AI_API_KEY"))
