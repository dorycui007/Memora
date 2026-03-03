"""Horizon — operational awareness engine for Memora.

Pure query-time computation over existing graph primitives.
Collects time-bound entities, scores them by 5 weighted signals,
buckets into temporal groups, and provides impact preview for completions.
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict

from memora.graph.models import enum_val
from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import UUID

from memora.graph.models import (
    ActionType,
    EdgeType,
    NetworkType,
    NodeFilter,
    NodeType,
)

logger = logging.getLogger(__name__)

# ── Temporal field mapping (mirrors decay.py) ─────────────────────────
_TEMPORAL_FIELDS: dict[str, str] = {
    "EVENT": "event_date",
    "COMMITMENT": "due_date",
    "DECISION": "decision_date",
    "GOAL": "target_date",
    "PROJECT": "target_date",
}

# Node types Horizon cares about
_HORIZON_TYPES = [
    NodeType.COMMITMENT,
    NodeType.GOAL,
    NodeType.EVENT,
    NodeType.PROJECT,
    NodeType.DECISION,
]

# Active statuses per type (nodes with these statuses are collected)
_ACTIVE_STATUSES: dict[str, set[str]] = {
    "COMMITMENT": {"open", "overdue"},
    "GOAL": {"active"},
    "PROJECT": {"active"},
    "EVENT": set(),      # events have no status filter
    "DECISION": set(),   # decisions have no status filter
}

# Completable types and their action mappings
_COMPLETABLE_ACTIONS: dict[str, ActionType] = {
    "COMMITMENT": ActionType.COMPLETE_COMMITMENT,
    "GOAL": ActionType.ADVANCE_GOAL,
}

# ── Priority signal weights ───────────────────────────────────────────
W_URGENCY = 0.35
W_CENTRALITY = 0.15
W_HEALTH_IMPACT = 0.20
W_DECAY_MOMENTUM = 0.10
W_DEPENDENCY = 0.20


# ── Data structures ──────────────────────────────────────────────────

@dataclass
class HorizonItem:
    """Unified representation of any time-bound graph entity."""

    node_id: str
    title: str
    kind: str                  # NodeType value
    anchor_date: datetime | None
    status: str
    completable: bool
    progress: float | None     # 0.0–1.0 for GOALs
    networks: list[str]
    # 5 scoring fields
    urgency: float = 0.0
    centrality: float = 0.0
    health_impact: float = 0.0
    decay_momentum: float = 0.0
    dependency_depth: float = 0.0
    # composite
    composite_priority: float = 0.0
    # derived helpers
    days_until: int | None = None
    overdue: bool = False
    blocking_count: int = 0
    parent_title: str | None = None


@dataclass
class HorizonView:
    """Time-bucketed collection of HorizonItems."""

    overdue: list[HorizonItem] = field(default_factory=list)
    today: list[HorizonItem] = field(default_factory=list)
    tomorrow: list[HorizonItem] = field(default_factory=list)
    this_week: list[HorizonItem] = field(default_factory=list)
    next_week: list[HorizonItem] = field(default_factory=list)
    this_month: list[HorizonItem] = field(default_factory=list)
    later: list[HorizonItem] = field(default_factory=list)
    undated: list[HorizonItem] = field(default_factory=list)
    # aggregates
    network_load: dict[str, int] = field(default_factory=dict)
    pattern_warnings: list[dict] = field(default_factory=list)

    @property
    def total(self) -> int:
        return sum(
            len(b)
            for b in (
                self.overdue, self.today, self.tomorrow,
                self.this_week, self.next_week, self.this_month,
                self.later, self.undated,
            )
        )

    @property
    def completable_count(self) -> int:
        return sum(
            1
            for b in (
                self.overdue, self.today, self.tomorrow,
                self.this_week, self.next_week, self.this_month,
                self.later, self.undated,
            )
            for item in b
            if item.completable
        )

    @property
    def overdue_count(self) -> int:
        return len(self.overdue)

    def all_items(self) -> list[HorizonItem]:
        """All items in priority order (buckets preserved, sorted within)."""
        out: list[HorizonItem] = []
        for bucket in (
            self.overdue, self.today, self.tomorrow,
            self.this_week, self.next_week, self.this_month,
            self.later, self.undated,
        ):
            out.extend(sorted(bucket, key=lambda i: -i.composite_priority))
        return out


@dataclass
class CompletionImpact:
    """What happens when you complete an item."""

    unblocked_items: list[dict]  # [{node_id, title, kind}]
    network_health_delta: dict[str, str]  # {network: status}
    pattern_note: str | None = None


# ── Engine ────────────────────────────────────────────────────────────

class HorizonEngine:
    """Builds operational awareness views over existing graph primitives."""

    def __init__(self, repo) -> None:
        self._repo = repo

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build_view(
        self,
        window: str = "week",
        networks: list[str] | None = None,
        kinds: list[str] | None = None,
        include_completed: bool = False,
    ) -> HorizonView:
        """Build a time-bucketed, priority-scored view.

        window: 'day' | 'week' | 'month' | 'all'
        """
        items = self._collect_items(
            networks=networks,
            kinds=kinds,
            include_completed=include_completed,
        )
        items = self._score_all(items)
        view = self._bucket_items(items, window)
        view.pattern_warnings = self._get_pattern_warnings(networks)
        return view

    def complete_item(self, node_id: str) -> CompletionImpact:
        """Complete an item via ActionEngine and return impact analysis."""
        from memora.core.actions import ActionEngine

        node = self._repo.get_node(UUID(node_id))
        if not node:
            return CompletionImpact([], {}, "Node not found")

        kind = node.node_type.value
        action_type = _COMPLETABLE_ACTIONS.get(kind)
        if not action_type:
            return CompletionImpact([], {}, f"{kind} is not completable")

        engine = ActionEngine(self._repo)
        result = engine.execute(action_type, {"node_id": node_id})

        if not result.get("success"):
            return CompletionImpact([], {}, f"Failed: {result.get('error', 'unknown')}")

        return self.get_impact_preview(node_id)

    def get_impact_preview(self, node_id: str) -> CompletionImpact:
        """Preview completion impact without executing."""
        node = self._repo.get_node(UUID(node_id))
        if not node:
            return CompletionImpact([], {})

        # Find items this node blocks (SUBTASK_OF children)
        unblocked = self._find_blocked_items(node_id)

        # Project network health delta
        health_delta = self._project_health_delta(node)

        # Pattern note
        pattern_note = self._get_pattern_note_for(node)

        return CompletionImpact(unblocked, health_delta, pattern_note)

    # ------------------------------------------------------------------
    # Collection
    # ------------------------------------------------------------------

    def _collect_items(
        self,
        networks: list[str] | None = None,
        kinds: list[str] | None = None,
        include_completed: bool = False,
    ) -> list[HorizonItem]:
        """Query repo for active time-bound entities."""
        type_filter = [NodeType(k) for k in kinds] if kinds else _HORIZON_TYPES
        network_filter = [NetworkType(n) for n in networks] if networks else None

        nodes = self._repo.query_nodes(
            NodeFilter(
                node_types=type_filter,
                networks=network_filter,
                limit=500,
            )
        )

        items: list[HorizonItem] = []
        for node in nodes:
            kind = node.node_type.value
            props = node.properties or {}
            status = props.get("status", "")

            # Filter by active status unless include_completed
            if not include_completed:
                active_set = _ACTIVE_STATUSES.get(kind)
                if active_set and status not in active_set:
                    continue

            # Parse temporal anchor
            anchor = self._parse_anchor(kind, props, node.created_at)

            # Progress for goals
            progress = None
            if kind == "GOAL":
                progress = props.get("progress", 0.0)
                if isinstance(progress, str):
                    try:
                        progress = float(progress)
                    except ValueError:
                        progress = 0.0

            # Days until
            days_until = None
            overdue = False
            if anchor:
                now = datetime.now(timezone.utc)
                delta = (anchor - now).total_seconds() / 86400
                days_until = int(delta)
                overdue = delta < 0

            item = HorizonItem(
                node_id=str(node.id),
                title=node.title,
                kind=kind,
                anchor_date=anchor,
                status=status,
                completable=kind in _COMPLETABLE_ACTIONS,
                progress=progress,
                networks=[enum_val(n) for n in node.networks],
                days_until=days_until,
                overdue=overdue,
            )
            items.append(item)

        return items

    def _parse_anchor(
        self, kind: str, props: dict, fallback: datetime | None
    ) -> datetime | None:
        """Extract temporal anchor from node properties."""
        field_name = _TEMPORAL_FIELDS.get(kind)
        if not field_name:
            return None

        raw = props.get(field_name)
        if not raw:
            return None

        if isinstance(raw, datetime):
            if raw.tzinfo is None:
                return raw.replace(tzinfo=timezone.utc)
            return raw

        if isinstance(raw, str):
            for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
                try:
                    dt = datetime.strptime(raw, fmt)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    return dt
                except ValueError:
                    continue

        return None

    # ------------------------------------------------------------------
    # Scoring
    # ------------------------------------------------------------------

    def _score_all(self, items: list[HorizonItem]) -> list[HorizonItem]:
        """Compute 5 priority signals + composite for each item."""
        if not items:
            return items

        # Batch-fetch edges for blocking count & dependency depth
        node_ids = [item.node_id for item in items]
        edges = self._repo.get_edges_batch(node_ids)

        # Build SUBTASK_OF adjacency for BFS depth
        subtask_children: dict[str, list[str]] = defaultdict(list)
        subtask_parent: dict[str, str] = {}
        blocking_counts: dict[str, int] = defaultdict(int)

        for edge in edges:
            src = str(edge.source_id) if hasattr(edge, "source_id") else str(edge.get("source_id", ""))
            tgt = str(edge.target_id) if hasattr(edge, "target_id") else str(edge.get("target_id", ""))
            etype = edge.edge_type if hasattr(edge, "edge_type") else edge.get("edge_type", "")
            etype_val = enum_val(etype)

            if etype_val == EdgeType.SUBTASK_OF.value:
                subtask_children[tgt].append(src)
                subtask_parent[src] = tgt
                blocking_counts[tgt] += 1

        # Get network health statuses
        network_health = self._get_network_health_map()

        # Fetch parent titles for items that are subtasks
        parent_ids = set(subtask_parent.values()) - set(node_ids)
        parent_nodes = {}
        if parent_ids:
            parent_nodes = self._repo.get_nodes_batch(list(parent_ids))

        for item in items:
            # Urgency: sigmoid on days_until
            if item.days_until is not None:
                item.urgency = 1.0 / (1.0 + math.exp(item.days_until / 3.0))
            else:
                item.urgency = 0.3  # undated gets moderate baseline

            # Centrality: log-scaled blocking count
            bc = blocking_counts.get(item.node_id, 0)
            item.blocking_count = bc
            item.centrality = math.log(1 + bc) / math.log(11) if bc > 0 else 0.0

            # Health impact: worst network status
            worst = 0.0
            for net in item.networks:
                status = network_health.get(net, "on_track")
                if status == "falling_behind":
                    worst = max(worst, 1.0)
                elif status == "needs_attention":
                    worst = max(worst, 0.6)
                else:
                    worst = max(worst, 0.2)
            item.health_impact = worst if item.networks else 0.2

            # Decay momentum: stale areas get a boost
            # We use 1 - decay_score; fetch from node if available
            try:
                node = self._repo.get_nodes_batch([item.node_id]).get(item.node_id)
                if node:
                    item.decay_momentum = 1.0 - (node.decay_score if node.decay_score is not None else 1.0)
            except Exception:
                item.decay_momentum = 0.0

            # Dependency depth: BFS up SUBTASK_OF chain
            depth = 0
            current = item.node_id
            visited = set()
            while current in subtask_parent and current not in visited:
                visited.add(current)
                current = subtask_parent[current]
                depth += 1
            item.dependency_depth = min(depth * 0.2, 1.0)

            # Parent title
            if item.node_id in subtask_parent:
                pid = subtask_parent[item.node_id]
                pnode = parent_nodes.get(pid)
                if pnode:
                    item.parent_title = pnode.title

            # Composite priority
            item.composite_priority = (
                W_URGENCY * item.urgency
                + W_CENTRALITY * item.centrality
                + W_HEALTH_IMPACT * item.health_impact
                + W_DECAY_MOMENTUM * item.decay_momentum
                + W_DEPENDENCY * item.dependency_depth
            )

        return items

    # ------------------------------------------------------------------
    # Bucketing
    # ------------------------------------------------------------------

    def _bucket_items(
        self, items: list[HorizonItem], window: str
    ) -> HorizonView:
        """Sort items into time buckets and compute network load."""
        view = HorizonView()
        network_load: dict[str, int] = defaultdict(int)

        for item in items:
            # Network load
            for net in item.networks:
                network_load[net] += 1

            if item.days_until is None:
                view.undated.append(item)
            elif item.overdue:
                view.overdue.append(item)
            elif item.days_until == 0:
                view.today.append(item)
            elif item.days_until == 1:
                view.tomorrow.append(item)
            elif item.days_until <= 7:
                view.this_week.append(item)
            elif item.days_until <= 14:
                view.next_week.append(item)
            elif item.days_until <= 30:
                view.this_month.append(item)
            else:
                view.later.append(item)

        view.network_load = dict(network_load)

        # Filter by window
        if window == "day":
            view.this_week = []
            view.next_week = []
            view.this_month = []
            view.later = []
        elif window == "week":
            view.next_week = []
            view.this_month = []
            view.later = []
        elif window == "month":
            view.later = []

        return view

    # ------------------------------------------------------------------
    # Health & patterns helpers
    # ------------------------------------------------------------------

    def _get_network_health_map(self) -> dict[str, str]:
        """Get {network_name: status} for all networks."""
        try:
            from memora.core.health_scoring import HealthScoring

            hs = HealthScoring(self._repo)
            results = hs.compute_all_networks()
            return {r["network"]: r["status"] for r in results}
        except Exception:
            logger.debug("Could not compute network health", exc_info=True)
            return {}

    def _get_pattern_warnings(
        self, networks: list[str] | None = None
    ) -> list[dict]:
        """Get active pattern warnings, optionally filtered by network."""
        try:
            from memora.core.patterns import PatternEngine

            pe = PatternEngine(self._repo)
            patterns = pe.detect_all()
            warnings = [
                p for p in patterns
                if p.get("severity") in ("warning", "critical")
                and p.get("status") == "active"
            ]
            if networks:
                net_set = set(networks)
                warnings = [
                    w for w in warnings
                    if set(w.get("networks", [])) & net_set
                ]
            return warnings[:5]  # cap at 5 warnings
        except Exception:
            logger.debug("Could not load patterns", exc_info=True)
            return []

    def _get_pattern_note_for(self, node) -> str | None:
        """Get a pattern note relevant to a specific node."""
        try:
            from memora.core.patterns import PatternEngine

            pe = PatternEngine(self._repo)
            patterns = pe.detect_all()
            node_networks = {
                enum_val(n) for n in node.networks
            }
            for p in patterns:
                if p.get("severity") in ("warning", "critical"):
                    p_nets = set(p.get("networks", []))
                    if p_nets & node_networks:
                        return p.get("description", "")
            return None
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Impact analysis
    # ------------------------------------------------------------------

    def _find_blocked_items(self, node_id: str) -> list[dict]:
        """Find items that this node blocks (SUBTASK_OF children)."""
        edges = self._repo.get_edges_batch([node_id])
        blocked: list[dict] = []

        for edge in edges:
            src = str(edge.source_id) if hasattr(edge, "source_id") else str(edge.get("source_id", ""))
            tgt = str(edge.target_id) if hasattr(edge, "target_id") else str(edge.get("target_id", ""))
            etype = edge.edge_type if hasattr(edge, "edge_type") else edge.get("edge_type", "")
            etype_val = enum_val(etype)

            if etype_val == EdgeType.SUBTASK_OF.value and tgt == node_id:
                child_node = self._repo.get_node(UUID(src))
                if child_node:
                    blocked.append({
                        "node_id": src,
                        "title": child_node.title,
                        "kind": child_node.node_type.value,
                    })

        return blocked

    def _project_health_delta(self, node) -> dict[str, str]:
        """Project how completing this node affects network health."""
        delta: dict[str, str] = {}
        health_map = self._get_network_health_map()
        for net in node.networks:
            net_val = enum_val(net)
            status = health_map.get(net_val, "on_track")
            delta[net_val] = status
        return delta
