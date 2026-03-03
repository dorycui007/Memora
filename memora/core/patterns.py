"""Pattern Detection Engine — identifies recurring behavioral patterns."""

from __future__ import annotations

import hashlib
import logging
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from memora.graph.models import NetworkType, PatternType

logger = logging.getLogger(__name__)

# ── Confidence model ──────────────────────────────────────────
# Scale: <0.4 = suggestive, 0.4-0.7 = moderate, >0.7 = strong
# Formula: base from data volume + signal strength modifier

_CONFIDENCE_BASE_MIN = 0.25
_CONFIDENCE_BASE_MAX = 0.55
_CONFIDENCE_VOLUME_CAP = 20  # data points needed to reach base max


def _compute_confidence(data_points: int, signal_strength: float) -> float:
    """Compute a consistent confidence score.

    Args:
        data_points: Number of observations backing this pattern.
        signal_strength: How extreme the signal is, 0.0-1.0
            (e.g., abs(rate - 0.5)/0.5 for rates, 1.0 for boolean flags).

    Returns:
        Confidence in [0.15, 0.95].
    """
    volume_ratio = min(data_points / _CONFIDENCE_VOLUME_CAP, 1.0)
    base = _CONFIDENCE_BASE_MIN + (_CONFIDENCE_BASE_MAX - _CONFIDENCE_BASE_MIN) * volume_ratio
    return min(0.95, base + signal_strength * 0.4)


