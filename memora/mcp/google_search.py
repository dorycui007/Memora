"""Google Search MCP Server wrapper.

Provides web search capabilities via Google Custom Search API.
Rate limited to 100 queries/day on free tier.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from memora.core.retry import retry_on_transient

logger = logging.getLogger(__name__)

GOOGLE_SEARCH_URL = "https://www.googleapis.com/customsearch/v1"


class GoogleSearchMCP:
    """Google Custom Search API wrapper as MCP tool."""

    def __init__(
        self,
        api_key: str | None = None,
        search_engine_id: str | None = None,
    ) -> None:
        self._api_key = api_key or os.getenv("GOOGLE_API_KEY", "")
        self._search_engine_id = search_engine_id or os.getenv("GOOGLE_CSE_ID", "")
        self._daily_count = 0
        self._daily_limit = 100

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "google_search",
            "description": "Search the web using Google. Limited to 100 queries/day.",
            "parameters": {
                "query": {"type": "string", "description": "Search query"},
                "num_results": {"type": "integer", "default": 5},
            },
        }

    def search(self, query: str, num_results: int = 5) -> list[dict[str, Any]]:
        """Execute a Google search."""
        if not self._api_key or not self._search_engine_id:
            logger.warning("Google Search not configured (missing API key or CSE ID)")
            return []

        if self._daily_count >= self._daily_limit:
            logger.warning("Google Search daily limit reached (%d)", self._daily_limit)
            return []

        try:
            data = self._execute_request(query, num_results)
            self._daily_count += 1

            results = []
            for item in data.get("items", []):
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("link", ""),
                    "snippet": item.get("snippet", ""),
                    "source_type": "SECONDARY",
                })
            return results

        except Exception:
            logger.warning("Google search failed", exc_info=True)
            return []

    @retry_on_transient(max_retries=2, base_delay=1.0, max_delay=10.0)
    def _execute_request(self, query: str, num_results: int) -> dict[str, Any]:
        """Execute the HTTP request with retry on transient errors."""
        with httpx.Client(timeout=10.0) as client:
            response = client.get(
                GOOGLE_SEARCH_URL,
                params={
                    "key": self._api_key,
                    "cx": self._search_engine_id,
                    "q": query,
                    "num": min(num_results, 10),
                },
            )
            response.raise_for_status()
            return response.json()

    @property
    def available(self) -> bool:
        return bool(self._api_key and self._search_engine_id)

    @property
    def remaining_quota(self) -> int:
        return max(0, self._daily_limit - self._daily_count)
