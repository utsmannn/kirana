"""Web scraper service using Jina AI Reader API."""

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import List, Optional
from urllib.parse import urljoin, urlparse

import httpx

from app.config import settings

logger = logging.getLogger(__name__)

# Jina AI Reader API endpoint
JINA_READER_URL = "https://r.jina.ai/"

# File extensions to skip (images, media, documents, etc.)
SKIP_EXTENSIONS = {
    '.jpg', '.jpeg', '.png', '.gif', '.webp', '.svg', '.ico', '.bmp',
    '.mp4', '.mp3', '.wav', '.avi', '.mov', '.wmv', '.flv',
    '.pdf', '.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx',
    '.zip', '.rar', '.tar', '.gz', '.7z',
    '.css', '.js', '.json', '.xml', '.rss',
    '.woff', '.woff2', '.ttf', '.eot', '.otf',
}

# URL patterns that are typically not crawlable pages
SKIP_PATTERNS = [
    r'/_next/image',          # Next.js image optimization
    r'/image\?',              # Image resize URLs
    r'\.(jpg|jpeg|png|gif|webp|svg|ico|bmp)',  # Image files
    r'#',                     # Anchors
    r'mailto:',               # Email links
    r'tel:',                  # Phone links
    r'javascript:',           # JavaScript links
]


@dataclass
class ScrapedPage:
    """Result of scraping a single page."""
    url: str
    title: str
    content: str
    success: bool
    error: Optional[str] = None


@dataclass
class CrawlResult:
    """Result of crawling a website."""
    pages: List[ScrapedPage]
    total_pages: int
    successful_pages: int
    failed_pages: int
    errors: List[str]


def normalize_url(url: str) -> str:
    """Normalize URL - add https:// if missing."""
    url = url.strip()
    if not url:
        return url

    # Add https:// if no protocol specified
    if not url.startswith(('http://', 'https://')):
        url = 'https://' + url

    return url


def is_crawlable_url(url: str) -> bool:
    """Check if URL is a crawlable HTML page (not an image, media, etc.)."""
    parsed = urlparse(url)
    path = parsed.path.lower()

    # Check file extension
    for ext in SKIP_EXTENSIONS:
        if path.endswith(ext):
            return False

    # Check skip patterns
    for pattern in SKIP_PATTERNS:
        if re.search(pattern, url, re.IGNORECASE):
            return False

    return True


def extract_title_from_content(content: str, url: str) -> str:
    """Extract title from content or URL."""
    # Try to find title in content (Jina usually includes it at the top)
    lines = content.strip().split('\n')
    if lines:
        first_line = lines[0].strip()
        # Check if first line looks like a title (starts with # or is short)
        if first_line.startswith('# '):
            return first_line[2:].strip()
        if len(first_line) < 100 and not first_line.startswith(('http', 'Title:', 'Date:')):
            return first_line

    # Fallback to URL path
    parsed = urlparse(url)
    title = parsed.path.strip('/').replace('/', ' - ') or parsed.netloc
    # Remove common prefixes and clean up
    title = re.sub(r'^www\.', '', title)
    return title


