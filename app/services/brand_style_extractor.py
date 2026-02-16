"""Brand style extractor using Jina.ai screenshot + Z.AI Vision."""

import base64
import json
import logging
from typing import Any, Dict, Optional

import httpx
from openai import AsyncOpenAI

from app.config import settings

logger = logging.getLogger(__name__)

# System prompt for extracting brand style
BRAND_STYLE_PROMPT = """You are a brand style extractor. Analyze the website screenshot and extract the brand's visual identity.

Extract the following information and return it as a JSON object:
1. primary_color: The main brand color (hex format, e.g., #4f46e5)
2. secondary_color: A secondary/accent color used on the website (hex format)
3. bg_color: The background color (hex format)
4. text_color: The main text color (hex format)
5. font_family: The primary font family used (CSS format, e.g., "Inter, sans-serif")

Rules:
- Return ONLY valid JSON, no markdown or explanations
- Colors must be in hex format (#RRGGBB)
- If you can't determine a color, use null for that field
- For font_family, provide the CSS font-family value
- Choose colors that best represent the brand identity

Example output:
{"primary_color": "#6366f1", "secondary_color": "#818cf8", "bg_color": "#09090b", "text_color": "#e4e4e7", "font_family": "Inter, sans-serif"}"""


class BrandStyleExtractor:
    """Extract brand style from website using Jina.ai + Z.AI Vision."""

    def __init__(self):
        self.jina_api_key = settings.JINA_API_KEY
        self.zai_api_key = settings.ZAI_API_KEY

    async def take_screenshot(self, url: str) -> Optional[bytes]:
        """Take screenshot of website using Jina.ai Reader."""
        if not self.jina_api_key:
            raise ValueError("JINA_API_KEY not configured")

        # Normalize URL
        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        jina_url = f"https://r.jina.ai/{url}"

        headers = {
            "Authorization": f"Bearer {self.jina_api_key}",
            "X-Return-Format": "pageshot",
        }

        logger.info("[BRAND EXTRACTOR] Taking screenshot of %s", url)

        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.get(jina_url, headers=headers, follow_redirects=True)

            if response.status_code != 200:
                logger.error("[BRAND EXTRACTOR] Jina.ai error: %s", response.text)
                raise Exception(f"Failed to take screenshot: HTTP {response.status_code}")

            return response.content

    async def analyze_screenshot(self, image_data: bytes) -> Dict[str, Any]:
        """Analyze screenshot using Z.AI Vision model."""
        if not self.zai_api_key:
            raise ValueError("ZAI_API_KEY not configured")

        # Convert image to base64
        base64_image = base64.b64encode(image_data).decode("utf-8")

        # Use OpenAI SDK with Z.AI endpoint
        client = AsyncOpenAI(
            api_key=self.zai_api_key,
            base_url="https://api.z.ai/api/coding/paas/v4",
        )

        logger.info("[BRAND EXTRACTOR] Analyzing screenshot with Z.AI Vision")

        response = await client.chat.completions.create(
            model="glm-4.6v",
            messages=[
                {"role": "system", "content": BRAND_STYLE_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/png;base64,{base64_image}",
                            },
                        },
                        {
                            "type": "text",
                            "text": "Extract the brand style from this website screenshot.",
                        },
                    ],
                },
            ],
            max_tokens=500,
            temperature=0.1,
        )

        content = response.choices[0].message.content
        logger.info("[BRAND EXTRACTOR] Raw response: %s", content)

        # Parse JSON from response
        try:
            # Try to extract JSON from the response
            content = content.strip()

            # Remove markdown code blocks if present
            if content.startswith("```"):
                lines = content.split("\n")
                content = "\n".join(lines[1:-1] if lines[-1] == "```" else lines[1:])

            return json.loads(content)
        except json.JSONDecodeError:
            logger.error("[BRAND EXTRACTOR] Failed to parse JSON from response")
            # Return empty dict if parsing fails
            return {}

    async def extract(self, url: str) -> Dict[str, Any]:
        """Extract brand style from URL.

        Returns:
            Dict with: primary_color, secondary_color, bg_color, text_color, font_family
        """
        try:
            # Step 1: Take screenshot
            screenshot = await self.take_screenshot(url)

            if not screenshot:
                return {"success": False, "error": "Failed to capture screenshot"}

            # Step 2: Analyze with vision model
            style_data = await self.analyze_screenshot(screenshot)

            # Step 3: Validate and return
            result = {
                "success": True,
                "primary_color": style_data.get("primary_color"),
                "secondary_color": style_data.get("secondary_color"),
                "bg_color": style_data.get("bg_color"),
                "text_color": style_data.get("text_color"),
                "font_family": style_data.get("font_family"),
            }

            logger.info("[BRAND EXTRACTOR] Extracted style: %s", result)
            return result

        except Exception as e:
            logger.exception("[BRAND EXTRACTOR] Error: %s", e)
            return {"success": False, "error": str(e)}


# Singleton instance
_brand_extractor: Optional[BrandStyleExtractor] = None


def get_brand_extractor() -> BrandStyleExtractor:
    """Get brand style extractor instance."""
    global _brand_extractor
    if _brand_extractor is None:
        _brand_extractor = BrandStyleExtractor()
    return _brand_extractor
