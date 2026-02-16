"""Brand style extractor using Jina.ai screenshot + Z.AI Vision."""

import base64
import json
import logging
import re
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional

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
5. font_family: The primary font family used (just the font name, e.g., "Inter", "Poppins", "Roboto")

Rules:
- Return ONLY valid JSON, no markdown or explanations
- Colors must be in hex format (#RRGGBB)
- If you can't determine a color, use null for that field
- For font_family, just return the main font name (e.g., "Inter" not "Inter, sans-serif")
- Choose colors that best represent the brand identity

Example output:
{"primary_color": "#6366f1", "secondary_color": "#818cf8", "bg_color": "#09090b", "text_color": "#e4e4e7", "font_family": "Inter"}"""


class GoogleFontsMatcher:
    """Match extracted fonts with Google Fonts."""

    def __init__(self):
        self.api_key = settings.GOOGLE_FONTS_API_KEY
        self._fonts_cache: Optional[List[str]] = None
        self._cache_time: Optional[float] = None
        self._cache_ttl = 3600 * 24  # 24 hours

    async def _fetch_fonts(self) -> List[str]:
        """Fetch list of available Google Fonts."""
        if not self.api_key:
            logger.warning("[GOOGLE FONTS] No API key configured")
            return []

        url = f"https://www.googleapis.com/webfonts/v1/webfonts?key={self.api_key}&sort=popularity"

        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(url)

            if response.status_code != 200:
                logger.error("[GOOGLE FONTS] API error: %s", response.text)
                return []

            data = response.json()
            fonts = [item["family"] for item in data.get("items", [])]
            logger.info("[GOOGLE FONTS] Loaded %d fonts", len(fonts))
            return fonts

    async def get_fonts(self) -> List[str]:
        """Get fonts list with caching."""
        import time

        now = time.time()

        if self._fonts_cache and self._cache_time and (now - self._cache_time) < self._cache_ttl:
            return self._fonts_cache

        self._fonts_cache = await self._fetch_fonts()
        self._cache_time = now
        return self._fonts_cache or []

    def _normalize_font_name(self, name: str) -> str:
        """Normalize font name for comparison."""
        if not name:
            return ""
        # Remove quotes, commas, and common suffixes
        name = name.strip().strip("'\"")
        name = re.sub(r'\s*(sans-serif|serif|monospace|display|handwriting).*$', '', name, flags=re.IGNORECASE)
        return name.lower().strip()

    async def match_font(self, extracted_font: Optional[str]) -> Optional[Dict[str, str]]:
        """Match extracted font with Google Fonts.

        Returns dict with 'name' and 'url' if matched, None otherwise.
        """
        if not extracted_font:
            return None

        fonts = await self.get_fonts()
        if not fonts:
            return None

        extracted_normalized = self._normalize_font_name(extracted_font)

        # Try exact match first
        for font in fonts:
            if self._normalize_font_name(font) == extracted_normalized:
                logger.info("[GOOGLE FONTS] Exact match: %s", font)
                return {
                    "name": font,
                    "url": self._build_google_fonts_url(font)
                }

        # Try fuzzy match
        best_match = None
        best_ratio = 0.0

        for font in fonts:
            font_normalized = self._normalize_font_name(font)
            ratio = SequenceMatcher(None, extracted_normalized, font_normalized).ratio()

            if ratio > best_ratio and ratio >= 0.7:  # 70% similarity threshold
                best_ratio = ratio
                best_match = font

        if best_match:
            logger.info("[GOOGLE FONTS] Fuzzy match: %s -> %s (%.0f%%)", extracted_font, best_match, best_ratio * 100)
            return {
                "name": best_match,
                "url": self._build_google_fonts_url(best_match)
            }

        logger.info("[GOOGLE FONTS] No match found for: %s", extracted_font)
        return None

    def _build_google_fonts_url(self, font_name: str) -> str:
        """Build Google Fonts CSS URL for a font."""
        # URL encode the font name (spaces become +)
        encoded = font_name.replace(" ", "+")
        # Include common weights
        return f"https://fonts.googleapis.com/css2?family={encoded}:wght@400;500;600;700&display=swap"


class BrandStyleExtractor:
    """Extract brand style from website using Jina.ai + Z.AI Vision."""

    def __init__(self):
        self.jina_api_key = settings.JINA_API_KEY
        self.zai_api_key = settings.ZAI_API_KEY
        self.fonts_matcher = GoogleFontsMatcher()

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
            Dict with: primary_color, secondary_color, bg_color, text_color, font_family, google_fonts_url
        """
        try:
            # Step 1: Take screenshot
            screenshot = await self.take_screenshot(url)

            if not screenshot:
                return {"success": False, "error": "Failed to capture screenshot"}

            # Step 2: Analyze with vision model
            style_data = await self.analyze_screenshot(screenshot)

            # Step 3: Match font with Google Fonts
            extracted_font = style_data.get("font_family")
            google_fonts_info = await self.fonts_matcher.match_font(extracted_font)

            # Build result
            result = {
                "success": True,
                "primary_color": style_data.get("primary_color"),
                "secondary_color": style_data.get("secondary_color"),
                "bg_color": style_data.get("bg_color"),
                "text_color": style_data.get("text_color"),
                "font_family": extracted_font,
            }

            # Add Google Fonts info if matched
            if google_fonts_info:
                result["google_fonts_name"] = google_fonts_info["name"]
                result["google_fonts_url"] = google_fonts_info["url"]
                # Use the matched Google Fonts name for font_family
                result["font_family"] = google_fonts_info["name"]

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