class WebScraper:
    """Web scraper using Jina AI Reader API."""

    def __init__(
        self,
        timeout: float = 60.0,
        delay: float = 1.0,
        max_pages: int = 50,
        max_depth: int = 3,
    ):
        self.timeout = timeout
        self.delay = delay
        self.max_pages = max_pages
        self.max_depth = max_depth

        # Check if Jina API key is configured
        self.jina_api_key = settings.JINA_API_KEY
        if not self.jina_api_key:
            logger.warning("[WEB_SCRAPER] JINA_API_KEY not configured. Web scraping will not work.")

    def _get_headers(self) -> dict:
        """Get headers for Jina API request."""
        return {
            "Authorization": f"Bearer {self.jina_api_key}",
            "Accept": "text/plain",
        }

    async def _fetch_with_jina(self, client: httpx.AsyncClient, url: str) -> tuple[Optional[str], Optional[str]]:
        """Fetch content using Jina AI Reader API."""
        if not self.jina_api_key:
            return None, "JINA_API_KEY not configured"

        try:
            # Jina Reader URL format: https://r.jina.ai/{url}
            jina_url = f"{JINA_READER_URL}{url}"

            response = await client.get(
                jina_url,
                headers=self._get_headers(),
                follow_redirects=True,
            )
            response.raise_for_status()

            content = response.text
            if not content or len(content.strip()) < 50:
                return None, "No meaningful content extracted"

            return content, None

        except httpx.TimeoutException:
            return None, f"Timeout fetching {url}"
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                return None, "Invalid Jina API key"
            elif e.response.status_code == 402:
                return None, "Jina API quota exceeded"
            return None, f"HTTP error {e.response.status_code} for {url}"
        except Exception as e:
            return None, f"Error fetching {url}: {str(e)}"

    def _extract_page_links(self, content: str, base_url: str) -> List[str]:
        """Extract only HTML page links from markdown content, excluding images/media."""
        links = []
        parsed_base = urlparse(base_url)

        # Match markdown links: [text](url)
        md_pattern = re.compile(r'\[([^\]]+)\]\(([^)]+)\)')

        for match in md_pattern.finditer(content):
            href = match.group(2)

            # Skip if not a web URL
            if not href.startswith(('http://', 'https://')):
                continue

            # Skip non-crawlable URLs (images, media, etc.)
            if not is_crawlable_url(href):
                continue

            parsed = urlparse(href)

            # Only same domain links
            if parsed.netloc != parsed_base.netloc:
                continue

            # Clean URL (remove fragment)
            clean = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
            if parsed.query:
                clean += f"?{parsed.query}"

            # Final check
            if is_crawlable_url(clean):
                links.append(clean)

        return list(set(links))

    async def scrape_url(self, url: str) -> ScrapedPage:
        """Scrape a single URL using Jina AI Reader."""
        url = normalize_url(url)
        logger.info("[WEB_SCRAPER] Scraping URL with Jina: %s", url)

        if not self.jina_api_key:
            return ScrapedPage(
                url=url,
                title="",
                content="",
                success=False,
                error="JINA_API_KEY not configured. Please add JINA_API_KEY to your .env file.",
            )

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            content, error = await self._fetch_with_jina(client, url)

            if error:
                logger.warning("[WEB_SCRAPER] Failed to fetch %s: %s", url, error)
                return ScrapedPage(
                    url=url,
                    title="",
                    content="",
                    success=False,
                    error=error,
                )

            title = extract_title_from_content(content, url)

            logger.info("[WEB_SCRAPER] Successfully scraped %s: %d chars, title='%s'",
                       url, len(content), title[:50] if title else "N/A")

            return ScrapedPage(
                url=url,
                title=title,
                content=content,
                success=True,
            )

    async def crawl_website(
        self,
        start_url: str,
        max_pages: Optional[int] = None,
        max_depth: Optional[int] = None,
        path_prefix: Optional[str] = None,
    ) -> CrawlResult:
        """Crawl a website starting from a URL, following links within the same domain.

        Args:
            start_url: Starting URL to crawl
            max_pages: Maximum number of pages to crawl
            max_depth: Maximum depth to follow links
            path_prefix: Only crawl URLs that start with this path prefix

        Returns:
            CrawlResult with all scraped pages
        """
        start_url = normalize_url(start_url)
        max_pages = max_pages or self.max_pages
        max_depth = max_depth or self.max_depth

        logger.info(
            "[WEB_SCRAPER] Starting crawl with Jina: %s (max_pages=%d, max_depth=%d)",
            start_url, max_pages, max_depth
        )

        if not self.jina_api_key:
            return CrawlResult(
                pages=[ScrapedPage(
                    url=start_url,
                    title="",
                    content="",
                    success=False,
                    error="JINA_API_KEY not configured",
                )],
                total_pages=1,
                successful_pages=0,
                failed_pages=1,
                errors=["JINA_API_KEY not configured"],
            )

        pages: List[ScrapedPage] = []
        errors: List[str] = []
        visited: set[str] = set()
        to_visit: List[tuple[str, int]] = [(start_url, 0)]

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            while to_visit and len(pages) < max_pages:
                current_url, depth = to_visit.pop(0)

                if current_url in visited:
                    continue

                # Skip non-crawlable URLs
                if not is_crawlable_url(current_url):
                    logger.debug("[WEB_SCRAPER] Skipping non-crawlable URL: %s", current_url)
                    continue

                # Check path prefix if specified
                if path_prefix:
                    parsed = urlparse(current_url)
                    if not parsed.path.startswith(path_prefix):
                        continue

                visited.add(current_url)

                # Respectful delay
                if pages:
                    await asyncio.sleep(self.delay)

                # Fetch with Jina
                content, error = await self._fetch_with_jina(client, current_url)

                if error:
                    errors.append(error)
                    pages.append(ScrapedPage(
                        url=current_url,
                        title="",
                        content="",
                        success=False,
                        error=error,
                    ))
                    continue

                title = extract_title_from_content(content, current_url)
                pages.append(ScrapedPage(
                    url=current_url,
                    title=title,
                    content=content,
                    success=True,
                ))

                logger.info("[WEB_SCRAPER] Crawled %d/%d: %s (%d chars)",
                           len([p for p in pages if p.success]), max_pages,
                           current_url, len(content))

                # Find more links if we haven't reached max depth
                if depth < max_depth and len(pages) < max_pages:
                    links = self._extract_page_links(content, current_url)
                    for link in links:
                        if link not in visited and link not in [u for u, _ in to_visit]:
                            to_visit.append((link, depth + 1))

        successful = [p for p in pages if p.success]
        failed = [p for p in pages if not p.success]

        logger.info(
            "[WEB_SCRAPER] Crawl complete: %d pages (%d successful, %d failed)",
            len(pages), len(successful), len(failed)
        )

        return CrawlResult(
            pages=pages,
            total_pages=len(pages),
            successful_pages=len(successful),
            failed_pages=len(failed),
            errors=errors,
        )


# Convenience functions
async def scrape_single_url(url: str) -> ScrapedPage:
    """Scrape a single URL using Jina AI Reader."""
    scraper = WebScraper()
    return await scraper.scrape_url(url)


async def crawl_website(
    start_url: str,
    max_pages: int = 50,
    max_depth: int = 3,
    path_prefix: Optional[str] = None,
) -> CrawlResult:
    """Crawl a website using Jina AI Reader."""
    scraper = WebScraper(max_pages=max_pages, max_depth=max_depth)
    return await scraper.crawl_website(
        start_url,
        max_pages=max_pages,
        max_depth=max_depth,
        path_prefix=path_prefix,
    )
