"""Z.AI Vision Service for image analysis using direct API."""

import base64
import logging
import mimetypes
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

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

    def _encode_pil_image_to_base64(self, image: Image.Image) -> str:
        """Encode PIL Image to base64 data URI."""
        buffer = BytesIO()
        # Convert to RGB if necessary
        if image.mode in ('RGBA', 'P'):
            image = image.convert('RGB')
        image.save(buffer, format='PNG')
        base64_data = base64.b64encode(buffer.getvalue()).decode("utf-8")
        return f"data:image/png;base64,{base64_data}"

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
                # No max_tokens limit - let API use model's maximum
            )

            # Extract response - ensure content is never None
            content = response.choices[0].message.content if response.choices else ""
            if content is None:
                content = ""
                logger.warning("[ZAI_VISION] API returned None content, defaulting to empty string")
            usage = response.usage

            logger.info("[ZAI_VISION] API success: content_length=%d, tokens_used=%s",
                       len(content),
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

    async def analyze_multiple_images(
        self,
        images: List[Union[str, Path, bytes, Image.Image]],
        prompt: str,
    ) -> Dict[str, Any]:
        """
        Analyze multiple images in a single multimodal request.

        This is efficient for multi-page PDFs where each page is an image.
        All images are sent together with the prompt.

        Args:
            images: List of image sources (file paths, bytes, or PIL Images)
            prompt: The analysis prompt/question

        Returns:
            Dict with 'success', 'content', 'error' keys
        """
        try:
            if not images:
                return {
                    "success": False,
                    "content": None,
                    "error": "No images provided",
                }

            logger.info("[ZAI_VISION] Encoding %d images for multimodal request", len(images))

            # Build content array with all images followed by text prompt
            content: List[Dict[str, Any]] = []

            for i, img_source in enumerate(images):
                try:
                    if isinstance(img_source, Image.Image):
                        # PIL Image directly
                        data_uri = self._encode_pil_image_to_base64(img_source)
                    else:
                        # File path or bytes
                        data_uri, _ = self._encode_image_to_base64(img_source)

                    content.append({
                        "type": "image_url",
                        "image_url": {
                            "url": data_uri,
                        },
                    })
                    logger.debug("[ZAI_VISION] Encoded image %d/%d (data_uri_length=%d)",
                               i + 1, len(images), len(data_uri))
                except Exception as e:
                    logger.warning("[ZAI_VISION] Failed to encode image %d: %s", i + 1, e)
                    continue

            if not content:
                return {
                    "success": False,
                    "content": None,
                    "error": "Failed to encode any images",
                }

            # Add the text prompt at the end
            content.append({
                "type": "text",
                "text": prompt,
            })

            logger.info("[ZAI_VISION] Calling multimodal API: model=%s, images=%d, prompt_length=%d",
                       self._model, len(content) - 1, len(prompt))

            client = self._get_client()

            # Call Z.AI Vision API with multiple images
            response = await client.chat.completions.create(
                model=self._model,
                messages=[
                    {
                        "role": "user",
                        "content": content,
                    }
                ],
                extra_body={
                    "thinking": {
                        "type": "enabled"
                    }
                }
            )

            # Extract response - ensure content is never None
            response_content = response.choices[0].message.content if response.choices else ""
            if response_content is None:
                response_content = ""
                logger.warning("[ZAI_VISION] API returned None content, defaulting to empty string")
            usage = response.usage

            logger.info("[ZAI_VISION] Multimodal API success: content_length=%d, tokens_used=%s",
                       len(response_content),
                       f"{usage.prompt_tokens}/{usage.completion_tokens}" if usage else "N/A")

            return {
                "success": True,
                "content": response_content,
                "error": None,
                "usage": {
                    "prompt_tokens": usage.prompt_tokens if usage else 0,
                    "completion_tokens": usage.completion_tokens if usage else 0,
                    "total_tokens": usage.total_tokens if usage else 0,
                } if usage else None,
            }

        except ValueError as e:
            logger.error("[ZAI_VISION] Configuration error: %s", e)
            return {
                "success": False,
                "content": None,
                "error": f"Configuration error: {str(e)}",
            }

        except Exception as e:
            logger.exception("[ZAI_VISION] Multimodal API error: %s", e)
            return {
                "success": False,
                "content": None,
                "error": f"API error: {str(e)}",
            }


# Global singleton instance
_zai_vision_service: Optional[ZaiVisionService] = None
_zai_vision_api_key: Optional[str] = None


def get_zai_vision_service() -> ZaiVisionService:
    """Get or create Z.AI Vision service instance.

    Will reinitialize if API key changes.
    """
    global _zai_vision_service, _zai_vision_api_key

    import os

    # Support both ZAI_API_KEY and Z_AI_API_KEY for flexibility
    current_api_key = os.getenv("ZAI_API_KEY") or os.getenv("Z_AI_API_KEY")

    # Reinitialize if API key changed or service not created
    if _zai_vision_service is None or _zai_vision_api_key != current_api_key:
        base_url = os.getenv("ZAI_VISION_BASE_URL", ZAI_VISION_BASE_URL)
        model = os.getenv("ZAI_VISION_MODEL", ZAI_VISION_MODEL)

        _zai_vision_service = ZaiVisionService(
            api_key=current_api_key,
            base_url=base_url,
            model=model,
        )
        _zai_vision_api_key = current_api_key

        if current_api_key:
            logger.info("[ZAI_VISION] Service initialized with API key (len=%d)", len(current_api_key))
        else:
            logger.warning("[ZAI_VISION] No API key configured. Image analysis will not work.")

    return _zai_vision_service


def is_zai_vision_configured() -> bool:
    """Check if Z.AI Vision is configured with an API key."""
    import os
    return bool(os.getenv("ZAI_API_KEY") or os.getenv("Z_AI_API_KEY"))
