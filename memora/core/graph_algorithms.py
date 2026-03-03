"""Graph Intelligence Algorithms — analytical engine over the knowledge graph.

Implements centrality, community detection, pathfinding, link prediction,
and anomaly detection. Operates in pure Python on DuckDB data (personal
graphs are small enough). Uses networkx for acceleration when available.
"""

from __future__ import annotations

import logging
import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

logger = logging.getLogger(__name__)

# Try to use networkx for acceleration
try:
    import networkx as nx
    HAS_NETWORKX = True
except ImportError:
    HAS_NETWORKX = False


class GraphAlgorithms:
    """Graph intelligence algorithms backed by GraphRepository."""

    def __init__(self, repo) -> None:
        self.repo = repo
        self._graph_cache: dict | None = None
        self._cache_time: float = 0

    # ── Graph Construction ────────────────────────────────────────

    def _build_graph(self, force: bool = False) -> dict:
        """Build an adjacency representation from the repository.

        Returns:
            {
                "adj": {node_id: {neighbor_id: {"weight": w, "edge_type": t, ...}, ...}},
                "nodes": {node_id: {"type": t, "title": t, "confidence": c, ...}},
                "edges": [(src, tgt, {attrs})],
            }
        """
        import time

        now = time.time()
        if not force and self._graph_cache and (now - self._cache_time) < 60:
            return self._graph_cache

        from memora.graph.models import NodeFilter

        all_nodes = self.repo.query_nodes(NodeFilter(limit=50000))
        adj: dict[str, dict[str, dict]] = defaultdict(dict)
        node_data: dict[str, dict] = {}
        edge_list: list[tuple[str, str, dict]] = []

        for node in all_nodes:
            nid = str(node.id)
            node_data[nid] = {
                "type": node.node_type.value if hasattr(node.node_type, "value") else str(node.node_type),
                "title": node.title,
                "confidence": node.confidence,
                "decay_score": node.decay_score or 0.5,
                "access_count": node.access_count,
                "networks": [n.value if hasattr(n, "value") else str(n) for n in node.networks],
                "created_at": node.created_at,
                "updated_at": node.updated_at,
                "tags": node.tags or [],
                "source_capture_id": str(node.source_capture_id) if node.source_capture_id else None,
            }

        # Fetch all edges
        all_node_ids = list(node_data.keys())
        if all_node_ids:
            all_edges = self.repo.get_edges_batch(all_node_ids)
            seen_edges: set[str] = set()
            for edge in all_edges:
                eid = str(edge.id)
                if eid in seen_edges:
                    continue
                seen_edges.add(eid)

                src = str(edge.source_id)
                tgt = str(edge.target_id)
                if src not in node_data or tgt not in node_data:
                    continue

                etype = edge.edge_type.value if hasattr(edge.edge_type, "value") else str(edge.edge_type)
                attrs = {
                    "weight": edge.weight,
                    "confidence": edge.confidence,
                    "edge_type": etype,
                    "created_at": edge.created_at,
                }

                adj[src][tgt] = attrs
                if edge.bidirectional:
                    adj[tgt][src] = attrs

                edge_list.append((src, tgt, attrs))

        self._graph_cache = {
            "adj": dict(adj),
            "nodes": node_data,
            "edges": edge_list,
        }
        self._cache_time = now
        return self._graph_cache

    def _to_networkx(self) -> Any:
        """Convert internal graph to a networkx DiGraph."""
        if not HAS_NETWORKX:
            raise ImportError("networkx is not installed")

        g = self._build_graph()
        G = nx.DiGraph()

        for nid, data in g["nodes"].items():
            G.add_node(nid, **data)

        for src, tgt, attrs in g["edges"]:
            G.add_edge(src, tgt, **attrs)

        return G

    # ── Degree Centrality ─────────────────────────────────────────

    def degree_centrality(self) -> list[dict]:
        """Compute degree centrality for all nodes.

        Returns list of {node_id, title, type, in_degree, out_degree, total_degree, centrality}
        sorted by centrality descending.
        """
        g = self._build_graph()
        n = len(g["nodes"])
        if n <= 1:
            return []

        in_degree: dict[str, int] = defaultdict(int)
        out_degree: dict[str, int] = defaultdict(int)

        for src, tgt, _ in g["edges"]:
            out_degree[src] += 1
            in_degree[tgt] += 1

        results = []
        for nid, data in g["nodes"].items():
            ind = in_degree.get(nid, 0)
            outd = out_degree.get(nid, 0)
            total = ind + outd
            centrality = total / (2 * (n - 1)) if n > 1 else 0
            results.append({
                "node_id": nid,
                "title": data["title"],
                "type": data["type"],
                "in_degree": ind,
                "out_degree": outd,
                "total_degree": total,
                "centrality": centrality,
            })

        results.sort(key=lambda x: x["centrality"], reverse=True)
        return results

    # ── Betweenness Centrality ────────────────────────────────────

    def betweenness_centrality(self, sample: int = 100) -> list[dict]:
        """Compute betweenness centrality (bridge/broker entities).

        Uses networkx if available, otherwise approximates via BFS sampling.

        Args:
            sample: Number of source nodes to sample for approximation.

        Returns list of {node_id, title, type, betweenness} sorted descending.
        """
        g = self._build_graph()
        nodes = list(g["nodes"].keys())
        if len(nodes) < 3:
            return []

        if HAS_NETWORKX:
            G = self._to_networkx()
            k = min(sample, len(nodes))
            bc = nx.betweenness_centrality(G, k=k, normalized=True, weight="weight")
            results = []
            for nid, score in bc.items():
                data = g["nodes"].get(nid, {})
                results.append({
                    "node_id": nid,
                    "title": data.get("title", ""),
                    "type": data.get("type", ""),
                    "betweenness": score,
                })
            results.sort(key=lambda x: x["betweenness"], reverse=True)
            return results

        # Pure Python approximation via BFS sampling
        import random

        adj = g["adj"]
        betweenness: dict[str, float] = defaultdict(float)
        sources = random.sample(nodes, min(sample, len(nodes)))

        for s in sources:
            # BFS shortest paths from s
            dist: dict[str, int] = {s: 0}
            paths: dict[str, int] = {s: 1}
            queue = [s]
            order = []
            idx = 0

            while idx < len(queue):
                v = queue[idx]
                idx += 1
                order.append(v)
                for w in adj.get(v, {}):
                    if w not in dist:
                        dist[w] = dist[v] + 1
                        paths[w] = 0
                        queue.append(w)
                    if dist[w] == dist[v] + 1:
                        paths[w] += paths[v]

            # Accumulate dependencies
            dep: dict[str, float] = defaultdict(float)
            for v in reversed(order):
                for w in adj.get(v, {}):
                    if dist.get(w, -1) == dist.get(v, -1) + 1 and paths.get(w, 0) > 0:
                        dep[v] += (paths[v] / paths[w]) * (1 + dep[w])
                if v != s:
                    betweenness[v] += dep[v]

        # Normalize
        n = len(nodes)
        norm = 2.0 / ((n - 1) * (n - 2)) if n > 2 else 1.0
        scale = len(nodes) / len(sources) if sources else 1.0

        results = []
        for nid, data in g["nodes"].items():
            score = betweenness.get(nid, 0) * norm * scale
            results.append({
                "node_id": nid,
                "title": data["title"],
                "type": data["type"],
                "betweenness": score,
            })
        results.sort(key=lambda x: x["betweenness"], reverse=True)
        return results

    # ── PageRank ──────────────────────────────────────────────────

    def pagerank(self, damping: float = 0.85, iterations: int = 50) -> list[dict]:
        """Compute PageRank scores for all nodes.

        Args:
            damping: Damping factor (probability of following a link).
            iterations: Maximum number of iterations.

        Returns list of {node_id, title, type, pagerank, rank} sorted descending.
        """
        g = self._build_graph()
        nodes = list(g["nodes"].keys())
        n = len(nodes)
        if n == 0:
            return []

        if HAS_NETWORKX:
            G = self._to_networkx()
            pr = nx.pagerank(G, alpha=damping, max_iter=iterations, weight="weight")
            results = []
            for rank, (nid, score) in enumerate(
                sorted(pr.items(), key=lambda x: x[1], reverse=True), 1
            ):
                data = g["nodes"].get(nid, {})
                results.append({
                    "node_id": nid,
                    "title": data.get("title", ""),
                    "type": data.get("type", ""),
                    "pagerank": score,
                    "rank": rank,
                })
            return results

        # Pure Python PageRank
        adj = g["adj"]
        rank_scores: dict[str, float] = {nid: 1.0 / n for nid in nodes}

        for _ in range(iterations):
            new_scores: dict[str, float] = {}
            for nid in nodes:
                incoming_sum = 0.0
                # Find all nodes pointing to nid
                for src in nodes:
                    if nid in adj.get(src, {}):
                        out_count = len(adj[src])
                        if out_count > 0:
                            weight = adj[src][nid].get("weight", 1.0)
                            total_weight = sum(
                                a.get("weight", 1.0) for a in adj[src].values()
                            )
                            if total_weight > 0:
                                incoming_sum += rank_scores[src] * (weight / total_weight)

                new_scores[nid] = (1 - damping) / n + damping * incoming_sum
            rank_scores = new_scores

        results = []
        for rank, (nid, score) in enumerate(
            sorted(rank_scores.items(), key=lambda x: x[1], reverse=True), 1
        ):
            data = g["nodes"][nid]
            results.append({
                "node_id": nid,
                "title": data["title"],
                "type": data["type"],
                "pagerank": score,
                "rank": rank,
            })
        return results

    # ── Community Detection (Label Propagation) ───────────────────

    def label_propagation_communities(self) -> list[dict]:
        """Detect communities using label propagation.

        Returns list of {community_id, members: [{node_id, title, type}], size}
        sorted by size descending.
        """
        g = self._build_graph()
        nodes = list(g["nodes"].keys())
        if not nodes:
            return []

        if HAS_NETWORKX:
            G = self._to_networkx().to_undirected()
            communities = list(nx.community.label_propagation_communities(G))
            results = []
            for i, community in enumerate(communities):
                members = []
                for nid in community:
                    data = g["nodes"].get(nid, {})
                    members.append({
                        "node_id": nid,
                        "title": data.get("title", ""),
                        "type": data.get("type", ""),
                    })
                results.append({
                    "community_id": i,
                    "members": members,
                    "size": len(members),
                })
            results.sort(key=lambda x: x["size"], reverse=True)
            return results

        # Pure Python label propagation
        import random

        adj = g["adj"]

        # Build undirected adjacency
        undirected: dict[str, set[str]] = defaultdict(set)
        for src, neighbors in adj.items():
            for tgt in neighbors:
                undirected[src].add(tgt)
                undirected[tgt].add(src)

        labels: dict[str, str] = {nid: nid for nid in nodes}

        for _ in range(50):  # max iterations
            changed = False
            shuffled = list(nodes)
            random.shuffle(shuffled)

            for nid in shuffled:
                neighbors = undirected.get(nid, set())
                if not neighbors:
                    continue

                # Count neighbor labels
                label_counts: dict[str, int] = defaultdict(int)
                for neighbor in neighbors:
                    label_counts[labels[neighbor]] += 1

                # Pick most common label
                max_count = max(label_counts.values())
                top_labels = [l for l, c in label_counts.items() if c == max_count]
                new_label = random.choice(top_labels)

                if labels[nid] != new_label:
                    labels[nid] = new_label
                    changed = True

            if not changed:
                break

        # Group by label
        communities_map: dict[str, list[str]] = defaultdict(list)
        for nid, label in labels.items():
            communities_map[label].append(nid)

        results = []
        for i, (_, members_ids) in enumerate(
            sorted(communities_map.items(), key=lambda x: len(x[1]), reverse=True)
        ):
            members = []
            for nid in members_ids:
                data = g["nodes"].get(nid, {})
                members.append({
                    "node_id": nid,
                    "title": data.get("title", ""),
                    "type": data.get("type", ""),
                })
            results.append({
                "community_id": i,
                "members": members,
                "size": len(members),
            })

        return results

    # ── Shortest Path (Dijkstra) ──────────────────────────────────

    def shortest_path(
        self, source_id: str, target_id: str, weighted: bool = True
    ) -> dict | None:
        """Find shortest path between two nodes using Dijkstra.

        Args:
            source_id: Source node ID.
            target_id: Target node ID.
            weighted: Use edge weights (True) or hop count (False).

        Returns:
            {path: [{node_id, title, type}], total_weight, hops} or None.
        """
        g = self._build_graph()
        adj = g["adj"]

        if source_id not in g["nodes"] or target_id not in g["nodes"]:
            return None

        # Build undirected adjacency for pathfinding
        undirected: dict[str, dict[str, dict]] = defaultdict(dict)
        for src, neighbors in adj.items():
            for tgt, attrs in neighbors.items():
                undirected[src][tgt] = attrs
                undirected[tgt][src] = attrs

        import heapq

        # Dijkstra
        dist: dict[str, float] = {source_id: 0}
        prev: dict[str, str | None] = {source_id: None}
        pq = [(0.0, source_id)]

        while pq:
            d, u = heapq.heappop(pq)
            if u == target_id:
                break
            if d > dist.get(u, float("inf")):
                continue

            for v, attrs in undirected.get(u, {}).items():
                w = (1.0 / max(attrs.get("weight", 1.0), 0.01)) if weighted else 1.0
                new_dist = d + w
                if new_dist < dist.get(v, float("inf")):
                    dist[v] = new_dist
                    prev[v] = u
                    heapq.heappush(pq, (new_dist, v))

        if target_id not in prev:
            return None

        # Reconstruct path
        path_ids = []
        current = target_id
        while current is not None:
            path_ids.append(current)
            current = prev[current]
        path_ids.reverse()

        path = []
        for nid in path_ids:
            data = g["nodes"].get(nid, {})
            path.append({
                "node_id": nid,
                "title": data.get("title", ""),
                "type": data.get("type", ""),
            })

        return {
            "path": path,
            "total_weight": dist[target_id],
            "hops": len(path_ids) - 1,
        }

    # ── K-Shortest Paths ──────────────────────────────────────────

    def k_shortest_paths(
        self, source_id: str, target_id: str, k: int = 3
    ) -> list[dict]:
        """Find k shortest paths using Yen's algorithm.

        Returns list of {path, total_weight, hops}.
        """
        first = self.shortest_path(source_id, target_id)
        if not first:
            return []

        results = [first]
        if k <= 1:
            return results

        g = self._build_graph()
        adj = g["adj"]

        # Build undirected adjacency
        undirected: dict[str, dict[str, dict]] = defaultdict(dict)
        for src, neighbors in adj.items():
            for tgt, attrs in neighbors.items():
                undirected[src][tgt] = attrs
                undirected[tgt][src] = attrs

        candidates = []
        previous_paths = [
            [step["node_id"] for step in first["path"]]
        ]

        for ki in range(1, k):
            last_path = previous_paths[-1]

            for i in range(len(last_path) - 1):
                spur_node = last_path[i]
                root_path = last_path[: i + 1]

                # Remove edges used by previous paths at this spur point
                removed_edges: list[tuple[str, str, dict]] = []
                for prev_p in previous_paths:
                    if prev_p[: i + 1] == root_path and i + 1 < len(prev_p):
                        u, v = prev_p[i], prev_p[i + 1]
                        if v in undirected.get(u, {}):
                            removed_edges.append((u, v, undirected[u].pop(v)))
                        if u in undirected.get(v, {}):
                            removed_edges.append((v, u, undirected[v].pop(u)))

                # Remove root path nodes (except spur)
                removed_nodes = set(root_path[:-1])

                # Find spur path
                spur_result = self._dijkstra_on(
                    undirected, g["nodes"], spur_node, target_id, removed_nodes
                )

                # Restore edges
                for u, v, attrs in removed_edges:
                    undirected[u][v] = attrs

                if spur_result:
                    full_path_ids = root_path[:-1] + [
                        step["node_id"] for step in spur_result["path"]
                    ]
                    full_path = []
                    for nid in full_path_ids:
                        data = g["nodes"].get(nid, {})
                        full_path.append({
                            "node_id": nid,
                            "title": data.get("title", ""),
                            "type": data.get("type", ""),
                        })

                    candidate = {
                        "path": full_path,
                        "total_weight": spur_result["total_weight"],
                        "hops": len(full_path) - 1,
                    }

                    path_key = tuple(full_path_ids)
                    existing_keys = {
                        tuple(step["node_id"] for step in r["path"])
                        for r in results + [c for _, c in candidates]
                    }
                    if path_key not in existing_keys:
                        candidates.append((candidate["total_weight"], candidate))

            if not candidates:
                break

            candidates.sort(key=lambda x: x[0])
            best = candidates.pop(0)[1]
            results.append(best)
            previous_paths.append([step["node_id"] for step in best["path"]])

        return results

    def _dijkstra_on(
        self,
        adj: dict[str, dict[str, dict]],
        node_data: dict[str, dict],
        source: str,
        target: str,
        excluded: set[str],
    ) -> dict | None:
        """Run Dijkstra on a given adjacency with excluded nodes."""
        import heapq

        dist: dict[str, float] = {source: 0}
        prev: dict[str, str | None] = {source: None}
        pq = [(0.0, source)]

        while pq:
            d, u = heapq.heappop(pq)
            if u == target:
                break
            if d > dist.get(u, float("inf")):
                continue
            for v, attrs in adj.get(u, {}).items():
                if v in excluded:
                    continue
                w = 1.0 / max(attrs.get("weight", 1.0), 0.01)
                new_dist = d + w
                if new_dist < dist.get(v, float("inf")):
                    dist[v] = new_dist
                    prev[v] = u
                    heapq.heappush(pq, (new_dist, v))

        if target not in prev:
            return None

        path_ids = []
        current = target
        while current is not None:
            path_ids.append(current)
            current = prev[current]
        path_ids.reverse()

        path = []
        for nid in path_ids:
            data = node_data.get(nid, {})
            path.append({
                "node_id": nid,
                "title": data.get("title", ""),
                "type": data.get("type", ""),
            })

        return {
            "path": path,
            "total_weight": dist[target],
            "hops": len(path_ids) - 1,
        }

    # ── Link Prediction ───────────────────────────────────────────

    def predict_links(self, top_k: int = 20) -> list[dict]:
        """Predict missing connections using Adamic-Adar + common neighbors.

        Returns list of {source_id, source_title, target_id, target_title,
                         score, common_neighbors, method} sorted by score descending.
        """
        g = self._build_graph()
        adj = g["adj"]

        # Build undirected neighbor sets
        neighbors: dict[str, set[str]] = defaultdict(set)
        for src, nbrs in adj.items():
            for tgt in nbrs:
                neighbors[src].add(tgt)
                neighbors[tgt].add(src)

        # Existing edges (undirected)
        existing: set[tuple[str, str]] = set()
        for src, nbrs in adj.items():
            for tgt in nbrs:
                existing.add((src, tgt))
                existing.add((tgt, src))

        predictions: dict[tuple[str, str], dict] = {}
        nodes = list(g["nodes"].keys())

        for u in nodes:
            u_neighbors = neighbors.get(u, set())
            for v in nodes:
                if u >= v:  # avoid duplicates
                    continue
                if (u, v) in existing:
                    continue

                common = u_neighbors & neighbors.get(v, set())
                if not common:
                    continue

                # Adamic-Adar index
                aa_score = 0.0
                for w in common:
                    degree = len(neighbors.get(w, set()))
                    if degree > 1:
                        aa_score += 1.0 / math.log(degree)

                # Common neighbors score (normalized)
                cn_score = len(common) / max(
                    math.sqrt(len(u_neighbors) * len(neighbors.get(v, set()))), 1
                )

                # Combined score
                combined = 0.6 * aa_score + 0.4 * cn_score

                predictions[(u, v)] = {
                    "source_id": u,
                    "source_title": g["nodes"][u]["title"],
                    "target_id": v,
                    "target_title": g["nodes"][v]["title"],
                    "score": combined,
                    "common_neighbors": len(common),
                    "method": "adamic_adar+common_neighbors",
                }

        results = sorted(predictions.values(), key=lambda x: x["score"], reverse=True)
        return results[:top_k]

    # ── Structural Anomalies ──────────────────────────────────────

    def structural_anomalies(self) -> list[dict]:
        """Detect structural anomalies in the graph.

        Finds:
        - Isolated high-importance nodes (high confidence but few connections)
        - Unusual density clusters (local density >> global)
        - Orphan nodes (no edges at all)

        Returns list of {anomaly_type, description, node_ids, severity, details}.
        """
        g = self._build_graph()
        adj = g["adj"]
        anomalies = []

        # Build undirected degree counts
        degree: dict[str, int] = defaultdict(int)
        for src, nbrs in adj.items():
            for tgt in nbrs:
                degree[src] += 1
                degree[tgt] += 1

        n = len(g["nodes"])
        avg_degree = sum(degree.values()) / max(n, 1)

        # Orphan nodes (no edges)
        orphans = [
            nid for nid in g["nodes"]
            if degree.get(nid, 0) == 0
        ]
        if orphans:
            anomalies.append({
                "anomaly_type": "orphan_nodes",
                "description": f"{len(orphans)} node(s) with no connections",
                "node_ids": orphans[:20],
                "severity": "info" if len(orphans) < 5 else "warning",
                "details": {
                    "titles": [g["nodes"][nid]["title"] for nid in orphans[:10]],
                },
            })

        # Isolated high-importance nodes
        for nid, data in g["nodes"].items():
            d = degree.get(nid, 0)
            conf = data.get("confidence", 0)
            if conf >= 0.8 and d <= 1 and d < avg_degree * 0.3:
                anomalies.append({
                    "anomaly_type": "isolated_high_importance",
                    "description": (
                        f"'{data['title']}' has high confidence ({conf:.0%}) "
                        f"but only {d} connection(s)"
                    ),
                    "node_ids": [nid],
                    "severity": "warning",
                    "details": {
                        "confidence": conf,
                        "degree": d,
                        "avg_degree": avg_degree,
                    },
                })

        # Dense clusters — nodes with degree >> average
        threshold = max(avg_degree * 3, 5)
        dense_nodes = [
            nid for nid, d in degree.items()
            if d >= threshold
        ]
        if dense_nodes:
            anomalies.append({
                "anomaly_type": "unusual_density",
                "description": (
                    f"{len(dense_nodes)} node(s) with unusually high connectivity "
                    f"(≥{threshold:.0f} edges vs avg {avg_degree:.1f})"
                ),
                "node_ids": dense_nodes[:10],
                "severity": "info",
                "details": {
                    "titles": [
                        f"{g['nodes'][nid]['title']} ({degree[nid]} edges)"
                        for nid in dense_nodes[:10]
                    ],
                },
            })

        return anomalies

    # ── Temporal Anomalies ────────────────────────────────────────

    def temporal_anomalies(self, window: int = 30) -> list[dict]:
        """Detect temporal anomalies in graph activity.

        Finds:
        - Activity bursts (sudden spikes in node creation)
        - Sudden silence (periods with no activity after regular activity)
        - Network-specific temporal shifts

        Args:
            window: Number of days to analyze.

        Returns list of {anomaly_type, description, severity, details}.
        """
        g = self._build_graph()
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=window)

        # Group nodes by creation day
        daily_counts: dict[str, int] = defaultdict(int)
        network_daily: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

        for nid, data in g["nodes"].items():
            created = data.get("created_at")
            if not created:
                continue
            if isinstance(created, str):
                try:
                    created = datetime.fromisoformat(created.replace("Z", "+00:00"))
                except (ValueError, TypeError):
                    continue
            if not hasattr(created, "date"):
                continue
            if created.replace(tzinfo=timezone.utc) < cutoff:
                continue

            day_key = created.strftime("%Y-%m-%d")
            daily_counts[day_key] += 1
            for net in data.get("networks", []):
                network_daily[net][day_key] += 1

        anomalies = []
        if not daily_counts:
            return anomalies

        counts = list(daily_counts.values())
        avg_daily = sum(counts) / max(len(counts), 1)
        std_daily = math.sqrt(
            sum((c - avg_daily) ** 2 for c in counts) / max(len(counts), 1)
        )

        # Activity bursts
        burst_threshold = avg_daily + 2 * std_daily if std_daily > 0 else avg_daily * 3
        bursts = [
            (day, count) for day, count in daily_counts.items()
            if count > burst_threshold and count > 3
        ]
        if bursts:
            anomalies.append({
                "anomaly_type": "activity_burst",
                "description": (
                    f"{len(bursts)} day(s) with unusually high activity "
                    f"(>{burst_threshold:.0f} nodes vs avg {avg_daily:.1f}/day)"
                ),
                "severity": "info",
                "details": {
                    "burst_days": sorted(bursts, key=lambda x: x[1], reverse=True)[:5],
                    "avg_daily": avg_daily,
                },
            })

        # Sudden silence — check if last 7 days have significantly less activity
        recent_7 = sum(
            1 for nid, data in g["nodes"].items()
            if data.get("created_at") and _parse_date(data["created_at"], now - timedelta(days=7))
        )
        prior_7 = sum(
            1 for nid, data in g["nodes"].items()
            if data.get("created_at")
            and _parse_date(data["created_at"], now - timedelta(days=14))
            and not _parse_date(data["created_at"], now - timedelta(days=7))
        )

        if prior_7 > 5 and recent_7 < prior_7 * 0.3:
            anomalies.append({
                "anomaly_type": "sudden_silence",
                "description": (
                    f"Activity dropped {((1 - recent_7 / max(prior_7, 1)) * 100):.0f}% "
                    f"in last 7 days ({recent_7} nodes vs {prior_7} prior week)"
                ),
                "severity": "warning",
                "details": {
                    "recent_7_days": recent_7,
                    "prior_7_days": prior_7,
                },
            })

        # Network-specific silence
        for net, daily in network_daily.items():
            net_counts = list(daily.values())
            if len(net_counts) < 3:
                continue
            net_avg = sum(net_counts) / len(net_counts)
            # Check last 7 days
            recent_days = set()
            for i in range(7):
                recent_days.add((now - timedelta(days=i)).strftime("%Y-%m-%d"))
            recent_net = sum(daily.get(d, 0) for d in recent_days)
            if net_avg > 1 and recent_net == 0:
                anomalies.append({
                    "anomaly_type": "network_silence",
                    "description": (
                        f"No activity in {net} network for 7+ days "
                        f"(previously avg {net_avg:.1f}/day)"
                    ),
                    "severity": "warning",
                    "details": {"network": net, "avg_daily": net_avg},
                })

        return anomalies

    # ── Summary / Combined Intelligence ───────────────────────────

    def graph_intelligence_summary(self) -> dict:
        """Generate a combined intelligence summary.

        Returns dict with top entities, communities, anomalies, and predictions.
        """
        pr = self.pagerank()
        communities = self.label_propagation_communities()
        structural = self.structural_anomalies()
        temporal = self.temporal_anomalies()
        predictions = self.predict_links(top_k=10)

        return {
            "top_entities": pr[:10],
            "communities": communities[:10],
            "structural_anomalies": structural,
            "temporal_anomalies": temporal,
            "predicted_links": predictions,
            "stats": {
                "total_nodes": len(self._build_graph()["nodes"]),
                "total_edges": len(self._build_graph()["edges"]),
                "num_communities": len(communities),
                "num_anomalies": len(structural) + len(temporal),
                "num_predictions": len(predictions),
            },
        }

    def get_entity_centrality_rank(self, node_id: str) -> int | None:
        """Get the PageRank position for a specific entity."""
        pr = self.pagerank()
        for entry in pr:
            if entry["node_id"] == node_id:
                return entry["rank"]
        return None

    def get_entity_communities(self, node_id: str) -> list[int]:
        """Get community IDs for a specific entity."""
        communities = self.label_propagation_communities()
        result = []
        for community in communities:
            for member in community["members"]:
                if member["node_id"] == node_id:
                    result.append(community["community_id"])
                    break
        return result

    def get_entity_predicted_links(self, node_id: str, top_k: int = 5) -> list[dict]:
        """Get predicted links for a specific entity."""
        all_predictions = self.predict_links(top_k=100)
        return [
            p for p in all_predictions
            if p["source_id"] == node_id or p["target_id"] == node_id
        ][:top_k]


def _parse_date(value, threshold: datetime) -> bool:
    """Check if a date value is after the threshold."""
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except (ValueError, TypeError):
            return False
    elif hasattr(value, "replace"):
        dt = value
    else:
        return False

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    if threshold.tzinfo is None:
        threshold = threshold.replace(tzinfo=timezone.utc)

    return dt >= threshold
