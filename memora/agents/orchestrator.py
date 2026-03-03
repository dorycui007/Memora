"""LangGraph Orchestrator — multi-agent coordination and query routing.

Routes user queries to the appropriate agent(s), coordinates multi-agent
deliberation, and synthesizes final responses with confidence-weighted merging.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, TypedDict
from uuid import UUID, uuid4

from langgraph.graph import END, StateGraph

from memora.agents.archivist import ArchivistAgent
from memora.agents.researcher import ResearcherAgent
from memora.agents.strategist import StrategistAgent
from memora.config import Settings
from memora.graph.models import enum_val
from memora.core.async_utils import run_async as _run_async
from memora.graph.repository import GraphRepository
from memora.vector.embeddings import EmbeddingEngine
from memora.vector.store import VectorStore

logger = logging.getLogger(__name__)


class QueryType(str, Enum):
    CAPTURE = "capture"
    ANALYSIS = "analysis"
    RESEARCH = "research"
    COUNCIL = "council"


# ---- LangGraph State ----


class CouncilState(TypedDict, total=False):
    """State carried through the LangGraph orchestration."""

    query_id: str
    query: str
    query_type: str
    graph_context: dict[str, Any]
    archivist_output: dict[str, Any] | None
    strategist_output: dict[str, Any] | None
    researcher_output: dict[str, Any] | None
    synthesis: str
    confidence: float
    citations: list[str]
    deliberation_round: int
    max_deliberation_rounds: int
    high_disagreement: bool
    error: str | None


# ---- Results ----


@dataclass
class OrchestratorResult:
    """Final result from the orchestrator."""

    query_id: str = ""
    query_type: QueryType = QueryType.ANALYSIS
    synthesis: str = ""
    agent_outputs: list[dict[str, Any]] = field(default_factory=list)
    confidence: float = 0.8
    citations: list[str] = field(default_factory=list)
    deliberation_rounds: int = 0
    high_disagreement: bool = False


class Orchestrator:
    """LangGraph-based multi-agent orchestrator for the AI Council."""

    def __init__(
        self,
        api_key: str,
        repo: GraphRepository | None = None,
        vector_store: VectorStore | None = None,
        embedding_engine: EmbeddingEngine | None = None,
        truth_layer: Any | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._api_key = api_key
        self._repo = repo
        self._vector_store = vector_store
        self._embedding_engine = embedding_engine
        self._truth_layer = truth_layer
        self._settings = settings

        # Initialize agents
        self._archivist = ArchivistAgent(
            api_key=api_key,
            vector_store=vector_store,
            embedding_engine=embedding_engine,
        ) if api_key else None

        self._strategist = StrategistAgent(
            api_key=api_key,
            repo=repo,
            vector_store=vector_store,
            embedding_engine=embedding_engine,
            truth_layer=truth_layer,
        ) if api_key else None

        self._researcher = ResearcherAgent(
            api_key=api_key,
            truth_layer=truth_layer,
        ) if api_key else None

        # Build the LangGraph
        self._graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """Build the LangGraph state graph for query orchestration."""
        graph = StateGraph(CouncilState)

        # Add nodes
        graph.add_node("classify", self._classify_node)
        graph.add_node("archivist", self._archivist_node)
        graph.add_node("strategist", self._strategist_node)
        graph.add_node("researcher", self._researcher_node)
        graph.add_node("council_all", self._council_all_agents_node)
        graph.add_node("synthesize", self._synthesize_node)
        graph.add_node("deliberate", self._deliberation_node)

        # Set entry point
        graph.set_entry_point("classify")

        # Add conditional edges from classify
        graph.add_conditional_edges(
            "classify",
            self._route_after_classify,
            {
                "archivist": "archivist",
                "strategist": "strategist",
                "researcher": "researcher",
                "council_all": "council_all",
            },
        )

        # After single-agent runs, go to synthesize
        graph.add_edge("archivist", "synthesize")
        graph.add_edge("strategist", "synthesize")
        graph.add_edge("researcher", "synthesize")
        # Council runs all agents, then synthesizes
        graph.add_edge("council_all", "synthesize")

        # Synthesize conditionally loops for deliberation or ends
        graph.add_conditional_edges(
            "synthesize",
            self._route_after_synthesize,
            {
                "deliberate": "deliberate",
                "end": END,
            },
        )

        # After deliberation, re-synthesize
        graph.add_edge("deliberate", "synthesize")

        return graph.compile()

    # ---- Query execution ----

    def run(
        self,
        query: str,
        query_type: str | None = None,
        context: dict[str, Any] | None = None,
        max_deliberation_rounds: int = 2,
    ) -> OrchestratorResult:
        """Execute the orchestration pipeline for a query."""
        query_id = str(uuid4())

        # Build graph context
        graph_context = context or {}
        if self._repo and not graph_context.get("nodes"):
            graph_context = self._gather_context(query)

        initial_state: CouncilState = {
            "query_id": query_id,
            "query": query,
            "query_type": query_type or "",
            "graph_context": graph_context,
            "archivist_output": None,
            "strategist_output": None,
            "researcher_output": None,
            "synthesis": "",
            "confidence": 0.0,
            "citations": [],
            "deliberation_round": 0,
            "max_deliberation_rounds": max_deliberation_rounds,
            "high_disagreement": False,
            "error": None,
        }

        try:
            final_state = self._graph.invoke(initial_state)
        except Exception as e:
            logger.error("Orchestrator pipeline failed: %s", e, exc_info=True)
            return OrchestratorResult(
                query_id=query_id,
                synthesis=f"Pipeline error: {e}",
            )

        return self._state_to_result(final_state)

    # ---- LangGraph nodes ----

    def _classify_node(self, state: CouncilState) -> CouncilState:
        """Classify the query type to determine routing."""
        query = state["query"].lower()
        query_type = state.get("query_type", "")

        if query_type:
            state["query_type"] = query_type
            return state

        # Heuristic classification with weighted scoring
        # Each category accumulates a score; highest wins.
        scores: dict[str, float] = {
            QueryType.CAPTURE.value: 0.0,
            QueryType.RESEARCH.value: 0.0,
            QueryType.ANALYSIS.value: 0.0,
            QueryType.COUNCIL.value: 0.0,
        }

        # Council signals (high weight — explicit intent for multi-agent)
        council_signals = [
            "complex decision", "weigh options", "major decision",
            "all things considered", "comprehensive analysis",
            "help me decide", "big picture",
        ]
        for sig in council_signals:
            if sig in query:
                scores[QueryType.COUNCIL.value] += 2.0

        # Analysis signals (explicit analytical intent)
        analysis_signals = [
            "analyze", "recommend", "prioritize", "assess", "evaluate",
            "should i", "what should", "how am i doing", "status",
            "health of", "progress on", "summary of", "briefing",
        ]
        for sig in analysis_signals:
            if sig in query:
                scores[QueryType.ANALYSIS.value] += 1.5

        # Research signals (information-seeking)
        research_signals = [
            "how does", "explain", "look up", "search for",
            "find information", "research", "what are the latest",
            "is it true", "fact check",
        ]
        for sig in research_signals:
            if sig in query:
                scores[QueryType.RESEARCH.value] += 1.5
        # "what is" is research UNLESS followed by analysis words like status/progress
        _analysis_after_what_is = ["status", "progress", "health", "state of"]
        if "what is" in query:
            if any(w in query for w in _analysis_after_what_is):
                scores[QueryType.ANALYSIS.value] += 1.5
            else:
                scores[QueryType.RESEARCH.value] += 1.5
        # "compare" is weaker — could be analysis or research
        if "compare" in query:
            scores[QueryType.RESEARCH.value] += 0.5
            scores[QueryType.ANALYSIS.value] += 0.5

        # Capture signals (lowest weight — most likely to false-positive)
        capture_signals = [
            "i did", "i met", "i went", "i bought", "i decided",
            "i learned", "i read", "i heard", "happened today",
            "note to self", "remember that", "i promised", "i owe",
        ]
        for sig in capture_signals:
            if sig in query:
                scores[QueryType.CAPTURE.value] += 1.0

        # If capture and analysis both triggered, analysis intent likely dominates
        # e.g. "what should I do about my decision" — analysis, not capture
        if (scores[QueryType.CAPTURE.value] > 0
                and scores[QueryType.ANALYSIS.value] > 0):
            scores[QueryType.CAPTURE.value] *= 0.5

        # Tie-break: prefer ANALYSIS over RESEARCH for internal-data queries
        if (scores[QueryType.ANALYSIS.value] > 0
                and scores[QueryType.ANALYSIS.value] == scores[QueryType.RESEARCH.value]):
            scores[QueryType.ANALYSIS.value] += 0.1

        # Pick highest score, default to ANALYSIS
        best_type = max(scores, key=scores.get)  # type: ignore[arg-type]
        if scores[best_type] > 0:
            state["query_type"] = best_type
        else:
            state["query_type"] = QueryType.ANALYSIS.value

        logger.info("Classified query as: %s", state["query_type"])
        return state

    def _archivist_node(self, state: CouncilState) -> CouncilState:
        """Run the Archivist agent for extraction."""
        if not self._archivist:
            state["archivist_output"] = {"error": "Archivist not configured"}
            return state

        try:
            result = _run_async(self._archivist.extract(
                state["query"], state["query_id"]
            ))
            # Use human_summary for readable output; fall back to raw JSON only if missing
            if result.proposal and result.proposal.human_summary:
                content = result.proposal.human_summary
            elif result.clarification_needed and result.clarification_message:
                content = result.clarification_message
            else:
                content = result.raw_response
            state["archivist_output"] = {
                "agent": "archivist",
                "content": content,
                "confidence": result.proposal.confidence if result.proposal else 0.0,
                "clarification_needed": result.clarification_needed,
                "clarification_message": result.clarification_message,
                "has_proposal": result.proposal is not None,
                "token_usage": result.token_usage,
            }
        except Exception as e:
            logger.error("Archivist node failed: %s", e)
            state["archivist_output"] = {"error": str(e)}

        return state

    def _strategist_node(self, state: CouncilState) -> CouncilState:
        """Run the Strategist agent for analysis."""
        if not self._strategist:
            state["strategist_output"] = {"error": "Strategist not configured"}
            return state

        try:
            # Include previous agent outputs for deliberation rounds
            context = dict(state["graph_context"])
            if state.get("archivist_output") and state["deliberation_round"] > 0:
                context["archivist_findings"] = state["archivist_output"]
            if state.get("researcher_output") and state["deliberation_round"] > 0:
                context["researcher_findings"] = state["researcher_output"]

            result = _run_async(self._strategist.analyze(state["query"], context))
            state["strategist_output"] = {
                "agent": "strategist",
                "content": result.analysis,
                "confidence": result.confidence,
                "citations": result.citations,
                "recommendations": result.recommendations,
                "token_usage": result.token_usage,
            }
        except Exception as e:
            logger.error("Strategist node failed: %s", e)
            state["strategist_output"] = {"error": str(e)}

        return state

    def _researcher_node(self, state: CouncilState) -> CouncilState:
        """Run the Researcher agent for external data."""
        if not self._researcher:
            state["researcher_output"] = {"error": "Researcher not configured"}
            return state

        try:
            result = _run_async(self._researcher.research(
                state["query"], state.get("graph_context")
            ))
            state["researcher_output"] = {
                "agent": "researcher",
                "content": result.answer,
                "confidence": result.confidence,
                "sources": [
                    {"url": s.url, "title": s.title, "reliability": s.reliability_score}
                    for s in result.sources
                ],
                "facts_deposited": len(result.facts_to_deposit),
                "anonymized_query": result.anonymized_query,
                "token_usage": result.token_usage,
            }
        except Exception as e:
            logger.error("Researcher node failed: %s", e)
            state["researcher_output"] = {"error": str(e)}

        return state

    def _council_all_agents_node(self, state: CouncilState) -> CouncilState:
        """Run ALL three agents for council queries (comprehensive analysis).

        Runs archivist and researcher in parallel (they are independent),
        then strategist analyzes with their combined output.
        """
        # 1. Archivist and researcher run concurrently
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            # Each runs in its own thread with its own event loop
            def run_archivist():
                s = dict(state)
                s = self._archivist_node(s)
                return s.get("archivist_output")

            def run_researcher():
                s = dict(state)
                s = self._researcher_node(s)
                return s.get("researcher_output")

            arch_future = pool.submit(run_archivist)
            res_future = pool.submit(run_researcher)

            state["archivist_output"] = arch_future.result()
            state["researcher_output"] = res_future.result()

        # 2. Strategist analyzes with all context available
        context = dict(state["graph_context"])
        if state.get("archivist_output") and "error" not in state["archivist_output"]:
            context["archivist_findings"] = state["archivist_output"].get("content", "")
        if state.get("researcher_output") and "error" not in state["researcher_output"]:
            context["researcher_findings"] = state["researcher_output"].get("content", "")
            context["external_sources"] = state["researcher_output"].get("sources", [])

        if self._strategist:
            try:
                result = _run_async(self._strategist.analyze(state["query"], context))
                state["strategist_output"] = {
                    "agent": "strategist",
                    "content": result.analysis,
                    "confidence": result.confidence,
                    "citations": result.citations,
                    "recommendations": result.recommendations,
                    "token_usage": result.token_usage,
                }
            except Exception as e:
                logger.error("Strategist node (council) failed: %s", e)
                state["strategist_output"] = {"error": str(e)}
        else:
            state["strategist_output"] = {"error": "Strategist not configured"}

        return state

    def _deliberation_node(self, state: CouncilState) -> CouncilState:
        """Run a deliberation round where agents review each other's outputs.

        The strategist reviews all findings and produces a revised analysis
        that addresses disagreements. The researcher is re-invoked if the
        strategist identifies knowledge gaps.
        """
        logger.info(
            "Deliberation round %d for query %s",
            state.get("deliberation_round", 0),
            state.get("query_id", "?"),
        )

        # Build context with all prior outputs for the strategist to review
        context = dict(state["graph_context"])

        prior_outputs = []
        for key in ("archivist_output", "strategist_output", "researcher_output"):
            output = state.get(key)
            if output and "error" not in output:
                prior_outputs.append(output)
                context[f"prior_{key}"] = output

        context["deliberation_instruction"] = (
            "This is a deliberation round. Review ALL prior agent outputs above "
            "and synthesize a revised analysis that resolves disagreements, fills gaps, "
            "and provides a unified recommendation. If prior outputs conflict, explain "
            "the tension and provide a balanced perspective."
        )

        # Re-run strategist with full context
        if self._strategist:
            try:
                result = _run_async(self._strategist.analyze(state["query"], context))
                state["strategist_output"] = {
                    "agent": "strategist",
                    "content": result.analysis,
                    "confidence": result.confidence,
                    "citations": result.citations,
                    "recommendations": result.recommendations,
                    "token_usage": result.token_usage,
                    "deliberation_round": state.get("deliberation_round", 0),
                }
            except Exception as e:
                logger.error("Deliberation strategist failed: %s", e)

        # Re-run researcher if strategist identified gaps
        strategist_content = (state.get("strategist_output") or {}).get("content", "")
        gap_signals = ["need more data", "insufficient evidence", "further research",
                       "unknown", "unclear", "no data available"]
        if any(sig in strategist_content.lower() for sig in gap_signals):
            if self._researcher:
                try:
                    result = _run_async(self._researcher.research(
                        state["query"], state.get("graph_context")
                    ))
                    state["researcher_output"] = {
                        "agent": "researcher",
                        "content": result.answer,
                        "confidence": result.confidence,
                        "sources": [
                            {"url": s.url, "title": s.title, "reliability": s.reliability_score}
                            for s in result.sources
                        ],
                        "facts_deposited": len(result.facts_to_deposit),
                        "anonymized_query": result.anonymized_query,
                        "token_usage": result.token_usage,
                        "deliberation_round": state.get("deliberation_round", 0),
                    }
                except Exception as e:
                    logger.error("Deliberation researcher failed: %s", e)

        return state

    def _synthesize_node(self, state: CouncilState) -> CouncilState:
        """Synthesize outputs from all agents with confidence-weighted merging."""
        outputs = []
        total_confidence = 0.0
        all_citations = []

        for key in ("archivist_output", "strategist_output", "researcher_output"):
            output = state.get(key)
            if output and "error" not in output:
                outputs.append(output)
                confidence = output.get("confidence", 0.5)
                total_confidence += confidence
                all_citations.extend(output.get("citations", []))

        # CRAG fallback: if the only output is a low-confidence researcher result,
        # the query was likely misrouted — fall back to the strategist.
        if (len(outputs) == 1
                and outputs[0].get("confidence", 0) <= 0.1
                and outputs[0].get("agent") == "researcher"
                and state.get("query_type") == QueryType.RESEARCH.value
                and self._strategist
                and not state.get("strategist_output")):
            logger.info("CRAG: researcher returned low confidence, falling back to strategist")
            state = self._strategist_node(state)
            # Re-collect outputs with strategist result
            outputs = []
            total_confidence = 0.0
            all_citations = []
            for key in ("archivist_output", "strategist_output", "researcher_output"):
                output = state.get(key)
                if output and "error" not in output:
                    outputs.append(output)
                    confidence = output.get("confidence", 0.5)
                    total_confidence += confidence
                    all_citations.extend(output.get("citations", []))

        if not outputs:
            state["synthesis"] = "No agent produced valid output."
            state["confidence"] = 0.0
            return state

        # Confidence-weighted synthesis
        avg_confidence = total_confidence / len(outputs)

        # Check for high disagreement
        confidences = [o.get("confidence", 0.5) for o in outputs]
        if len(confidences) > 1:
            spread = max(confidences) - min(confidences)
            state["high_disagreement"] = spread > 0.3 + 1e-9

        # Build synthesis from agent outputs using LLM
        synthesis_parts = []
        for output in sorted(outputs, key=lambda o: o.get("confidence", 0), reverse=True):
            agent = output.get("agent", "unknown")
            content = output.get("content", "")
            conf = output.get("confidence", 0.5)
            if content:
                synthesis_parts.append(f"[{agent} (confidence: {conf:.2f})] {content}")

        raw_synthesis = "\n\n".join(synthesis_parts)

        # Apply truth layer fact-check if available
        if self._truth_layer and state.get("query_type") != QueryType.CAPTURE.value:
            fact_check = self._fact_check_synthesis(raw_synthesis)
            if fact_check:
                raw_synthesis += f"\n\n[fact_check] {fact_check}"

        # Use LLM to produce a coherent synthesis when multiple agents contributed
        if len(outputs) > 1 and self._api_key:
            state["synthesis"] = self._llm_synthesize(
                state["query"], raw_synthesis, outputs,
            )
        else:
            # Single agent — just use its content directly
            state["synthesis"] = outputs[0].get("content", raw_synthesis) if outputs else raw_synthesis
        state["confidence"] = avg_confidence
        state["citations"] = list(set(all_citations))
        state["deliberation_round"] = state.get("deliberation_round", 0) + 1

        return state

    # ---- Routing functions ----

    def _route_after_classify(self, state: CouncilState) -> str:
        """Route to appropriate agent(s) after classification.

        Applies CRAG: if retrieval quality is poor for ANALYSIS queries,
        escalate to council_all so the Researcher can supplement with
        web search.
        """
        qt = state.get("query_type", "")

        if qt == QueryType.CAPTURE.value:
            return "archivist"
        elif qt == QueryType.RESEARCH.value:
            return "researcher"
        elif qt == QueryType.COUNCIL.value:
            return "council_all"
        else:  # ANALYSIS or default
            # CRAG: check retrieval quality and escalate if poor
            retrieval_quality = state.get("graph_context", {}).get(
                "retrieval_quality", "sufficient"
            )
            if retrieval_quality == "poor":
                logger.info("CRAG: poor retrieval quality, escalating to council_all")
                return "council_all"
            return "strategist"

    def _route_after_synthesize(self, state: CouncilState) -> str:
        """Decide whether to deliberate further or end."""
        current_round = state.get("deliberation_round", 1)
        max_rounds = state.get("max_deliberation_rounds", 2)
        query_type = state.get("query_type", "")
        high_disagreement = state.get("high_disagreement", False)

        # Only deliberate for council queries with high disagreement
        if (
            query_type == QueryType.COUNCIL.value
            and high_disagreement
            and current_round < max_rounds
        ):
            return "deliberate"

        return "end"

    # ---- Helpers ----

    def _assess_retrieval_quality(
        self, query: str, results: list[Any],
    ) -> str:
        """Assess retrieval quality for CRAG gating.

        Returns "sufficient" or "poor" based on:
        - Top result relevance score vs threshold
        - Number of results vs minimum required
        - Query term coverage in retrieved content
        """
        settings = self._settings
        relevance_threshold = settings.crag_relevance_threshold if settings else 0.5
        min_results = settings.crag_min_results if settings else 3
        term_coverage_threshold = settings.crag_term_coverage_threshold if settings else 0.3

        # Check 1: sufficient number of results
        if len(results) < min_results:
            logger.debug("CRAG: insufficient results (%d < %d)", len(results), min_results)
            return "poor"

        # Check 2: top result relevance score
        if results:
            top_score = results[0].score if hasattr(results[0], "score") else 0.0
            if top_score < relevance_threshold:
                logger.debug("CRAG: low top score (%.2f < %.2f)", top_score, relevance_threshold)
                return "poor"

        # Check 3: query term coverage
        query_terms = {t.lower() for t in query.split() if len(t) > 2}
        if query_terms:
            all_content = " ".join(
                (r.content if hasattr(r, "content") else "").lower()
                for r in results
            )
            covered = sum(1 for t in query_terms if t in all_content)
            coverage = covered / len(query_terms)
            if coverage < term_coverage_threshold:
                logger.debug("CRAG: low term coverage (%.2f < %.2f)", coverage, term_coverage_threshold)
                return "poor"

        return "sufficient"

    def _gather_context(self, query: str) -> dict[str, Any]:
        """Gather graph context for the query via hybrid search + 1-hop expansion.

        Includes CRAG quality assessment on the retrieval results and
        entity-aware graph lookup for named entities mentioned in the query.
        """
        context: dict[str, Any] = {
            "nodes": [], "expanded_nodes": [], "stats": {},
            "retrieval_quality": "sufficient",
        }

        if self._repo:
            try:
                context["stats"] = self._repo.get_graph_stats()
            except Exception:
                pass

        if self._vector_store and self._embedding_engine:
            try:
                embedding = self._embedding_engine.embed_text(query)

                # Use hybrid search (dense + FTS with RRF) instead of dense only
                results = self._vector_store.hybrid_search(
                    query_vector=embedding["dense"],
                    query_text=query,
                    top_k=10,
                )
                context["nodes"] = [r.to_dict() for r in results]

                # CRAG quality assessment
                context["retrieval_quality"] = self._assess_retrieval_quality(
                    query, results,
                )

                # 1-hop neighborhood expansion for top results
                if self._repo and results:
                    expanded = set()
                    for r in results[:5]:  # Expand top 5
                        try:
                            subgraph = self._repo.get_neighborhood(
                                UUID(r.node_id), hops=1
                            )
                            for n in subgraph.nodes:
                                nid = str(n.id)
                                if nid not in expanded and nid != r.node_id:
                                    expanded.add(nid)
                                    context["expanded_nodes"].append({
                                        "node_id": nid,
                                        "title": n.title,
                                        "node_type": n.node_type.value
                                            if hasattr(n.node_type, "value") else str(n.node_type),
                                        "networks": [
                                            enum_val(net)
                                            for net in n.networks
                                        ],
                                    })
                        except Exception:
                            pass  # Node may not exist in graph DB

                    # Deduplicate: remove expanded nodes already in primary results
                    primary_ids = {n["node_id"] for n in context["nodes"]}
                    context["expanded_nodes"] = [
                        n for n in context["expanded_nodes"]
                        if n["node_id"] not in primary_ids
                    ]

            except Exception:
                logger.warning("Context gathering failed", exc_info=True)
                context["retrieval_quality"] = "poor"

        else:
            # No vector store available — retrieval quality is inherently poor
            context["retrieval_quality"] = "poor"

        # Entity-aware graph lookup: search for named entities directly in the
        # graph DB by title.  This supplements vector search and is critical
        # when the vector store is empty or returns poor results.
        if self._repo:
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
                        enum_val(net)
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
                                enum_val(net)
                                for net in neighbor.networks
                            ],
                            "properties": neighbor.properties,
                        })
                    # Include edges for relationship context
                    if subgraph.edges and "edges" not in context:
                        context["edges"] = []
                    for edge in subgraph.edges:
                        context.setdefault("edges", []).append({
                            "source_id": str(edge.source_id),
                            "target_id": str(edge.target_id),
                            "edge_type": edge.edge_type.value
                                if hasattr(edge.edge_type, "value")
                                else str(edge.edge_type),
                            "properties": edge.properties,
                        })
                except Exception:
                    logger.debug("Neighborhood expansion failed for entity %s", nid)

        # If entity lookup found nodes, upgrade retrieval quality from poor
        if context["nodes"] and context.get("retrieval_quality") == "poor":
            context["retrieval_quality"] = "sufficient"
            logger.info(
                "Entity lookup found %d nodes, upgraded retrieval quality",
                len(context["nodes"]),
            )

    def _llm_synthesize(
        self, query: str, raw_synthesis: str, outputs: list[dict[str, Any]],
    ) -> str:
        """Use the LLM to produce a coherent, readable synthesis from agent outputs."""
        import openai as _openai

        agent_sections = []
        for out in outputs:
            agent = out.get("agent", "unknown")
            content = out.get("content", "")
            conf = out.get("confidence", 0.5)
            if content:
                agent_sections.append(
                    f"## {agent.title()} (confidence: {conf:.0%})\n{content}"
                )

        prompt = (
            "You are synthesizing outputs from multiple AI agents into a single, "
            "clear response for the user. Write in a natural, readable style — "
            "no JSON, no agent labels, no technical metadata. "
            "Organize the information logically with clear paragraphs. "
            "If agents disagree, note the tension. "
            "Be concise and actionable.\n\n"
            f"User's question: {query}\n\n"
            f"Agent outputs:\n{''.join(agent_sections)}"
        )

        try:
            client = _openai.OpenAI(api_key=self._api_key)
            from memora.config import DEFAULT_LLM_MODEL
            response = client.responses.create(
                model=DEFAULT_LLM_MODEL,
                input=prompt,
                max_output_tokens=2048,
            )
            return response.output_text.strip()
        except Exception as e:
            logger.warning("LLM synthesis failed, using fallback: %s", e)
            # Fallback: return the highest-confidence agent's content
            best = max(outputs, key=lambda o: o.get("confidence", 0))
            return best.get("content", raw_synthesis)

    def _fact_check_synthesis(self, synthesis_text: str) -> str | None:
        """Check synthesis against Truth Layer verified facts."""
        if not self._truth_layer:
            return None
        try:
            # Query facts that might be relevant
            facts = self._truth_layer.query_facts(status="active", limit=20)
            if not facts:
                return None

            # Stopwords to exclude from overlap matching
            _stopwords = {
                "the", "a", "an", "is", "are", "was", "were", "be", "been",
                "being", "have", "has", "had", "do", "does", "did", "will",
                "would", "could", "should", "may", "might", "can", "shall",
                "to", "of", "in", "for", "on", "with", "at", "by", "from",
                "as", "into", "through", "during", "before", "after", "and",
                "but", "or", "nor", "not", "no", "so", "if", "then", "than",
                "too", "very", "just", "about", "above", "also", "both",
                "each", "few", "more", "most", "other", "some", "such",
                "that", "this", "these", "those", "it", "its", "i", "my",
                "me", "we", "our", "you", "your", "he", "she", "they",
                "his", "her", "their", "what", "which", "who", "when",
                "where", "how", "all", "any", "there", "here",
            }

            contradictions = []
            synth_words = {
                w for w in synthesis_text.lower().split()
                if w not in _stopwords and len(w) > 2
            }
            for fact in facts:
                statement = fact.get("statement", "")
                if not statement:
                    continue
                fact_words = {
                    w for w in statement.lower().split()
                    if w not in _stopwords and len(w) > 2
                }
                overlap = fact_words & synth_words
                if len(overlap) >= 3:
                    contradictions.append(
                        f"Verified fact: \"{statement}\" "
                        f"(confidence: {fact.get('confidence', '?')})"
                    )

            if contradictions:
                return "Relevant verified facts: " + "; ".join(contradictions[:5])
        except Exception:
            logger.debug("Fact-check gate failed", exc_info=True)
        return None

    def _state_to_result(self, state: CouncilState) -> OrchestratorResult:
        """Convert final LangGraph state to OrchestratorResult."""
        agent_outputs = []
        for key in ("archivist_output", "strategist_output", "researcher_output"):
            output = state.get(key)
            if output and "error" not in output:
                agent_outputs.append(output)

        query_type = QueryType.ANALYSIS
        try:
            query_type = QueryType(state.get("query_type", "analysis"))
        except ValueError:
            pass

        return OrchestratorResult(
            query_id=state.get("query_id", ""),
            query_type=query_type,
            synthesis=state.get("synthesis", ""),
            agent_outputs=agent_outputs,
            confidence=state.get("confidence", 0.0),
            citations=state.get("citations", []),
            deliberation_rounds=state.get("deliberation_round", 0),
            high_disagreement=state.get("high_disagreement", False),
        )
