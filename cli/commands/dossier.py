"""Dossier command — intent-aware entity intelligence hub.

Classifies user input into PROFILE / QUESTION / EXPLORE intents,
then routes to enhanced profile view, graph-traversal Q&A, or investigate mode.
"""

from __future__ import annotations

import re
from enum import Enum, auto

from cli.rendering import (
    C, DOSSIER_CONFIG, NETWORK_ICONS, NODE_ICONS,
    divider, horizontal_bar, prompt, subcommand_header,
)
from cli.commands.browse import render_node_detail, render_ascii_graph


# ── Intent Classification ────────────────────────────────────────

class DossierIntent(Enum):
    PROFILE = auto()
    QUESTION = auto()
    EXPLORE = auto()


_QUESTION_WORDS = {"what", "how", "who", "where", "when", "why", "which", "does", "do", "is", "are", "can", "has", "have"}

_EXPLORE_PATTERNS = [
    re.compile(r"\bpath\s+between\b", re.I),
    re.compile(r"\bconnection[s]?\s+between\b", re.I),
    re.compile(r"\bhow\s+(?:are|is)\s+\w+\s+(?:and|&)\s+\w+\s+(?:connected|related|linked)\b", re.I),
]

_PROFILE_PATTERNS = [
    re.compile(r"^who\s+is\b", re.I),
    re.compile(r"^tell\s+me\s+about\b", re.I),
    re.compile(r"^show\s+me\b", re.I),
    re.compile(r"^details?\s+(?:on|for|about)\b", re.I),
]

# Keywords that signal a question about attributes/relationships
_QUESTION_FOCUS_KEYWORDS = {
    "status", "investigation", "commitment", "commitments", "decision", "decisions",
    "goal", "goals", "progress", "outcome", "outcomes", "pattern", "patterns",
    "responsible", "working", "involved", "budget", "timeline", "deadline",
    "project", "projects", "task", "tasks", "role", "plan", "plans",
}

# Maps question focus keywords to expected node types and edge types for traversal
QUESTION_TYPE_MAP: dict[str, tuple[list[str] | None, list[str] | None]] = {
    "commitment":    (["COMMITMENT"], ["COMMITTED_TO"]),
    "commitments":   (["COMMITMENT"], ["COMMITTED_TO"]),
    "investigation": (["PROJECT", "GOAL"], ["RESPONSIBLE_FOR"]),
    "decision":      (["DECISION"], ["DECIDED"]),
    "decisions":     (["DECISION"], ["DECIDED"]),
    "goal":          (["GOAL"], ["RESPONSIBLE_FOR", "PART_OF"]),
    "goals":         (["GOAL"], ["RESPONSIBLE_FOR", "PART_OF"]),
    "project":       (["PROJECT"], ["RESPONSIBLE_FOR", "PART_OF"]),
    "projects":      (["PROJECT"], ["RESPONSIBLE_FOR", "PART_OF"]),
    "task":          (["PROJECT", "GOAL", "COMMITMENT"], ["RESPONSIBLE_FOR", "PART_OF", "SUBTASK_OF"]),
    "tasks":         (["PROJECT", "GOAL", "COMMITMENT"], ["RESPONSIBLE_FOR", "PART_OF", "SUBTASK_OF"]),
    "budget":        (["FINANCIAL_ITEM"], ["RELATED_TO", "PART_OF"]),
    "role":          (["PROJECT", "GOAL"], ["RESPONSIBLE_FOR", "MEMBER_OF"]),
    "plan":          (["PROJECT", "GOAL"], ["PART_OF", "RESPONSIBLE_FOR"]),
    "plans":         (["PROJECT", "GOAL"], ["PART_OF", "RESPONSIBLE_FOR"]),
    "outcome":       (None, None),
    "outcomes":      (None, None),
    "pattern":       (None, None),
    "patterns":      (None, None),
    "status":        (None, None),
    "progress":      (None, None),
    "deadline":      (None, None),
    "timeline":      (None, None),
}


def _classify_intent(query: str) -> tuple[DossierIntent, dict]:
    """Classify user input into PROFILE/QUESTION/EXPLORE via heuristics.

    Returns (intent, metadata) where metadata contains:
      - entity_names: list[str] — extracted proper-noun candidates
      - question_focus: str | None — attribute/relationship focus for QUESTION
      - raw_query: str — original query
    """
    from memora.core.text_utils import extract_entity_candidates, extract_question_focus

    entity_names = extract_entity_candidates(query)
    question_focus = extract_question_focus(query)

    metadata = {
        "entity_names": entity_names,
        "question_focus": question_focus,
        "raw_query": query,
    }

    # EXPLORE: two+ entities with path/connection language
    for pattern in _EXPLORE_PATTERNS:
        if pattern.search(query):
            return DossierIntent.EXPLORE, metadata

    # PROFILE: explicit profile phrases
    for pattern in _PROFILE_PATTERNS:
        if pattern.search(query):
            return DossierIntent.PROFILE, metadata

    # QUESTION: question word + focus keyword overlap
    words_lower = set(query.lower().split())
    has_question_word = bool(words_lower & _QUESTION_WORDS)
    has_focus_keyword = bool(words_lower & _QUESTION_FOCUS_KEYWORDS)
    has_question_mark = "?" in query

    if (has_question_word or has_question_mark) and has_focus_keyword:
        return DossierIntent.QUESTION, metadata

    # If it looks like a question but no focus keyword, still try QUESTION
    if has_question_mark and question_focus:
        return DossierIntent.QUESTION, metadata

    # Default: PROFILE (bare entity name or generic lookup)
    return DossierIntent.PROFILE, metadata


