"""Strategist Agent — analytical advisor for cross-network insights and decision support.

Interprets graph data, identifies patterns, assesses network health, discovers
cross-network insights, and provides actionable recommendations.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import openai

from memora.core.retry import async_call_with_retry
from memora.graph.models import NetworkType, NodeFilter, NodeType
from memora.graph.repository import GraphRepository

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gpt-5-nano"


@dataclass
class StrategistResult:
    """Result from a Strategist analysis."""

    analysis: str = ""
    recommendations: list[dict[str, Any]] = field(default_factory=list)
    confidence: float = 0.8
    citations: list[str] = field(default_factory=list)
    token_usage: dict[str, int] = field(default_factory=dict)


@dataclass
class BriefingSection:
    """A section of the daily briefing."""

    title: str = ""
    items: list[str] = field(default_factory=list)
    priority: str = "medium"


@dataclass
class DailyBriefing:
    """Complete daily briefing."""

    sections: list[BriefingSection] = field(default_factory=list)
    summary: str = ""
    generated_at: datetime = field(default_factory=datetime.utcnow)


class StrategistAgent:
    """Analytical advisor that interprets graph data and provides strategic insights."""

    def __init__(
        self,
        api_key: str,
        repo: GraphRepository | None = None,
        vector_store: Any | None = None,
        embedding_engine: Any | None = None,
        truth_layer: Any | None = None,
        model: str = DEFAULT_MODEL,
    ) -> None:
        self._client = openai.AsyncOpenAI(api_key=api_key)
        self._model = model
        self._repo = repo
        self._vector_store = vector_store
        self._embedding_engine = embedding_engine
        self._truth_layer = truth_layer
        self._system_prompt = self._load_system_prompt()

    def _load_system_prompt(self) -> str:
        """Load the strategist system prompt from the prompts directory."""
        prompt_path = Path(__file__).parent / "prompts" / "strategist_system.md"
        return prompt_path.read_text(encoding="utf-8")

    async def analyze(self, query: str, graph_context: dict[str, Any] | None = None) -> StrategistResult:
        """Run strategic analysis on a query with graph context.

        Args:
            query: The user's analysis question.
            graph_context: Pre-gathered graph context (nodes, edges, health, etc.).

        Returns:
            StrategistResult with analysis and recommendations.
        """
        if graph_context is None:
            graph_context = self._build_graph_context(query)

        context_text = self._format_context(graph_context)

        try:
            response = await async_call_with_retry(
                self._client.responses.create,
                model=self._model,
                instructions=self._system_prompt,
                input=(
                    f"Analyze the following query using the provided graph context. "
                    f"Respond with a JSON object containing analysis, recommendations, confidence, and citations.\n\n"
                    f"Query: {query}\n\n"
                    f"Graph Context:\n{context_text}"
                ),
                text={"format": {"type": "json_object"}},
                max_output_tokens=4096,
            )
        except openai.APIError as e:
            logger.error("OpenAI API error in Strategist: %s", e)
            return StrategistResult(analysis=f"Analysis failed: {e}")

        raw_text = response.output_text
        token_usage = self._extract_token_usage(response)

        return self._parse_analysis_response(raw_text, token_usage)

    async def generate_briefing(
        self,
        health_scores: list[dict[str, Any]] | None = None,
        alerts: list[dict[str, Any]] | None = None,
        bridges: list[dict[str, Any]] | None = None,
        commitments: dict[str, Any] | None = None,
        review_items: list[dict[str, Any]] | None = None,
    ) -> DailyBriefing:
        """Generate the daily briefing from all background job results."""
        briefing_input = self._format_briefing_input(
            health_scores or [],
            alerts or [],
            bridges or [],
            commitments or {},
            review_items or [],
        )

        try:
            response = await async_call_with_retry(
                self._client.responses.create,
                model=self._model,
                instructions=self._system_prompt,
                input=(
                    f"Generate today's daily briefing using this data. "
                    f"Respond with a JSON object matching the Daily Briefing schema.\n\n"
                    f"{briefing_input}"
                ),
                text={"format": {"type": "json_object"}},
                max_output_tokens=4096,
            )
        except openai.APIError as e:
            logger.error("OpenAI API error generating briefing: %s", e)
            return DailyBriefing(
                summary=f"Briefing generation failed: {e}",
            )

        raw_text = response.output_text
        return self._parse_briefing_response(raw_text)

    async def critique(self, statement: str, graph_context: dict[str, Any] | None = None) -> StrategistResult:
        """Invoke critic mode: challenge a statement using graph evidence.

        Args:
            statement: The statement or decision to critique.
            graph_context: Pre-gathered graph context.

        Returns:
            StrategistResult with critique analysis.
        """
        if graph_context is None:
            graph_context = self._build_graph_context(statement)

        context_text = self._format_context(graph_context)

        try:
            response = await async_call_with_retry(
                self._client.responses.create,
                model=self._model,
                instructions=self._system_prompt,
                input=(
                    f"CRITIC MODE: Challenge the following statement/decision "
                    f"using graph evidence. Identify counter-evidence, blind spots, "
                    f"and overlooked risks. Respond with a JSON object containing analysis, "
                    f"recommendations, confidence, and citations.\n\n"
                    f"Statement: {statement}\n\n"
                    f"Graph Context:\n{context_text}"
                ),
                text={"format": {"type": "json_object"}},
                max_output_tokens=4096,
            )
        except openai.APIError as e:
            logger.error("OpenAI API error in Strategist critique: %s", e)
            return StrategistResult(analysis=f"Critique failed: {e}")

        raw_text = response.output_text
        token_usage = self._extract_token_usage(response)

        return self._parse_analysis_response(raw_text, token_usage)

    def _build_graph_context(self, query: str) -> dict[str, Any]:
        """Gather graph context relevant to the query."""
        context: dict[str, Any] = {
            "nodes": [],
            "health": [],
            "bridges": [],
            "facts": [],
            "stats": {},
        }

        if not self._repo:
            return context

        # Get graph stats
        try:
            context["stats"] = self._repo.get_graph_stats()
        except Exception:
            logger.warning("Failed to get graph stats", exc_info=True)

        # Search for relevant nodes via vector similarity
        if self._vector_store and self._embedding_engine:
            try:
                embedding = self._embedding_engine.embed_text(query)
                results = self._vector_store.dense_search(
                    embedding["dense"], top_k=15
                )
                context["nodes"] = [r.to_dict() for r in results]
            except Exception:
                logger.warning("Vector search failed in strategist context", exc_info=True)

        # Get network health
        try:
            context["health"] = self._repo.get_latest_health_scores()
        except Exception:
            logger.debug("No network health data available")

        # Get recent bridges
        try:
            context["bridges"] = self._repo.get_recent_bridges(limit=10)
        except Exception:
            logger.debug("No bridge data available")

        # Get relevant facts from truth layer
        if self._truth_layer:
            try:
                context["facts"] = self._truth_layer.query_facts(
                    status="active", limit=20
                )
            except Exception:
                logger.debug("No truth layer facts available")

        return context

    def _format_context(self, context: dict[str, Any]) -> str:
        """Format graph context for injection into the prompt."""
        parts = []

        if context.get("stats"):
            parts.append(f"Graph Stats: {json.dumps(context['stats'])}")

        if context.get("nodes"):
            node_lines = []
            for node in context["nodes"]:
                node_lines.append(
                    f"  - [{node.get('node_type', '?')}] \"{node.get('content', '')}\" "
                    f"(id: {node.get('node_id', '?')}, networks: {node.get('networks', [])})"
                )
            parts.append("Relevant Nodes:\n" + "\n".join(node_lines))

        if context.get("health"):
            health_lines = []
            for h in context["health"]:
                health_lines.append(
                    f"  - {h['network']}: {h['status']} ({h['momentum']}) "
                    f"completion={h.get('commitment_completion_rate', 'N/A')}"
                )
            parts.append("Network Health:\n" + "\n".join(health_lines))

        if context.get("bridges"):
            bridge_lines = []
            for b in context["bridges"]:
                bridge_lines.append(
                    f"  - {b['source_network']} <-> {b['target_network']} "
                    f"(similarity: {b['similarity']:.2f}, meaningful: {b.get('meaningful', 'unknown')})"
                )
            parts.append("Recent Bridges:\n" + "\n".join(bridge_lines))

        if context.get("facts"):
            fact_lines = []
            for f in context["facts"][:10]:
                fact_lines.append(
                    f"  - [{f.get('status', '?')}] \"{f.get('statement', '')}\" "
                    f"(confidence: {f.get('confidence', '?')})"
                )
            parts.append("Verified Facts:\n" + "\n".join(fact_lines))

        return "\n\n".join(parts) if parts else "No graph context available."

    def _format_briefing_input(
        self,
        health_scores: list[dict[str, Any]],
        alerts: list[dict[str, Any]],
        bridges: list[dict[str, Any]],
        commitments: dict[str, Any],
        review_items: list[dict[str, Any]],
    ) -> str:
        """Format all background job data for the briefing prompt."""
        parts = [f"Date: {datetime.utcnow().date().isoformat()}"]

        if health_scores:
            parts.append(f"Network Health Scores:\n{json.dumps(health_scores, indent=2, default=str)}")

        if alerts:
            parts.append(f"Active Alerts:\n{json.dumps(alerts, indent=2, default=str)}")

        if bridges:
            parts.append(f"Recent Bridge Discoveries:\n{json.dumps(bridges, indent=2, default=str)}")

        if commitments:
            parts.append(f"Commitment Scan:\n{json.dumps(commitments, indent=2, default=str)}")

        if review_items:
            parts.append(f"Review Queue ({len(review_items)} items):\n{json.dumps(review_items[:20], indent=2, default=str)}")

        return "\n\n".join(parts)

    def _parse_analysis_response(
        self, raw_text: str, token_usage: dict[str, int]
    ) -> StrategistResult:
        """Parse the LLM analysis response into a StrategistResult."""
        try:
            data = self._extract_json(raw_text)
            return StrategistResult(
                analysis=data.get("analysis", raw_text),
                recommendations=data.get("recommendations", []),
                confidence=data.get("confidence", 0.8),
                citations=data.get("citations", []),
                token_usage=token_usage,
            )
        except ValueError:
            # If JSON parsing fails, return the raw text as analysis
            return StrategistResult(
                analysis=raw_text,
                token_usage=token_usage,
            )

    def _parse_briefing_response(self, raw_text: str) -> DailyBriefing:
        """Parse the LLM briefing response into a DailyBriefing."""
        try:
            data = self._extract_json(raw_text)
            sections = []
            for s in data.get("sections", []):
                raw_items = s.get("items", [])
                items = [
                    str(item) if not isinstance(item, str) else item
                    for item in raw_items
                ]
                sections.append(BriefingSection(
                    title=s.get("title", ""),
                    items=items,
                    priority=s.get("priority", "medium"),
                ))
            return DailyBriefing(
                sections=sections,
                summary=data.get("summary", ""),
            )
        except ValueError:
            logger.warning("Failed to parse briefing JSON, using truncated raw text")
            truncated = raw_text[:500] + ("..." if len(raw_text) > 500 else "")
            return DailyBriefing(summary=truncated)

    def _extract_json(self, text: str) -> dict[str, Any]:
        """Extract JSON object from LLM response."""
        text = text.strip()

        if text.startswith("{"):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                pass

        pattern = r"```(?:json)?\s*\n?(.*?)\n?\s*```"
        matches = re.findall(pattern, text, re.DOTALL)
        for match in matches:
            try:
                return json.loads(match.strip())
            except json.JSONDecodeError:
                continue

        brace_start = text.find("{")
        if brace_start >= 0:
            depth = 0
            for i in range(brace_start, len(text)):
                if text[i] == "{":
                    depth += 1
                elif text[i] == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(text[brace_start:i + 1])
                        except json.JSONDecodeError:
                            break

        raise ValueError(f"No valid JSON found in response: {text[:200]}...")

    def _extract_token_usage(self, response: Any) -> dict[str, int]:
        """Extract token usage from API response."""
        return {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        }
