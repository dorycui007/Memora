"""Brave Search MCP Server wrapper.

Provides privacy-focused web search as fallback when Google quota is exhausted.
Rate limited to 2,000 queries/month on free tier.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

from memora.core.retry import retry_on_transient

logger = logging.getLogger(__name__)

BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"


class BraveSearchMCP:
    """Brave Search API wrapper as MCP tool."""

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key or os.getenv("BRAVE_API_KEY", "")
        self._monthly_count = 0
        self._monthly_limit = 2000

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "brave_search",
            "description": "Privacy-focused web search via Brave. 2,000 queries/month.",
            "parameters": {
                "query": {"type": "string", "description": "Search query"},
                "num_results": {"type": "integer", "default": 5},
            },
        }

    def search(self, query: str, num_results: int = 5) -> list[dict[str, Any]]:
        """Execute a Brave search."""
        if not self._api_key:
            logger.warning("Brave Search not configured (missing API key)")
            return []

        if self._monthly_count >= self._monthly_limit:
            logger.warning("Brave Search monthly limit reached")
            return []

        try:
            data = self._execute_request(query, num_results)
            self._monthly_count += 1

            results = []
            for item in data.get("web", {}).get("results", []):
                results.append({
                    "title": item.get("title", ""),
                    "url": item.get("url", ""),
                    "snippet": item.get("description", ""),
                    "source_type": "SECONDARY",
                })
            return results

        except Exception:
            logger.warning("Brave search failed", exc_info=True)
            return []

    @retry_on_transient(max_retries=2, base_delay=1.0, max_delay=10.0)
    def _execute_request(self, query: str, num_results: int) -> dict[str, Any]:
        """Execute the HTTP request with retry on transient errors."""
        with httpx.Client(timeout=10.0) as client:
            response = client.get(
                BRAVE_SEARCH_URL,
                headers={
                    "Accept": "application/json",
                    "X-Subscription-Token": self._api_key,
                },
                params={
                    "q": query,
                    "count": min(num_results, 20),
                },
            )
            response.raise_for_status()
            return response.json()

    @property
    def available(self) -> bool:
        return bool(self._api_key)

    @property
    def remaining_quota(self) -> int:
        return max(0, self._monthly_limit - self._monthly_count)
