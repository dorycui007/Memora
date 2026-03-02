"""Investigation Mode — deep link analysis and path-finding with enrichment."""

from __future__ import annotations

import logging
from uuid import UUID

logger = logging.getLogger(__name__)


class InvestigationEngine:
    """Interactive investigation engine for deep link analysis."""

    def __init__(self, repo, truth_layer=None) -> None:
        self.repo = repo
        self._truth_layer = truth_layer

    def _get_truth_layer(self):
        """Lazily resolve truth layer."""
        if self._truth_layer is not None:
            return self._truth_layer
        try:
            from memora.core.truth_layer import TruthLayer
            self._truth_layer = TruthLayer(self.repo.get_truth_layer_conn())
            return self._truth_layer
        except Exception:
            return None

    def expand(
        self,
        node_id: str,
        hops: int = 1,
        node_types: list[str] | None = None,
        edge_types: list[str] | None = None,
        networks: list[str] | None = None,
    ) -> dict:
        """Get filtered neighborhood around a node, enriched with context."""
        result = self.repo.get_filtered_neighborhood(
            node_id=node_id,
            hops=hops,
            node_types=node_types,
            edge_types=edge_types,
            networks=networks,
        )

        # Enrich each node with decay_score, health context, pending outcome status
        for node_data in result.get("nodes", []):
            nid = node_data.get("id", "")
            enrichment = {}

            # Decay score is already in the node data from model_dump
            enrichment["decay_score"] = node_data.get("decay_score", 1.0)

            # Network health status for the node's networks
            node_networks = node_data.get("networks", [])
            if node_networks:
                net_val = node_networks[0]
                if hasattr(net_val, "value"):
                    net_val = net_val.value
                health = self.repo.get_latest_network_health(net_val)
                if health:
                    enrichment["network_health"] = health.get("status", "unknown")

            # Check if this node has pending outcomes
            outcomes = self.repo.get_outcomes_for_node(nid)
            enrichment["has_outcomes"] = len(outcomes) > 0
            enrichment["outcome_count"] = len(outcomes)
            if outcomes:
                enrichment["latest_outcome_rating"] = outcomes[0].get("rating")

            node_data["enrichment"] = enrichment

        return result

    def search(
        self,
        raw_query: str,
        entity_names: list[str],
        filters: dict | None = None,
        embedding_engine=None,
        vector_store=None,
        top_k: int = 15,
    ) -> list[dict]:
        """Discovery search with content matching, enrichment, and ranking.

        Multi-query hybrid search across entity names (or raw query as fallback),
        with batch enrichment for connection counts and node metadata.
        """
        filters = filters or {}

        # ── 1. Collect search results with scores ──
        # {node_id: best_score}
        scored: dict[str, float] = {}
        queries = entity_names if entity_names else [raw_query]

        if embedding_engine and vector_store:
            for q in queries:
                try:
                    vector = embedding_engine.embed_text(q)
                    results = vector_store.hybrid_search(
                        query_vector=vector,
                        query_text=q,
                        top_k=8,
                        filters=filters if filters else None,
                    )
                    for r in results:
                        # Max-score deduplication
                        if r.node_id not in scored or r.score > scored[r.node_id]:
                            scored[r.node_id] = r.score
                except Exception:
                    logger.debug("Hybrid search failed for query '%s'", q, exc_info=True)
        else:
            # ── Fallback: substring search ──
            for q in queries:
                try:
                    ilike_results = self.repo.search_nodes_ilike(q, limit=10)
                    for row in ilike_results:
                        nid = str(row["id"])
                        if nid not in scored:
                            scored[nid] = 0.5  # default score for text match
                except Exception:
                    logger.debug("ilike search failed for '%s'", q, exc_info=True)
                try:
                    title_results = self.repo.search_by_title(q, limit=10)
                    for node in title_results:
                        nid = str(node.id)
                        if nid not in scored or scored[nid] < 0.6:
                            scored[nid] = 0.6  # title match slightly higher
                except Exception:
                    logger.debug("Title search failed for '%s'", q, exc_info=True)

        if not scored:
            return []

        # ── 2. Batch enrichment ──
        node_ids = list(scored.keys())
        nodes_map = self.repo.get_nodes_batch(node_ids)
        conn_counts = self.repo.get_connection_counts_batch(node_ids)

        # ── 3. Build result dicts, apply type/network filters for fallback path ──
        results = []
        filter_types = {t.upper() for t in (filters.get("node_types") or [])}
        filter_networks = {n.upper() for n in (filters.get("networks") or [])}

        for nid, score in scored.items():
            node = nodes_map.get(nid)
            if not node:
                continue

            ntype = node.node_type.value if hasattr(node.node_type, "value") else str(node.node_type)
            networks = [n.value if hasattr(n, "value") else str(n) for n in node.networks]

            # Apply filters (vector store may already filter, but fallback path doesn't)
            if filter_types and ntype.upper() not in filter_types:
                continue
            if filter_networks and not any(n.upper() in filter_networks for n in networks):
                continue

            snippet = ""
            if node.content:
                snippet = node.content[:80].replace("\n", " ")
                if len(node.content) > 80:
                    snippet += "..."

            results.append({
                "id": str(node.id),
                "title": node.title,
                "node_type": ntype,
                "content_snippet": snippet,
                "networks": networks,
                "confidence": node.confidence or 0,
                "decay_score": node.decay_score if hasattr(node, "decay_score") else 1.0,
                "connection_count": conn_counts.get(nid, 0),
                "score": score,
            })

        # ── 4. Rank by score descending, cap at top_k ──
        results.sort(key=lambda r: r["score"], reverse=True)
        return results[:top_k]

    def find_path(self, source_id: str, target_id: str, max_depth: int = 6) -> dict:
        """Find shortest path between two nodes, enriched with edge semantics."""
        path = self.repo.find_shortest_path(source_id, target_id, max_depth=max_depth)

        if path is None:
            return {"found": False, "path": [], "nodes": [], "hops": []}

        # Fetch node details for path
        nodes_map = self.repo.get_nodes_batch(path)

        # Build hops with edge information between consecutive nodes
        hops = []
        for i in range(len(path) - 1):
            current_id = path[i]
            next_id = path[i + 1]
            current_node = nodes_map.get(current_id)
            next_node = nodes_map.get(next_id)

            # Get edge between these two nodes
            edges = self.repo.get_edges_between(current_id, next_id)
            edge_info = None
            if edges:
                e = edges[0]
                edge_info = {
                    "edge_type": e.edge_type.value,
                    "edge_category": e.edge_category.value,
                    "confidence": e.confidence,
                    "properties": e.properties,
                }

            hops.append({
                "from": {
                    "id": current_id,
                    "node_type": current_node.node_type.value if current_node else "?",
                    "title": current_node.title if current_node else "?",
                },
                "to": {
                    "id": next_id,
                    "node_type": next_node.node_type.value if next_node else "?",
                    "title": next_node.title if next_node else "?",
                },
                "edge": edge_info,
            })

        # Also return flat node list for backward compat
        nodes = []
        for nid in path:
            node = nodes_map.get(nid)
            if node:
                nodes.append({
                    "id": str(node.id),
                    "node_type": node.node_type.value,
                    "title": node.title,
                    "networks": [n.value for n in node.networks],
                })

        return {"found": True, "path": path, "nodes": nodes, "hops": hops}

    def find_common(self, node_ids: list[str]) -> list[dict]:
        """Find entities connected to all specified nodes."""
        return self.repo.get_shared_connections(node_ids)

    def highlight_bridges(self, node_ids: list[str] | None = None) -> list[dict]:
        """Surface cross-network connections in the current view."""
        if not node_ids:
            return self.repo.query_bridges(validated_only=True, limit=20)

        # Query bridges directly for the given nodes instead of fetching all
        return self.repo.get_bridges_for_nodes(node_ids)

    def get_node_summary(self, node_id: str) -> dict | None:
        """Get a comprehensive summary of a node for investigation."""
        node = self.repo.get_node(UUID(node_id))
        if not node:
            return None

        edges = self.repo.get_edges(UUID(node_id))
        actions = self.repo.get_actions_for_node(node_id)
        outcomes = self.repo.get_outcomes_for_node(node_id)

        # Collect connected node IDs
        connected_ids = set()
        for e in edges:
            connected_ids.add(str(e.source_id))
            connected_ids.add(str(e.target_id))
        connected_ids.discard(node_id)

        connected_nodes = self.repo.get_nodes_batch(list(connected_ids))

        connections = []
        for e in edges:
            other_id = str(e.target_id) if str(e.source_id) == node_id else str(e.source_id)
            other = connected_nodes.get(other_id)
            connections.append({
                "edge_type": e.edge_type.value,
                "direction": "outgoing" if str(e.source_id) == node_id else "incoming",
                "node_id": other_id,
                "node_type": other.node_type.value if other else "?",
                "title": other.title if other else "?",
            })

        # Related patterns from detected_patterns where this node appears in evidence
        patterns = self.repo.get_patterns_for_node(node_id)

        # Truth layer facts for this node
        facts = []
        tl = self._get_truth_layer()
        if tl:
            try:
                facts = tl.query_facts(node_id=node_id)
            except Exception:
                pass

        return {
            "node": node.model_dump(mode="json"),
            "connections": connections,
            "connection_count": len(connections),
            "actions": actions[:10],
            "outcomes": outcomes,
            "patterns": patterns,
            "facts": facts,
        }
