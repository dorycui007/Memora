"""Semantic Scholar MCP Server — academic paper search and citation analysis.

Provides access to academic research papers via the Semantic Scholar API.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from memora.core.retry import retry_on_transient

logger = logging.getLogger(__name__)

SEMANTIC_SCHOLAR_URL = "https://api.semanticscholar.org/graph/v1"


class SemanticScholarMCP:
    """Semantic Scholar API wrapper for academic research."""

    def __init__(self, api_key: str | None = None) -> None:
        self._api_key = api_key  # Optional — rate limits are more generous with key
        self._headers: dict[str, str] = {}
        if api_key:
            self._headers["x-api-key"] = api_key

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "semantic_scholar_search",
            "description": "Search academic papers on Semantic Scholar",
            "parameters": {
                "query": {"type": "string", "description": "Search query for papers"},
                "limit": {"type": "integer", "default": 5},
                "fields": {"type": "string", "default": "title,abstract,year,citationCount,url"},
            },
        }

    def search_papers(
        self,
        query: str,
        limit: int = 5,
        fields: str = "title,abstract,year,citationCount,url",
    ) -> list[dict[str, Any]]:
        """Search for academic papers."""
        try:
            data = self._execute_search(query, limit, fields)

            results = []
            for paper in data.get("data", []):
                results.append({
                    "title": paper.get("title", ""),
                    "abstract": (paper.get("abstract") or "")[:500],
                    "year": paper.get("year"),
                    "citation_count": paper.get("citationCount", 0),
                    "url": paper.get("url", ""),
                    "source_type": "PRIMARY",
                    "reliability_score": 0.90,
                })
            return results

        except Exception:
            logger.warning("Semantic Scholar search failed", exc_info=True)
            return []

    def get_paper(self, paper_id: str) -> dict[str, Any] | None:
        """Get detailed information about a specific paper."""
        try:
            return self._execute_get_paper(paper_id)
        except Exception:
            logger.warning("Failed to get paper %s", paper_id, exc_info=True)
            return None

    @retry_on_transient(max_retries=2, base_delay=1.0, max_delay=10.0)
    def _execute_search(self, query: str, limit: int, fields: str) -> dict[str, Any]:
        """Execute the search HTTP request with retry."""
        with httpx.Client(timeout=10.0) as client:
            response = client.get(
                f"{SEMANTIC_SCHOLAR_URL}/paper/search",
                headers=self._headers,
                params={
                    "query": query,
                    "limit": min(limit, 100),
                    "fields": fields,
                },
            )
            response.raise_for_status()
            return response.json()

    @retry_on_transient(max_retries=2, base_delay=1.0, max_delay=10.0)
    def _execute_get_paper(self, paper_id: str) -> dict[str, Any]:
        """Execute the get paper HTTP request with retry."""
        with httpx.Client(timeout=10.0) as client:
            response = client.get(
                f"{SEMANTIC_SCHOLAR_URL}/paper/{paper_id}",
                headers=self._headers,
                params={
                    "fields": "title,abstract,year,authors,citationCount,referenceCount,url,venue",
                },
            )
            response.raise_for_status()
            return response.json()
