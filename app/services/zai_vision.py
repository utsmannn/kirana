"""Vision analysis service — Z.AI Vision with automatic fallback to configured LLM provider.

Priority:
1. Z.AI Vision (GLM-4.6V) if ZAI_API_KEY is set — highest quality OCR + vision
2. Fallback to the configured LLM provider (OPENAI_API_KEY + DEFAULT_MODEL)
   for multimodal-capable models like GPT-4o, GPT-4V, etc.
"""

import asyncio
import base64
import logging
import mimetypes
import os
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union

from openai import AsyncOpenAI
from PIL import Image

from app.config import settings

logger = logging.getLogger(__name__)

# Z.AI Vision API defaults
ZAI_VISION_BASE_URL = "https://api.z.ai/api/coding/paas/v4"
ZAI_VISION_MODEL = "glm-4.6v"


class ZaiVisionService:
    """Image/vision analysis service.

    Tries Z.AI Vision first (best OCR quality). Falls back to the configured
    LLM provider when ZAI_API_KEY is not set. The fallback works with any
    multimodal-capable model (GPT-4o, GPT-4V, etc.).
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
    ):
        self._zai_api_key = api_key
        self._zai_base_url = base_url or ZAI_VISION_BASE_URL
        self._zai_model = model or ZAI_VISION_MODEL
        self._zai_client: Optional[AsyncOpenAI] = None
        self._fallback_client: Optional[AsyncOpenAI] = None

    # ------------------------------------------------------------------
    # Client resolution
    # ------------------------------------------------------------------

    @property
    def has_zai(self) -> bool:
        """Whether Z.AI Vision is explicitly configured."""
        return bool(self._zai_api_key)

    @property
    def has_fallback(self) -> bool:
        """Whether a fallback LLM provider is available."""
        return bool(settings.OPENAI_API_KEY)

    def _get_zai_client(self) -> AsyncOpenAI:
        if self._zai_client is None:
            if not self._zai_api_key:
                raise ValueError("ZAI_API_KEY not configured")
            self._zai_client = AsyncOpenAI(
                api_key=self._zai_api_key,
                base_url=self._zai_base_url,
            )
        return self._zai_client

    def _get_fallback_client(self) -> AsyncOpenAI:
        if self._fallback_client is None:
            if not settings.OPENAI_API_KEY:
                raise ValueError("Neither ZAI_API_KEY nor OPENAI_API_KEY is configured")
            kwargs: Dict[str, Any] = {
                "api_key": settings.OPENAI_API_KEY,
                "max_retries": settings.LLM_MAX_RETRIES,
                "timeout": float(settings.LLM_TIMEOUT),
            }
            if settings.OPENAI_BASE_URL:
                kwargs["base_url"] = settings.OPENAI_BASE_URL
            self._fallback_client = AsyncOpenAI(**kwargs)
        return self._fallback_client

    def _resolve_backend(self) -> Tuple[AsyncOpenAI, str, str]:
        """Return (client, model, backend_label)."""
        if self.has_zai:
            return self._get_zai_client(), self._zai_model, "zai"
        if self.has_fallback:
            return self._get_fallback_client(), settings.DEFAULT_MODEL, "fallback"
        raise ValueError(
            "No vision backend available. Set ZAI_API_KEY for Z.AI Vision "
            "or OPENAI_API_KEY for LLM-based vision analysis."
        )

    # ------------------------------------------------------------------
    # Image encoding helpers
    # ------------------------------------------------------------------

    def _encode_image_to_base64(
        self,
        image_source: Union[str, Path, bytes],
        mime_type: Optional[str] = None,
    ) -> Tuple[str, str]:
        """Encode image to base64 data URI. Returns (data_uri, mime_type)."""
        if isinstance(image_source, bytes):
            image_data = image_source
            if not mime_type:
                try:
                    img = Image.open(BytesIO(image_data))
                    mime_type = Image.MIME.get(img.format, "image/jpeg")
                except Exception:
                    mime_type = "image/jpeg"
        else:
            file_path = Path(image_source)
            if not file_path.exists():
                raise FileNotFoundError(f"Image file not found: {file_path}")
            with open(file_path, "rb") as f:
                image_data = f.read()
            if not mime_type:
                mime_type, _ = mimetypes.guess_type(str(file_path))
                if not mime_type:
                    try:
                        img = Image.open(file_path)
                        mime_type = Image.MIME.get(img.format, "image/jpeg")
                    except Exception:
                        mime_type = "image/jpeg"

        b64 = base64.b64encode(image_data).decode("utf-8")
        return f"data:{mime_type};base64,{b64}", mime_type

    def _encode_pil_image_to_base64(self, image: Image.Image) -> str:
        buffer = BytesIO()
        if image.mode in ("RGBA", "P"):
            image = image.convert("RGB")
        image.save(buffer, format="PNG")
        b64 = base64.b64encode(buffer.getvalue()).decode("utf-8")
        return f"data:image/png;base64,{b64}"

    # ------------------------------------------------------------------
    # Single-image analysis
    # ------------------------------------------------------------------

    async def analyze_image(
        self,
        image_source: Union[str, Path, bytes],
        prompt: str,
        mime_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Analyze a single image.

        Uses Z.AI Vision if configured, otherwise falls back to the
        configured LLM provider via multimodal chat.
        """
        try:
            data_uri, detected_mime = self._encode_image_to_base64(image_source, mime_type)
            logger.info(
                "[VISION] Image encoded: mime=%s len=%d",
                detected_mime,
                len(data_uri),
            )

            client, model, backend = self._resolve_backend()
            logger.info("[VISION] Using backend=%s model=%s", backend, model)

            response = await client.chat.completions.create(
                model=model,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image_url", "image_url": {"url": data_uri}},
                        {"type": "text", "text": prompt},
                    ],
                }],
            )

            content = response.choices[0].message.content if response.choices else ""
            if content is None:
                content = ""
                logger.warning("[VISION] API returned None content, defaulting to empty")

            usage = response.usage
            logger.info(
                "[VISION] Success: backend=%s content_len=%d tokens=%s",
                backend,
                len(content),
                f"{usage.prompt_tokens}/{usage.completion_tokens}" if usage else "N/A",
            )

            return {
                "success": True,
                "content": content,
                "error": None,
                "backend": backend,
                "model": model,
                "usage": {
                    "prompt_tokens": usage.prompt_tokens if usage else 0,
                    "completion_tokens": usage.completion_tokens if usage else 0,
                    "total_tokens": usage.total_tokens if usage else 0,
                } if usage else None,
            }

        except FileNotFoundError as e:
            logger.error("[VISION] File not found: %s", e)
            return {"success": False, "content": None, "error": f"File not found: {e}"}
        except ValueError as e:
            logger.error("[VISION] Configuration error: %s", e)
            return {"success": False, "content": None, "error": f"Configuration error: {e}"}
        except Exception as e:
            logger.exception("[VISION] API error: %s", e)
            return {"success": False, "content": None, "error": f"API error: {e}"}

    # ------------------------------------------------------------------
    # Multi-image analysis
    # ------------------------------------------------------------------

    async def analyze_multiple_images(
        self,
        images: List[Union[str, Path, bytes, Image.Image]],
        prompt: str,
    ) -> Dict[str, Any]:
        """Analyze multiple images in a single multimodal request.

        Efficient for multi-page PDFs. All images are sent together with
        the prompt. Z.AI-specific features (thinking extra_body) are only
        applied on the Z.AI path.
        """
        try:
            if not images:
                return {"success": False, "content": None, "error": "No images provided"}

            logger.info("[VISION] Encoding %d images for multimodal request", len(images))

            client, model, backend = self._resolve_backend()

            # Build content array
            content: List[Dict[str, Any]] = []
            for i, img_source in enumerate(images):
                try:
                    if isinstance(img_source, Image.Image):
                        data_uri = self._encode_pil_image_to_base64(img_source)
                    else:
                        data_uri, _ = self._encode_image_to_base64(img_source)
                    content.append({
                        "type": "image_url",
                        "image_url": {"url": data_uri},
                    })
                except Exception as e:
                    logger.warning("[VISION] Failed to encode image %d: %s", i + 1, e)
                    continue

            if not content:
                return {"success": False, "content": None, "error": "Failed to encode any images"}

            content.append({"type": "text", "text": prompt})

            logger.info(
                "[VISION] Calling multimodal API: backend=%s model=%s images=%d prompt_len=%d",
                backend, model, len(content) - 1, len(prompt),
            )

            # Z.AI-specific: enable thinking mode for better OCR quality
            create_kwargs: Dict[str, Any] = {
                "model": model,
                "messages": [{"role": "user", "content": content}],
            }
            if backend == "zai":
                create_kwargs["extra_body"] = {"thinking": {"type": "enabled"}}

            response = await client.chat.completions.create(**create_kwargs)

            resp_content = response.choices[0].message.content if response.choices else ""
            if resp_content is None:
                resp_content = ""
                logger.warning("[VISION] API returned None content, defaulting to empty")

            usage = response.usage
            logger.info(
                "[VISION] Multimodal success: backend=%s content_len=%d tokens=%s",
                backend,
                len(resp_content),
                f"{usage.prompt_tokens}/{usage.completion_tokens}" if usage else "N/A",
            )

            return {
                "success": True,
                "content": resp_content,
                "error": None,
                "backend": backend,
                "model": model,
                "usage": {
                    "prompt_tokens": usage.prompt_tokens if usage else 0,
                    "completion_tokens": usage.completion_tokens if usage else 0,
                    "total_tokens": usage.total_tokens if usage else 0,
                } if usage else None,
            }

        except ValueError as e:
            logger.error("[VISION] Configuration error: %s", e)
            return {"success": False, "content": None, "error": f"Configuration error: {e}"}
        except Exception as e:
            logger.exception("[VISION] Multimodal API error: %s", e)
            return {"success": False, "content": None, "error": f"API error: {e}"}


# ------------------------------------------------------------------
# Singleton
# ------------------------------------------------------------------

_zai_vision_service: Optional[ZaiVisionService] = None
_zai_vision_api_key: Optional[str] = None


def get_zai_vision_service() -> ZaiVisionService:
    """Get or create the vision service singleton.

    Reinitialises if the ZAI_API_KEY env var has changed since last call.
    """
    global _zai_vision_service, _zai_vision_api_key

    current_api_key = os.getenv("ZAI_API_KEY") or os.getenv("Z_AI_API_KEY")

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
            logger.info("[VISION] Z.AI backend available (key len=%d)", len(current_api_key))
        elif settings.OPENAI_API_KEY:
            logger.info("[VISION] Z.AI not configured — will use LLM fallback (model=%s)", settings.DEFAULT_MODEL)
        else:
            logger.warning("[VISION] No vision backend available. Set ZAI_API_KEY or OPENAI_API_KEY.")

    return _zai_vision_service


def is_zai_vision_configured() -> bool:
    """Check whether ANY vision backend is available (Z.AI or fallback LLM)."""
    return bool(
        os.getenv("ZAI_API_KEY") or os.getenv("Z_AI_API_KEY") or settings.OPENAI_API_KEY
    )
