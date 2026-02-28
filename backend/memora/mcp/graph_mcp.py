"""Graph MCP Server — internal graph + vector DB as MCP tool.

Provides agents with the ability to query their own knowledge graph,
perform semantic search, and access the Truth Layer.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from memora.graph.models import NodeFilter, NodeType, NetworkType
from memora.graph.repository import GraphRepository
from memora.vector.store import VectorStore
from memora.vector.embeddings import EmbeddingEngine

logger = logging.getLogger(__name__)


class GraphMCPServer:
    """MCP tool server for querying the internal knowledge graph."""

    def __init__(
        self,
        repo: GraphRepository,
        vector_store: VectorStore | None = None,
        embedding_engine: EmbeddingEngine | None = None,
        truth_layer: Any | None = None,
    ) -> None:
        self._repo = repo
        self._vector_store = vector_store
        self._embedding_engine = embedding_engine
        self._truth_layer = truth_layer

    def get_tools(self) -> list[dict[str, Any]]:
        """Return MCP tool definitions for agents."""
        return [
            {
                "name": "graph_query_nodes",
                "description": "Query nodes in the knowledge graph with filters",
                "parameters": {
                    "node_types": {"type": "array", "items": {"type": "string"}, "description": "Filter by node types"},
                    "networks": {"type": "array", "items": {"type": "string"}, "description": "Filter by networks"},
                    "tags": {"type": "array", "items": {"type": "string"}, "description": "Filter by tags"},
                    "limit": {"type": "integer", "default": 20},
                },
            },
            {
                "name": "graph_get_node",
                "description": "Get a specific node by ID with all properties",
                "parameters": {
                    "node_id": {"type": "string", "description": "The node UUID"},
                },
            },
            {
                "name": "graph_get_neighborhood",
                "description": "Get the 1-2 hop neighborhood around a node",
                "parameters": {
                    "node_id": {"type": "string", "description": "The center node UUID"},
                    "hops": {"type": "integer", "default": 1, "description": "Number of hops (1 or 2)"},
                },
            },
            {
                "name": "graph_semantic_search",
                "description": "Semantic search over graph nodes using embeddings",
                "parameters": {
                    "query": {"type": "string", "description": "Search query text"},
                    "top_k": {"type": "integer", "default": 10},
                    "node_type": {"type": "string", "description": "Optional node type filter"},
                },
            },
            {
                "name": "graph_get_stats",
                "description": "Get graph statistics (node count, edge count, breakdowns)",
                "parameters": {},
            },
            {
                "name": "truth_layer_query",
                "description": "Query verified facts from the Truth Layer",
                "parameters": {
                    "node_id": {"type": "string", "description": "Filter by node ID"},
                    "status": {"type": "string", "description": "Filter by status (active/stale/contradicted)"},
                    "limit": {"type": "integer", "default": 20},
                },
            },
        ]

    def execute_tool(self, tool_name: str, parameters: dict[str, Any]) -> dict[str, Any]:
        """Execute a tool by name with the given parameters."""
        handlers = {
            "graph_query_nodes": self._query_nodes,
            "graph_get_node": self._get_node,
            "graph_get_neighborhood": self._get_neighborhood,
            "graph_semantic_search": self._semantic_search,
            "graph_get_stats": self._get_stats,
            "truth_layer_query": self._truth_layer_query,
        }

        handler = handlers.get(tool_name)
        if not handler:
            return {"error": f"Unknown tool: {tool_name}"}

        try:
            return handler(parameters)
        except Exception as e:
            logger.error("Tool %s failed: %s", tool_name, e)
            return {"error": str(e)}

    def _query_nodes(self, params: dict[str, Any]) -> dict[str, Any]:
        node_types = None
        if params.get("node_types"):
            node_types = [NodeType(t) for t in params["node_types"]]

        networks = None
        if params.get("networks"):
            networks = [NetworkType(n) for n in params["networks"]]

        filters = NodeFilter(
            node_types=node_types,
            networks=networks,
            tags=params.get("tags"),
            limit=params.get("limit", 20),
        )

        nodes = self._repo.query_nodes(filters)
        return {
            "nodes": [
                {
                    "id": str(n.id),
                    "node_type": n.node_type.value,
                    "title": n.title,
                    "content": n.content[:200] if n.content else "",
                    "networks": [net.value for net in n.networks],
                    "confidence": n.confidence,
                    "tags": n.tags,
                    "created_at": n.created_at.isoformat(),
                }
                for n in nodes
            ],
            "count": len(nodes),
        }

    def _get_node(self, params: dict[str, Any]) -> dict[str, Any]:
        node = self._repo.get_node(UUID(params["node_id"]))
        if not node:
            return {"error": "Node not found"}

        return {
            "id": str(node.id),
            "node_type": node.node_type.value,
            "title": node.title,
            "content": node.content,
            "properties": node.properties,
            "confidence": node.confidence,
            "networks": [n.value for n in node.networks],
            "tags": node.tags,
            "decay_score": node.decay_score,
            "created_at": node.created_at.isoformat(),
            "updated_at": node.updated_at.isoformat(),
        }

    def _get_neighborhood(self, params: dict[str, Any]) -> dict[str, Any]:
        hops = min(params.get("hops", 1), 2)
        subgraph = self._repo.get_neighborhood(UUID(params["node_id"]), hops=hops)

        return {
            "nodes": [
                {
                    "id": str(n.id),
                    "node_type": n.node_type.value,
                    "title": n.title,
                    "networks": [net.value for net in n.networks],
                }
                for n in subgraph.nodes
            ],
            "edges": [
                {
                    "id": str(e.id),
                    "source_id": str(e.source_id),
                    "target_id": str(e.target_id),
                    "edge_type": e.edge_type.value,
                    "edge_category": e.edge_category.value,
                }
                for e in subgraph.edges
            ],
            "node_count": len(subgraph.nodes),
            "edge_count": len(subgraph.edges),
        }

    def _semantic_search(self, params: dict[str, Any]) -> dict[str, Any]:
        if not self._vector_store or not self._embedding_engine:
            return {"error": "Vector search not available"}

        query = params.get("query", "")
        top_k = params.get("top_k", 10)

        embedding = self._embedding_engine.embed_text(query)
        filters = {}
        if params.get("node_type"):
            filters["node_type"] = params["node_type"]

        results = self._vector_store.dense_search(
            embedding["dense"], top_k=top_k, filters=filters or None
        )

        return {
            "results": [r.to_dict() for r in results],
            "count": len(results),
        }

    def _get_stats(self, params: dict[str, Any]) -> dict[str, Any]:
        return self._repo.get_graph_stats()

    def _truth_layer_query(self, params: dict[str, Any]) -> dict[str, Any]:
        if not self._truth_layer:
            return {"error": "Truth Layer not available"}

        facts = self._truth_layer.query_facts(
            node_id=params.get("node_id"),
            status=params.get("status"),
            limit=params.get("limit", 20),
        )
        return {"facts": facts, "count": len(facts)}