# ── Entity Resolution ────────────────────────────────────────────

def _resolve_entity(app, query: str, entity_names: list[str] | None = None):
    """Search and score entities, returning the selected entity or None.

    When entity_names are provided (from intent classification), searches for
    each name individually instead of the full question string.
    """
    # 1. Hybrid search — use entity names when available, fall back to full query
    search_terms = entity_names if entity_names else [query]

    seen_ids: dict[str, object] = {}
    for term in search_terms:
        for node in app.repo.search_by_title(term, limit=DOSSIER_CONFIG["title_search_limit"]):
            seen_ids.setdefault(str(node.id), node)

    # Semantic fallback on the full query
    for node in _semantic_fallback(app, query):
        seen_ids.setdefault(str(node.id), node)

    # Proper-noun candidate fallback
    if not seen_ids:
        from memora.core.text_utils import extract_entity_candidates
        for candidate in extract_entity_candidates(query):
            for node in app.repo.search_by_title(candidate, limit=DOSSIER_CONFIG["title_search_limit"]):
                seen_ids.setdefault(str(node.id), node)

    all_matches = list(seen_ids.values())
    if not all_matches:
        print(f"\n  {C.DIM}No entities matching '{query}'.{C.RESET}")
        return None

    # Multi-signal scoring — compare against individual entity candidates
    from memora.core.text_utils import extract_entity_candidates as _extract
    candidates = entity_names or _extract(query)
    lower_candidates = [c.lower() for c in candidates] if candidates else [query.lower()]
    scored: list[tuple[float, object]] = []
    for node in all_matches:
        lt = node.title.lower()
        title_score = 0.0
        for lc in lower_candidates:
            if lt == lc:
                title_score = max(title_score, 0.50)
            elif lt.startswith(lc):
                title_score = max(title_score, 0.40)
            elif lc.startswith(lt):
                title_score = max(title_score, 0.35)
            elif lc in lt:
                title_score = max(title_score, 0.25)
        conf_score = node.confidence * 0.25
        decay_score = (node.decay_score or 0.5) * 0.15
        access_score = min(node.access_count / 100, 1.0) * 0.10
        score = title_score + conf_score + decay_score + access_score
        scored.append((score, node))
    scored.sort(key=lambda x: x[0], reverse=True)

    if len(scored) > 1:
        print(f"\n  {C.BOLD}{len(scored)} matches found:{C.RESET}\n")
        for i, (sc, n) in enumerate(scored, 1):
            icon = NODE_ICONS.get(n.node_type.value, " ")
            nets = " ".join(NETWORK_ICONS.get(nt.value, f"[{nt.value[0]}]") for nt in n.networks)
            print(f"  {C.DIM}{i:2}.{C.RESET} {icon} {C.BOLD}{n.title}{C.RESET}  {nets}  "
                  f"conf={n.confidence:.0%}  {C.DIM}{str(n.id)[:8]}{C.RESET}")
        choice = prompt(f"  Select [1-{len(scored)}, default 1]: ")
        try:
            idx = int(choice) - 1 if choice else 0
            entity = scored[idx][1]
        except (ValueError, IndexError):
            entity = scored[0][1]
    else:
        entity = scored[0][1]

    return entity


# ── Graph Traversal Q&A ──────────────────────────────────────────

