"""Researcher Agent — external information gathering with PII anonymization.

Gathers external information via MCP tool servers, anonymizes queries to protect
user privacy, and deposits verified findings to the Truth Layer.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import openai

from memora.core.json_utils import extract_json
from memora.core.retry import async_call_with_retry
from memora.core.truth_layer import FactLifecycle, TruthLayer

logger = logging.getLogger(__name__)

from memora.config import DEFAULT_LLM_MODEL

DEFAULT_MODEL = DEFAULT_LLM_MODEL

# PII patterns for anonymization
_EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b")
_PHONE_PATTERN = re.compile(r"\b(?:\+?1[-.\s]?)?(?:\(?\d{3}\)?[-.\s]?)?\d{3}[-.\s]?\d{4}\b")
_SSN_PATTERN = re.compile(r"\b\d{3}-\d{2}-\d{4}\b")
_DOLLAR_PATTERN = re.compile(r"\$[\d,]+(?:\.\d{2})?(?:\s*(?:k|K|million|billion|M|B))?")
_DATE_PATTERN = re.compile(
    r"\b(?:\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{2,4}|"
    r"(?:January|February|March|April|May|June|July|August|September|October|November|December)"
    r"\s+\d{1,2},?\s+\d{4})\b",
    re.IGNORECASE,
)


@dataclass
class ResearchSource:
    """A single source from external research."""

    url: str = ""
    title: str = ""
    snippet: str = ""
    source_type: str = "SECONDARY"  # PRIMARY or SECONDARY
    reliability_score: float = 0.5


@dataclass
class ResearchResult:
    """Result from the Researcher agent."""

    answer: str = ""
    sources: list[ResearchSource] = field(default_factory=list)
    facts_to_deposit: list[dict[str, Any]] = field(default_factory=list)
    confidence: float = 0.7
    anonymized_query: str = ""
    token_usage: dict[str, int] = field(default_factory=dict)


class ResearcherAgent:
    """External information gathering agent with PII anonymization and MCP tools."""

    def __init__(
        self,
        api_key: str,
        truth_layer: TruthLayer | None = None,
        model: str = DEFAULT_MODEL,
        mcp_tools: dict[str, Any] | None = None,
    ) -> None:
        self._client = openai.AsyncOpenAI(api_key=api_key)
        self._model = model
        self._truth_layer = truth_layer
        self._system_prompt = self._load_system_prompt()
        # MCP tool servers keyed by name
        self._mcp_tools = mcp_tools or {}
        self._init_default_tools()

    def _init_default_tools(self) -> None:
        """Lazily initialize default MCP tools from environment variables."""
        # Google and Brave search disabled for now
        # if "google_search" not in self._mcp_tools:
        #     try:
        #         from memora.mcp.google_search import GoogleSearchMCP
        #         self._mcp_tools["google_search"] = GoogleSearchMCP()
        #     except Exception:
        #         logger.debug("Google Search MCP not available")

        # if "brave_search" not in self._mcp_tools:
        #     try:
        #         from memora.mcp.brave_search import BraveSearchMCP
        #         self._mcp_tools["brave_search"] = BraveSearchMCP()
        #     except Exception:
        #         logger.debug("Brave Search MCP not available")

        if "semantic_scholar" not in self._mcp_tools:
            try:
                from memora.mcp.semantic_scholar import SemanticScholarMCP
                self._mcp_tools["semantic_scholar"] = SemanticScholarMCP()
            except Exception:
                logger.debug("Semantic Scholar MCP not available")

        if "playwright_scraper" not in self._mcp_tools:
            try:
                from memora.mcp.playwright_scraper import PlaywrightScraperMCP
                self._mcp_tools["playwright_scraper"] = PlaywrightScraperMCP()
            except Exception:
                logger.debug("Playwright Scraper MCP not available")

        if "github" not in self._mcp_tools:
            try:
                from memora.mcp.github_mcp import GitHubMCP
                self._mcp_tools["github"] = GitHubMCP()
            except Exception:
                logger.debug("GitHub MCP not available")

    def _load_system_prompt(self) -> str:
        """Load the researcher system prompt from the prompts directory."""
        prompt_path = Path(__file__).parent / "prompts" / "researcher_system.md"
        return prompt_path.read_text(encoding="utf-8")

    async def research(
        self, query: str, graph_context: dict[str, Any] | None = None
    ) -> ResearchResult:
        """Run external research on a query using MCP tools.

        1. Anonymize the query (strip PII).
        2. Execute search tools to gather external data.
        3. Send results to LLM for synthesis.
        4. Deposit verified facts to Truth Layer.
        """
        anonymized = self._anonymize_query(query, graph_context)

        # Execute MCP tool searches with anonymized query
        tool_results = self._execute_tool_searches(anonymized)

        if not tool_results:
            return ResearchResult(
                answer="No external search results available for this query. "
                       "This may be better answered using internal graph data.",
                confidence=0.0,
                anonymized_query=anonymized,
            )

        context_text = ""
        if graph_context:
            context_text = f"\n\nGraph context (anonymized):\n{json.dumps(self._anonymize_context(graph_context), indent=2, default=str)}"

        tool_results_text = ""
        if tool_results:
            tool_results_text = f"\n\nExternal search results:\n{json.dumps(tool_results, indent=2, default=str)}"

        try:
            response = await async_call_with_retry(
                self._client.responses.create,
                model=self._model,
                instructions=self._system_prompt,
                input=(
                    f"Research the following query. I've already gathered search "
                    f"results from external tools — synthesize them into a clear "
                    f"answer with source citations and identify facts to deposit. "
                    f"Respond with a JSON object containing answer, sources, facts_to_deposit, and confidence.\n\n"
                    f"Original query: {query}\n"
                    f"Anonymized search query: {anonymized}"
                    f"{context_text}"
                    f"{tool_results_text}"
                ),
                text={"format": {"type": "json_object"}},
                max_output_tokens=4096,
            )
        except openai.APIError as e:
            logger.error("OpenAI API error in Researcher: %s", e)
            return ResearchResult(
                answer=f"Research failed: {e}",
                anonymized_query=anonymized,
            )

        raw_text = response.output_text
        token_usage = self._extract_token_usage(response)

        result = self._parse_research_response(raw_text)
        result.anonymized_query = anonymized
        result.token_usage = token_usage

        # Add sources from tool results if not already parsed from LLM response
        if not result.sources and tool_results:
            for tr in tool_results:
                for item in tr.get("results", []):
                    result.sources.append(ResearchSource(
                        url=item.get("url", ""),
                        title=item.get("title", ""),
                        snippet=item.get("snippet", ""),
                        source_type=item.get("source_type", "SECONDARY"),
                        reliability_score=item.get("reliability_score", 0.5),
                    ))

        # Deposit facts to Truth Layer if available
        if self._truth_layer and result.facts_to_deposit:
            self._deposit_facts(result)

        return result

    def _execute_tool_searches(self, anonymized_query: str) -> list[dict[str, Any]]:
        """Execute MCP tool searches and collect results.

        Tries Google first, falls back to Brave, also queries academic
        sources if the query looks academic.
        """
        results = []

        # Web search — try Google first, fall back to Brave
        web_results = self._search_web(anonymized_query)
        if web_results:
            results.append({"tool": "web_search", "results": web_results})

        # Academic search for research-like queries
        academic_signals = ["paper", "study", "research", "journal", "academic",
                           "published", "theory", "hypothesis", "evidence"]
        if any(sig in anonymized_query.lower() for sig in academic_signals):
            academic_results = self._search_academic(anonymized_query)
            if academic_results:
                results.append({"tool": "semantic_scholar", "results": academic_results})

        # GitHub search for code/tech queries
        tech_signals = ["code", "library", "framework", "api", "github",
                        "open source", "repository", "implementation"]
        if any(sig in anonymized_query.lower() for sig in tech_signals):
            github_results = self._search_github(anonymized_query)
            if github_results:
                results.append({"tool": "github", "results": github_results})

        return results

    def _search_web(self, query: str) -> list[dict[str, Any]]:
        """Search the web via Google or Brave fallback."""
        # Try Google first
        google = self._mcp_tools.get("google_search")
        if google:
            try:
                results = google.search(query, num_results=5)
                if results:
                    return results
            except Exception:
                logger.debug("Google search failed, trying Brave fallback")

        # Fall back to Brave
        brave = self._mcp_tools.get("brave_search")
        if brave:
            try:
                return brave.search(query, num_results=5)
            except Exception:
                logger.debug("Brave search also failed")

        return []

    def _search_academic(self, query: str) -> list[dict[str, Any]]:
        """Search academic papers via Semantic Scholar."""
        scholar = self._mcp_tools.get("semantic_scholar")
        if not scholar:
            return []
        try:
            papers = scholar.search_papers(query, limit=5)
            return [
                {
                    "title": p.get("title", ""),
                    "url": p.get("url", ""),
                    "snippet": p.get("abstract", "")[:300],
                    "source_type": "PRIMARY",
                    "reliability_score": 0.90,
                    "year": p.get("year"),
                    "citation_count": p.get("citation_count", 0),
                }
                for p in papers
            ]
        except Exception:
            logger.debug("Semantic Scholar search failed")
            return []

    def _search_github(self, query: str) -> list[dict[str, Any]]:
        """Search GitHub repositories."""
        github = self._mcp_tools.get("github")
        if not github:
            return []
        try:
            repos = github.search_repositories(query, limit=5)
            return [
                {
                    "title": r.get("name", ""),
                    "url": r.get("url", ""),
                    "snippet": r.get("description", ""),
                    "source_type": "SECONDARY",
                    "reliability_score": 0.6,
                }
                for r in repos
            ]
        except Exception:
            logger.debug("GitHub search failed")
            return []

    def _anonymize_query(
        self, query: str, graph_context: dict[str, Any] | None = None
    ) -> str:
        """Strip PII from the query before external searches."""
        text = query

        # Remove emails
        text = _EMAIL_PATTERN.sub("[email]", text)

        # Remove phone numbers
        text = _PHONE_PATTERN.sub("[phone]", text)

        # Remove SSNs
        text = _SSN_PATTERN.sub("[id-number]", text)

        # Replace dollar amounts with generic terms
        text = _DOLLAR_PATTERN.sub("a sum of money", text)

        # Replace specific dates with generic terms
        text = _DATE_PATTERN.sub("recently", text)

        # Replace names found in graph context
        if graph_context:
            names = self._extract_names_from_context(graph_context)
            for name in names:
                if len(name) > 2:  # Avoid replacing very short strings
                    text = text.replace(name, "someone")

        # Clean up multiple spaces
        text = re.sub(r"\s+", " ", text).strip()

        # Remove placeholders for cleaner queries
        text = text.replace("[email]", "").replace("[phone]", "").replace("[id-number]", "")
        text = re.sub(r"\s+", " ", text).strip()

        return text

    def _extract_names_from_context(self, context: dict[str, Any]) -> list[str]:
        """Extract person names from graph context for anonymization."""
        names = []
        for node in context.get("nodes", []):
            if node.get("node_type") == "PERSON":
                name = node.get("content", "") or node.get("title", "")
                if name:
                    names.append(name)
                    # Also add individual parts of multi-word names
                    parts = name.split()
                    names.extend(p for p in parts if len(p) > 2)
        # Sort by length descending to replace longer names first
        return sorted(set(names), key=len, reverse=True)

    def _anonymize_context(self, context: dict[str, Any]) -> dict[str, Any]:
        """Create an anonymized version of graph context for the prompt."""
        anon = {}
        if "nodes" in context:
            anon_nodes = []
            for node in context["nodes"]:
                anon_node = {
                    "node_type": node.get("node_type"),
                    "networks": node.get("networks", []),
                }
                # Include content only for non-person nodes
                if node.get("node_type") != "PERSON":
                    anon_node["content_summary"] = (
                        node.get("content", "")[:100] if node.get("content") else ""
                    )
                anon_nodes.append(anon_node)
            anon["nodes"] = anon_nodes

        if "stats" in context:
            anon["stats"] = context["stats"]

        return anon

    def _deposit_facts(self, result: ResearchResult) -> None:
        """Deposit research findings as verified facts in the Truth Layer."""
        if not self._truth_layer:
            return

        for fact_data in result.facts_to_deposit:
            try:
                lifecycle = FactLifecycle.DYNAMIC
                if fact_data.get("lifecycle") == "STATIC":
                    lifecycle = FactLifecycle.STATIC

                # Use source URL as node_id for traceability
                node_id = fact_data.get("source_url", "research") or "research"

                self._truth_layer.deposit_fact(
                    node_id=node_id,
                    statement=fact_data["statement"],
                    confidence=fact_data.get("confidence", 0.7),
                    lifecycle=lifecycle,
                    verified_by="researcher",
                    recheck_interval_days=fact_data.get("recheck_interval_days", 90),
                    metadata={"source_url": fact_data.get("source_url", "")},
                )
                logger.info("Deposited research fact: %s", fact_data["statement"][:80])
            except Exception:
                logger.warning("Failed to deposit fact", exc_info=True)

    def _parse_research_response(self, raw_text: str) -> ResearchResult:
        """Parse the LLM research response into a ResearchResult."""
        try:
            data = self._extract_json(raw_text)
            sources = []
            for s in data.get("sources", []):
                sources.append(ResearchSource(
                    url=s.get("url", ""),
                    title=s.get("title", ""),
                    snippet=s.get("snippet", ""),
                    source_type=s.get("source_type", "SECONDARY"),
                    reliability_score=s.get("reliability_score", 0.5),
                ))

            return ResearchResult(
                answer=data.get("answer", raw_text),
                sources=sources,
                facts_to_deposit=data.get("facts_to_deposit", []),
                confidence=data.get("confidence", 0.7),
            )
        except ValueError:
            return ResearchResult(answer=raw_text)

    def _extract_json(self, text: str) -> dict[str, Any]:
        """Extract JSON object from LLM response."""
        return extract_json(text)

    def _extract_token_usage(self, response: Any) -> dict[str, int]:
        """Extract token usage from API response."""
        return {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        }
