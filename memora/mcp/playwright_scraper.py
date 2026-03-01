"""Playwright Scraper MCP Server — full web page content extraction.

Uses httpx for lightweight scraping (Playwright is optional for JS-heavy sites).
"""

from __future__ import annotations

import logging
import re
from typing import Any

import httpx

from memora.core.retry import retry_on_transient

logger = logging.getLogger(__name__)


class PlaywrightScraperMCP:
    """Web scraping tool for deep research content extraction."""

    def __init__(self, timeout: float = 15.0) -> None:
        self._timeout = timeout

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "web_scrape",
            "description": "Scrape full page content from a URL for deep research",
            "parameters": {
                "url": {"type": "string", "description": "URL to scrape"},
                "extract_text_only": {"type": "boolean", "default": True},
            },
        }

    def scrape(self, url: str, extract_text_only: bool = True) -> dict[str, Any]:
        """Scrape content from a URL."""
        try:
            response = self._execute_request(url)

            html = response.text

            if extract_text_only:
                content = self._html_to_text(html)
            else:
                content = html

            title = self._extract_title(html)

            return {
                "success": True,
                "url": str(response.url),
                "title": title,
                "content": content[:10000],  # Limit content size
                "content_length": len(content),
            }

        except Exception as e:
            logger.warning("Scraping failed for %s: %s", url, e)
            return {
                "success": False,
                "url": url,
                "error": str(e),
            }

    @retry_on_transient(max_retries=2, base_delay=1.0, max_delay=10.0)
    def _execute_request(self, url: str) -> httpx.Response:
        """Execute the HTTP request with retry."""
        with httpx.Client(
            timeout=self._timeout,
            follow_redirects=True,
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; MemoraBot/1.0)",
            },
        ) as client:
            response = client.get(url)
            response.raise_for_status()
            return response

    def _html_to_text(self, html: str) -> str:
        """Basic HTML to text conversion."""
        # Remove script and style elements
        text = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL | re.IGNORECASE)

        # Remove HTML tags
        text = re.sub(r"<[^>]+>", " ", text)

        # Decode common entities
        text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
        text = text.replace("&quot;", '"').replace("&nbsp;", " ")

        # Collapse whitespace
        text = re.sub(r"\s+", " ", text).strip()

        return text

    def _extract_title(self, html: str) -> str:
        """Extract the page title from HTML."""
        match = re.search(r"<title[^>]*>(.*?)</title>", html, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1).strip()
        return ""