def _answer_entity_question(app, entity, metadata: dict) -> dict | None:
    """Deterministic graph traversal to answer a question about an entity.

    Returns a structured result dict or None if no relevant data found:
      {
        "relevant_nodes": [...],
        "relevant_edges": [...],
        "outcomes": [...],
        "patterns": [...],
        "facts": [...],
      }
    """
    question_focus = metadata.get("question_focus", "") or ""
    focus_words = set(question_focus.lower().split())

    # Determine target node/edge types from question focus
    target_node_types: set[str] = set()
    target_edge_types: set[str] = set()
    check_properties = False

    for word in focus_words:
        if word in QUESTION_TYPE_MAP:
            node_types, edge_types = QUESTION_TYPE_MAP[word]
            if node_types is None:
                check_properties = True
            else:
                target_node_types.update(node_types)
            if edge_types:
                target_edge_types.update(edge_types)

    # Get 2-hop neighborhood
    subgraph = app.repo.get_neighborhood(entity.id, hops=DOSSIER_CONFIG["neighborhood_hops"])
    entity_str = str(entity.id)
    nodes_by_id = {str(n.id): n for n in subgraph.nodes}

    # Filter neighbors
    relevant_nodes = []
    relevant_edges = []

    for edge in subgraph.edges:
        src, tgt = str(edge.source_id), str(edge.target_id)
        neighbor_id = tgt if src == entity_str else src
        neighbor = nodes_by_id.get(neighbor_id)
        if not neighbor:
            continue

        etype = edge.edge_type.value if hasattr(edge.edge_type, "value") else str(edge.edge_type)
        ntype = neighbor.node_type.value if hasattr(neighbor.node_type, "value") else str(neighbor.node_type)

        score = 0.0

        # Type matching
        if target_node_types and ntype in target_node_types:
            score += 0.4
        if target_edge_types and etype in target_edge_types:
            score += 0.3

        # Property matching (for status/progress queries)
        if check_properties and neighbor.properties:
            for key in ("status", "progress", "state", "phase"):
                if key in neighbor.properties:
                    score += 0.5
                    break

        # Keyword overlap with title and content
        neighbor_text = (neighbor.title + " " + (neighbor.content or "")).lower()
        overlap = sum(1 for w in focus_words if w in neighbor_text)
        if overlap:
            score += 0.2 * min(overlap, 3)

        if score > 0:
            relevant_nodes.append((score, neighbor))
            relevant_edges.append(edge)

    # Sort by relevance score
    relevant_nodes.sort(key=lambda x: x[0], reverse=True)

    if not relevant_nodes and not check_properties:
        return None

    # Enrich top results with outcomes, patterns, facts
    top_node_ids = [str(n.id) for _, n in relevant_nodes[:10]]
    all_ids = [entity_str] + top_node_ids

    outcomes = []
    patterns = []
    facts = []
    for nid in all_ids[:5]:
        outcomes.extend(app.repo.get_outcomes_for_node(nid))
        patterns.extend(app.repo.get_patterns_for_node(nid, limit=DOSSIER_CONFIG["patterns_limit"]))

    facts = _get_facts(app, entity_str)

    # Filter outcomes/patterns by keyword relevance
    if focus_words:
        outcomes = [o for o in outcomes if any(w in (o.get("outcome_text", "") or "").lower() for w in focus_words)] or outcomes[:5]
        patterns = [p for p in patterns if any(w in (p.get("description", "") or "").lower() for w in focus_words)] or patterns[:5]

    return {
        "relevant_nodes": [(s, n) for s, n in relevant_nodes[:10]],
        "relevant_edges": relevant_edges[:10],
        "outcomes": outcomes[:DOSSIER_CONFIG["outcomes_limit"]],
        "patterns": patterns[:DOSSIER_CONFIG["patterns_limit"]],
        "facts": [f for f in facts if any(w in (f.get("statement", "") or "").lower() for w in focus_words)][:5] if focus_words else facts[:5],
    }


# ── LLM Answer Synthesis ─────────────────────────────────────────

def _synthesize_answer(app, query: str, entity, traversal: dict) -> str | None:
    """Use LLM to synthesize a natural language answer from traversal results.

    Falls back to None if no API key available, letting caller render structured data.
    """
    if not app._has_api_key:
        return None

    try:
        import openai
        from memora.core.retry import call_with_retry

        # Build context from traversal results
        context_parts = []
        context_parts.append(f"Entity: {entity.title} (type: {entity.node_type.value})")
        if entity.content:
            context_parts.append(f"Description: {entity.content[:200]}")

        for score, node in traversal["relevant_nodes"][:5]:
            ntype = node.node_type.value if hasattr(node.node_type, "value") else str(node.node_type)
            line = f"- {node.title} ({ntype})"
            if node.content:
                line += f": {node.content[:150]}"
            if node.properties:
                props = ", ".join(f"{k}={v}" for k, v in node.properties.items())
                line += f" [{props}]"
            context_parts.append(line)

        for outcome in traversal["outcomes"][:3]:
            context_parts.append(f"- Outcome: {outcome.get('outcome_text', '')}")

        for pattern in traversal["patterns"][:3]:
            context_parts.append(f"- Pattern: {pattern.get('description', '')}")

        for fact in traversal["facts"][:3]:
            context_parts.append(f"- Fact: {fact.get('statement', '')}")

        context = "\n".join(context_parts)

        system_prompt = (
            "You answer questions about entities in a personal knowledge graph. "
            "Be concise and direct. Cite specific data from the context. "
            "If the data is insufficient, say so clearly."
        )
        user_content = f"Question: {query}\n\nContext from knowledge graph:\n{context}"
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ]

        client = openai.OpenAI(api_key=app.settings.openai_api_key)

        # gpt-5-nano is a reasoning model — give generous token budget
        response = call_with_retry(
            client.chat.completions.create,
            model="gpt-5-nano",
            messages=messages,
            max_completion_tokens=2048,
            max_retries=2,
        )
        choice = response.choices[0]
        raw_content = choice.message.content
        finish = choice.finish_reason

        # If reasoning exhausted tokens with no visible output, retry with more
        if finish == "length" and not (raw_content or "").strip():
            response = call_with_retry(
                client.chat.completions.create,
                model="gpt-5-nano",
                messages=messages,
                max_completion_tokens=4096,
                max_retries=2,
            )
            raw_content = response.choices[0].message.content

        answer = (raw_content or "").strip()
        return answer if answer else None
    except Exception as e:
        print(f"  {C.DIM}(synthesis unavailable: {e}){C.RESET}")
        return None


