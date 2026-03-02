"""Timeline Analysis — temporal reconstruction and causal chain tracing."""

from __future__ import annotations

import logging
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone

logger = logging.getLogger(__name__)


class TimelineEngine:
    """Reconstruct timelines and trace causal chains through the graph."""

    def __init__(self, repo) -> None:
        self.repo = repo

    def get_timeline(
        self,
        start: str | None = None,
        end: str | None = None,
        networks: list[str] | None = None,
        node_types: list[str] | None = None,
        limit: int = 100,
        include_actions: bool = True,
    ) -> list[dict]:
        """Get chronologically ordered nodes using best-available dates,
        optionally interleaved with actions.
        """
        # Use best-date-aware query instead of plain created_at
        nodes = self.repo.get_nodes_with_best_date(
            start=start, end=end, networks=networks,
            node_types=node_types, limit=limit,
        )

        if not include_actions:
            return nodes

        # Interleave actions into the timeline
        actions = self.repo.get_actions_by_date_range(start=start, end=end, limit=limit)
        for a in actions:
            a["_timeline_type"] = "action"
            a["_sort_date"] = a.get("executed_at", "")
        for n in nodes:
            n["_timeline_type"] = "node"
            n["_sort_date"] = n.get("effective_date") or n.get("created_at", "")

        combined = nodes + actions
        combined.sort(key=lambda x: x.get("_sort_date", ""))
        return combined[:limit]

    def trace_causal_chain(
        self,
        node_id: str,
        direction: str = "both",
        max_depth: int = 5,
    ) -> dict:
        """BFS along temporal edges to reconstruct causal chains.

        Args:
            node_id: Starting node.
            direction: "forward" (EVOLVED_INTO, TRIGGERED), "backward" (PRECEDED_BY), or "both".
            max_depth: Maximum hops to traverse.

        Returns:
            Dict with "nodes" (list) and "edges" (list) forming the causal chain.

        Direction semantics:
            - Forward: follow edges where current node is source (TRIGGERED, EVOLVED_INTO)
            - Backward: follow edges where current node is target (PRECEDED_BY means
              "something preceded me", so going backward from B finds A in A->PRECEDED_BY->B)
        """
        forward_types = ["EVOLVED_INTO", "TRIGGERED"]
        backward_types = ["PRECEDED_BY"]

        visited = {node_id}
        queue = deque([(node_id, 0)])
        chain_nodes = [node_id]
        chain_edges = []

        while queue:
            current_id, depth = queue.popleft()
            if depth >= max_depth:
                continue

            neighbors = []
            if direction in ("forward", "both"):
                # Follow forward edges: current node is source
                neighbors.extend(
                    self.repo.get_temporal_neighbors_directed(
                        current_id, direction="forward", edge_types=forward_types
                    )
                )
            if direction in ("backward", "both"):
                # Follow backward edges: current node is target
                # For PRECEDED_BY: A→PRECEDED_BY→B means A preceded B.
                # Going backward from B means finding edges where B is the target.
                neighbors.extend(
                    self.repo.get_temporal_neighbors_directed(
                        current_id, direction="backward", edge_types=backward_types
                    )
                )

            for neighbor in neighbors:
                nid = neighbor["node_id"]
                if nid not in visited:
                    visited.add(nid)
                    chain_nodes.append(nid)
                    chain_edges.append({
                        "edge_id": neighbor["edge_id"],
                        "edge_type": neighbor["edge_type"],
                        "source_id": neighbor["source_id"],
                        "target_id": neighbor["target_id"],
                    })
                    queue.append((nid, depth + 1))

        # Fetch full node data
        nodes_map = self.repo.get_nodes_batch(chain_nodes)
        nodes = []
        for nid in chain_nodes:
            node = nodes_map.get(nid)
            if node:
                nodes.append(node.model_dump(mode="json"))

        return {"nodes": nodes, "edges": chain_edges}

    def find_concurrent(self, node_id: str, window_hours: int = 48) -> list[dict]:
        """Find nodes in other networks created within the same time window."""
        from uuid import UUID

        node = self.repo.get_node(UUID(node_id))
        if not node:
            return []

        node_created = node.created_at
        if isinstance(node_created, str):
            node_created = datetime.fromisoformat(node_created)

        start = (node_created - timedelta(hours=window_hours)).isoformat()
        end = (node_created + timedelta(hours=window_hours)).isoformat()

        candidates = self.repo.get_nodes_by_date_range(start=start, end=end, limit=50)

        node_networks = {n.value for n in node.networks} if node.networks else set()
        concurrent = []
        for c in candidates:
            if c["id"] == str(node.id):
                continue
            c_networks = set(c.get("networks", []))
            # Only include nodes from different networks
            if c_networks and not c_networks.intersection(node_networks):
                concurrent.append(c)

        return concurrent

    def detect_activity_bursts(
        self, window_days: int = 7, threshold: float = 2.0
    ) -> list[dict]:
        """Find periods with above-average node creation.

        Args:
            window_days: Size of the sliding window.
            threshold: Multiplier over average to count as a burst.
        """
        # Get all nodes for the last 90 days
        cutoff = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()
        nodes = self.repo.get_nodes_by_date_range(start=cutoff, limit=5000)

        if not nodes:
            return []

        # Bucket by day
        daily_counts: dict[str, int] = defaultdict(int)
        for n in nodes:
            created = n.get("created_at")
            if created:
                if isinstance(created, datetime):
                    day = created.strftime("%Y-%m-%d")
                else:
                    day = str(created)[:10]
                daily_counts[day] += 1

        if not daily_counts:
            return []

        avg = sum(daily_counts.values()) / max(len(daily_counts), 1)
        burst_threshold = avg * threshold

        bursts = []
        sorted_days = sorted(daily_counts.keys())
        i = 0
        while i < len(sorted_days):
            day = sorted_days[i]
            # Check window
            window_count = 0
            window_end = i
            for j in range(i, min(i + window_days, len(sorted_days))):
                window_count += daily_counts[sorted_days[j]]
                window_end = j

            window_avg = window_count / window_days
            if window_avg > burst_threshold / window_days:
                bursts.append({
                    "start": sorted_days[i],
                    "end": sorted_days[window_end],
                    "node_count": window_count,
                    "average_daily": round(window_avg, 1),
                    "overall_average": round(avg, 1),
                })
                i = window_end + 1
            else:
                i += 1

        return bursts

    def get_weekly_digest(self) -> dict:
        """Generate a structured weekly digest."""
        now = datetime.now(timezone.utc)
        week_ago = (now - timedelta(days=7)).isoformat()
        now_str = now.isoformat()

        nodes = self.repo.get_nodes_by_date_range(start=week_ago, end=now_str, limit=200)

        # Group by type
        by_type: dict[str, list] = defaultdict(list)
        by_network: dict[str, int] = defaultdict(int)

        for n in nodes:
            by_type[n.get("node_type", "UNKNOWN")].append(n)
            for net in (n.get("networks") or []):
                by_network[net] += 1

        return {
            "period": {"start": week_ago, "end": now_str},
            "total_nodes": len(nodes),
            "by_type": {k: len(v) for k, v in by_type.items()},
            "by_network": dict(by_network),
            "decisions": [
                {"id": n["id"], "title": n["title"]}
                for n in by_type.get("DECISION", [])
            ],
            "commitments": [
                {"id": n["id"], "title": n["title"]}
                for n in by_type.get("COMMITMENT", [])
            ],
            "events": [
                {"id": n["id"], "title": n["title"]}
                for n in by_type.get("EVENT", [])
            ],
        }
