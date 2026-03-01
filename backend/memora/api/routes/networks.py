"""Network API routes — network health, details, and bridge endpoints."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request

from memora.graph.models import NetworkType

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/networks", tags=["networks"])

VALID_NETWORKS = {n.value for n in NetworkType}


@router.get("")
async def list_networks(request: Request):
    """Get all 7 networks with current health status and momentum."""
    repo = request.app.state.repo

    networks = []
    for network in NetworkType:
        health = _get_latest_health(repo, network.value)
        node_count = _get_network_node_count(repo, network.value)

        networks.append({
            "name": network.value,
            "node_count": node_count,
            "health": health,
        })

    return {"networks": networks}


@router.get("/bridges")
async def get_bridges(
    request: Request,
    network: str | None = None,
    validated_only: bool = False,
    limit: int = 50,
):
    """Get cross-network bridge discoveries."""
    repo = request.app.state.repo

    conditions = []
    params: list[Any] = []

    if network:
        if network not in VALID_NETWORKS:
            raise HTTPException(status_code=400, detail=f"Invalid network: {network}")
        conditions.append("(source_network = ? OR target_network = ?)")
        params.extend([network, network])

    if validated_only:
        conditions.append("llm_validated = TRUE AND meaningful = TRUE")

    where = " AND ".join(conditions) if conditions else "1=1"

    try:
        rows = repo._conn.execute(
            f"""SELECT id, source_node_id, target_node_id, source_network,
                       target_network, similarity, llm_validated, meaningful,
                       description, discovered_at
                FROM bridges WHERE {where}
                ORDER BY similarity DESC LIMIT ?""",
            params + [limit],
        ).fetchall()

        cols = [
            "id", "source_node_id", "target_node_id", "source_network",
            "target_network", "similarity", "llm_validated", "meaningful",
            "description", "discovered_at",
        ]
        bridges = [dict(zip(cols, row)) for row in rows]

        return {"bridges": bridges, "count": len(bridges)}
    except Exception:
        return {"bridges": [], "count": 0}


@router.get("/{network_name}")
async def get_network_detail(network_name: str, request: Request):
    """Get network detail with nodes, health history, alerts, and commitment stats."""
    if network_name not in VALID_NETWORKS:
        raise HTTPException(status_code=404, detail=f"Network not found: {network_name}")

    repo = request.app.state.repo

    # Current health
    health = _get_latest_health(repo, network_name)

    # Health history (last 30 snapshots)
    health_history = _get_health_history(repo, network_name, limit=30)

    # Node count and recent nodes
    node_count = _get_network_node_count(repo, network_name)
    recent_nodes = _get_recent_network_nodes(repo, network_name, limit=20)

    # Commitment stats
    commitment_stats = _get_commitment_stats(repo, network_name)

    # Active alerts
    alerts = _get_network_alerts(repo, network_name)

    return {
        "name": network_name,
        "node_count": node_count,
        "health": health,
        "health_history": health_history,
        "recent_nodes": recent_nodes,
        "commitment_stats": commitment_stats,
        "alerts": alerts,
    }


# ---- Helper functions ----


def _get_latest_health(repo, network: str) -> dict[str, Any] | None:
    """Get the latest health snapshot for a network."""
    try:
        row = repo._conn.execute(
            """SELECT status, momentum, commitment_completion_rate,
                      alert_ratio, staleness_flags, computed_at
               FROM network_health
               WHERE network = ?
               ORDER BY computed_at DESC LIMIT 1""",
            [network],
        ).fetchone()
        if row:
            return {
                "status": row[0],
                "momentum": row[1],
                "commitment_completion_rate": row[2],
                "alert_ratio": row[3],
                "staleness_flags": row[4],
                "computed_at": row[5],
            }
    except Exception:
        pass
    return None


def _get_health_history(repo, network: str, limit: int = 30) -> list[dict[str, Any]]:
    """Get health history for trend analysis."""
    try:
        rows = repo._conn.execute(
            """SELECT status, momentum, commitment_completion_rate,
                      alert_ratio, staleness_flags, computed_at
               FROM network_health
               WHERE network = ?
               ORDER BY computed_at DESC LIMIT ?""",
            [network, limit],
        ).fetchall()
        cols = ["status", "momentum", "commitment_completion_rate",
                "alert_ratio", "staleness_flags", "computed_at"]
        return [dict(zip(cols, row)) for row in rows]
    except Exception:
        return []


def _get_network_node_count(repo, network: str) -> int:
    """Count nodes in a network."""
    try:
        result = repo._conn.execute(
            "SELECT COUNT(*) FROM nodes WHERE deleted = FALSE AND list_contains(networks, ?)",
            [network],
        ).fetchone()
        return result[0] if result else 0
    except Exception:
        return 0


def _get_recent_network_nodes(repo, network: str, limit: int = 20) -> list[dict[str, Any]]:
    """Get recent nodes in a network."""
    try:
        rows = repo._conn.execute(
            """SELECT id, node_type, title, confidence, decay_score, created_at
               FROM nodes
               WHERE deleted = FALSE AND list_contains(networks, ?)
               ORDER BY created_at DESC LIMIT ?""",
            [network, limit],
        ).fetchall()
        cols = ["id", "node_type", "title", "confidence", "decay_score", "created_at"]
        return [dict(zip(cols, row)) for row in rows]
    except Exception:
        return []


def _get_commitment_stats(repo, network: str) -> dict[str, Any]:
    """Get commitment statistics for a network."""
    try:
        total = repo._conn.execute(
            """SELECT COUNT(*) FROM nodes
               WHERE deleted = FALSE AND node_type = 'COMMITMENT'
               AND list_contains(networks, ?)""",
            [network],
        ).fetchone()[0]

        completed = repo._conn.execute(
            """SELECT COUNT(*) FROM nodes
               WHERE deleted = FALSE AND node_type = 'COMMITMENT'
               AND list_contains(networks, ?)
               AND json_extract_string(properties, '$.status') = 'completed'""",
            [network],
        ).fetchone()[0]

        open_count = repo._conn.execute(
            """SELECT COUNT(*) FROM nodes
               WHERE deleted = FALSE AND node_type = 'COMMITMENT'
               AND list_contains(networks, ?)
               AND json_extract_string(properties, '$.status') = 'open'""",
            [network],
        ).fetchone()[0]

        return {
            "total": total,
            "completed": completed,
            "open": open_count,
            "completion_rate": completed / total if total > 0 else 0.0,
        }
    except Exception:
        return {"total": 0, "completed": 0, "open": 0, "completion_rate": 0.0}


def _get_network_alerts(repo, network: str) -> list[dict[str, Any]]:
    """Get active alerts for a network."""
    alerts = []
    try:
        # Overdue commitments
        rows = repo._conn.execute(
            """SELECT id, title, properties FROM nodes
               WHERE deleted = FALSE AND node_type = 'COMMITMENT'
               AND list_contains(networks, ?)
               AND json_extract_string(properties, '$.status') = 'open'""",
            [network],
        ).fetchall()

        from datetime import datetime, timezone
        import json
        now = datetime.now(timezone.utc)

        for row in rows:
            props = json.loads(row[2]) if isinstance(row[2], str) else (row[2] or {})
            due_date_str = props.get("due_date") or props.get("due_at")
            if due_date_str:
                try:
                    due_date = datetime.fromisoformat(due_date_str.replace("Z", "+00:00").replace("+00:00", ""))
                    if due_date < now:
                        alerts.append({
                            "type": "overdue_commitment",
                            "node_id": row[0],
                            "title": row[1],
                            "days_overdue": (now - due_date).days,
                        })
                except (ValueError, TypeError):
                    pass
    except Exception:
        pass

    return alerts
