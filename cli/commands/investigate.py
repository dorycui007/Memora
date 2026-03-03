"""Investigate command — free-form natural language investigation mode."""

from __future__ import annotations

import json
import logging
import re

import openai

from cli.rendering import C, NETWORK_ICONS, NODE_ICONS, divider, health_bar, investigate_header, prompt, render_search_card, spinner
from memora.config import DEFAULT_LLM_MODEL
from memora.graph.models import enum_val
from memora.core.retry import call_with_retry

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You interpret natural language queries about a knowledge graph into structured actions.

Graph schema:
- node_types: EVENT, PERSON, COMMITMENT, DECISION, GOAL, FINANCIAL_ITEM, NOTE, IDEA, PROJECT, CONCEPT, REFERENCE, INSIGHT
- edge_types: PART_OF, CONTAINS, SUBTASK_OF, RELATED_TO, INSPIRED_BY, CONTRADICTS, SIMILAR_TO, COMPLEMENTS, DERIVED_FROM, VERIFIED_BY, SOURCE_OF, EXTRACTED_FROM, PRECEDED_BY, EVOLVED_INTO, TRIGGERED, CONCURRENT_WITH, COMMITTED_TO, DECIDED, FELT_ABOUT, RESPONSIBLE_FOR, KNOWS, INTRODUCED_BY, OWES_FAVOR, COLLABORATES_WITH, REPORTS_TO, BRIDGES, MEMBER_OF, IMPACTS, CORRELATES_WITH

Available actions:
- "expand": Show what a node is connected to. Use when asking about relationships, connections, "who works with", "what is related to", etc.
- "path": Find how two entities are connected. Use for "how are X and Y connected", "path between", "link between", "what is the connection between", "why are they related", etc.
- "common": Find entities shared by multiple nodes. Use for "what do X and Y have in common", "shared connections", etc.
- "summary": Get a full overview of a single entity. Use for "tell me about X", "what do I know about X", "details on X", etc.
- "bridges": Show cross-network connections. Use for "show bridges", "cross-network links", "what connects different areas", etc.
- "search": Just find and show matching entities. Use when the intent is vague or just searching.

Return JSON only, no explanation:
{
  "action": "<action>",
  "entities": ["<entity name 1>", ...],
  "filters": {"edge_types": [...], "node_types": [...], "networks": [...]},
  "hops": 1
}

Rules:
- Extract entity names as the user wrote them (e.g. "alice" not "Alice Johnson")
- filters is optional, omit if not needed
- Infer node_types from intent: questions about people → PERSON, events → EVENT, promises/obligations → COMMITMENT, choices → DECISION, objectives → GOAL, money → FINANCIAL_ITEM, ideas → IDEA, projects → PROJECT
- Infer edge_types from intent: "works with"/"collaborates" → COLLABORATES_WITH, "knows" → KNOWS, "reports to" → REPORTS_TO, "part of" → PART_OF, "inspired by" → INSPIRED_BY, "caused"/"triggered" → TRIGGERED
- hops defaults to 1, use 2-3 only if user asks for broader exploration
- For bridges, entities list can be empty
- For expand/summary, extract exactly 1 entity
- For path, extract exactly 2 entities
- For common, extract 2+ entities
- For "search", extract the TOPIC as entity names (e.g. "what about ML?" → entities: ["ML"])
- If the user's query is broad or exploratory, prefer "search" over "summary"
- Infer networks from context: "work stuff" → PROFESSIONAL, "family" → PERSONAL