def _render_answer(query: str, entity, traversal: dict, synthesis: str | None):
    """Render the Q&A answer — synthesized text or structured fallback."""
    print(f"\n{divider('═', C.INTEL)}")
    print(f"  {C.BOLD}{C.INTEL}ANSWER{C.RESET}  {C.DIM}re: {entity.title}{C.RESET}")
    print(divider('─', C.INTEL))

    if synthesis:
        # Wrap and print synthesized answer
        import textwrap
        for line in textwrap.wrap(synthesis, min(76, __import__('shutil').get_terminal_size((80, 24)).columns - 6)):
            print(f"  {C.BASE}{line}{C.RESET}")
    else:
        print(f"  {C.DIM}(No LLM available — showing structured results){C.RESET}")

    # Always show supporting evidence
    if traversal["relevant_nodes"]:
        print(f"\n  {C.BOLD}Relevant entities:{C.RESET}")
        for score, node in traversal["relevant_nodes"][:5]:
            icon = NODE_ICONS.get(node.node_type.value, " ")
            ntype = node.node_type.value if hasattr(node.node_type, "value") else str(node.node_type)
            title = node.title[:40]
            extras = []
            if node.properties:
                for key in ("status", "progress", "state", "phase"):
                    if key in node.properties:
                        extras.append(f"{key}={node.properties[key]}")
            extra_str = f"  {C.DIM}{', '.join(extras)}{C.RESET}" if extras else ""
            print(f"    {icon} {C.BOLD}{title}{C.RESET}  {C.DIM}[{ntype}]{C.RESET}{extra_str}")

    if traversal["outcomes"]:
        print(f"\n  {C.BOLD}Outcomes:{C.RESET}")
        for outcome in traversal["outcomes"][:3]:
            text = outcome.get("outcome_text", "")[:70]
            rating = outcome.get("rating", "")
            rating_str = f"  {C.DIM}({rating}){C.RESET}" if rating else ""
            print(f"    {C.SIGNAL}>{C.RESET} {text}{rating_str}")

    if traversal["patterns"]:
        print(f"\n  {C.BOLD}Patterns:{C.RESET}")
        for pattern in traversal["patterns"][:3]:
            desc = pattern.get("description", "")[:70]
            conf = pattern.get("confidence", 0)
            print(f"    {C.INTEL}~{C.RESET} {desc}  {C.DIM}conf={conf:.0%}{C.RESET}")

    if traversal["facts"]:
        print(f"\n  {C.BOLD}Supporting facts:{C.RESET}")
        for fact in traversal["facts"][:3]:
            print(f"    {C.GREEN}✓{C.RESET} {fact.get('statement', '')[:70]}")


# ── Enhanced Intelligence Profile ─────────────────────────────────

