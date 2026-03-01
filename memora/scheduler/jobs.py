"""Background job implementations for the living graph engine."""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta
from typing import Any

logger = logging.getLogger(__name__)


# ── Helpers ──────────────────────────────────────────────────────────

def _elapsed(start: float) -> str:
    """Return a human-friendly elapsed-time string."""
    return f"{time.time() - start:.2f}s"


def _get_notification_manager(repo):
    """Build a NotificationManager from the repo's DuckDB connection.

    Attempts to hook up the global SSE manager for real-time push.
    """
    from memora.core.notifications import NotificationManager
    sse = None
    try:
        from memora.api.websocket import sse_manager
        sse = sse_manager
    except Exception:
        pass
    return NotificationManager(repo._conn, sse_manager=sse)


# ── Decay Scoring ────────────────────────────────────────────────────

async def run_decay_scoring(repo, settings=None) -> None:
    """Recompute decay scores for all nodes."""
    start = time.time()
    logger.info("Job [decay_scoring] started")
    try:
        from memora.core.decay import DecayScoring

        default_lambda = settings.decay_lambda if settings else 0.01
        decay = DecayScoring(repo, default_lambda=default_lambda)
        count = decay.batch_update_scores()
        logger.info("Job [decay_scoring] completed in %s — %d nodes updated", _elapsed(start), count)
    except Exception:
        logger.error("Job [decay_scoring] failed after %s", _elapsed(start), exc_info=True)


# ── Bridge Discovery (batch) ────────────────────────────────────────

async def run_bridge_discovery_batch(repo, vector_store, embedding_engine, settings=None) -> None:
    """Run bridge discovery for nodes modified in the last 24 hours.

    1. Discover candidate bridges per-node via embedding similarity.
    2. Collect unvalidated bridges and run a single LLM call to assess which
       are meaningful (batch validation).
    """
    start = time.time()
    logger.info("Job [bridge_discovery_batch] started")
    try:
        from memora.core.bridge_discovery import BridgeDiscovery

        bd = BridgeDiscovery(repo, vector_store, embedding_engine)

        # Use repo helper instead of direct _conn access
        node_ids = repo.get_recently_modified_node_ids(hours=24)
        logger.info("Bridge discovery: %d nodes modified in last 24h", len(node_ids))

        total_bridges = 0
        for nid in node_ids:
            bridges = bd.discover_bridges_for_node(str(nid))
            total_bridges += len(bridges)

        # Batch LLM validation of unvalidated bridges
        validated_count = 0
        unvalidated = repo.get_unvalidated_bridges(limit=30)
        if unvalidated:
            validated_count = _validate_bridges_with_llm(repo, unvalidated, settings)

        if total_bridges:
            nm = _get_notification_manager(repo)
            from memora.core.notifications import BRIDGE_DISCOVERED
            nm.create_notification(
                type=BRIDGE_DISCOVERED,
                message=(
                    f"Discovered {total_bridges} new cross-network bridge(s)"
                    f"{f', validated {validated_count}' if validated_count else ''}."
                ),
                priority="low",
                trigger_condition="bridge_discovery_batch",
            )

        logger.info(
            "Job [bridge_discovery_batch] completed in %s — %d bridges found, %d validated",
            _elapsed(start),
            total_bridges,
            validated_count,
        )
    except Exception:
        logger.error(
            "Job [bridge_discovery_batch] failed after %s", _elapsed(start), exc_info=True
        )


def _validate_bridges_with_llm(repo, bridges: list[dict], settings=None) -> int:
    """Validate a batch of bridges with a single LLM call.

    Returns count of bridges that were validated.
    """
    import json as _json

    api_key = getattr(settings, "openai_api_key", None) if settings else None
    if not api_key:
        import os
        api_key = os.getenv("OPENAI_API_KEY", "")
    if not api_key:
        logger.debug("No API key for bridge LLM validation")
        return 0

    try:
        import openai
        client = openai.OpenAI(api_key=api_key)

        # Build a prompt describing all candidate bridges
        bridge_descriptions = []
        for i, b in enumerate(bridges):
            bridge_descriptions.append(
                f"{i+1}. [{b['source_network']}] \"{b.get('source_title', '?')}\" "
                f"<-> [{b['target_network']}] \"{b.get('target_title', '?')}\" "
                f"(similarity: {b['similarity']:.2f})"
            )

        prompt = (
            "Below are candidate cross-network knowledge bridge connections. "
            "For each, determine if it represents a MEANINGFUL connection "
            "(shared concepts, complementary ideas, actionable insight) "
            "or a SPURIOUS match (superficial similarity, coincidence).\n\n"
            "Respond with a JSON array where each element has:\n"
            '  {"index": <1-based>, "meaningful": true/false, "description": "brief explanation"}\n\n'
            "Bridges:\n" + "\n".join(bridge_descriptions)
        )

        response = client.responses.create(
            model="gpt-5-nano",
            input=prompt,
            max_output_tokens=2048,
        )

        raw = response.output_text

        # Extract JSON array from response
        import re
        arr_match = re.search(r"\[.*\]", raw, re.DOTALL)
        if not arr_match:
            return 0
        assessments = _json.loads(arr_match.group())

        validated = 0
        for assessment in assessments:
            idx = assessment.get("index", 0) - 1
            if 0 <= idx < len(bridges):
                bridge = bridges[idx]
                repo.update_bridge_validation(
                    bridge_id=bridge["id"],
                    meaningful=assessment.get("meaningful", False),
                    description=assessment.get("description", ""),
                )
                validated += 1

        return validated

    except Exception:
        logger.warning("Bridge LLM validation failed", exc_info=True)
        return 0


