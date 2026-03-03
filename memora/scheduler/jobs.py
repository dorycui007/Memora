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
    """Build a NotificationManager from the repo's DuckDB connection."""
    from memora.core.notifications import NotificationManager
    return NotificationManager(repo.get_truth_layer_conn())


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

    Uses BriefingCollector to gather data from all sources with time-windowing,
    then invokes the Strategist for synthesis. Falls back to a notification
    summary if the Strategist is not available.
    """
    start = time.time()
    logger.info("Job [daily_briefing] started")
    try:
        nm = _get_notification_manager(repo)

        from memora.core.briefing import BriefingCollector, get_last_briefing_time

        since = get_last_briefing_time(repo)
        collector = BriefingCollector(repo, truth_layer=truth_layer)
        briefing_data = collector.collect(since=since)

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
                briefing = await strategist.generate_briefing(briefing_data)
                summary = briefing.summary or "Daily briefing generated."

                section_counts = []
                for label, items in [
                    ("urgent", briefing.urgent),
                    ("upcoming", briefing.upcoming),
                    ("people", briefing.people_followup),
                    ("wins", briefing.wins),
                    ("stalled", briefing.stalled_attention),
                    ("review", briefing.review_items),
                ]:
                    if items:
                        section_counts.append(f"- {label}: {len(items)} item(s)")
                if section_counts:
                    summary += "\n" + "\n".join(section_counts)

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


# ── Outcome Review ──────────────────────────────────────────────────

async def run_outcome_review(repo) -> None:
    """Scan for decisions/goals needing outcome recording and create notifications."""
    start = time.time()
    logger.info("Job [outcome_review] started")
    try:
        from memora.core.outcomes import OutcomeTracker

        tracker = OutcomeTracker(repo)
        pending = tracker.get_pending_outcomes(days_threshold=14)

        if pending:
            nm = _get_notification_manager(repo)
            prompts = tracker.generate_outcome_prompts(limit=5)
            prompt_lines = [f"- {p['prompt']}" for p in prompts]
            message = (
                f"{len(pending)} decision(s)/goal(s) need outcome recording:\n"
                + "\n".join(prompt_lines[:5])
            )
            nm.create_notification(
                type="OUTCOME_DUE",
                message=message,
                priority="medium",
                trigger_condition="outcome_review",
            )

        logger.info(
            "Job [outcome_review] completed in %s — %d pending outcomes",
            _elapsed(start),
            len(pending),
        )
    except Exception:
        logger.error("Job [outcome_review] failed after %s", _elapsed(start), exc_info=True)


# ── Confidence Decay ────────────────────────────────────────────────

async def run_confidence_decay(repo, truth_layer=None) -> None:
    """Decay confidence for facts that have missed their recheck date.

    Automatically reduces confidence and marks sufficiently degraded facts
    as STALE so they surface in briefings and alerts.
    """
    start = time.time()
    logger.info("Job [confidence_decay] started")
    try:
        if truth_layer is None:
            from memora.core.truth_layer import TruthLayer
            truth_layer = TruthLayer(repo.get_truth_layer_conn())

        updated = truth_layer.decay_stale_confidence()

        if updated:
            nm = _get_notification_manager(repo)
            nm.create_notification(
                type="FACT_DECAY",
                message=f"Confidence decayed for {updated} overdue fact(s). Review recommended.",
                priority="low",
                trigger_condition="confidence_decay",
            )

        logger.info(
            "Job [confidence_decay] completed in %s — %d facts decayed",
            _elapsed(start),
            updated,
        )
    except Exception:
        logger.error("Job [confidence_decay] failed after %s", _elapsed(start), exc_info=True)


# ── Pattern Detection ───────────────────────────────────────────────

async def run_pattern_detection(repo) -> None:
    """Run all pattern detectors and store results."""
    start = time.time()
    logger.info("Job [pattern_detection] started")
    try:
        from memora.core.patterns import PatternEngine

        engine = PatternEngine(repo)
        patterns = engine.detect_all()

        if patterns:
            stored = engine.store_patterns(patterns)

            nm = _get_notification_manager(repo)
            significant = [p for p in patterns if p.get("confidence", 0) >= 0.6]
            if significant:
                descriptions = [p["description"] for p in significant[:3]]
                nm.create_notification(
                    type="PATTERN_DETECTED",
                    message=(
                        f"Detected {len(patterns)} pattern(s), "
                        f"{len(significant)} significant:\n"
                        + "\n".join(f"- {d}" for d in descriptions)
                    ),
                    priority="low",
                    trigger_condition="pattern_detection",
                )

        logger.info(
            "Job [pattern_detection] completed in %s — %d patterns detected",
            _elapsed(start),
            len(patterns),
        )
    except Exception:
        logger.error("Job [pattern_detection] failed after %s", _elapsed(start), exc_info=True)


# ── Connector Sync ─────────────────────────────────────────────

async def run_connector_sync(repo, settings=None) -> None:
    """Sync all configured connectors and process new captures."""
    start = time.time()
    logger.info("Job [connector_sync] started")
    try:
        connectors_config = getattr(settings, "connectors", {}) if settings else {}
        if not connectors_config:
            logger.debug("No connectors configured, skipping sync")
            return

        from memora.connectors.base import get_default_registry

        registry = get_default_registry()

        # Create connector instances from config
        for name, cfg in connectors_config.items():
            ctype = cfg.get("type", "")
            if ctype and not registry.get(name):
                try:
                    registry.create(name, ctype, cfg.get("config", {}))
                except ValueError:
                    logger.warning("Unknown connector type '%s' for '%s'", ctype, name)
                    continue

        # Sync all
        records = registry.sync_all()

        total_items = 0
        total_errors = 0
        for record in records:
            captures = record.config.pop("captures", [])
            total_items += len(captures)
            total_errors += record.errors

            # Store captures (dedup check)
            for capture in captures:
                if not repo.check_capture_exists(capture.content_hash):
                    repo.create_capture(capture)

            # Save sync record
            try:
                import json as _json
                repo.get_truth_layer_conn().execute(
                    """INSERT INTO sync_records (id, connector_name, connector_type, last_sync,
                       items_synced, errors, cursor, config, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    [
                        record.id,
                        record.connector_name,
                        record.connector_type,
                        record.last_sync,
                        record.items_synced,
                        record.errors,
                        record.cursor,
                        _json.dumps({}),
                        record.created_at,
                        record.updated_at,
                    ],
                )
            except Exception:
                logger.debug("Failed to save sync record for %s", record.connector_name)

        if total_items > 0:
            nm = _get_notification_manager(repo)
            nm.create_notification(
                type="CONNECTOR_SYNC",
                message=f"Connector sync: {total_items} new item(s) from {len(records)} source(s).",
                priority="low",
                trigger_condition="connector_sync",
            )

        logger.info(
            "Job [connector_sync] completed in %s — %d items, %d errors",
            _elapsed(start),
            total_items,
            total_errors,
        )
    except Exception:
        logger.error("Job [connector_sync] failed after %s", _elapsed(start), exc_info=True)