def _render_intelligence_profile(app, entity):
    """Render the full enhanced entity profile using ObjectViewBuilder."""
    from memora.core.object_view import ObjectViewBuilder

    entity_str = str(entity.id)

    # Build ObjectView with graph intelligence if available
    algorithms = None
    try:
        from memora.core.graph_algorithms import GraphAlgorithms
        algorithms = GraphAlgorithms(app.repo)
    except Exception:
        pass

    builder = ObjectViewBuilder(app.repo, algorithms=algorithms)
    view = builder.build(
        entity,
        neighborhood_hops=DOSSIER_CONFIG["neighborhood_hops"],
        facts_limit=DOSSIER_CONFIG["facts_limit"],
        patterns_limit=DOSSIER_CONFIG["patterns_limit"],
        outcomes_limit=DOSSIER_CONFIG["outcomes_limit"],
        bridges_limit=DOSSIER_CONFIG["bridges_limit"],
    )

    # Entity card
    print()
    render_node_detail(entity)

    # ── Graph Position (NEW — from Enhancement 1) ─────────────
    if view.centrality_rank or view.communities or view.pagerank_score:
        print(f"\n{divider('─', C.INTEL)}")
        print(f"  {C.BOLD}{C.INTEL}GRAPH POSITION{C.RESET}  {C.DIM}centrality & community analysis{C.RESET}")
        print(divider())
        if view.centrality_rank:
            print(f"  {C.INTEL}#{C.RESET} PageRank: #{view.centrality_rank}  "
                  f"{C.DIM}score={view.pagerank_score:.4f}{C.RESET}")
        if view.communities:
            comm_str = ", ".join(str(c) for c in view.communities)
            print(f"  {C.INTEL}⊂{C.RESET} Communities: {comm_str}")
        print(f"  {C.INTEL}°{C.RESET} Degree: {view.degree} direct connections")

    # Connections (from ObjectView)
    subgraph = app.repo.get_neighborhood(entity.id, hops=DOSSIER_CONFIG["neighborhood_hops"])
    min_strength = DOSSIER_CONFIG["connection_min_strength"]
    connections = _compute_connections(entity_str, subgraph)
    top_connections = _render_connections(connections, entity_str, min_strength)

    # Related entities
    neighborhood_ids = {str(n.id) for n in subgraph.nodes}
    related = _find_related(app, entity, neighborhood_ids)
    if related:
        print(f"\n{divider('─', C.MAGENTA)}")
        print(f"  {C.BOLD}{C.MAGENTA}RELATED ENTITIES ({len(related)}){C.RESET}  {C.DIM}semantically similar, not directly connected{C.RESET}")
        print(divider())
        for sim_score, rel_node in related:
            icon = NODE_ICONS.get(rel_node.node_type.value, " ")
            nets = " ".join(NETWORK_ICONS.get(nt.value, f"[{nt.value[0]}]") for nt in rel_node.networks)
            pct = f"{sim_score * 100:.0f}%"
            print(f"  {C.MAGENTA}~{C.RESET} {icon} {C.BOLD}{rel_node.title[:35]:<35}{C.RESET} "
                  f"{nets}  {C.DIM}similarity {pct}{C.RESET}")

    # ── Predicted Links (NEW — from Enhancement 1) ────────────
    if view.predicted_links:
        print(f"\n{divider('─', C.SIGNAL)}")
        print(f"  {C.BOLD}{C.SIGNAL}PREDICTED LINKS ({len(view.predicted_links)}){C.RESET}  {C.DIM}suggested missing connections{C.RESET}")
        print(divider())
        for pred in view.predicted_links[:5]:
            other_title = pred["target_title"] if pred["source_id"] == entity_str else pred["source_title"]
            print(f"  {C.SIGNAL}···{C.RESET} {C.BOLD}{other_title[:40]}{C.RESET}  "
                  f"{C.DIM}score={pred['score']:.3f}  common={pred['common_neighbors']}{C.RESET}")

    # Facts
    if view.facts:
        print(f"\n{divider('─', C.GREEN)}")
        print(f"  {C.BOLD}{C.GREEN}VERIFIED FACTS ({len(view.facts)}){C.RESET}")
        print(divider())
        for fact in view.facts[:15]:
            conf = fact.get("confidence", 0)
            lifecycle = fact.get("lifecycle", "")
            lc_color = C.GREEN if lifecycle == "static" else C.YELLOW
            statement = fact.get("statement", "")
            print(f"  {C.GREEN}✓{C.RESET} {statement[:70]}")
            print(f"    {horizontal_bar(conf, 10, C.GREEN)}  "
                  f"{lc_color}{lifecycle}{C.RESET}")
        if len(view.facts) > 15:
            print(f"    {C.DIM}... and {len(view.facts) - 15} more{C.RESET}")
    else:
        print(f"\n  {C.DIM}No verified facts for this entity.{C.RESET}")

    # Timeline
    if view.timeline:
        print(f"\n{divider('─', C.SIGNAL)}")
        print(f"  {C.BOLD}{C.SIGNAL}TIMELINE ({len(view.timeline)}){C.RESET}  {C.DIM}temporal connections{C.RESET}")
        print(divider())
        for item in view.timeline[:10]:
            icon = NODE_ICONS.get(item.node_type, " ")
            print(f"  {C.SIGNAL}>{C.RESET} {icon} {C.BOLD}{item.title[:40]}{C.RESET}  "
                  f"{C.DIM}[{item.edge_type}]  {item.date}{C.RESET}")

    # Patterns
    if view.patterns:
        print(f"\n{divider('─', C.INTEL)}")
        print(f"  {C.BOLD}{C.INTEL}PATTERNS ({len(view.patterns)}){C.RESET}  {C.DIM}detected behavioral patterns{C.RESET}")
        print(divider())
        for pat in view.patterns:
            desc = pat.get("description", "")[:65]
            conf = pat.get("confidence", 0)
            ptype = pat.get("pattern_type", "")
            action = pat.get("suggested_action", "")
            print(f"  {C.INTEL}~{C.RESET} {desc}")
            detail_parts = []
            if ptype:
                detail_parts.append(ptype)
            detail_parts.append(f"conf={conf:.0%}")
            if action:
                detail_parts.append(f"action: {action[:30]}")
            print(f"    {C.DIM}{' | '.join(detail_parts)}{C.RESET}")

    # Outcomes
    if view.outcomes:
        print(f"\n{divider('─', C.CONFIRM)}")
        print(f"  {C.BOLD}{C.CONFIRM}OUTCOMES ({len(view.outcomes)}){C.RESET}  {C.DIM}recorded results & consequences{C.RESET}")
        print(divider())
        for outcome in view.outcomes:
            text = outcome.get("outcome_text", "")[:65]
            rating = outcome.get("rating", "")
            recorded = outcome.get("recorded_at", "")
            date_str = str(recorded)[:10] if recorded else ""
            rating_color = C.CONFIRM if rating in ("positive", "success") else C.SIGNAL if rating in ("mixed", "neutral") else C.DANGER if rating in ("negative", "failure") else C.DIM
            print(f"  {C.CONFIRM}>{C.RESET} {text}")
            detail_parts = []
            if rating:
                detail_parts.append(f"{rating_color}{rating}{C.RESET}")
            if date_str:
                detail_parts.append(f"{C.DIM}{date_str}{C.RESET}")
            if detail_parts:
                print(f"    {'  '.join(detail_parts)}")

    # Bridges
    if view.bridges:
        print(f"\n{divider('─', C.WARM)}")
        print(f"  {C.BOLD}{C.WARM}BRIDGES ({len(view.bridges)}){C.RESET}  {C.DIM}cross-network connections{C.RESET}")
        print(divider())
        for bridge in view.bridges:
            src_net = bridge.get("source_network", "?")
            tgt_net = bridge.get("target_network", "?")
            desc = bridge.get("description", "")[:55]
            sim = bridge.get("similarity", 0)
            validated = bridge.get("llm_validated", False)
            check = f"{C.CONFIRM}✓{C.RESET}" if validated else f"{C.DIM}?{C.RESET}"
            print(f"  {C.WARM}◇{C.RESET} {desc}")
            print(f"    {check}  {C.DIM}{src_net} → {tgt_net}  similarity={sim:.0%}{C.RESET}")

    # ── Data Sources (NEW — from Enhancement 2) ──────────────
    if view.data_sources:
        print(f"\n{divider('─', C.DIM)}")
        print(f"  {C.BOLD}DATA SOURCES{C.RESET}  {C.DIM}{', '.join(view.data_sources)}{C.RESET}")

    # Graph summary
    print(f"\n{divider('─', C.BLUE)}")
    print(f"  {C.BOLD}{C.BLUE}SUBGRAPH{C.RESET}  "
          f"{C.BOLD}{view.subgraph_nodes}{C.RESET} nodes  {C.DIM}|{C.RESET}  "
          f"{C.BOLD}{view.subgraph_edges}{C.RESET} edges  {C.DIM}(2-hop neighborhood){C.RESET}")

    return subgraph, connections, top_connections