# ── Network Health ───────────────────────────────────────────────────

async def run_network_health(repo) -> None:
    """Compute health scores for all networks."""
    start = time.time()
    logger.info("Job [network_health] started")
    try:
        from memora.core.health_scoring import HealthScoring

        hs = HealthScoring(repo)
        results = hs.compute_all_networks()

        # Notify on any health drops
        nm = _get_notification_manager(repo)
        from memora.core.notifications import HEALTH_DROP

        for health in results:
            if health.get("status") == "falling_behind":
                nm.create_notification(
                    type=HEALTH_DROP,
                    message=f"Network '{health['network']}' is falling behind "
                            f"(completion: {health.get('commitment_completion_rate', 0):.0%}).",
                    priority="high",
                    trigger_condition="network_health",
                )

        logger.info("Job [network_health] completed in %s", _elapsed(start))
    except Exception:
        logger.error("Job [network_health] failed after %s", _elapsed(start), exc_info=True)


# ── Commitment Scan ──────────────────────────────────────────────────

async def run_commitment_scan(repo) -> None:
    """Scan for stale or approaching commitments and generate notifications."""
    start = time.time()
    logger.info("Job [commitment_scan] started")
    try:
        from memora.core.commitment_scan import CommitmentScanner

        scanner = CommitmentScanner(repo)
        result = scanner.scan()

        nm = _get_notification_manager(repo)
        from memora.core.notifications import STALE_COMMITMENT, DEADLINE_APPROACHING

        for item in result.get("overdue", []):
            nm.create_notification(
                type=STALE_COMMITMENT,
                message=f"Overdue: \"{item['title']}\" (due {item['due_date']}, {item['days_overdue']}d overdue)",
                related_node_ids=[item["node_id"]],
                priority="high",
                trigger_condition="commitment_scan",
            )

        for item in result.get("approaching", []):
            nm.create_notification(
                type=DEADLINE_APPROACHING,
                message=f"Due soon: \"{item['title']}\" (due {item['due_date']}, {item['days_until_due']}d remaining)",
                related_node_ids=[item["node_id"]],
                priority="medium",
                trigger_condition="commitment_scan",
            )

        stats = result.get("stats", {})
        logger.info(
            "Job [commitment_scan] completed in %s — %d overdue, %d approaching",
            _elapsed(start),
            stats.get("overdue_count", 0),
            stats.get("approaching_count", 0),
        )
    except Exception:
        logger.error("Job [commitment_scan] failed after %s", _elapsed(start), exc_info=True)


# ── Relationship Decay ───────────────────────────────────────────────

async def run_relationship_decay(repo) -> None:
    """Detect decaying relationships and generate notifications."""
    start = time.time()
    logger.info("Job [relationship_decay] started")
    try:
        from memora.core.relationship_decay import RelationshipDecayDetector

        detector = RelationshipDecayDetector(repo)
        decaying = detector.scan()

        nm = _get_notification_manager(repo)
        from memora.core.notifications import RELATIONSHIP_DECAY as RD_TYPE

        for item in decaying:
            nm.create_notification(
                type=RD_TYPE,
                message=(
                    f"You haven't interacted with {item['person_name']} "
                    f"in {item['days_since_interaction']} days "
                    f"(threshold: {item['threshold']}d for {item['relationship_type']})"
                ),
                related_node_ids=[item["node_id"]],
                priority="medium" if item["relationship_type"] != "close" else "high",
                trigger_condition="relationship_decay",
            )

        logger.info(
            "Job [relationship_decay] completed in %s — %d decaying relationships",
            _elapsed(start),
            len(decaying),
        )
    except Exception:
        logger.error(
            "Job [relationship_decay] failed after %s", _elapsed(start), exc_info=True
        )


# ── Spaced Repetition Queue ─────────────────────────────────────────

