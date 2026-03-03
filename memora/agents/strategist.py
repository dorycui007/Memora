"""Strategist Agent — analytical advisor for cross-network insights and decision support.

Interprets graph data, identifies patterns, assesses network health, discovers
cross-network insights, and provides actionable recommendations.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timezone
from pathlib import Path
from typing import Any

import openai

from memora.core.json_utils import extract_json
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
class CounterEvidence:
    """A single piece of counter-evidence from a critique."""

    point: str = ""
    evidence_nodes: list[str] = field(default_factory=list)
    strength: str = "moderate"  # strong, moderate, weak


@dataclass
class CritiqueResult:
    """Result from a Strategist critique."""

    analysis: str = ""
    counter_evidence: list[CounterEvidence] = field(default_factory=list)
    blind_spots: list[str] = field(default_factory=list)
    confidence: float = 0.75
    citations: list[str] = field(default_factory=list)
    token_usage: dict[str, int] = field(default_factory=dict)


@dataclass
class DailyBriefing:
    """Complete daily briefing with typed sections."""

    summary: str = ""
    mood: str = "mixed"  # good_day, mixed, needs_focus, urgent
    network_overview: str = ""
    urgent: list[str] = field(default_factory=list)
    since_last: list[str] = field(default_factory=list)
    upcoming: list[str] = field(default_factory=list)
    people_followup: list[str] = field(default_factory=list)
    patterns_insights: list[str] = field(default_factory=list)
    wins: list[str] = field(default_factory=list)
    stalled_attention: list[str] = field(default_factory=list)
    review_items: list[str] = field(default_factory=list)
    data_sources_used: list[str] = field(default_factory=list)
    generated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


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
                reasoning={"effort": "medium"},
                max_output_tokens=16384,
            )
        except openai.APIError as e:
            logger.error("OpenAI API error in Strategist: %s", e)
            return StrategistResult(analysis=f"Analysis failed: {e}")

        raw_text = response.output_text
        token_usage = self._extract_token_usage(response)

        return self._parse_analysis_response(raw_text, token_usage)

    async def generate_briefing(
        self,
        briefing_data: dict[str, Any],
    ) -> DailyBriefing:
        """Generate the daily briefing from collected data.

        Args:
            briefing_data: Dict from BriefingCollector.collect() with all source data.

        Returns:
            DailyBriefing with typed sections.
        """
        formatted = self._format_briefing_data(briefing_data)

        try:
            response = await async_call_with_retry(
                self._client.responses.create,
                model=self._model,
                instructions=self._system_prompt,
                input=(
                    "Generate today's daily briefing using the data below. "
                    "Respond with a JSON object matching the Daily Briefing schema.\n\n"
                    "IMPORTANT: Write in second person ('you'). Use specific names, dates, "
                    "and numbers. Maximum 5 items per section. Empty sections = empty arrays. "
                    "Do NOT echo raw metric names.\n\n"
                    f"{formatted}"
                ),
                text={"format": {"type": "json_object"}},
                reasoning={"effort": "medium"},
                max_output_tokens=16384,
            )
        except openai.APIError as e:
            logger.error("OpenAI API error generating briefing: %s", e)
            return DailyBriefing(
                summary=f"Briefing generation failed: {e}",
                data_sources_used=briefing_data.get("data_sources_used", []),
            )

        raw_text = response.output_text
        if not raw_text:
            output_types = [item.type for item in response.output] if response.output else []
            logger.warning("Empty briefing response from LLM, output types: %s, status: %s", output_types, response.status)
            return DailyBriefing(
                summary="Briefing generation returned empty response.",
                data_sources_used=briefing_data.get("data_sources_used", []),
            )
        briefing = self._parse_briefing_response(raw_text)
        briefing.data_sources_used = briefing_data.get("data_sources_used", [])
        return briefing

    async def critique(self, statement: str, graph_context: dict[str, Any] | None = None) -> CritiqueResult:
        """Invoke critic mode: challenge a statement using graph evidence.

        Args:
            statement: The statement or decision to critique.
            graph_context: Pre-gathered graph context.

        Returns:
            CritiqueResult with counter-evidence and blind spots.
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
                    f"and overlooked risks. Respond with a JSON object matching the "
                    f"Critique Response schema: analysis, counter_evidence (list of "
                    f"objects with point/evidence_nodes/strength), blind_spots (list "
                    f"of strings), confidence, and citations.\n\n"
                    f"Statement: {statement}\n\n"
                    f"Graph Context:\n{context_text}"
                ),
                text={"format": {"type": "json_object"}},
                reasoning={"effort": "medium"},
                max_output_tokens=16384,
            )
        except openai.APIError as e:
            logger.error("OpenAI API error in Strategist critique: %s", e)
            return CritiqueResult(analysis=f"Critique failed: {e}")

        raw_text = response.output_text
        token_usage = self._extract_token_usage(response)

        return self._parse_critique_response(raw_text, token_usage)

    def _build_graph_context(self, query: str) -> dict[str, Any]:
        """Gather graph context relevant to the query."""
        context: dict[str, Any] = {
            "nodes": [],
            "expanded_nodes": [],
            "edges": [],
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

        # Search for relevant nodes via hybrid search (dense + FTS with RRF)
        if self._vector_store and self._embedding_engine:
            try:
                embedding = self._embedding_engine.embed_text(query)
                results = self._vector_store.hybrid_search(
                    query_vector=embedding["dense"],
                    query_text=query,
                    top_k=15,
                )
                context["nodes"] = [r.to_dict() for r in results]
            except Exception:
                logger.warning("Hybrid search failed in strategist context, falling back to dense", exc_info=True)
                try:
                    embedding = self._embedding_engine.embed_text(query)
                    results = self._vector_store.dense_search(
                        embedding["dense"], top_k=15
                    )
                    context["nodes"] = [r.to_dict() for r in results]
                except Exception:
                    logger.warning("Dense search also failed in strategist context", exc_info=True)

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

        # Entity-aware graph lookup
        self._enrich_context_with_entity_lookup(query, context)

        return context

    def _enrich_context_with_entity_lookup(
        self, query: str, context: dict[str, Any],
    ) -> None:
        """Search the graph for named entities mentioned in the query.

        Extracts capitalized words (likely proper nouns) from the query,
        searches for matching nodes by title, and expands their 1-hop
        neighborhoods so the strategist has concrete data about the people,
        projects, and goals mentioned.
        """
        if not self._repo:
            return

        from memora.core.text_utils import extract_entity_candidates
        entity_candidates = extract_entity_candidates(query)

        if not entity_candidates:
            return

        existing_ids = {n.get("node_id") for n in context.get("nodes", [])}
        existing_ids |= {n.get("node_id") for n in context.get("expanded_nodes", [])}

        for candidate in entity_candidates:
            try:
                matches = self._repo.search_by_title(candidate, limit=5)
            except Exception:
                logger.debug("Entity lookup failed for %r", candidate)
                continue

            for node in matches:
                nid = str(node.id)
                if nid in existing_ids:
                    continue
                existing_ids.add(nid)

                # Add the matched node as a primary context node
                context["nodes"].append({
                    "node_id": nid,
                    "node_type": node.node_type.value
                        if hasattr(node.node_type, "value") else str(node.node_type),
                    "title": node.title,
                    "content": node.content or node.title,
                    "networks": [
                        net.value if hasattr(net, "value") else str(net)
                        for net in node.networks
                    ],
                    "confidence": node.confidence,
                    "properties": node.properties,
                })

                # Expand 1-hop neighborhood for the entity
                try:
                    subgraph = self._repo.get_neighborhood(node.id, hops=1)
                    for neighbor in subgraph.nodes:
                        neighbor_id = str(neighbor.id)
                        if neighbor_id in existing_ids:
                            continue
                        existing_ids.add(neighbor_id)
                        context["expanded_nodes"].append({
                            "node_id": neighbor_id,
                            "title": neighbor.title,
                            "content": neighbor.content or neighbor.title,
                            "node_type": neighbor.node_type.value
                                if hasattr(neighbor.node_type, "value")
                                else str(neighbor.node_type),
                            "networks": [
                                net.value if hasattr(net, "value") else str(net)
                                for net in neighbor.networks
                            ],
                            "properties": neighbor.properties,
                        })
                    # Include edges for relationship context
                    for edge in subgraph.edges:
                        context["edges"].append({
                            "source_id": str(edge.source_id),
                            "target_id": str(edge.target_id),
                            "edge_type": edge.edge_type.value
                                if hasattr(edge.edge_type, "value")
                                else str(edge.edge_type),
                            "properties": edge.properties,
                        })
                except Exception:
                    logger.debug("Neighborhood expansion failed for entity %s", nid)

    def _format_context(self, context: dict[str, Any]) -> str:
        """Format graph context for injection into the prompt."""
        parts = []

        if context.get("stats"):
            parts.append(f"Graph Stats: {json.dumps(context['stats'])}")

        if context.get("nodes"):
            node_lines = []
            for node in context["nodes"]:
                title = node.get("title", "")
                content = node.get("content", "")
                display = content or title
                props = node.get("properties", {})
                props_str = f", properties: {json.dumps(props)}" if props else ""
                node_lines.append(
                    f"  - [{node.get('node_type', '?')}] \"{display}\" "
                    f"(id: {node.get('node_id', '?')}, networks: {node.get('networks', [])}{props_str})"
                )
            parts.append("Relevant Nodes:\n" + "\n".join(node_lines))

        if context.get("expanded_nodes"):
            exp_lines = []
            for node in context["expanded_nodes"]:
                title = node.get("title", "")
                content = node.get("content", "")
                display = content or title
                props = node.get("properties", {})
                props_str = f", properties: {json.dumps(props)}" if props else ""
                exp_lines.append(
                    f"  - [{node.get('node_type', '?')}] \"{display}\" "
                    f"(id: {node.get('node_id', '?')}, networks: {node.get('networks', [])}{props_str})"
                )
            parts.append("Connected Nodes (1-hop neighborhood):\n" + "\n".join(exp_lines))

        if context.get("edges"):
            edge_lines = []
            for edge in context["edges"]:
                edge_lines.append(
                    f"  - {edge.get('source_id', '?')} --[{edge.get('edge_type', '?')}]--> "
                    f"{edge.get('target_id', '?')}"
                )
            parts.append("Relationships:\n" + "\n".join(edge_lines))

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

    def _format_briefing_data(self, data: dict[str, Any]) -> str:
        """Format collected briefing data as labeled sections for the LLM prompt."""
        parts = [f"Date: {data.get('date', datetime.now(UTC).date().isoformat())}"]
        parts.append(f"Data window since: {data.get('since', 'N/A')}")

        health = data.get("health", [])
        if health:
            parts.append(f"=== NETWORK HEALTH ===\n{json.dumps(health, indent=2, default=str)}")

        urgent = data.get("urgent", {})
        if any(urgent.get(k) for k in ("overdue_commitments", "decaying_close", "stale_facts")):
            parts.append(f"=== URGENT ===\n{json.dumps(urgent, indent=2, default=str)}")

        since_last = data.get("since_last", {})
        if any(since_last.get(k) for k in ("new_nodes", "actions", "bridges")):
            summary = {
                "new_nodes_count": len(since_last.get("new_nodes", [])),
                "new_nodes": [
                    {"type": n.get("node_type"), "title": n.get("title"), "networks": n.get("networks")}
                    for n in since_last.get("new_nodes", [])[:20]
                ],
                "actions_count": len(since_last.get("actions", [])),
                "actions": [
                    {"type": a.get("action_type"), "executed_at": a.get("executed_at")}
                    for a in since_last.get("actions", [])[:10]
                ],
                "bridges": since_last.get("bridges", []),
            }
            parts.append(f"=== SINCE LAST CHECK ===\n{json.dumps(summary, indent=2, default=str)}")

        upcoming = data.get("upcoming", {})
        if any(upcoming.get(k) for k in ("approaching", "pending_outcomes", "review_count")):
            parts.append(f"=== COMING UP ===\n{json.dumps(upcoming, indent=2, default=str)}")

        people = data.get("people", {})
        if people.get("decaying_all") or people.get("stats"):
            summary = {}
            if people.get("decaying_all"):
                summary["decaying_relationships"] = people["decaying_all"][:10]
            stats = people.get("stats", {})
            if stats:
                summary["people_stats"] = {
                    "total": stats.get("total_people", 0),
                    "relationship_health": stats.get("relationship_health", {}),
                }
            parts.append(f"=== PEOPLE ===\n{json.dumps(summary, indent=2, default=str)}")

        patterns = data.get("patterns", [])
        if patterns:
            pattern_summary = [
                {"type": p.get("pattern_type"), "description": p.get("description"),
                 "confidence": p.get("confidence"), "action": p.get("suggested_action")}
                for p in patterns[:10]
            ]
            parts.append(f"=== PATTERNS & INSIGHTS ===\n{json.dumps(pattern_summary, indent=2, default=str)}")

        wins = data.get("wins", {})
        if wins.get("completed") or wins.get("momentum_up"):
            parts.append(f"=== WINS ===\n{json.dumps(wins, indent=2, default=str)}")

        stalled = data.get("stalled", {})
        if any(v for v in stalled.values() if v):
            summary = {k: v[:5] for k, v in stalled.items() if v}
            parts.append(f"=== STALLED ===\n{json.dumps(summary, indent=2, default=str)}")

        review = data.get("review_queue", [])
        if review:
            review_summary = [
                {"title": r.get("title"), "type": r.get("node_type")}
                for r in review[:10]
            ]
            parts.append(f"=== REVIEW QUEUE ({len(review)} items) ===\n{json.dumps(review_summary, indent=2, default=str)}")

        truth = data.get("truth_alerts", [])
        if truth:
            truth_summary = [
                {"statement": f.get("statement"), "confidence": f.get("confidence")}
                for f in truth[:5]
            ]
            parts.append(f"=== TRUTH ALERTS ===\n{json.dumps(truth_summary, indent=2, default=str)}")

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

    def _parse_critique_response(
        self, raw_text: str, token_usage: dict[str, int]
    ) -> CritiqueResult:
        """Parse the LLM critique response into a CritiqueResult."""
        try:
            data = self._extract_json(raw_text)
            counter_evidence = []
            for ce in data.get("counter_evidence", []):
                if isinstance(ce, dict):
                    counter_evidence.append(CounterEvidence(
                        point=ce.get("point", ""),
                        evidence_nodes=ce.get("evidence_nodes", []),
                        strength=ce.get("strength", "moderate"),
                    ))
                elif isinstance(ce, str):
                    counter_evidence.append(CounterEvidence(point=ce))
            return CritiqueResult(
                analysis=data.get("analysis", raw_text),
                counter_evidence=counter_evidence,
                blind_spots=data.get("blind_spots", []),
                confidence=data.get("confidence", 0.75),
                citations=data.get("citations", []),
                token_usage=token_usage,
            )
        except ValueError:
            return CritiqueResult(
                analysis=raw_text,
                token_usage=token_usage,
            )

    def _parse_briefing_response(self, raw_text: str) -> DailyBriefing:
        """Parse the LLM briefing response into a DailyBriefing."""
        def _str_list(val: Any) -> list[str]:
            if not isinstance(val, list):
                return []
            return [str(item) for item in val]

        try:
            data = self._extract_json(raw_text)
            logger.debug("Parsed briefing JSON keys: %s", list(data.keys()))

            mood = data.get("mood", "mixed")
            if mood not in ("good_day", "mixed", "needs_focus", "urgent"):
                mood = "mixed"

            return DailyBriefing(
                summary=data.get("summary", ""),
                mood=mood,
                network_overview=data.get("network_overview", ""),
                urgent=_str_list(data.get("urgent")),
                since_last=_str_list(data.get("since_last")),
                upcoming=_str_list(data.get("upcoming")),
                people_followup=_str_list(data.get("people_followup")),
                patterns_insights=_str_list(data.get("patterns_insights")),
                wins=_str_list(data.get("wins")),
                stalled_attention=_str_list(data.get("stalled_attention")),
                review_items=_str_list(data.get("review_items")),
            )
        except ValueError:
            logger.warning("Failed to parse briefing JSON, raw (first 300 chars): %s", raw_text[:300])
            truncated = raw_text[:500] + ("..." if len(raw_text) > 500 else "")
            return DailyBriefing(summary=truncated)

    def _extract_json(self, text: str) -> dict[str, Any]:
        """Extract JSON object from LLM response."""
        return extract_json(text)

    def _extract_token_usage(self, response: Any) -> dict[str, int]:
        """Extract token usage from API response."""
        return {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        }