# ── Interactive Actions ───────────────────────────────────────────

def _interactive_actions(app, entity, subgraph, connections, top_connections):
    """Enhanced interactive action menu."""
    entity_str = str(entity.id)
    min_strength = DOSSIER_CONFIG["connection_min_strength"]

    drill_hint = f"[1-{len(top_connections)}] Drill  " if top_connections else ""
    print(f"\n  {C.DIM}{drill_hint}[t] Timeline  [p] Patterns  [o] Outcomes  [v] Visualize  [i] Investigate  [m] Compare  [q] Back{C.RESET}")
    action = prompt("dossier> ").strip()

    if action == "v":
        render_ascii_graph(subgraph, center_id=entity.id)
    elif action == "i":
        from cli.commands.investigate import cmd_investigate
        cmd_investigate(app, prefill_query=f"tell me about {entity.title}")
    elif action == "t":
        _drill_timeline(app, entity_str)
    elif action == "p":
        _drill_patterns(app, entity_str)
    elif action == "o":
        _drill_outcomes(app, entity_str)
    elif action == "m":
        _compare_mode(app, entity)
    elif action.isdigit() and top_connections:
        idx = int(action) - 1
        if 0 <= idx < len(top_connections):
            _, _, drill_node = top_connections[idx]
            print(f"\n  {C.DIM}Drilling into {drill_node.title}...{C.RESET}")
            render_node_detail(drill_node)

            drill_sub = app.repo.get_neighborhood(drill_node.id, hops=DOSSIER_CONFIG["neighborhood_hops"])
            drill_str = str(drill_node.id)
            drill_conns = _compute_connections(drill_str, drill_sub, exclude_id=entity_str)
            _render_connections(drill_conns, drill_str, min_strength)
        else:
            print(f"  {C.DIM}Invalid selection.{C.RESET}")


def _drill_timeline(app, entity_str: str):
    """Show expanded timeline view."""
    try:
        temporal = app.repo.get_temporal_neighbors(entity_str)
        if not temporal:
            print(f"\n  {C.DIM}No timeline data.{C.RESET}")
            return
        print(f"\n{divider('═', C.SIGNAL)}")
        print(f"  {C.BOLD}{C.SIGNAL}FULL TIMELINE ({len(temporal)}){C.RESET}")
        print(divider('─', C.SIGNAL))
        for item in temporal:
            etype = item.get("edge_type", "")
            title = item.get("title", "unknown")[:50]
            ntype = item.get("node_type", "")
            created = item.get("created_at", "")
            icon = NODE_ICONS.get(ntype, " ")
            date_str = str(created)[:10] if created else ""
            print(f"  {C.SIGNAL}>{C.RESET} {icon} {C.BOLD}{title}{C.RESET}  "
                  f"{C.DIM}[{etype}]  {date_str}{C.RESET}")
    except Exception as e:
        print(f"  {C.DIM}(timeline unavailable: {e}){C.RESET}")


def _drill_patterns(app, entity_str: str):
    """Show expanded patterns view."""
    try:
        patterns = app.repo.get_patterns_for_node(entity_str, limit=20)
        if not patterns:
            print(f"\n  {C.DIM}No patterns detected.{C.RESET}")
            return
        print(f"\n{divider('═', C.INTEL)}")
        print(f"  {C.BOLD}{C.INTEL}ALL PATTERNS ({len(patterns)}){C.RESET}")
        print(divider('─', C.INTEL))
        for pat in patterns:
            desc = pat.get("description", "")
            conf = pat.get("confidence", 0)
            ptype = pat.get("pattern_type", "")
            action = pat.get("suggested_action", "")
            status = pat.get("status", "")
            print(f"  {C.INTEL}~{C.RESET} {desc[:70]}")
            detail_parts = []
            if ptype:
                detail_parts.append(ptype)
            detail_parts.append(f"conf={conf:.0%}")
            if status:
                detail_parts.append(status)
            if action:
                detail_parts.append(f"action: {action[:40]}")
            print(f"    {C.DIM}{' | '.join(detail_parts)}{C.RESET}")
    except Exception as e:
        print(f"  {C.DIM}(patterns unavailable: {e}){C.RESET}")


