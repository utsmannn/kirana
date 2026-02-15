"""Web scraper service for extracting content from websites."""

import asyncio
import logging
import re
import time
from dataclasses import dataclass
from typing import List, Optional
from urllib.parse import urljoin, urlparse

import httpx
import trafilatura

logger = logging.getLogger(__name__)


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


class WebScraper:
    """Web scraper with support for single URL and recursive crawling."""

    def __init__(
        self,
        timeout: float = 30.0,
        delay: float = 1.0,
        max_pages: int = 50,
        max_depth: int = 3,
        user_agent: str = "KiranaBot/1.0 (Knowledge Crawler)",
    ):
        self.timeout = timeout
        self.delay = delay  # Delay between requests (respectful crawling)
        self.max_pages = max_pages
        self.max_depth = max_depth
        self.user_agent = user_agent
        self.headers = {
            "User-Agent": user_agent,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.5",
        }

    def _is_same_domain(self, base_url: str, target_url: str) -> bool:
        """Check if target URL is from the same domain as base URL."""
        base_parsed = urlparse(base_url)
        target_parsed = urlparse(target_url)
        return base_parsed.netloc == target_parsed.netloc

    def _normalize_url(self, base_url: str, href: str) -> Optional[str]:
        """Normalize a URL relative to base URL."""
        if not href:
            return None

        # Skip anchors, javascript, mailto, etc.
        if href.startswith(('#', 'javascript:', 'mailto:', 'tel:', 'data:')):
            return None

        # Make absolute URL
        full_url = urljoin(base_url, href)

        # Parse and clean
        parsed = urlparse(full_url)

        # Only allow http/https
        if parsed.scheme not in ('http', 'https'):
            return None

        # Remove fragment
        clean_url = f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
        if parsed.query:
            clean_url += f"?{parsed.query}"

        return clean_url

    def _extract_links(self, html_content: str, base_url: str) -> List[str]:
        """Extract all links from HTML content."""
        links = []

        # Simple regex to find href attributes (works well enough for most cases)
        href_pattern = re.compile(r'href=["\']([^"\']+)["\']', re.IGNORECASE)
        matches = href_pattern.findall(html_content)

        for href in matches:
            url = self._normalize_url(base_url, href)
            if url and self._is_same_domain(base_url, url):
                links.append(url)

        return list(set(links))  # Remove duplicates

    async def _fetch_page(self, client: httpx.AsyncClient, url: str) -> tuple[Optional[str], Optional[str]]:
        """Fetch a page and return (html_content, error)."""
        try:
            response = await client.get(url, follow_redirects=True)
            response.raise_for_status()
            return response.text, None
        except httpx.TimeoutException:
            return None, f"Timeout fetching {url}"
        except httpx.HTTPStatusError as e:
            return None, f"HTTP error {e.response.status_code} for {url}"
        except Exception as e:
            return None, f"Error fetching {url}: {str(e)}"

    def _extract_content(self, html_content: str, url: str) -> tuple[str, str]:
        """Extract title and main content from HTML using trafilatura."""
        # Extract content with trafilatura
        extracted = trafilatura.extract(
            html_content,
            include_comments=False,
            include_tables=True,
            no_fallback=False,
            output_format='txt',
            url=url,
        )

        # Extract title
        metadata = trafilatura.baseline(html_content)
        title = ""
        if metadata and 'title' in metadata:
            title = metadata['title'] or ""

        # Fallback: try to get title from HTML
        if not title:
            title_match = re.search(r'<title[^>]*>([^<]+)</title>', html_content, re.IGNORECASE)
            if title_match:
                title = title_match.group(1).strip()

        if not title:
            # Use URL path as title
            parsed = urlparse(url)
            title = parsed.path.strip('/').replace('/', ' - ') or parsed.netloc

        content = extracted or ""

        return title, content

    async def scrape_url(self, url: str) -> ScrapedPage:
        """Scrape a single URL and extract content."""
        logger.info("[WEB_SCRAPER] Scraping URL: %s", url)

        async with httpx.AsyncClient(
            timeout=self.timeout,
            headers=self.headers,
            follow_redirects=True,
        ) as client:
            html_content, error = await self._fetch_page(client, url)

            if error:
                logger.warning("[WEB_SCRAPER] Failed to fetch %s: %s", url, error)
                return ScrapedPage(
                    url=url,
                    title="",
                    content="",
                    success=False,
                    error=error,
                )

            title, content = self._extract_content(html_content, url)

            if not content.strip():
                logger.warning("[WEB_SCRAPER] No content extracted from %s", url)
                return ScrapedPage(
                    url=url,
                    title=title,
                    content="",
                    success=False,
                    error="No content could be extracted",
                )

            logger.info("[WEB_SCRAPER] Successfully scraped %s: %d chars", url, len(content))
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
            max_pages: Maximum number of pages to crawl (default from constructor)
            max_depth: Maximum depth to follow links (default from constructor)
            path_prefix: Only crawl URLs that start with this path prefix (e.g., "/blog/")

        Returns:
            CrawlResult with all scraped pages
        """
        max_pages = max_pages or self.max_pages
        max_depth = max_depth or self.max_depth

        logger.info(
            "[WEB_SCRAPER] Starting crawl: %s (max_pages=%d, max_depth=%d)",
            start_url, max_pages, max_depth
        )

        pages: List[ScrapedPage] = []
        errors: List[str] = []
        visited: set[str] = set()
        to_visit: List[tuple[str, int]] = [(start_url, 0)]  # (url, depth)

        async with httpx.AsyncClient(
            timeout=self.timeout,
            headers=self.headers,
            follow_redirects=True,
        ) as client:
            while to_visit and len(pages) < max_pages:
                current_url, depth = to_visit.pop(0)

                # Skip if already visited
                if current_url in visited:
                    continue

                # Check path prefix if specified
                if path_prefix:
                    parsed = urlparse(current_url)
                    if not parsed.path.startswith(path_prefix):
                        logger.debug("[WEB_SCRAPER] Skipping %s (path prefix mismatch)", current_url)
                        continue

                visited.add(current_url)

                # Respectful delay
                if pages:  # Don't delay on first request
                    await asyncio.sleep(self.delay)

                # Fetch page
                html_content, error = await self._fetch_page(client, current_url)

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

                # Extract content
                title, content = self._extract_content(html_content, current_url)

                if content.strip():
                    pages.append(ScrapedPage(
                        url=current_url,
                        title=title,
                        content=content,
                        success=True,
                    ))
                    logger.info("[WEB_SCRAPER] Scraped %d/%d: %s (%d chars)",
                               len([p for p in pages if p.success]), max_pages,
                               current_url, len(content))
                else:
                    pages.append(ScrapedPage(
                        url=current_url,
                        title=title,
                        content="",
                        success=False,
                        error="No content extracted",
                    ))

                # Find more links if we haven't reached max depth
                if depth < max_depth and len(pages) < max_pages:
                    links = self._extract_links(html_content, current_url)
                    for link in links:
                        if link not in visited and link not in [u for u, _ in to_visit]:
                            to_visit.append((link, depth + 1))

        successful = [p for p in pages if p.success]
        failed = [p for p in pages if not p.success]

        logger.info(
            "[WEB_SCRAPER] Crawl complete: %d pages scraped (%d successful, %d failed)",
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
    """Scrape a single URL."""
    scraper = WebScraper()
    return await scraper.scrape_url(url)


async def crawl_website(
    start_url: str,
    max_pages: int = 50,
    max_depth: int = 3,
    path_prefix: Optional[str] = None,
) -> CrawlResult:
    """Crawl a website."""
    scraper = WebScraper(max_pages=max_pages, max_depth=max_depth)
    return await scraper.crawl_website(
        start_url,
        max_pages=max_pages,
        max_depth=max_depth,
        path_prefix=path_prefix,
    )
