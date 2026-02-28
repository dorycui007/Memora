"""Unit tests for bridge discovery (Phase 5)."""

from __future__ import annotations

import json
from datetime import datetime
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from memora.core.bridge_discovery import BridgeDiscovery
from memora.graph.repository import GraphRepository


def _insert_node(
    repo: GraphRepository,
    node_id: str | None = None,
    node_type: str = "CONCEPT",
    title: str = "Test Node",
    content: str = "",
    networks: list[str] | None = None,
) -> str:
    """Insert a raw node row directly into DuckDB."""
    nid = node_id or str(uuid4())
    now = datetime.utcnow().isoformat()
    repo._conn.execute(
        """INSERT INTO nodes
           (id, node_type, title, content, content_hash, properties,
            confidence, networks, human_approved, access_count,
            decay_score, tags, created_at, updated_at, deleted)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            nid,
            node_type,
            title,
            content,
            f"hash_{nid[:8]}",
            json.dumps({}),
            1.0,
            networks or [],
            False,
            0,
            1.0,
            [],
            now,
            now,
            False,
        ],
    )
    return nid


def _insert_bridge(
    repo: GraphRepository,
    source_node_id: str,
    target_node_id: str,
    source_network: str = "ACADEMIC",
    target_network: str = "PROFESSIONAL",
    similarity: float = 0.85,
) -> str:
    """Insert a bridge row directly into DuckDB."""
    bid = str(uuid4())
    now = datetime.utcnow().isoformat()
    repo._conn.execute(
        """INSERT INTO bridges
           (id, source_node_id, target_node_id, source_network,
            target_network, similarity, llm_validated, meaningful,
            description, discovered_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        [
            bid,
            source_node_id,
            target_node_id,
            source_network,
            target_network,
            similarity,
            False,
            None,
            None,
            now,
        ],
    )
    return bid


class TestBridgeExists:
    def test_bridge_exists_true(self, repo: GraphRepository):
        """_bridge_exists should return True when a bridge already exists."""
        mock_vector = MagicMock()
        mock_embed = MagicMock()
        bd = BridgeDiscovery(repo, mock_vector, mock_embed)

        nid1 = _insert_node(repo, title="Node A", networks=["ACADEMIC"])
        nid2 = _insert_node(repo, title="Node B", networks=["PROFESSIONAL"])
        _insert_bridge(repo, nid1, nid2)

        assert bd._bridge_exists(nid1, nid2) is True

    def test_bridge_exists_false(self, repo: GraphRepository):
        """_bridge_exists should return False when no bridge exists."""
        mock_vector = MagicMock()
        mock_embed = MagicMock()
        bd = BridgeDiscovery(repo, mock_vector, mock_embed)

        nid1 = _insert_node(repo, title="Node A", networks=["ACADEMIC"])
        nid2 = _insert_node(repo, title="Node B", networks=["PROFESSIONAL"])

        assert bd._bridge_exists(nid1, nid2) is False

    def test_bridge_exists_reverse(self, repo: GraphRepository):
        """_bridge_exists should detect bridges regardless of direction."""
        mock_vector = MagicMock()
        mock_embed = MagicMock()
        bd = BridgeDiscovery(repo, mock_vector, mock_embed)

        nid1 = _insert_node(repo, title="Node A", networks=["ACADEMIC"])
        nid2 = _insert_node(repo, title="Node B", networks=["PROFESSIONAL"])
        _insert_bridge(repo, nid1, nid2)

        # Check reverse direction
        assert bd._bridge_exists(nid2, nid1) is True


class TestStoreBridge:
    def test_store_bridge(self, repo: GraphRepository):
        """_store_bridge should persist a bridge record."""
        mock_vector = MagicMock()
        mock_embed = MagicMock()
        bd = BridgeDiscovery(repo, mock_vector, mock_embed)

        nid1 = _insert_node(repo, title="Node A", networks=["ACADEMIC"])
        nid2 = _insert_node(repo, title="Node B", networks=["VENTURES"])

        bridge = {
            "source_node_id": nid1,
            "target_node_id": nid2,
            "source_network": "ACADEMIC",
            "target_network": "VENTURES",
            "similarity": 0.92,
        }
        bd._store_bridge(bridge)

        rows = repo._conn.execute(
            "SELECT source_node_id, target_node_id, similarity FROM bridges"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0][0] == nid1
        assert rows[0][1] == nid2
        assert rows[0][2] == pytest.approx(0.92)


class TestGetBridges:
    def test_get_bridges_all(self, repo: GraphRepository):
        """get_bridges with no filters should return all bridges."""
        mock_vector = MagicMock()
        mock_embed = MagicMock()
        bd = BridgeDiscovery(repo, mock_vector, mock_embed)

        nid1 = _insert_node(repo, title="Node A", networks=["ACADEMIC"])
        nid2 = _insert_node(repo, title="Node B", networks=["PROFESSIONAL"])
        nid3 = _insert_node(repo, title="Node C", networks=["SOCIAL"])
        _insert_bridge(repo, nid1, nid2, "ACADEMIC", "PROFESSIONAL", 0.90)
        _insert_bridge(repo, nid1, nid3, "ACADEMIC", "SOCIAL", 0.85)

        bridges = bd.get_bridges()
        assert len(bridges) == 2

    def test_get_bridges_by_network(self, repo: GraphRepository):
        """get_bridges with a network filter should return only matching bridges."""
        mock_vector = MagicMock()
        mock_embed = MagicMock()
        bd = BridgeDiscovery(repo, mock_vector, mock_embed)

        nid1 = _insert_node(repo, title="Node A", networks=["ACADEMIC"])
        nid2 = _insert_node(repo, title="Node B", networks=["PROFESSIONAL"])
        nid3 = _insert_node(repo, title="Node C", networks=["SOCIAL"])
        _insert_bridge(repo, nid1, nid2, "ACADEMIC", "PROFESSIONAL", 0.90)
        _insert_bridge(repo, nid1, nid3, "ACADEMIC", "SOCIAL", 0.85)

        bridges = bd.get_bridges(network="SOCIAL")
        assert len(bridges) == 1
        assert bridges[0]["target_network"] == "SOCIAL"

    def test_get_bridges_empty(self, repo: GraphRepository):
        """get_bridges on empty table should return empty list."""
        mock_vector = MagicMock()
        mock_embed = MagicMock()
        bd = BridgeDiscovery(repo, mock_vector, mock_embed)

        bridges = bd.get_bridges()
        assert bridges == []


class TestDiscoverBridgesForNode:
    def test_discover_bridges_nonexistent_node(self, repo: GraphRepository):
        """Discovering bridges for a non-existent node should return empty."""
        mock_vector = MagicMock()
        mock_embed = MagicMock()
        bd = BridgeDiscovery(repo, mock_vector, mock_embed)

        result = bd.discover_bridges_for_node(str(uuid4()))
        assert result == []

    def test_discover_bridges_no_networks(self, repo: GraphRepository):
        """A node with no networks should return empty bridges."""
        mock_vector = MagicMock()
        mock_embed = MagicMock()
        bd = BridgeDiscovery(repo, mock_vector, mock_embed)

        nid = _insert_node(repo, title="Networkless", networks=[])
        result = bd.discover_bridges_for_node(nid)
        assert result == []