def _drill_outcomes(app, entity_str: str):
    """Show expanded outcomes view."""
    try:
        outcomes = app.repo.get_outcomes_for_node(entity_str)
        if not outcomes:
            print(f"\n  {C.DIM}No outcomes recorded.{C.RESET}")
            return
        print(f"\n{divider('═', C.CONFIRM)}")
        print(f"  {C.BOLD}{C.CONFIRM}ALL OUTCOMES ({len(outcomes)}){C.RESET}")
        print(divider('─', C.CONFIRM))
        for outcome in outcomes:
            text = outcome.get("outcome_text", "")
            rating = outcome.get("rating", "")
            recorded = outcome.get("recorded_at", "")
            date_str = str(recorded)[:10] if recorded else ""
            rating_color = C.CONFIRM if rating in ("positive", "success") else C.SIGNAL if rating in ("mixed", "neutral") else C.DANGER if rating in ("negative", "failure") else C.DIM
            print(f"  {C.CONFIRM}>{C.RESET} {text[:70]}")
            detail_parts = []
            if rating:
                detail_parts.append(f"{rating_color}{rating}{C.RESET}")
            if date_str:
                detail_parts.append(f"{C.DIM}{date_str}{C.RESET}")
            if detail_parts:
                print(f"    {'  '.join(detail_parts)}")
    except Exception as e:
        print(f"  {C.DIM}(outcomes unavailable: {e}){C.RESET}")


def _compare_mode(app, entity_a):
    """Compare two entities side by side."""
    query = prompt(f"  Compare '{entity_a.title}' with: ").strip()
    if not query:
        return

    entity_b = _resolve_entity(app, query)
    if not entity_b:
        return

    from memora.core.object_view import ObjectViewBuilder, compare_entities

    algorithms = None
    try:
        from memora.core.graph_algorithms import GraphAlgorithms
        algorithms = GraphAlgorithms(app.repo)
    except Exception:
        pass

    builder = ObjectViewBuilder(app.repo, algorithms=algorithms)
    comparison = compare_entities(builder, entity_a, entity_b)

    view_a = comparison["entity_a"]
    view_b = comparison["entity_b"]

    print(f"\n{divider('═', C.ACCENT)}")
    print(f"  {C.BOLD}{C.ACCENT}ENTITY COMPARISON{C.RESET}")
    print(divider('─', C.ACCENT))

    # Side by side metrics
    a_title = entity_a.title[:25]
    b_title = entity_b.title[:25]

    print(f"\n  {'Metric':<25} {a_title:<25} {b_title:<25}")
    print(f"  {'─' * 75}")
    print(f"  {'Connections':<25} {view_a.degree:<25} {view_b.degree:<25}")
    print(f"  {'Facts':<25} {len(view_a.facts):<25} {len(view_b.facts):<25}")
    print(f"  {'Patterns':<25} {len(view_a.patterns):<25} {len(view_b.patterns):<25}")
    print(f"  {'Outcomes':<25} {len(view_a.outcomes):<25} {len(view_b.outcomes):<25}")
    print(f"  {'Bridges':<25} {len(view_a.bridges):<25} {len(view_b.bridges):<25}")

    if view_a.centrality_rank and view_b.centrality_rank:
        print(f"  {'PageRank':<25} {'#' + str(view_a.centrality_rank):<25} {'#' + str(view_b.centrality_rank):<25}")

    print(f"\n  {C.BOLD}Overlap:{C.RESET}")
    print(f"    Shared connections: {comparison['shared_connections']}")
    print(f"    Unique to {a_title}: {comparison['a_unique_connections']}")
    print(f"    Unique to {b_title}: {comparison['b_unique_connections']}")
    if comparison['shared_communities']:
        print(f"    Shared communities: {comparison['shared_communities']}")


# ── Main Flow ─────────────────────────────────────────────────────

def cmd_dossier(app):
    subcommand_header(
        title="DOSSIER",
        symbol="◇",
        color=C.ACCENT,
        taglines=["Intent-aware entity intelligence", "Graph traversal · Pattern analysis · Q&A"],
        border="simple",
    )

    query = prompt(f"  {C.ACCENT}Entity name or question{C.RESET}\n  ❯ ")
    if not query or query == "q":
        return

    # 1. Classify intent
    intent, metadata = _classify_intent(query)

    # 2. Route EXPLORE to investigate
    if intent == DossierIntent.EXPLORE:
        print(f"\n  {C.DIM}Routing to investigation mode...{C.RESET}")
        from cli.commands.investigate import cmd_investigate
        cmd_investigate(app, prefill_query=query)
        return

    # 3. Resolve entity
    entity = _resolve_entity(app, query, metadata["entity_names"])
    if not entity:
        return

    # 4. Branch on intent
    if intent == DossierIntent.QUESTION:
        # Graph traversal Q&A
        traversal = _answer_entity_question(app, entity, metadata)
        if traversal and (traversal["relevant_nodes"] or traversal["outcomes"] or traversal["patterns"]):
            synthesis = _synthesize_answer(app, query, entity, traversal)
            _render_answer(query, entity, traversal, synthesis)

            # Offer to see full profile or investigate deeper
            print(f"\n  {C.DIM}[f] Full profile  [i] Investigate deeper  [q] Back{C.RESET}")
            action = prompt("dossier> ").strip()
            if action == "f":
                subgraph, connections, top_connections = _render_intelligence_profile(app, entity)
                _interactive_actions(app, entity, subgraph, connections, top_connections)
            elif action == "i":
                from cli.commands.investigate import cmd_investigate
                cmd_investigate(app, prefill_query=query)
        else:
            # No traversal results — fall back to enhanced profile
            print(f"\n  {C.DIM}No direct answer found — showing full profile.{C.RESET}")
            subgraph, connections, top_connections = _render_intelligence_profile(app, entity)
            _interactive_actions(app, entity, subgraph, connections, top_connections)
    else:
        # PROFILE intent — enhanced profile
        subgraph, connections, top_connections = _render_intelligence_profile(app, entity)
        _interactive_actions(app, entity, subgraph, connections, top_connections)


