"""GitHub MCP Server — code and repository search.

Provides code search and repository information via the GitHub API.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

GITHUB_API_URL = "https://api.github.com"


class GitHubMCP:
    """GitHub API wrapper for code and repository search."""

    def __init__(self, token: str | None = None) -> None:
        self._token = token or os.getenv("GITHUB_TOKEN", "")
        self._headers: dict[str, str] = {
            "Accept": "application/vnd.github.v3+json",
        }
        if self._token:
            self._headers["Authorization"] = f"token {self._token}"

    def get_tool_definition(self) -> dict[str, Any]:
        return {
            "name": "github_search",
            "description": "Search code and repositories on GitHub",
            "parameters": {
                "query": {"type": "string", "description": "Search query"},
                "search_type": {"type": "string", "default": "repositories", "description": "repositories or code"},
                "limit": {"type": "integer", "default": 5},
            },
        }

    def search_repositories(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        """Search GitHub repositories."""
        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(
                    f"{GITHUB_API_URL}/search/repositories",
                    headers=self._headers,
                    params={
                        "q": query,
                        "per_page": min(limit, 30),
                        "sort": "stars",
                        "order": "desc",
                    },
                )
                response.raise_for_status()
                data = response.json()

            results = []
            for repo in data.get("items", []):
                results.append({
                    "name": repo.get("full_name", ""),
                    "description": repo.get("description", ""),
                    "url": repo.get("html_url", ""),
                    "stars": repo.get("stargazers_count", 0),
                    "language": repo.get("language", ""),
                    "updated_at": repo.get("updated_at", ""),
                    "source_type": "SECONDARY",
                })
            return results

        except Exception:
            logger.warning("GitHub repository search failed", exc_info=True)
            return []

    def search_code(self, query: str, limit: int = 5) -> list[dict[str, Any]]:
        """Search GitHub code."""
        if not self._token:
            logger.warning("GitHub code search requires authentication")
            return []

        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(
                    f"{GITHUB_API_URL}/search/code",
                    headers=self._headers,
                    params={
                        "q": query,
                        "per_page": min(limit, 30),
                    },
                )
                response.raise_for_status()
                data = response.json()

            results = []
            for item in data.get("items", []):
                results.append({
                    "name": item.get("name", ""),
                    "path": item.get("path", ""),
                    "repository": item.get("repository", {}).get("full_name", ""),
                    "url": item.get("html_url", ""),
                    "source_type": "SECONDARY",
                })
            return results

        except Exception:
            logger.warning("GitHub code search failed", exc_info=True)
            return []

    @property
    def available(self) -> bool:
        return bool(self._token)