Conversation continuity:
- Resolve pronouns ("they", "he", "she", "it", "them") from conversation history
- When comparing two previously mentioned entities, prefer "path" over "expand"
- Use entity names from prior results when the user refers back to them
"""


def cmd_investigate(app, prefill_query: str | None = None):
    """Free-form natural language investigation mode."""
    if not app._has_api_key:
        print(f"  {C.YELLOW}Investigation mode requires an OpenAI API key.{C.RESET}")
        return

    from memora.core.investigation import InvestigationEngine

    client = openai.OpenAI(api_key=app.settings.openai_api_key)
    engine = InvestigationEngine(app.repo)
    last_results = []
    history: list[dict] = []

    _print_header()

    first_query = prefill_query
    while True:
        if first_query:
            raw = first_query
            print(f"\n{C.BOLD}{C.ACCENT}investigate> {C.RESET}{raw}")
            first_query = None
        else:
            raw = prompt("investigate> ")
        if raw in ("b", "back", "q", "quit"):
            return
        if not raw:
            continue

        # Pivot: user typed a number to focus on a previous result
        if raw.isdigit() and last_results:
            idx = int(raw) - 1
            if 0 <= idx < len(last_results):
                node = last_results[idx]
                spinner("Loading summary")
                summary = engine.get_node_summary(node["id"])
                if summary:
                    last_results = _display_summary(summary, app)
                    # Track pivot in history
                    history.append({"role": "user", "content": f"[Pivoted to #{idx + 1}]"})
                    history.append({"role": "assistant", "content":
                        _build_context_summary("summary", [node], last_results)})
                    history = history[-20:]
                else:
                    print(f"  {C.DIM}Could not load node details.{C.RESET}")
                continue
            else:
                print(f"  {C.DIM}Invalid selection. Pick 1-{len(last_results)}.{C.RESET}")
                continue

        # LLM interprets the free-form query
        try:
            spinner("Thinking")
            parsed = _interpret_query(client, raw, history)
        except Exception as e:
            print(f"  {C.RED}Query interpretation failed:{C.RESET} {e}")
            print(f"  {C.DIM}Try rephrasing your question.{C.RESET}")
            continue

        action = parsed.get("action", "search")
        entity_names = parsed.get("entities", [])
        filters = parsed.get("filters", {})
        hops = parsed.get("hops", 1)

        logger.debug("Parsed query: action=%s entities=%s filters=%s", action, entity_names, filters)

        # Search bypasses entity resolution — it does its own content search
        if action == "search":
            spinner("Searching")
            search_results = []
            try:
                search_results = engine.search(
                    raw_query=raw,
                    entity_names=entity_names,
                    filters=filters,
                    embedding_engine=app._get_embedding_engine(),
                    vector_store=app._get_vector_store(),
                )
            except Exception as e:
                logger.debug("Search failed", exc_info=True)
                print(f"  {C.RED}Error:{C.RESET} {e}")

            # If search returned nothing but we have entity names, try resolving
            # them as graph nodes and expanding the first match
            if not search_results and entity_names:
                spinner("Resolving entities")
                resolved = _resolve_entities(app, entity_names)
                if resolved:
                    spinner("Expanding connections")
                    result = engine.expand(node_id=resolved[0]["id"], hops=1)
                    last_results = _display_expand(resolved[0], result)
                    context_summary = _build_context_summary("expand", resolved, last_results)
                else:
                    last_results = []
                    context_summary = ""
            else:
                last_results = _display_search_results(search_results)
                context_summary = _build_context_summary(action, [], last_results)

            # Append to conversation history
            history.append({"role": "user", "content": raw})
            if context_summary:
                history.append({"role": "assistant", "content": context_summary})
            history = history[-20:]

            if last_results:
                print(f"\n  {C.DIM}Ask more, or pick # to focus on a node.{C.RESET}")
            continue

        # Resolve entities semantically
        if entity_names:
            spinner("Resolving entities")
            entities = _resolve_entities(app, entity_names)
            if not entities and action != "bridges":
                print(f"  {C.DIM}Could not resolve any entities. Try different names.{C.RESET}")
                continue
        else:
            entities = []

        # Execute the action
        context_summary = ""
        result = {}
        try:
            if action == "expand" and entities:
                spinner("Expanding connections")
                result = engine.expand(
                    node_id=entities[0]["id"],
                    hops=min(hops, 3),
                    edge_types=filters.get("edge_types"),
                    node_types=filters.get("node_types"),
                )
                last_results = _display_expand(entities[0], result)
                context_summary = _build_context_summary(action, entities, last_results)

            elif action == "path" and len(entities) >= 2:
                spinner("Finding path")
                result = engine.find_path(entities[0]["id"], entities[1]["id"])
                if result.get("found"):
                    last_results = _display_path(entities[0], entities[1], result)
                    context_summary = _build_context_summary(action, entities, last_results)
                else:
                    # Path not found — fall back to expanding the first entity
                    # and highlighting the second entity in the results
                    spinner("Expanding connections")
                    result = engine.expand(
                        node_id=entities[0]["id"], hops=2,
                    )
                    last_results = _display_expand(entities[0], result)
                    context_summary = _build_context_summary("expand", entities, last_results)

            elif action == "common" and len(entities) >= 2:
                spinner("Finding common connections")
                node_ids = [e["id"] for e in entities]
                result = engine.find_common(node_ids)
                last_results = _display_common(entities, result)
                context_summary = _build_context_summary(action, entities, last_results)

            elif action == "summary" and entities:
                spinner("Loading summary")
                result = engine.get_node_summary(entities[0]["id"])
                if result:
                    last_results = _display_summary(result, app)
                else:
                    print(f"  {C.RED}Node not found.{C.RESET}")
                    last_results = []
                context_summary = _build_context_summary(action, entities, last_results)

            elif action == "bridges":
                spinner("Finding bridges")
                node_ids = [e["id"] for e in entities] if entities else None
                result = engine.highlight_bridges(node_ids)
                last_results = _display_bridges(result)
                context_summary = _build_context_summary(action, entities, last_results)

            else:
                if not entities and action != "bridges":
                    print(f"  {C.DIM}No entities found in your query. Try mentioning a name or topic.{C.RESET}")
                else:
                    print(f"  {C.DIM}Not enough entities for '{action}'. Try rephrasing.{C.RESET}")
                last_results = []

        except Exception as e:
            logger.debug("Investigation action failed", exc_info=True)
            print(f"  {C.RED}Error:{C.RESET} {e}")
            last_results = []

        # Synthesize a natural language answer for non-search, non-bridge actions
        answer = None
        if action not in ("search", "bridges") and entities and last_results:
            context = _gather_context(app, entities, action, result)
            if context:
                print()  # protect prior output from spinner \r overwrite
                spinner("Synthesizing")
                answer = _synthesize_answer(client, raw, context, history)
                if answer:
                    print(f"\n  {C.BOLD}{C.TEAL}>{C.RESET} {answer}")

        # Append to conversation history
        history.append({"role": "user", "content": raw})
        if answer:
            history.append({"role": "assistant", "content": answer})
        elif context_summary:
            history.append({"role": "assistant", "content": context_summary})
        history = history[-20:]

        if last_results:
            print(f"\n  {C.DIM}Ask more, or pick # to focus on a node.{C.RESET}")


def _gather_context(app, entities: list[dict], action: str, raw_result: dict) -> str:
    """Gather rich context from captures, truth layer, and node content for synthesis."""
    try:
        from uuid import UUID
        from memora.core.truth_layer import TruthLayer

        parts = []
        entity_ids = {e["id"] for e in entities}

        # 1. Source captures — the raw user text that created these entities.
        #    Shared captures (same capture produced multiple queried entities) are
        #    the strongest signal for explaining relationships.
        capture_ids: dict[str, list[str]] = {}  # capture_id -> [entity titles]
        for entity in entities:
            try:
                node_obj = app.repo.get_node(UUID(entity["id"]))
                if node_obj and node_obj.source_capture_id:
                    cid = str(node_obj.source_capture_id)
                    capture_ids.setdefault(cid, []).append(entity["title"])
            except Exception:
                pass

        # Sort: shared captures first (mentioned multiple entities), then individual
        sorted_cids = sorted(capture_ids.keys(), key=lambda c: len(capture_ids[c]), reverse=True)
        seen_captures = 0
        for cid in sorted_cids:
            if seen_captures >= 3:
                break
            try:
                capture = app.repo.get_capture(UUID(cid))
                if capture and capture.raw_content:
                    who = ", ".join(capture_ids[cid])
                    label = "Shared source" if len(capture_ids[cid]) > 1 else f"Source for {who}"
                    parts.append(f"{label}: {capture.raw_content[:300]}")
                    seen_captures += 1
            except Exception:
                pass

        # 2. Also search for captures that mention entity names but weren't the
        #    direct source (e.g. a later capture referencing an existing person).
        if entities:
            try:
                entity_names_lower = [e["title"].lower() for e in entities]
                recent = app.repo.list_captures(limit=30)
                for cap in recent:
                    if str(cap.id) in capture_ids:
                        continue  # already included above
                    text_lower = cap.raw_content.lower()
                    matches = sum(1 for name in entity_names_lower if name in text_lower)
                    # For path/common queries, include captures mentioning ANY entity
                    min_matches = 1 if action in ("path", "common") else (
                        1 if len(entities) == 1 else 2
                    )
                    if matches >= min_matches:
                        parts.append(f"Related capture: {cap.raw_content[:250]}")
                        seen_captures += 1
                        if seen_captures >= 4:
                            break
            except Exception:
                logger.debug("Capture search failed", exc_info=True)

        # 3. Truth layer facts for each entity
        try:
            truth_layer = TruthLayer(app.repo.get_truth_layer_conn())
            for entity in entities:
                facts = truth_layer.query_facts(
                    node_id=entity["id"], status="active", limit=3,
                )
                for fact in facts:
                    stmt = fact.get("statement", "")
                    if stmt:
                        parts.append(f"Fact about {entity['title']}: {stmt[:150]}")
        except Exception:
            logger.debug("Truth layer context failed", exc_info=True)

        # 4. Node content for each entity
        for entity in entities:
            try:
                node_obj = app.repo.get_node(UUID(entity["id"]))
                if node_obj and node_obj.content:
                    parts.append(f"{entity['title']}: {node_obj.content[:200]}")
            except Exception:
                pass

        # 5. Path edge details (for path action)
        if action == "path":
            hops = raw_result.get("hops", [])
            for hop in hops:
                edge = hop.get("edge")
                if edge:
                    from_title = hop.get("from", {}).get("title", "?")
                    to_title = hop.get("to", {}).get("title", "?")
                    etype = edge.get("edge_type", "RELATED_TO")
                    props = edge.get("properties", {})
                    detail = f"Edge: {from_title} --[{etype}]--> {to_title}"
                    if props:
                        detail += f" (properties: {str(props)[:80]})"
                    parts.append(detail)

        # 6. If we still have no context, include the entities' connections
        #    as minimal context so the LLM has something to work with.
        if not parts:
            for entity in entities:
                try:
                    edges = app.repo.get_edges(UUID(entity["id"]))
                    connected_ids = set()
                    for e in edges:
                        connected_ids.add(str(e.source_id))
                        connected_ids.add(str(e.target_id))
                    connected_ids.discard(entity["id"])
                    if connected_ids:
                        connected_nodes = app.repo.get_nodes_batch(list(connected_ids))
                        conn_names = []
                        for e in edges:
                            other_id = str(e.target_id) if str(e.source_id) == entity["id"] else str(e.source_id)
                            other = connected_nodes.get(other_id)
                            if other:
                                etype = enum_val(e.edge_type)
                                conn_names.append(f"{other.title} ({etype})")
                        if conn_names:
                            parts.append(f"{entity['title']} is connected to: {', '.join(conn_names[:8])}")
                except Exception:
                    pass

        # Cap total context at ~2000 chars
        context = "\n".join(parts)
        if len(context) > 2000:
            context = context[:2000] + "..."
        return context

    except Exception:
        logger.debug("Context gathering failed", exc_info=True)
        return ""


_SYNTHESIS_SYSTEM_PROMPT = (
    "You are a knowledge graph assistant. Given the source captures and facts below, "
    "answer the user's question directly in 1-3 sentences. Focus on the SUBSTANCE of "
    "relationships — why people know each other, what they worked on together, what "
    "events connect them — not graph structure like edge types or node labels. "
    "Draw from the original captured text to explain the real-world connection. "
    "If context is insufficient to explain the relationship, say so briefly."
)


def _synthesize_answer(
    client: openai.OpenAI,
    user_query: str,
    context: str,
    history: list[dict],
) -> str | None:
    """Synthesize a natural language answer from gathered context."""
    if not context:
        return None

    try:
        # Include recent history for continuity
        history_text = ""
        if history:
            recent = history[-6:]
            lines = []
            for msg in recent:
                prefix = "User" if msg["role"] == "user" else "Assistant"
                lines.append(f"{prefix}: {msg['content']}")
            history_text = "\nRecent conversation:\n" + "\n".join(lines) + "\n"

        user_content = (
            f"Context:\n{context}\n"
            f"{history_text}\n"
            f"Question: {user_query}"
        )

        # gpt-5-nano is a reasoning model — provide generous token budget
        # so it has room for internal reasoning plus visible output.
        response = call_with_retry(
            client.chat.completions.create,
            model=DEFAULT_LLM_MODEL,
            messages=[
                {"role": "system", "content": _SYNTHESIS_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            max_completion_tokens=2048,
        )
        choice = response.choices[0]
        raw_content = choice.message.content
        finish = choice.finish_reason
        logger.debug("Synthesis raw: finish=%s content=%r", finish, (raw_content or "")[:200])

        # If the model hit the token limit (used all budget on reasoning),
        # retry with even more headroom.
        if finish == "length" and not (raw_content or "").strip():
            response = call_with_retry(
                client.chat.completions.create,
                model=DEFAULT_LLM_MODEL,
                messages=[
                    {"role": "system", "content": _SYNTHESIS_SYSTEM_PROMPT},
                    {"role": "user", "content": user_content},
                ],
                max_completion_tokens=4096,
            )
            choice = response.choices[0]
            raw_content = choice.message.content

        answer = (raw_content or "").strip()
        return answer if answer else None
    except Exception as exc:
        logger.warning("Synthesis failed: %s", exc)
        return None


def _print_header():
    investigate_header()


def _build_context_summary(action: str, entities: list[dict], results: list[dict]) -> str:
    """Build a concise context summary for conversation history."""
    entity_desc = ", ".join(
        f"{e['title']} ({e.get('node_type', '?')})" for e in entities
    ) if entities else "none"

    if action == "expand" and entities:
        if results:
            connections = ", ".join(
                f"{r['title']} ({r.get('node_type', '?')})" for r in results[:6]
            )
            more = f", ... and {len(results) - 6} more" if len(results) > 6 else ""
            return (f"Expanded {entity_desc}. "
                    f"Found {len(results)} connections: {connections}{more}.")
        return f"Expanded {entity_desc}. No connections found."

    if action == "path":
        if results:
            steps = " → ".join(r["title"] for r in results)
            return (f"Found path between {entity_desc} "
                    f"({len(results)} steps): {steps}.")
        return f"No path found between {entity_desc}."

    if action == "common":
        if results:
            shared = ", ".join(r["title"] for r in results[:6])
            return f"Common connections of {entity_desc}: {shared}."
        return f"No common connections found for {entity_desc}."

    if action == "summary" and entities:
        if results:
            connections = ", ".join(
                f"{r['title']} ({r.get('node_type', '?')})" for r in results[:6]
            )
            return (f"Summary of {entity_desc}. "
                    f"Connected to: {connections}.")
        return f"Summary of {entity_desc}. No connections."

    if action == "bridges":
        return f"Showed cross-network bridges."

    if action == "search":
        items = []
        for r in results[:6]:
            snippet = (r.get("content_snippet") or "")[:60]
            items.append(f"{r['title']} ({r.get('node_type', '?')}: {snippet})")
        return f"Search results: {'; '.join(items)}."

    return f"Action: {action}, entities: {entity_desc}."


def _interpret_query(client: openai.OpenAI, user_input: str, history: list[dict] | None = None) -> dict:
    """Use LLM to interpret a free-form query into a structured action."""
    # Build user message with conversation context inlined so the assistant
    # role only ever produces JSON (history as assistant messages confuses it).
    if history:
        context_lines = []
        for msg in history[-20:]:
            prefix = "User" if msg["role"] == "user" else "Result"
            context_lines.append(f"- {prefix}: {msg['content']}")
        context_block = "\n".join(context_lines)
        user_content = (
            f"Conversation so far:\n{context_block}\n\n"
            f"Current query: {user_input}"
        )
    else:
        user_content = user_input

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]

    # Try LLM interpretation up to 2 attempts (second with higher token limit)
    text = ""
    for attempt_tokens in (1024, 2048):
        try:
            response = call_with_retry(
                client.chat.completions.create,
                model=DEFAULT_LLM_MODEL,
                messages=messages,
                max_completion_tokens=attempt_tokens,
            )
            text = (response.choices[0].message.content or "").strip()
            if text:
                break
        except Exception:
            if attempt_tokens == 2048:
                raise
            logger.debug("LLM interpret attempt failed, retrying with more tokens")

    # Strip markdown code fences if present
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.startswith("```")]
        text = "\n".join(lines)

    # Extract JSON from surrounding text if needed
    if text and not text.startswith("{"):
        start = text.find("{")
        end = text.rfind("}") + 1
        if start != -1 and end > start:
            text = text[start:end]

    # If LLM returned nothing usable, fall back to local pattern matching
    if not text:
        fallback = _fallback_interpret(user_input)
        if fallback:
            logger.debug("Using fallback interpretation for: %s", user_input)
            return fallback
        raise ValueError("Model returned empty response")

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        # JSON parse failed — try local fallback before raising
        fallback = _fallback_interpret(user_input)
        if fallback:
            logger.debug("LLM returned invalid JSON, using fallback for: %s", user_input)
            return fallback
        raise ValueError(f"Could not parse model response as JSON: {text[:100]}")

    # Validate and normalize
    valid_actions = {"expand", "path", "common", "summary", "bridges", "search"}
    if parsed.get("action") not in valid_actions:
        parsed["action"] = "search"
    if "entities" not in parsed:
        parsed["entities"] = []
    if "filters" not in parsed:
        parsed["filters"] = {}
    if "hops" not in parsed:
        parsed["hops"] = 1

    return parsed


# ── Local fallback patterns for when LLM fails ──────────────────────

# Regex patterns mapping common query shapes to actions.
# Each tuple: (compiled_regex, action, entity_group_indices, optional_filters)
_FALLBACK_PATTERNS: list[tuple[re.Pattern, str, list[int], dict]] = [
    # "Who is X working with" / "Who does X work with" / "Who does X collaborate with"
    (re.compile(
        r"(?:who\s+(?:is|does)\s+)(.+?)\s+(?:work|collaborate|working|collaborating)\s+with",
        re.IGNORECASE,
    ), "expand", [1], {}),

    # "What is X connected to" / "What is X related to"
    (re.compile(
        r"what\s+is\s+(.+?)\s+(?:connected|related|linked)\s+to",
        re.IGNORECASE,
    ), "expand", [1], {}),

    # "How are X and Y connected" / "connection between X and Y"
    (re.compile(
        r"(?:how\s+are\s+(.+?)\s+and\s+(.+?)\s+(?:connected|related|linked))"
        r"|(?:(?:connection|path|link|relationship)\s+between\s+(.+?)\s+and\s+(.+?))\s*\??$",
        re.IGNORECASE,
    ), "path", [1, 2, 3, 4], {}),

    # "Why is X connected with/to Y" / "How is X connected to Y" / "How is X a connection of Y"
    (re.compile(
        r"(?:why|how)\s+is\s+(.+?)\s+(?:connected\s+(?:with|to)|a\s+connection\s+of|related\s+to|linked\s+to)\s+(.+)",
        re.IGNORECASE,
    ), "path", [1, 2], {}),

    # "Why does X know Y" / "How does X know Y"
    (re.compile(
        r"(?:why|how)\s+does\s+(.+?)\s+(?:know|work\s+with|collaborate\s+with)\s+(.+)",
        re.IGNORECASE,
    ), "path", [1, 2], {}),

    # "Tell me about X" / "What do I know about X"
    (re.compile(
        r"(?:tell\s+me\s+about|what\s+do\s+(?:I|we)\s+know\s+about|details?\s+(?:on|about))\s+(.+?)[\?\.]?$",
        re.IGNORECASE,
    ), "summary", [1], {}),

    # "What do X and Y have in common"
    (re.compile(
        r"what\s+do\s+(.+?)\s+and\s+(.+?)\s+have\s+in\s+common",
        re.IGNORECASE,
    ), "common", [1, 2], {}),

    # "Show bridges" / "cross-network"
    (re.compile(
        r"(?:show\s+)?bridges|cross[\s-]network",
        re.IGNORECASE,
    ), "bridges", [], {}),
]


def _fallback_interpret(user_input: str) -> dict | None:
    """Attempt to interpret a query using local regex patterns.

    Returns a parsed dict on match, or None if no pattern matches.
    """
    query = user_input.strip().rstrip("?").strip()

    for pattern, action, groups, filters in _FALLBACK_PATTERNS:
        m = pattern.search(query)
        if not m:
            continue

        entities = []
        for g in groups:
            try:
                val = m.group(g)
                if val:
                    entities.append(val.strip())
            except IndexError:
                pass

        # Deduplicate while preserving order
        seen = set()
        unique = []
        for e in entities:
            if e.lower() not in seen:
                seen.add(e.lower())
                unique.append(e)

        return {
            "action": action,
            "entities": unique,
            "filters": filters,
            "hops": 1,
        }

    # No pattern matched — fall back with entity extraction
    # Extract likely entity names: capitalized multi-word sequences
    caps = re.findall(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)\b", user_input)
    if caps:
        # If query mentions 2+ entities and seems relational, use path
        relational = re.search(
            r"\b(?:connect|relation|between|with|know|work|link|why|how)\b",
            user_input, re.IGNORECASE,
        )
        if len(caps) >= 2 and relational:
            return {
                "action": "path",
                "entities": caps[:2],
                "filters": {},
                "hops": 1,
            }
        return {
            "action": "search",
            "entities": caps,
            "filters": {},
            "hops": 1,
        }

    # Single-word capitalized names as last resort
    single_caps = re.findall(r"\b([A-Z][a-z]{2,})\b", user_input)
    # Filter out common English words
    stopwords = {"The", "This", "That", "What", "Why", "How", "Who", "Where",
                 "When", "Which", "Are", "Was", "Were", "Has", "Have", "Does",
                 "Did", "Can", "Could", "Would", "Should", "May", "Will"}
    single_caps = [w for w in single_caps if w not in stopwords]
    if single_caps:
        relational = re.search(
            r"\b(?:connect|relation|between|with|know|work|link|why|how)\b",
            user_input, re.IGNORECASE,
        )
        if len(single_caps) >= 2 and relational:
            return {
                "action": "path",
                "entities": single_caps[:2],
                "filters": {},
                "hops": 1,
            }
        return {
            "action": "search",
            "entities": single_caps,
            "filters": {},
            "hops": 1,
        }

    return None


def _resolve_entities(app, entity_names: list[str]) -> list[dict]:
    """Resolve entity name strings to actual graph nodes using semantic + substring search."""
    resolved = []

    embedding_engine = app._get_embedding_engine()
    vector_store = app._get_vector_store()

    for name in entity_names:
        node = None

        # Try semantic search first (if vector infrastructure available)
        if embedding_engine and vector_store:
            try:
                vector = embedding_engine.embed_text(name)
                results = vector_store.hybrid_search(
                    query_vector=vector,
                    query_text=name,
                    top_k=5,
                )
                if results:
                    top = results[0]
                    if top.score > 0.7:
                        # Auto-select high-confidence match
                        node = _search_result_to_node(top, app)
                        if node:
                            print(f"  {C.DIM}Resolved:{C.RESET} {C.BOLD}{node['title']}{C.RESET}"
                                  f"  {C.DIM}({node['node_type']}, {top.score:.0%}){C.RESET}")
                    elif len(results) >= 2 and results[0].score > 0.4:
                        # Multiple close matches — let user pick
                        print(f"\n  {C.YELLOW}Multiple matches for '{name}':{C.RESET}")
                        candidates = []
                        for i, r in enumerate(results[:3], 1):
                            n = _search_result_to_node(r, app)
                            if n:
                                candidates.append(n)
                                icon = NODE_ICONS.get(n["node_type"], " ")
                                print(f"    {C.DIM}{i}.{C.RESET} {icon} {n['title']}"
                                      f"  {C.DIM}({n['node_type']}, {r.score:.0%}){C.RESET}")
                        if candidates:
                            pick = prompt(f"  Select # for '{name}' [1]: ")
                            try:
                                idx = int(pick) - 1 if pick else 0
                                node = candidates[idx]
                            except (ValueError, IndexError):
                                node = candidates[0]
            except Exception as e:
                logger.debug("Semantic search failed for '%s': %s", name, e)

        # Fall back to substring search
        if not node:
            try:
                results = app.repo.search_nodes_ilike(name, limit=5)
                if results:
                    if len(results) == 1:
                        node = results[0]
                        print(f"  {C.DIM}Resolved:{C.RESET} {C.BOLD}{node['title']}{C.RESET}"
                              f"  {C.DIM}({node['node_type']}){C.RESET}")
                    else:
                        print(f"\n  {C.YELLOW}Multiple matches for '{name}':{C.RESET}")
                        for i, n in enumerate(results[:5], 1):
                            icon = NODE_ICONS.get(n["node_type"], " ")
                            print(f"    {C.DIM}{i}.{C.RESET} {icon} {n['title']}"
                                  f"  {C.DIM}({n['node_type']}){C.RESET}")
                        pick = prompt(f"  Select # for '{name}' [1]: ")
                        try:
                            idx = int(pick) - 1 if pick else 0
                            node = results[idx]
                        except (ValueError, IndexError):
                            node = results[0]
                else:
                    print(f"  {C.DIM}Could not find '{name}'{C.RESET}")
            except Exception as e:
                logger.debug("Substring search failed for '%s': %s", name, e)
                print(f"  {C.DIM}Could not find '{name}'{C.RESET}")

        if node:
            # Normalize id to string
            node["id"] = str(node["id"])
            resolved.append(node)

    return resolved


def _search_result_to_node(result, app) -> dict | None:
    """Convert a vector SearchResult to a node dict by looking up in the graph."""
    try:
        from uuid import UUID
        node_obj = app.repo.get_node(UUID(result.node_id))
        if node_obj:
            return {
                "id": str(node_obj.id),
                "node_type": node_obj.node_type.value,
                "title": node_obj.title,
            }
    except Exception:
        pass
    # Fallback: construct from search result data
    return {
        "id": result.node_id,
        "node_type": result.node_type,
        "title": result.content[:80] if result.content else result.node_id[:8],
    }


# ── Display helpers ──────────────────────────────────────────────────


def _display_expand(focus_node: dict, result: dict) -> list[dict]:
    """Display expanded neighborhood and return numbered node list."""
    nodes = result.get("nodes", [])
    edges = result.get("edges", [])

    # Build edge info per node
    edge_info = {}
    focus_id = focus_node["id"]
    for e in edges:
        src = str(e.get("source_id", e.get("id", "")))
        tgt = str(e.get("target_id", ""))
        etype = e.get("edge_type", "RELATED_TO")
        if isinstance(etype, dict):
            etype = etype.get("value", str(etype))
        elif hasattr(etype, "value"):
            etype = etype.value

        if src == focus_id:
            edge_info[tgt] = etype
        elif tgt == focus_id:
            edge_info[src] = etype

    # Filter out the focus node itself
    display_nodes = [n for n in nodes if str(n.get("id", "")) != focus_id]

    print(f"\n  {C.BOLD}{focus_node['title']}{C.RESET} — connections:")
    print(f"  {C.DIM}{len(display_nodes)} nodes, {len(edges)} edges{C.RESET}\n")

    numbered = []
    for i, n in enumerate(display_nodes[:30], 1):
        nid = str(n.get("id", ""))
        ntype = n.get("node_type", "")
        if hasattr(ntype, "value"):
            ntype = ntype.value
        title = n.get("title", "?")
        icon = NODE_ICONS.get(ntype, " ")
        etype = edge_info.get(nid, "")

        print(f"    {C.DIM}{i:2d}.{C.RESET} {icon} {title}"
              f"  {C.DIM}({ntype}){C.RESET}"
              f"  {C.CYAN}→ {etype}{C.RESET}" if etype else
              f"    {C.DIM}{i:2d}.{C.RESET} {icon} {title}"
              f"  {C.DIM}({ntype}){C.RESET}")

        numbered.append({"id": nid, "title": title, "node_type": ntype})

    if len(display_nodes) > 30:
        print(f"\n  {C.DIM}... and {len(display_nodes) - 30} more{C.RESET}")

    return numbered


def _display_path(source: dict, target: dict, result: dict) -> list[dict]:
    """Display a path between two nodes."""
    if not result.get("found"):
        print(f"\n  {C.YELLOW}No path found{C.RESET} between "
              f"'{source['title']}' and '{target['title']}'")
        return []

    nodes = result.get("nodes", [])
    hops = result.get("hops", [])

    print(f"\n  {C.BOLD}Path{C.RESET} ({len(nodes)} steps):\n")

    numbered = []
    for i, n in enumerate(nodes):
        ntype = n.get("node_type", "")
        icon = NODE_ICONS.get(ntype, " ")
        title = n.get("title", "?")
        prefix = "  ┌─" if i == 0 else "  ├─" if i < len(nodes) - 1 else "  └─"

        # Show edge type between hops
        edge_label = ""
        if i < len(hops):
            edge = hops[i].get("edge", {})
            if edge:
                edge_label = f"  {C.DIM}[{edge.get('edge_type', '')}]{C.RESET}"

        print(f"  {C.CYAN}{prefix}{C.RESET} {icon} {n.get('title', '?')}"
              f"  {C.DIM}({ntype}){C.RESET}{edge_label}")
        if i < len(nodes) - 1:
            print(f"  {C.DIM}  │{C.RESET}")

        numbered.append({
            "id": str(n.get("id", "")),
            "title": title,
            "node_type": ntype,
        })

    return numbered


def _display_common(entities: list[dict], common: list[dict]) -> list[dict]:
    """Display common connections between entities."""
    names = ", ".join(e["title"] for e in entities)
    if not common:
        print(f"\n  {C.DIM}No common connections found between: {names}{C.RESET}")
        return []

    print(f"\n  {C.BOLD}Common Connections ({len(common)}):{C.RESET}")
    print(f"  {C.DIM}Shared by: {names}{C.RESET}\n")

    numbered = []
    for i, c in enumerate(common, 1):
        ntype = c.get("node_type", "")
        icon = NODE_ICONS.get(ntype, " ")
        print(f"    {C.DIM}{i:2d}.{C.RESET} {icon} {c.get('title', '?')}"
              f"  {C.DIM}({ntype}){C.RESET}")
        numbered.append(c)

    return numbered


def _display_summary(summary: dict, app) -> list[dict]:
    """Display a comprehensive node summary with pivotable connections."""
    n = summary["node"]
    title = n.get("title", "?")
    ntype = n.get("node_type", "")
    conf = n.get("confidence", 0)

    connections = summary.get("connections", [])
    facts = summary.get("facts", [])
    outcomes = summary.get("outcomes", [])

    # PERSON nodes get the extended search card
    if ntype == "PERSON":
        props = n.get("properties", {})
        networks = n.get("networks", [])

        # Build subtitle
        sub_parts = []
        if props.get("role"):
            sub_parts.append(props["role"])
        if props.get("organization"):
            sub_parts.append(props["organization"])
        if networks:
            net_badges = "".join(
                NETWORK_ICONS.get(net, f"[{net[0]}]") for net in networks
            )
            sub_parts.append(net_badges)
        subtitle = f"{C.DIM} · {C.RESET}".join(
            f"{C.BASE}{p}{C.RESET}" if i == 0 else p
            for i, p in enumerate(sub_parts)
        ) if sub_parts else ""

        # Edge summary lines
        edge_lines: list[str] = []
        try:
            edge_data = app.repo.get_edge_type_summary(str(n.get("id", "")))
            if edge_data:
                for es in edge_data[:5]:
                    arrow = "→" if es["direction"] == "outgoing" else "←"
                    edge_lines.append(
                        f"{C.ACCENT}{arrow}{C.RESET} {C.BOLD}{es['edge_type']}{C.RESET}"
                        f"  {C.DIM}{es['count']} node{'s' if es['count'] != 1 else ''}{C.RESET}"
                    )
        except Exception:
            pass

        # Also add top connection names
        if connections:
            by_etype: dict[str, list[str]] = {}
            for c in connections[:10]:
                et = c.get("edge_type", "RELATED_TO")
                by_etype.setdefault(et, []).append(c["title"])
            edge_lines = []
            for et, names in list(by_etype.items())[:5]:
                arrow = "→"
                name_str = ", ".join(names[:3])
                if len(names) > 3:
                    name_str += f" +{len(names) - 3}"
                edge_lines.append(
                    f"{C.ACCENT}{arrow}{C.RESET} {C.BOLD}{et}{C.RESET}  {C.BASE}{name_str}{C.RESET}"
                )

        # Footer
        footer: list[str] = []
        if facts:
            footer.append(f"{C.BOLD}Facts:{C.RESET} {len(facts)} verified")
        if outcomes:
            footer.append(f"{C.BOLD}Outcomes:{C.RESET} {len(outcomes)} tracked")

        decay = n.get("decay_score") or n.get("decay") or None

        render_search_card(
            name=title,
            subtitle=subtitle,
            confidence=conf,
            decay=decay,
            connections=len(connections),
            snippet=n.get("content", "")[:200] if n.get("content") else "",
            edge_summary=edge_lines,
            footer_parts=footer if footer else None,
        )

        # Build numbered list for pivoting
        numbered = []
        for c in connections[:20]:
            numbered.append({
                "id": c["node_id"],
                "title": c["title"],
                "node_type": c.get("node_type", ""),
            })
        if connections:
            print(f"\n  {C.BOLD}Connections ({len(connections)}):{C.RESET}\n")
            for i, c in enumerate(connections[:20], 1):
                icon = NODE_ICONS.get(c.get("node_type", ""), " ")
                arrow = "→" if c["direction"] == "outgoing" else "←"
                print(f"    {C.DIM}{i:2d}.{C.RESET} {arrow} {c['edge_type']:20s}"
                      f"  {icon} {c['title']}")
            if len(connections) > 20:
                print(f"\n  {C.DIM}... and {len(connections) - 20} more{C.RESET}")

        return numbered

    # Non-person: original rendering
    print(f"\n  {C.BOLD}{title}{C.RESET}"
          f"  {C.DIM}({ntype} | confidence: {conf:.0%}){C.RESET}")

    if n.get("content"):
        content = n["content"][:200]
        print(f"  {C.DIM}{content}{C.RESET}")

    # Edge type summary
    try:
        edge_summary = app.repo.get_edge_type_summary(str(n.get("id", "")))
        if edge_summary:
            print(f"\n  {C.BOLD}Edge overview:{C.RESET}")
            for es in edge_summary:
                arrow = "→" if es["direction"] == "outgoing" else "←"
                print(f"    {arrow} {es['edge_type']:20s} {C.DIM}{es['count']} node{'s' if es['count'] != 1 else ''}{C.RESET}")
    except Exception:
        pass

    # Connections (numbered for pivoting)
    numbered = []
    if connections:
        print(f"\n  {C.BOLD}Connections ({len(connections)}):{C.RESET}\n")
        for i, c in enumerate(connections[:20], 1):
            icon = NODE_ICONS.get(c.get("node_type", ""), " ")
            arrow = "→" if c["direction"] == "outgoing" else "←"
            print(f"    {C.DIM}{i:2d}.{C.RESET} {arrow} {c['edge_type']:20s}"
                  f"  {icon} {c['title']}")
            numbered.append({
                "id": c["node_id"],
                "title": c["title"],
                "node_type": c.get("node_type", ""),
            })
        if len(connections) > 20:
            print(f"\n  {C.DIM}... and {len(connections) - 20} more{C.RESET}")

    # Facts
    if facts:
        print(f"\n  {C.BOLD}Facts ({len(facts)}):{C.RESET}")
        for f in facts[:5]:
            claim = f.get("claim", "") if isinstance(f, dict) else str(f)
            print(f"    {C.DIM}•{C.RESET} {claim[:80]}")

    # Outcomes
    if outcomes:
        print(f"\n  {C.BOLD}Outcomes ({len(outcomes)}):{C.RESET}")
        for o in outcomes:
            color = {"positive": C.GREEN, "negative": C.RED, "mixed": C.MAGENTA}.get(
                o.get("rating", ""), C.YELLOW
            )
            print(f"    {color}●{C.RESET} [{o.get('rating', '?')}] {o.get('outcome_text', '')[:60]}")

    return numbered


def _display_bridges(bridges: list[dict]) -> list[dict]:
    """Display cross-network bridge connections."""
    if not bridges:
        print(f"\n  {C.DIM}No cross-network bridges found.{C.RESET}")
        return []

    print(f"\n  {C.BOLD}Cross-Network Bridges ({len(bridges)}):{C.RESET}\n")

    for b in bridges:
        validated = f"{C.GREEN}✓{C.RESET}" if b.get("meaningful") else f"{C.DIM}?{C.RESET}"
        sim = b.get("similarity", 0)
        print(f"    {validated} [{b.get('source_network', '?')}] ←→ [{b.get('target_network', '?')}]"
              f"  {C.DIM}sim={sim:.2f}{C.RESET}")
        if b.get("description"):
            print(f"      {C.DIM}{b['description'][:60]}{C.RESET}")

    return []


def _display_search_results(results: list[dict]) -> list[dict]:
    """Display enriched search results with snippets, connections, and confidence."""
    if not results:
        print(f"\n  {C.DIM}No results found.{C.RESET}")
        return []

    print(f"\n  {C.BOLD}Search — {len(results)} result{'s' if len(results) != 1 else ''}{C.RESET}\n")

    numbered = []
    for i, r in enumerate(results, 1):
        ntype = r.get("node_type", "")
        title = r.get("title", "?")
        networks = r.get("networks", [])
        conn_count = r.get("connection_count", 0)
        confidence = r.get("confidence", 0)
        snippet = r.get("content_snippet", "")

        if ntype == "PERSON":
            # Extended search card for person results
            props = r.get("properties", {})
            sub_parts = []
            if props.get("role"):
                sub_parts.append(props["role"])
            if props.get("organization"):
                sub_parts.append(props["organization"])
            if networks:
                net_badges = "".join(
                    NETWORK_ICONS.get(net, f"[{net[0]}]") for net in networks
                )
                sub_parts.append(net_badges)
            subtitle = f"{C.DIM} · {C.RESET}".join(sub_parts) if sub_parts else ""

            decay = r.get("decay_score") or r.get("decay") or None

            print(f"    {C.DIM}{i:2d}.{C.RESET}")
            render_search_card(
                name=title,
                subtitle=subtitle,
                confidence=confidence,
                decay=decay,
                connections=conn_count,
                snippet=snippet,
            )
        else:
            # Non-person: keep existing compact format
            icon = NODE_ICONS.get(ntype, " ")
            primary_net = networks[0].lower() if networks else ""

            print(f"    {C.DIM}{i:2d}.{C.RESET} {icon} {C.BOLD}{title}{C.RESET}")
            meta_parts = [ntype]
            if primary_net:
                meta_parts.append(primary_net)
            meta_parts.append(f"{conn_count} connection{'s' if conn_count != 1 else ''}")
            meta_parts.append(f"confidence: {confidence:.0%}")
            print(f"        {C.DIM}{'  |  '.join(meta_parts)}{C.RESET}")
            if snippet:
                print(f"        {C.DIM}\"{snippet}\"{C.RESET}")
            print()

        numbered.append(r)

    return numbered