# ── Existing Helpers (preserved) ──────────────────────────────────

def _compute_connections(node_id_str, subgraph, exclude_id=None):
    direct_edges = [e for e in subgraph.edges
                    if str(e.source_id) == node_id_str or str(e.target_id) == node_id_str]
    nodes_by_id = {str(n.id): n for n in subgraph.nodes}

    connections = []
    for edge in direct_edges:
        neighbor_id = str(edge.target_id) if str(edge.source_id) == node_id_str else str(edge.source_id)
        if exclude_id and neighbor_id == exclude_id:
            continue
        neighbor_node = nodes_by_id.get(neighbor_id)
        if neighbor_node:
            strength = (
                edge.weight * 0.4
                + edge.confidence * 0.3
                + neighbor_node.confidence * 0.2
                + (neighbor_node.decay_score or 0.5) * 0.1
            )
            connections.append((strength, edge, neighbor_node))
    connections.sort(key=lambda x: x[0], reverse=True)
    return connections


def _render_connections(connections, node_id_str, min_strength):
    top = [(s, e, n) for s, e, n in connections if s >= min_strength]
    if not connections:
        print(f"\n  {C.DIM}No direct connections.{C.RESET}")
        return []
    hidden = len(connections) - len(top)
    print(f"\n{divider('─', C.CYAN)}")
    print(f"  {C.BOLD}{C.CYAN}CONNECTIONS ({len(top)}){C.RESET}  {C.DIM}sorted by strength, ≥{min_strength:.0%}{C.RESET}")
    print(divider())
    for i, (strength, edge, neighbor) in enumerate(top, 1):
        direction = "→" if str(edge.source_id) == node_id_str else "←"
        icon = NODE_ICONS.get(neighbor.node_type.value, " ")
        etype = edge.edge_type.value if hasattr(edge.edge_type, 'value') else str(edge.edge_type)
        bar = horizontal_bar(min(strength, 1.0), 10, C.CYAN)
        print(f"  {C.DIM}{i}.{C.RESET} {C.CYAN}{direction}{C.RESET} {icon} {C.BOLD}{neighbor.title[:35]:<35}{C.RESET} "
              f"{C.DIM}[{etype}]{C.RESET}  {bar}")
    if hidden:
        print(f"    {C.DIM}... {hidden} weaker connections below {min_strength:.0%}{C.RESET}")
    return top


def _semantic_fallback(app, query: str) -> list:
    try:
        engine = app._get_embedding_engine()
        store = app._get_vector_store()
        if not engine or not store:
            return []
        embedding = engine.embed_text(query)
        results = store.dense_search(query_vector=embedding["dense"], top_k=DOSSIER_CONFIG["title_search_limit"])
        min_score = DOSSIER_CONFIG["semantic_min_score"]
        qualified_ids = [sr.node_id for sr in results if sr.score >= min_score]
        if not qualified_ids:
            return []
        nodes_map = app.repo.get_nodes_batch(qualified_ids)
        return list(nodes_map.values())
    except Exception as e:
        print(f"  {C.DIM}(semantic search unavailable: {e}){C.RESET}")
        return []


def _find_related(app, entity, exclude_ids: set[str]) -> list[tuple[float, object]]:
    try:
        engine = app._get_embedding_engine()
        store = app._get_vector_store()
        if not engine or not store:
            return []
        text = f"{entity.title} {entity.content or ''}"
        embedding = engine.embed_text(text)
        results = store.dense_search(query_vector=embedding["dense"], top_k=20)
        entity_str = str(entity.id)
        min_score = DOSSIER_CONFIG["related_min_score"]
        candidate_ids = [
            sr.node_id for sr in results
            if sr.node_id not in exclude_ids
            and sr.node_id != entity_str
            and sr.score >= min_score
        ]
        if not candidate_ids:
            return []
        nodes_map = app.repo.get_nodes_batch(candidate_ids)
        score_by_id = {sr.node_id: sr.score for sr in results}
        related = [
            (score_by_id[nid], nodes_map[nid])
            for nid in candidate_ids
            if nid in nodes_map
        ]
        related.sort(key=lambda x: x[0], reverse=True)
        return related
    except Exception as e:
        print(f"  {C.DIM}(vector search unavailable: {e}){C.RESET}")
        return []


def _get_facts(app, node_id: str) -> list[dict]:
    try:
        from memora.core.truth_layer import TruthLayer
        truth = TruthLayer(conn=app.repo.get_truth_layer_conn())
        return truth.query_facts(node_id=node_id, status="active", limit=DOSSIER_CONFIG["facts_limit"])
    except Exception as e:
        print(f"  {C.DIM}(facts query unavailable: {e}){C.RESET}")
        return []