async def run_spaced_repetition_queue(repo) -> None:
    """Compute today's review queue and store as a notification."""
    start = time.time()
    logger.info("Job [spaced_repetition] started")
    try:
        from memora.core.spaced_repetition import SpacedRepetition

        sr = SpacedRepetition(repo)
        queue = sr.get_review_queue()

        if queue:
            nm = _get_notification_manager(repo)
            from memora.core.notifications import REVIEW_DUE

            node_ids = [item.get("id", "") for item in queue if item.get("id")]
            nm.create_notification(
                type=REVIEW_DUE,
                message=f"You have {len(queue)} item(s) due for review today.",
                related_node_ids=node_ids,
                priority="medium",
                trigger_condition="spaced_repetition",
            )

        logger.info(
            "Job [spaced_repetition] completed in %s — %d items queued",
            _elapsed(start),
            len(queue or []),
        )
    except Exception:
        logger.error(
            "Job [spaced_repetition] failed after %s", _elapsed(start), exc_info=True
        )


# ── Gap Detection ────────────────────────────────────────────────────

async def run_gap_detection(repo) -> None:
    """Detect knowledge gaps across all networks and store results."""
    start = time.time()
    logger.info("Job [gap_detection] started")
    try:
        from memora.core.gap_detection import GapDetector

        detector = GapDetector(repo)
        gaps = detector.detect_all()

        total_gaps = sum(len(v) for v in gaps.values())
        if total_gaps > 0:
            nm = _get_notification_manager(repo)
            from memora.core.notifications import GOAL_DRIFT

            parts = []
            for gap_type, items in gaps.items():
                if items:
                    parts.append(f"{len(items)} {gap_type.replace('_', ' ')}")
            nm.create_notification(
                type=GOAL_DRIFT,
                message=f"Gap detection found: {', '.join(parts)}",
                priority="low",
                trigger_condition="gap_detection",
            )

        logger.info(
            "Job [gap_detection] completed in %s — %d gaps found",
            _elapsed(start),
            total_gaps,
        )
    except Exception:
        logger.error("Job [gap_detection] failed after %s", _elapsed(start), exc_info=True)


# ── Daily Briefing ───────────────────────────────────────────────────

async def run_daily_briefing(
    repo,
    vector_store=None,
    embedding_engine=None,
    truth_layer=None,
    settings=None,
) -> None:
    """Generate a daily briefing summary using the Strategist agent.

    Gathers data from all background systems and invokes the Strategist
    to produce a structured daily briefing. Falls back to a notification
    summary if the Strategist is not available.
    """
    start = time.time()
    logger.info("Job [daily_briefing] started")
    try:
        nm = _get_notification_manager(repo)

        # Gather briefing input data
        health_scores = repo.get_latest_health_scores()

        try:
            from memora.core.commitment_scan import CommitmentScanner
            commitments = CommitmentScanner(repo).scan()
        except Exception:
            commitments = {}

        bridges = repo.get_recent_bridges(limit=10)

        try:
            from memora.core.spaced_repetition import SpacedRepetition
            review_items = SpacedRepetition(repo).get_review_queue()
        except Exception:
            review_items = []

        alerts = list(commitments.get("overdue", []))

        # Try to use the Strategist agent for a rich briefing
        api_key = getattr(settings, "openai_api_key", None) if settings else None
        if not api_key:
            import os
            api_key = os.getenv("OPENAI_API_KEY", "")

        if api_key:
            try:
                from memora.agents.strategist import StrategistAgent
                strategist = StrategistAgent(
                    api_key=api_key,
                    repo=repo,
                    vector_store=vector_store,
                    embedding_engine=embedding_engine,
                    truth_layer=truth_layer,
                )
                briefing = await strategist.generate_briefing(
                    health_scores=health_scores,
                    alerts=alerts,
                    bridges=bridges,
                    commitments=commitments,
                    review_items=review_items,
                )
                summary = briefing.summary or "Daily briefing generated."
                if briefing.sections:
                    section_summaries = [
                        f"- {s.title} ({len(s.items)} items, {s.priority})"
                        for s in briefing.sections
                    ]
                    summary += "\n" + "\n".join(section_summaries)

                nm.create_notification(
                    type="daily_briefing",
                    message=summary,
                    priority="medium",
                    trigger_condition="daily_briefing",
                )
                logger.info("Job [daily_briefing] completed in %s (strategist)", _elapsed(start))
                return
            except Exception:
                logger.warning("Strategist briefing failed, falling back to summary", exc_info=True)

        # Fallback: notification-based summary
        unread = nm.get_unread(limit=100)
        if unread:
            summary_lines = [f"- [{n['type']}] {n['message']}" for n in unread[:20]]
            summary = "Daily briefing — {} unread notification(s):\n{}".format(
                len(unread), "\n".join(summary_lines)
            )
        else:
            summary = "Daily briefing — no unread notifications. All clear!"

        nm.create_notification(
            type="daily_briefing",
            message=summary,
            priority="low",
            trigger_condition="daily_briefing",
        )

        logger.info("Job [daily_briefing] completed in %s (fallback)", _elapsed(start))
    except Exception:
        logger.error("Job [daily_briefing] failed after %s", _elapsed(start), exc_info=True)