class PatternEngine:
    """Detect behavioral patterns across the knowledge graph."""

    # TTL for auto-expiring unconfirmed patterns
    PATTERN_TTL_DAYS = 30

    def __init__(self, repo) -> None:
        self.repo = repo

    def detect_all(self) -> list[dict]:
        """Run all pattern detectors, reconcile with stored patterns, and return results."""
        patterns = []
        detectors = [
            self.detect_commitment_patterns,
            self.detect_goal_lifecycle_patterns,
            self.detect_temporal_patterns,
            self.detect_cross_network_correlations,
            self.detect_relationship_patterns,
            self.detect_outcome_patterns,
            self.detect_decision_quality_patterns,
            self.detect_goal_alignment_patterns,
            self.detect_commitment_scope_patterns,
            self.detect_idea_maturity_patterns,
            self.detect_network_balance_patterns,
            self.detect_community_patterns,
            self.detect_centrality_anomalies,
        ]

        for detector in detectors:
            try:
                results = detector()
                patterns.extend(results)
            except Exception:
                logger.warning("Pattern detector %s failed", detector.__name__, exc_info=True)

        # ── Lifecycle: resolve stale patterns ──
        self._reconcile_patterns(patterns)

        return patterns

    def _reconcile_patterns(self, new_patterns: list[dict]) -> None:
        """Auto-resolve active patterns whose conditions are no longer detected.

        Also expire patterns not confirmed within the TTL.
        """
        try:
            active = self.repo.get_active_pattern_types()
        except Exception:
            logger.debug("Could not fetch active patterns for reconciliation")
            return

        # Build a set of (pattern_type, description) from new detections
        new_keys = {(p["pattern_type"], p["description"]) for p in new_patterns}

        for stored in active:
            key = (stored["pattern_type"], stored["description"])
            if key not in new_keys:
                # This pattern's conditions are no longer detected — resolve it
                try:
                    self.repo.resolve_pattern(stored["id"], reason="conditions_cleared")
                except Exception:
                    logger.debug("Failed to resolve pattern %s", stored["id"])

        # Expire old unconfirmed patterns
        try:
            self.repo.expire_stale_patterns(max_age_days=self.PATTERN_TTL_DAYS)
        except Exception:
            logger.debug("Failed to expire stale patterns")

    # ── Diagnostic report ─────────────────────────────────────────

    def diagnose(self) -> dict:
        """Return a diagnostic report showing what data is available and what's missing."""
        counts = self.repo.get_node_type_counts_by_network()
        total_by_type: dict[str, int] = defaultdict(int)
        for net_counts in counts.values():
            for ntype, cnt in net_counts.items():
                total_by_type[ntype] += cnt

        commitments = total_by_type.get("COMMITMENT", 0)
        goals = total_by_type.get("GOAL", 0)
        decisions = total_by_type.get("DECISION", 0)
        ideas = total_by_type.get("IDEA", 0)
        persons = total_by_type.get("PERSON", 0)
        outcomes_total = 0
        for net in NetworkType:
            stats = self.repo.get_outcome_stats(network=net.value)
            outcomes_total += stats.get("total", 0)

        total_nodes = sum(total_by_type.values())
        active_networks = len(counts)

        data_summary = {
            "commitments": commitments,
            "goals": goals,
            "decisions": decisions,
            "ideas": ideas,
            "persons": persons,
            "outcomes": outcomes_total,
            "total_nodes": total_nodes,
            "active_networks": active_networks,
        }

        missing: list[str] = []
        satisfied: list[str] = []

        # Check commitment threshold
        best_net_commits = 0
        best_net_name = "none"
        for net in NetworkType:
            net_commits = counts.get(net.value, {}).get("COMMITMENT", 0)
            if net_commits > best_net_commits:
                best_net_commits = net_commits
                best_net_name = net.value
        if best_net_commits < 2:
            missing.append(f"Need ≥2 commitments in a network (best: {best_net_name} with {best_net_commits})")
        else:
            satisfied.append(f"{commitments} commitments across {sum(1 for n in NetworkType if counts.get(n.value, {}).get('COMMITMENT', 0) > 0)} networks")

        # Check goals
        if goals == 0:
            missing.append("No goals recorded yet — create goals to unlock lifecycle patterns")
        else:
            satisfied.append(f"{goals} goal(s) recorded")

        # Check decisions
        if decisions == 0:
            missing.append("No decisions recorded yet — record decisions to unlock quality patterns")
        else:
            satisfied.append(f"{decisions} decision(s) recorded")

        # Check outcomes
        if outcomes_total == 0:
            missing.append("No outcomes recorded — use 'outcomes' to record decision results")
        else:
            satisfied.append(f"{outcomes_total} outcome(s) recorded")

        # Check ideas
        if ideas == 0:
            missing.append("No ideas recorded yet — capture ideas to unlock maturity patterns")
        else:
            satisfied.append(f"{ideas} idea(s) recorded")

        # Check persons (Flaw 11)
        if persons < 3:
            missing.append(
                f"Need ≥3 person nodes for relationship patterns (currently {persons})"
            )
        else:
            satisfied.append(f"{persons} person(s) recorded")

        # Overall node count
        if total_nodes > 0:
            satisfied.append(f"{total_nodes} nodes across {active_networks} networks")
        else:
            missing.append("Graph is empty — start capturing to build your knowledge graph")

        return {
            "data_summary": data_summary,
            "missing": missing,
            "satisfied": satisfied,
        }

    # ── Original detectors (with lowered thresholds) ──────────────

    def detect_commitment_patterns(self) -> list[dict]:
        """Analyze commitment completion rates by network, enriched with outcome data."""
        patterns = []

        network_stats: dict[str, dict] = {}
        for net in NetworkType:
            stats = self.repo.get_network_commitment_stats(net.value)
            if stats["total"] >= 2:  # lowered from 3
                network_stats[net.value] = stats

        for net, stats in network_stats.items():
            rate = stats["completion_rate"]

            outcome_stats = self.repo.get_outcome_stats(network=net)
            outcome_total = outcome_stats.get("total", 0)
            positive_rate = outcome_stats.get("positive_rate", 0.0)

            total = stats["total"]
            completed = stats.get("completed", 0)
            confidence = _compute_confidence(total, abs(rate - 0.5) / 0.5)

            if rate < 0.3 and total >= 2:  # lowered from 3
                patterns.append(self._make_pattern(
                    PatternType.COMMITMENT_PATTERN,
                    f"Low commitment completion in {net} network ({rate:.0%} of {total})",
                    confidence=confidence,
                    severity="warning",
                    suggested_action=(
                        f"You've completed {completed}/{total} commitments in {net} — "
                        f"review open items with `commitments` and consider reducing scope or setting deadlines"
                    ),
                    networks=[net],
                    current_value=rate,
                ))
            elif rate > 0.8 and total >= 5:
                if outcome_total >= 3 and positive_rate < 0.5:
                    patterns.append(self._make_pattern(
                        PatternType.COMMITMENT_PATTERN,
                        f"High completion rate but poor outcomes in {net} "
                        f"({rate:.0%} completed, {positive_rate:.0%} positive outcomes)",
                        confidence=min(0.9, confidence),
                        severity="warning",
                        suggested_action=(
                            f"You're completing commitments in {net} but only "
                            f"{positive_rate:.0%} have positive outcomes — "
                            f"run `outcomes` to review what's not working"
                        ),
                        networks=[net],
                        current_value=rate,
                    ))
                else:
                    patterns.append(self._make_pattern(
                        PatternType.COMMITMENT_PATTERN,
                        f"Strong commitment follow-through in {net} network ({rate:.0%})",
                        confidence=confidence,
                        severity="info",
                        networks=[net],
                        current_value=rate,
                    ))

        return patterns

    def detect_goal_lifecycle_patterns(self) -> list[dict]:
        """Analyze goal outcomes: stall patterns, abandon timing."""
        patterns = []

        cutoff = (datetime.now(timezone.utc) - timedelta(days=21)).isoformat()
        stalled = self.repo.find_stalled_active_nodes("GOAL", cutoff)

        if len(stalled) >= 1:  # lowered from 2
            evidence = [g["id"] for g in stalled[:10]]
            stalled_names = [g.get("title", "untitled") for g in stalled[:3]]
            names_str = ", ".join(f"'{n}'" for n in stalled_names)
            if len(stalled) > 3:
                names_str += f" and {len(stalled) - 3} more"
            patterns.append(self._make_pattern(
                PatternType.GOAL_LIFECYCLE,
                f"{len(stalled)} active goal(s) with no activity for 3+ weeks",
                evidence=evidence,
                confidence=_compute_confidence(len(stalled), 0.7),
                severity="warning" if len(stalled) >= 3 else "info",
                suggested_action=(
                    f"Stalled goals: {names_str} — "
                    f"run `goals` to archive or break them into smaller steps"
                ),
                current_value=float(len(stalled)),
            ))

        abandoned = self.repo.count_nodes_by_status("GOAL", "abandoned")
        active = self.repo.count_nodes_by_status("GOAL", "active")
        achieved = self.repo.count_nodes_by_status("GOAL", "achieved")
        total = abandoned + active + achieved

        if total >= 5 and abandoned / total > 0.5:
            patterns.append(self._make_pattern(
                PatternType.GOAL_LIFECYCLE,
                f"High goal abandonment rate: {abandoned}/{total} goals abandoned ({abandoned/total:.0%})",
                confidence=_compute_confidence(total, abandoned / total),
                severity="critical" if abandoned / total > 0.7 else "warning",
                suggested_action=(
                    f"{abandoned} of {total} goals abandoned — "
                    f"try setting smaller milestones or use `goals` to review active ones"
                ),
                current_value=abandoned / total,
            ))

        return patterns

    def detect_temporal_patterns(self) -> list[dict]:
        """Detect activity bursts and lulls."""
        patterns = []

        now = datetime.now(timezone.utc)
        recent = self.repo.get_nodes_by_date_range(
            start=(now - timedelta(days=30)).isoformat(),
            end=now.isoformat(),
            limit=1000,
        )
        older = self.repo.get_nodes_by_date_range(
            start=(now - timedelta(days=60)).isoformat(),
            end=(now - timedelta(days=30)).isoformat(),
            limit=1000,
        )

        recent_count = len(recent)
        older_count = len(older)

        if older_count > 0:
            ratio = recent_count / older_count
            if ratio < 0.3 and older_count >= 5:
                patterns.append(self._make_pattern(
                    PatternType.TEMPORAL_PATTERN,
                    f"Activity has dropped significantly: {recent_count} nodes this month vs {older_count} last month",
                    confidence=_compute_confidence(older_count, 1.0 - ratio),
                    severity="warning",
                    suggested_action=(
                        f"Activity dropped from {older_count} to {recent_count} nodes — "
                        f"run `capture` to log recent events, decisions, or thoughts"
                    ),
                    current_value=float(recent_count),
                ))
            elif ratio > 3.0 and recent_count >= 10:
                patterns.append(self._make_pattern(
                    PatternType.TEMPORAL_PATTERN,
                    f"Activity surge: {recent_count} nodes this month vs {older_count} last month",
                    confidence=_compute_confidence(recent_count, min(ratio / 5.0, 1.0)),
                    severity="info",
                    current_value=float(recent_count),
                ))

        day_counts: dict[int, int] = defaultdict(int)
        day_types: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        for n in recent:
            created = n.get("created_at")
            if isinstance(created, datetime):
                day_counts[created.weekday()] += 1
                node_type = (n.get("node_type") or n.get("type") or "unknown").lower()
                day_types[created.weekday()][node_type] += 1

        if day_counts and len(recent) >= 14:
            avg = sum(day_counts.values()) / 7
            peak_day = max(day_counts, key=day_counts.get)
            day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
            inactive_days = 7 - len(day_counts)
            if day_counts[peak_day] > avg * 2:
                # Find dominant type on peak day
                peak_types = day_types.get(peak_day, {})
                dominant_type = max(peak_types, key=peak_types.get) if peak_types else "entries"
                dominant_type_label = dominant_type.lower().replace("_", " ") + "s"

                desc = (
                    f"{day_names[peak_day]}s are your capture-heavy day "
                    f"({day_counts[peak_day]} entries, mostly {dominant_type_label})"
                )
                if inactive_days > 0:
                    desc += f" — {inactive_days} day(s) have no activity"

                inactive_day_names = [
                    day_names[d] for d in range(7) if d not in day_counts
                ]
                action = (
                    f"You capture most on {day_names[peak_day]}s "
                    f"but have gaps on {', '.join(inactive_day_names) if inactive_day_names else 'no days'} — "
                    f"try a quick `capture` on those days to avoid blind spots"
                ) if inactive_days > 0 else (
                    f"Heavy capture on {day_names[peak_day]}s — consider spreading activity more evenly"
                )

                patterns.append(self._make_pattern(
                    PatternType.TEMPORAL_PATTERN,
                    desc,
                    confidence=_compute_confidence(len(recent), 0.5),
                    severity="info",
                    suggested_action=action,
                ))

        return patterns

    def detect_cross_network_correlations(self) -> list[dict]:
        """Check if health changes in one network correlate with others."""
        patterns = []

        health_data = {}
        for net in NetworkType:
            history = self.repo.get_network_health_history(net.value, limit=10)
            if len(history) >= 2:
                health_data[net.value] = history

        declining = []
        improving = []
        for net, history in health_data.items():
            if len(history) >= 2:
                latest = history[0]
                prev = history[1]
                if latest.get("momentum") == "down" and prev.get("momentum") != "down":
                    declining.append(net)
                elif latest.get("momentum") == "up" and prev.get("momentum") != "up":
                    improving.append(net)

        if len(declining) >= 2:
            patterns.append(self._make_pattern(
                PatternType.CROSS_NETWORK,
                f"Multiple networks declining simultaneously: {', '.join(declining)}",
                confidence=_compute_confidence(len(declining) * 5, 0.8),
                severity="critical",
                suggested_action=(
                    f"{', '.join(declining)} are all trending down — "
                    f"check if they share a common blocker (e.g., a stalled commitment or overdue deadline)"
                ),
                networks=declining,
            ))

        # Flaw 10: Also detect positive correlations
        if len(improving) >= 2:
            patterns.append(self._make_pattern(
                PatternType.CROSS_NETWORK,
                f"Multiple networks improving together: {', '.join(improving)}",
                confidence=_compute_confidence(len(improving) * 5, 0.7),
                severity="info",
                suggested_action=(
                    f"Positive momentum in {', '.join(improving)} — "
                    f"keep it up and consider what's driving the improvement"
                ),
                networks=improving,
            ))

        return patterns

    def detect_relationship_patterns(self) -> list[dict]:
        """Analyze interaction frequency and relationship outcomes."""
        patterns = []

        person_nodes = self.repo.get_person_nodes()
        if len(person_nodes) < 3:
            return patterns

        now = datetime.now(timezone.utc)
        stale_people = []  # (name, days_since)
        active_count = 0
        for p in person_nodes:
            last = p.get("last_accessed")
            if last:
                if isinstance(last, str):
                    try:
                        last = datetime.fromisoformat(last)
                    except (ValueError, TypeError):
                        continue
                age = (now - last).days if hasattr(last, "days") else 999
                if age > 30:
                    name = p.get("title") or p.get("name") or "unnamed"
                    stale_people.append((name, age))
                else:
                    active_count += 1

        stale_count = len(stale_people)
        total = stale_count + active_count
        if total >= 5 and stale_count / total > 0.6:
            # Sort by staleness (longest gap first), show top 5
            stale_people.sort(key=lambda x: x[1], reverse=True)
            top = stale_people[:5]
            names_str = ", ".join(f"{name} ({days}d)" for name, days in top)
            if stale_count > 5:
                names_str += f" and {stale_count - 5} more"
            longest_name, longest_days = stale_people[0]
            patterns.append(self._make_pattern(
                PatternType.RELATIONSHIP_PATTERN,
                f"{stale_count}/{total} relationships gone cold: {names_str}",
                confidence=_compute_confidence(total, stale_count / total),
                severity="warning",
                suggested_action=(
                    f"Reconnect with {longest_name} first (longest gap: {longest_days} days) — "
                    f"run `people` to see all contacts"
                ),
                current_value=stale_count / total,
            ))

        return patterns

    def detect_outcome_patterns(self) -> list[dict]:
        """Detect patterns from outcome data across networks."""
        patterns = []

        for net in NetworkType:
            stats = self.repo.get_outcome_stats(network=net.value)
            total = stats.get("total", 0)
            if total < 3:  # lowered from 5
                continue

            by_rating = stats.get("by_rating", {})
            negative = by_rating.get("negative", 0)
            positive = by_rating.get("positive", 0)
            negative_rate = negative / total
            positive_rate = positive / total

            # Flaw 3: Use OUTCOME_PATTERN instead of COMMITMENT_PATTERN
            if negative_rate > 0.5:
                patterns.append(self._make_pattern(
                    PatternType.OUTCOME_PATTERN,
                    f"Your {net.value} decisions tend to have negative outcomes "
                    f"({negative}/{total} negative, {negative_rate:.0%})",
                    confidence=_compute_confidence(total, negative_rate),
                    severity="warning" if negative_rate < 0.7 else "critical",
                    suggested_action=(
                        f"{negative}/{total} outcomes in {net.value} are negative — "
                        f"run `outcomes` to review recent results and identify what's going wrong"
                    ),
                    networks=[net.value],
                    current_value=negative_rate,
                ))
            elif positive_rate > 0.8:
                patterns.append(self._make_pattern(
                    PatternType.OUTCOME_PATTERN,
                    f"Strong decision-making in {net.value} "
                    f"({positive}/{total} positive outcomes, {positive_rate:.0%})",
                    confidence=_compute_confidence(total, positive_rate),
                    severity="info",
                    networks=[net.value],
                    current_value=positive_rate,
                ))

        return patterns

    # ── Content-level detectors ───────────────────────────────────

    def detect_decision_quality_patterns(self) -> list[dict]:
        """Examine DECISION node properties for quality signals."""
        patterns = []

        decisions = self.repo.get_nodes_by_type_with_properties("DECISION")
        if not decisions:
            return patterns

        no_options = []
        no_rationale = []

        for d in decisions:
            props = d["properties"]
            options = props.get("options_considered") or []
            rationale = props.get("rationale") or ""

            if not options:
                no_options.append(d)
            if not rationale.strip():
                no_rationale.append(d)

        total = len(decisions)

        if no_options and len(no_options) >= 1:
            sample_titles = [d.get("title", "untitled") for d in no_options[:3]]
            sample_str = ", ".join(f"'{t}'" for t in sample_titles)
            if len(no_options) > 3:
                sample_str += f" and {len(no_options) - 3} more"
            patterns.append(self._make_pattern(
                PatternType.DECISION_QUALITY,
                f"{len(no_options)}/{total} decisions had no alternatives considered",
                evidence=[d["id"] for d in no_options[:10]],
                confidence=_compute_confidence(total, len(no_options) / total),
                severity="warning" if len(no_options) / total > 0.5 else "info",
                suggested_action=(
                    f"Decisions without alternatives: {sample_str} — "
                    f"listing even 2-3 options before deciding improves outcomes"
                ),
                current_value=len(no_options) / total,
            ))

        if no_rationale and len(no_rationale) >= 1:
            sample_titles = [d.get("title", "untitled") for d in no_rationale[:3]]
            sample_str = ", ".join(f"'{t}'" for t in sample_titles)
            if len(no_rationale) > 3:
                sample_str += f" and {len(no_rationale) - 3} more"
            patterns.append(self._make_pattern(
                PatternType.DECISION_QUALITY,
                f"{len(no_rationale)}/{total} decisions have no recorded rationale",
                evidence=[d["id"] for d in no_rationale[:10]],
                confidence=_compute_confidence(total, len(no_rationale) / total),
                severity="warning" if len(no_rationale) / total > 0.5 else "info",
                suggested_action=(
                    f"Missing rationale on: {sample_str} — "
                    f"recording your reasoning helps future review and learning"
                ),
                current_value=len(no_rationale) / total,
            ))

        # Flaw 4: Removed bogus network-level rationale/outcome correlation.
        # The old code assigned aggregate network negative rates uniformly to
        # every decision, making the correlation statistically meaningless.

        return patterns

    def detect_goal_alignment_patterns(self) -> list[dict]:
        """Check goal connectivity, milestones, and progress staleness."""
        patterns = []

        active_goals = self.repo.get_active_goals_with_edges()
        if not active_goals:
            return patterns

        now = datetime.now(timezone.utc)

        disconnected = []
        no_milestones = []
        stale_progress = []

        for g in active_goals:
            props = g["properties"]

            # Disconnected: no supporting edges
            if g.get("edge_count", 0) == 0:
                disconnected.append(g)

            # Missing milestones
            milestones = props.get("milestones") or []
            if not milestones:
                no_milestones.append(g)

            # Stale progress: still at 0.0 after 14+ days
            progress = props.get("progress", 0.0)
            created = g.get("created_at")
            if progress == 0.0 and created:
                if isinstance(created, str):
                    try:
                        created = datetime.fromisoformat(created)
                    except (ValueError, TypeError):
                        created = None
                if created:
                    # Normalise to tz-aware for comparison
                    if created.tzinfo is None:
                        created = created.replace(tzinfo=timezone.utc)
                    if (now - created).days >= 14:
                        stale_progress.append(g)

        total = len(active_goals)

        if disconnected:
            names = [g["title"] for g in disconnected]
            names_str = ", ".join(f"'{n}'" for n in names[:3])
            if len(names) > 3:
                names_str += f" and {len(names) - 3} more"
            all_networks = [n for g in disconnected for n in g.get("networks", [])]
            patterns.append(self._make_pattern(
                PatternType.GOAL_ALIGNMENT,
                f"{len(disconnected)} goal(s) are disconnected: {names_str}",
                evidence=[g["id"] for g in disconnected],
                confidence=_compute_confidence(len(disconnected), 0.6),
                severity="warning",
                suggested_action=(
                    f"'{names[0]}' has no linked commitments or projects — "
                    f"link related items to make progress actionable"
                ),
                networks=list(set(all_networks)),
            ))

        if no_milestones:
            names = [g["title"] for g in no_milestones]
            if len(names) <= 3:
                names_str = ", ".join(f"'{n}'" for n in names)
            else:
                names_str = ", ".join(f"'{n}'" for n in names[:3]) + f" and {len(names) - 3} more"
            patterns.append(self._make_pattern(
                PatternType.GOAL_ALIGNMENT,
                f"{len(no_milestones)} goal(s) have no milestones: {names_str}",
                evidence=[g["id"] for g in no_milestones[:10]],
                confidence=_compute_confidence(total, len(no_milestones) / max(total, 1)),
                severity="info",
                suggested_action=(
                    f"Add milestones to '{names[0]}' first — "
                    f"goals with checkpoints are completed more often"
                ),
            ))

        if stale_progress:
            stale_names = [g["title"] for g in stale_progress[:3]]
            stale_str = ", ".join(f"'{n}'" for n in stale_names)
            if len(stale_progress) > 3:
                stale_str += f" and {len(stale_progress) - 3} more"
            patterns.append(self._make_pattern(
                PatternType.GOAL_ALIGNMENT,
                f"{len(stale_progress)} goal(s) at 0% progress for 14+ days",
                evidence=[g["id"] for g in stale_progress[:10]],
                confidence=_compute_confidence(len(stale_progress), 0.7),
                severity="warning",
                suggested_action=(
                    f"Goals with no progress: {stale_str} — "
                    f"update progress or break into smaller steps with `goals`"
                ),
            ))

        return patterns

    def detect_commitment_scope_patterns(self) -> list[dict]:
        """Analyze commitment scope signals: deadlines, priority balance, overdue clustering."""
        patterns = []

        commitments = self.repo.get_nodes_by_type_with_properties("COMMITMENT")
        if not commitments:
            return patterns

        now = datetime.now(timezone.utc)

        no_deadline = []
        overdue_by_network: dict[str, list] = defaultdict(list)
        commits_by_network: dict[str, int] = defaultdict(int)

        for c in commitments:
            props = c["properties"]
            status = props.get("status", "open")
            networks = c.get("networks", [])

            for net in networks:
                commits_by_network[net] += 1

            # Missing deadline
            due_date = props.get("due_date") or ""
            if not due_date and status == "open":
                no_deadline.append(c)

            # Overdue check
            if due_date and status == "open":
                try:
                    due = datetime.fromisoformat(due_date) if isinstance(due_date, str) else due_date
                    if hasattr(due, "tzinfo") and due.tzinfo is None:
                        due = due.replace(tzinfo=timezone.utc)
                    if due < now:
                        for net in networks:
                            overdue_by_network[net].append(c)
                except (ValueError, TypeError):
                    pass

        total = len(commitments)

        if no_deadline:
            sample_titles = [c.get("title", "untitled") for c in no_deadline[:3]]
            sample_str = ", ".join(f"'{t}'" for t in sample_titles)
            if len(no_deadline) > 3:
                sample_str += f" and {len(no_deadline) - 3} more"
            patterns.append(self._make_pattern(
                PatternType.COMMITMENT_SCOPE,
                f"{len(no_deadline)}/{total} open commitments have no deadline set",
                evidence=[c["id"] for c in no_deadline[:10]],
                confidence=_compute_confidence(total, len(no_deadline) / max(total, 1)),
                severity="info",
                suggested_action=(
                    f"No deadline on: {sample_str} — "
                    f"set deadlines with `commitments` to create accountability"
                ),
                current_value=len(no_deadline) / max(total, 1),
            ))

        # Priority imbalance across networks
        if len(commits_by_network) >= 2:
            sorted_nets = sorted(commits_by_network.items(), key=lambda x: x[1], reverse=True)
            top_net, top_count = sorted_nets[0]
            # Check for networks with 0 commitments
            all_nets = {n.value for n in NetworkType}
            empty_nets = all_nets - set(commits_by_network.keys())
            if empty_nets and top_count >= 3:
                sample_empty = sorted(empty_nets)[:3]
                patterns.append(self._make_pattern(
                    PatternType.COMMITMENT_SCOPE,
                    f"You have {top_count} {top_net} commitments but 0 in {', '.join(sample_empty)}",
                    confidence=_compute_confidence(top_count, 0.5),
                    severity="info",
                    suggested_action=(
                        f"{top_count} commitments in {top_net} vs none in "
                        f"{', '.join(sample_empty)} — if those areas matter, add commitments there"
                    ),
                    networks=[top_net] + list(sample_empty),
                ))

        # Overdue clustering
        for net, overdue_list in overdue_by_network.items():
            if len(overdue_list) >= 2:
                overdue_titles = [c.get("title", "untitled") for c in overdue_list[:3]]
                overdue_str = ", ".join(f"'{t}'" for t in overdue_titles)
                if len(overdue_list) > 3:
                    overdue_str += f" and {len(overdue_list) - 3} more"
                patterns.append(self._make_pattern(
                    PatternType.COMMITMENT_SCOPE,
                    f"{len(overdue_list)} overdue commitments in {net} — consider renegotiating scope",
                    evidence=[c["id"] for c in overdue_list[:10]],
                    confidence=_compute_confidence(len(overdue_list), 0.8),
                    severity="critical" if len(overdue_list) >= 4 else "warning",
                    suggested_action=(
                        f"Overdue in {net}: {overdue_str} — "
                        f"run `commitments` to prioritize, defer, or complete these"
                    ),
                    networks=[net],
                ))

        return patterns

    def detect_idea_maturity_patterns(self) -> list[dict]:
        """Analyze idea maturity distribution and staleness."""
        patterns = []

        ideas = self.repo.get_nodes_by_type_with_properties("IDEA")
        if not ideas:
            return patterns

        now = datetime.now(timezone.utc)

        seed_stale = []
        ideas_by_network: dict[str, int] = defaultdict(int)

        for idea in ideas:
            props = idea["properties"]
            maturity = props.get("maturity", "seed")
            networks = idea.get("networks", [])

            for net in networks:
                ideas_by_network[net] += 1

            # Seed for 30+ days
            if maturity == "seed":
                created = idea.get("created_at")
                if created:
                    if isinstance(created, str):
                        try:
                            created = datetime.fromisoformat(created)
                        except (ValueError, TypeError):
                            created = None
                    if created:
                        if created.tzinfo is None:
                            created = created.replace(tzinfo=timezone.utc)
                        if (now - created).days >= 30:
                            seed_stale.append(idea)

        total = len(ideas)

        if seed_stale:
            stale_names = [i.get("title", "untitled") for i in seed_stale[:3]]
            stale_str = ", ".join(f"'{n}'" for n in stale_names)
            if len(seed_stale) > 3:
                stale_str += f" and {len(seed_stale) - 3} more"
            patterns.append(self._make_pattern(
                PatternType.IDEA_MATURITY,
                f"{len(seed_stale)} idea(s) stuck at seed stage for 30+ days",
                evidence=[i["id"] for i in seed_stale[:10]],
                confidence=_compute_confidence(total, len(seed_stale) / max(total, 1)),
                severity="info",
                suggested_action=(
                    f"Stale seeds: {stale_str} — "
                    f"promote promising ones with `ideas` or archive the rest"
                ),
            ))

        # Network imbalance for ideas
        if len(ideas_by_network) >= 1 and total >= 3:
            all_nets = {n.value for n in NetworkType}
            active_nets = set(ideas_by_network.keys())
            empty_nets = all_nets - active_nets

            if empty_nets and len(active_nets) <= 2:
                top_net = max(ideas_by_network, key=ideas_by_network.get)
                top_count = ideas_by_network[top_net]
                sample_empty = sorted(list(empty_nets)[:3])
                patterns.append(self._make_pattern(
                    PatternType.IDEA_MATURITY,
                    f"Ideas concentrated in {', '.join(sorted(active_nets))} — none in {', '.join(sample_empty)}",
                    confidence=_compute_confidence(total, 0.5),
                    severity="info",
                    suggested_action=(
                        f"{top_count} ideas in {top_net} but none in "
                        f"{', '.join(sample_empty)} — brainstorm in those areas if they matter to you"
                    ),
                    networks=list(active_nets),
                ))

        return patterns

    def detect_network_balance_patterns(self) -> list[dict]:
        """Analyze node distribution and activity across all networks."""
        patterns = []

        counts = self.repo.get_node_type_counts_by_network()
        if not counts:
            return patterns

        # Total nodes per network
        net_totals: dict[str, int] = {}
        grand_total = 0
        for net in NetworkType:
            total = sum(counts.get(net.value, {}).values())
            net_totals[net.value] = total
            grand_total += total

        if grand_total == 0:
            return patterns

        # Neglected networks (0 nodes) — consolidated into single pattern
        neglected = [n for n, t in net_totals.items() if t == 0]
        if neglected:
            names_str = ", ".join(n.lower().replace("_", " ") for n in sorted(neglected))
            patterns.append(self._make_pattern(
                PatternType.NETWORK_BALANCE,
                f"{len(neglected)} network(s) have no data yet: {names_str}",
                confidence=_compute_confidence(grand_total, 0.3),
                severity="info",
                suggested_action=(
                    f"Empty networks: {names_str} — "
                    f"if relevant, start capturing in these areas with `capture`"
                ),
                networks=neglected,
            ))

        # Concentration risk (one network >60% of all nodes)
        for net, total in net_totals.items():
            if grand_total >= 5 and total / grand_total > 0.6:
                pct = total / grand_total
                # Find the smallest active network for contrast
                active_nets = {n: t for n, t in net_totals.items() if t > 0 and n != net}
                contrast = ""
                if active_nets:
                    smallest_net = min(active_nets, key=active_nets.get)
                    smallest_count = active_nets[smallest_net]
                    contrast = f" (vs {smallest_count} in {smallest_net})"
                patterns.append(self._make_pattern(
                    PatternType.NETWORK_BALANCE,
                    f"{pct:.0%} of your nodes are in {net}{contrast}",
                    confidence=_compute_confidence(grand_total, pct),
                    severity="warning" if pct > 0.8 else "info",
                    suggested_action=(
                        f"{total}/{grand_total} nodes in {net} — "
                        f"consider capturing more in other networks for a balanced picture"
                    ),
                    networks=[net],
                    current_value=pct,
                ))

        # Activity gaps: networks with nodes but no recent activity (30+ days)
        now = datetime.now(timezone.utc)
        recent_nodes = self.repo.get_nodes_by_date_range(
            start=(now - timedelta(days=30)).isoformat(),
            end=now.isoformat(),
            limit=2000,
        )

        recent_nets: set[str] = set()
        for n in recent_nodes:
            for net in (n.get("networks") or []):
                recent_nets.add(net)

        active_but_stale = [
            net for net, total in net_totals.items()
            if total > 0 and net not in recent_nets
        ]
        for net in active_but_stale:
            patterns.append(self._make_pattern(
                PatternType.NETWORK_BALANCE,
                f"No new nodes in {net} for 30+ days ({net_totals[net]} existing nodes)",
                confidence=_compute_confidence(net_totals[net], 0.6),
                severity="warning",
                suggested_action=(
                    f"Your {net} network has {net_totals[net]} nodes but nothing new in 30 days — "
                    f"run `capture` to log recent {net.lower()} activity"
                ),
                networks=[net],
            ))

        return patterns

    # ── Graph Algorithm-Based Detectors ─────────────────────────────

    def detect_community_patterns(self) -> list[dict]:
        """Detect patterns in graph community structure.

        Flags: single-entity communities (isolated clusters), dominant communities
        (one community holding >60% of nodes), and cross-network communities.
        """
        patterns = []
        try:
            from memora.core.graph_algorithms import GraphAlgorithms
            algo = GraphAlgorithms(self.repo)
            communities = algo.label_propagation_communities()
        except Exception:
            logger.debug("Graph algorithms unavailable for community detection")
            return patterns

        if not communities:
            return patterns

        total_nodes = sum(c["size"] for c in communities)
        if total_nodes == 0:
            return patterns

        # Singleton communities (isolated nodes in their own cluster)
        singletons = [c for c in communities if c["size"] == 1]
        if len(singletons) >= 3:
            names = [c["members"][0]["title"] for c in singletons[:5]]
            patterns.append(self._make_pattern(
                PatternType.CROSS_NETWORK,
                f"{len(singletons)} entity(ies) form isolated communities: {', '.join(names)}",
                confidence=_compute_confidence(len(singletons), 0.4),
                severity="info",
                suggested_action="Consider connecting these isolated entities to related nodes",
            ))

        # Dominant community (>60% of all nodes)
        for comm in communities:
            ratio = comm["size"] / total_nodes
            if ratio > 0.6 and comm["size"] >= 5:
                type_counts = {}
                for m in comm["members"]:
                    type_counts[m["type"]] = type_counts.get(m["type"], 0) + 1
                dominant_type = max(type_counts, key=type_counts.get)
                patterns.append(self._make_pattern(
                    PatternType.CROSS_NETWORK,
                    f"Dominant community holds {ratio:.0%} of nodes ({comm['size']}/{total_nodes}), mostly {dominant_type}",
                    confidence=_compute_confidence(total_nodes, ratio),
                    severity="warning" if ratio > 0.8 else "info",
                    suggested_action="Graph may lack diversity — capture data across more domains",
                    current_value=ratio,
                ))

        # Community count as a health indicator
        if len(communities) >= 2:
            patterns.append(self._make_pattern(
                PatternType.CROSS_NETWORK,
                f"Graph has {len(communities)} natural communities across {total_nodes} nodes",
                confidence=_compute_confidence(total_nodes, 0.3),
                severity="info",
                current_value=float(len(communities)),
            ))

        return patterns

    def detect_centrality_anomalies(self) -> list[dict]:
        """Detect anomalies in centrality distribution.

        Flags: hub-and-spoke patterns (single node with extreme centrality),
        high-importance nodes with low connectivity, and bridge entities
        (high betweenness, low degree).
        """
        patterns = []
        try:
            from memora.core.graph_algorithms import GraphAlgorithms
            algo = GraphAlgorithms(self.repo)
            degree = algo.degree_centrality()
            pr = algo.pagerank()
        except Exception:
            logger.debug("Graph algorithms unavailable for centrality analysis")
            return patterns

        if len(degree) < 3:
            return patterns

        # Hub-and-spoke: top entity has >3x the degree of the median
        degrees = [d["total_degree"] for d in degree if d["total_degree"] > 0]
        if degrees:
            top_degree = degrees[0]
            median_idx = len(degrees) // 2
            median_degree = degrees[median_idx] if median_idx < len(degrees) else 1
            if median_degree > 0 and top_degree > median_degree * 3:
                top_entity = degree[0]
                patterns.append(self._make_pattern(
                    PatternType.CROSS_NETWORK,
                    f"Hub-and-spoke: '{top_entity['title']}' has {top_entity['total_degree']} connections ({top_degree / median_degree:.1f}x median)",
                    confidence=_compute_confidence(len(degrees), min(top_degree / max(median_degree * 3, 1), 1.0)),
                    severity="info",
                    suggested_action=f"'{top_entity['title']}' is a central hub — ensure connections are well-typed",
                    current_value=float(top_degree),
                ))

        # PageRank outliers — top entity has >5x the average PR
        if pr:
            scores = [p["pagerank"] for p in pr]
            avg_pr = sum(scores) / len(scores)
            if avg_pr > 0:
                top_pr = pr[0]
                ratio = top_pr["pagerank"] / avg_pr
                if ratio > 5:
                    patterns.append(self._make_pattern(
                        PatternType.CROSS_NETWORK,
                        f"PageRank outlier: '{top_pr['title']}' is {ratio:.1f}x more influential than average",
                        confidence=_compute_confidence(len(pr), min(ratio / 10, 1.0)),
                        severity="info",
                        suggested_action=f"'{top_pr['title']}' dominates graph influence — review if this matches importance",
                        current_value=top_pr["pagerank"],
                    ))

        return patterns

    # ── Storage + helpers ─────────────────────────────────────────

    def store_patterns(self, patterns: list[dict]) -> int:
        """Store detected patterns in the database. Returns count stored."""
        stored = 0
        for pattern in patterns:
            try:
                # Enrich with trend data from existing pattern before storing
                self._enrich_with_trend(pattern)
                self.repo.store_pattern(pattern)
                stored += 1
            except Exception:
                logger.warning("Failed to store pattern: %s", pattern.get("description", "?"))
        return stored

    def _enrich_with_trend(self, pattern: dict) -> None:
        """Compare pattern against stored version to compute trend delta."""
        try:
            existing = self.repo.find_matching_pattern(
                pattern["pattern_type"], pattern["description"]
            )
            if existing and existing.get("current_value") is not None:
                pattern["previous_value"] = existing["current_value"]
                # Enrich description with trend if we have both values
                prev = existing["current_value"]
                curr = pattern.get("current_value")
                if curr is not None and prev != curr:
                    direction = "up" if curr > prev else "down"
                    if isinstance(curr, float) and curr <= 1.0:
                        delta_str = f"{direction} from {prev:.0%}"
                    else:
                        delta_str = f"{direction} from {prev:.0f}"
                    pattern["description"] += f" ({delta_str})"
        except Exception:
            pass  # Trend enrichment is best-effort

    def _make_pattern(
        self,
        pattern_type: PatternType,
        description: str,
        evidence: list[str] | None = None,
        confidence: float = 0.5,
        severity: str = "info",
        suggested_action: str = "",
        networks: list[str] | None = None,
        current_value: float | None = None,
    ) -> dict:
        now = datetime.now(timezone.utc).isoformat()
        return {
            "id": str(uuid4()),
            "pattern_type": pattern_type.value,
            "description": description,
            "evidence": evidence or [],
            "confidence": confidence,
            "severity": severity,
            "suggested_action": suggested_action,
            "networks": networks or [],
            "first_detected": now,
            "last_confirmed": now,
            "status": "active",
            "previous_value": None,
            "current_value": current_value,
            "created_at": now,
        }
