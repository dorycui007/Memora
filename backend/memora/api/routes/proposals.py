"""Proposal API routes — list, review, approve/reject, edit proposals."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request

from memora.api.schemas.proposal_schemas import (
    ProposalDetail,
    ProposalEdit,
    ProposalResponse,
    build_proposal_actions,
)
from memora.graph.models import ProposalStatus

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/proposals", tags=["proposals"])


@router.get("", response_model=list[ProposalResponse])
async def list_proposals(
    request: Request,
    status: str = "pending",
    route: str | None = None,
    limit: int = Query(default=20, le=100),
    offset: int = 0,
):
    """List proposals with pagination, filter by status and route."""
    repo = request.app.state.repo

    conditions = ["status = ?"]
    params: list[Any] = [status]

    if route:
        conditions.append("route = ?")
        params.append(route)

    where = " AND ".join(conditions)
    query = f"SELECT * FROM proposals WHERE {where} ORDER BY created_at DESC LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    rows = repo._conn.execute(query, params).fetchall()
    cols = [desc[0] for desc in repo._conn.description]

    results = []
    for row in rows:
        data = dict(zip(cols, row))
        proposal_data = data.get("proposal_data", "{}")
        if isinstance(proposal_data, str):
            proposal_data = json.loads(proposal_data)

        actions = build_proposal_actions(proposal_data)
        results.append(ProposalResponse(
            id=data["id"],
            capture_id=data.get("capture_id"),
            status=data["status"],
            route=data.get("route"),
            confidence=data.get("confidence", 0.0),
            human_summary=data.get("human_summary", ""),
            action_count=len(actions),
            created_at=data["created_at"],
            reviewed_at=data.get("reviewed_at"),
        ))

    return results


@router.get("/{proposal_id}", response_model=ProposalDetail)
async def get_proposal(proposal_id: str, request: Request):
    """Get full proposal detail with action breakdown."""
    repo = request.app.state.repo
    row = repo._conn.execute(
        "SELECT * FROM proposals WHERE id = ?", [proposal_id]
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Proposal not found")

    cols = [desc[0] for desc in repo._conn.description]
    data = dict(zip(cols, row))

    proposal_data = data.get("proposal_data", "{}")
    if isinstance(proposal_data, str):
        proposal_data = json.loads(proposal_data)

    actions = build_proposal_actions(proposal_data)

    return ProposalDetail(
        id=data["id"],
        capture_id=data.get("capture_id"),
        status=data["status"],
        route=data.get("route"),
        confidence=data.get("confidence", 0.0),
        human_summary=data.get("human_summary", ""),
        action_count=len(actions),
        created_at=data["created_at"],
        reviewed_at=data.get("reviewed_at"),
        actions=actions,
        proposal_data=proposal_data,
        reviewer=data.get("reviewer"),
    )


@router.post("/{proposal_id}/approve")
async def approve_proposal(proposal_id: str, request: Request):
    """Approve a proposal, commit it to the graph, and trigger post-commit processing."""
    repo = request.app.state.repo

    # Verify proposal exists and is pending
    row = repo._conn.execute(
        "SELECT status FROM proposals WHERE id = ?", [proposal_id]
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Proposal not found")
    if row[0] != "pending":
        raise HTTPException(status_code=400, detail=f"Proposal is already {row[0]}")

    success = repo.commit_proposal(UUID(proposal_id))
    if not success:
        raise HTTPException(status_code=400, detail="Failed to commit proposal")

    # Trigger async post-commit processing (embeddings, bridges)
    asyncio.create_task(_post_commit_processing(request.app, proposal_id))

    return {"status": "approved", "proposal_id": proposal_id}


@router.post("/{proposal_id}/reject")
async def reject_proposal(
    proposal_id: str,
    request: Request,
    reason: str = "",
):
    """Reject a proposal with optional reason."""
    repo = request.app.state.repo

    row = repo._conn.execute(
        "SELECT status FROM proposals WHERE id = ?", [proposal_id]
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Proposal not found")
    if row[0] != "pending":
        raise HTTPException(status_code=400, detail=f"Proposal is already {row[0]}")

    repo.update_proposal_status(UUID(proposal_id), ProposalStatus.REJECTED, "human")
    return {"status": "rejected", "proposal_id": proposal_id, "reason": reason}


@router.patch("/{proposal_id}")
async def edit_proposal(
    proposal_id: str,
    body: ProposalEdit,
    request: Request,
):
    """Edit a proposal before approving it."""
    repo = request.app.state.repo

    row = repo._conn.execute(
        "SELECT status FROM proposals WHERE id = ?", [proposal_id]
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Proposal not found")
    if row[0] != "pending":
        raise HTTPException(status_code=400, detail=f"Cannot edit a {row[0]} proposal")

    updates = []
    params: list[Any] = []

    if body.human_summary is not None:
        updates.append("human_summary = ?")
        params.append(body.human_summary)

    if body.proposal_data is not None:
        updates.append("proposal_data = ?")
        params.append(json.dumps(body.proposal_data))

    if not updates:
        raise HTTPException(status_code=400, detail="No updates provided")

    params.append(proposal_id)
    repo._conn.execute(
        f"UPDATE proposals SET {', '.join(updates)} WHERE id = ?",
        params,
    )

    return {"status": "updated", "proposal_id": proposal_id}


async def _post_commit_processing(app: Any, proposal_id: str) -> None:
    """Run post-commit processing: embeddings and bridge detection."""
    try:
        repo = app.state.repo
        embedding_engine = getattr(app.state, "embedding_engine", None)
        vector_store = getattr(app.state, "vector_store", None)

        if not embedding_engine or not vector_store:
            return

        # Get the capture_id for this proposal
        row = repo._conn.execute(
            "SELECT capture_id FROM proposals WHERE id = ?", [proposal_id]
        ).fetchone()
        if not row or not row[0]:
            return

        capture_id = row[0]

        # Generate embeddings for committed nodes
        nodes = repo._conn.execute(
            "SELECT id, node_type, title, content, networks FROM nodes "
            "WHERE source_capture_id = ? AND deleted = FALSE",
            [capture_id],
        ).fetchall()

        for node_row in nodes:
            node_id, node_type, title, content, networks = node_row
            text = f"{title} {content}" if content else title
            embedding = embedding_engine.embed_text(text)
            vector_store.upsert_embedding(
                node_id=node_id,
                content=text,
                node_type=node_type,
                networks=networks if networks else [],
                vector=embedding["dense"],
            )

        # Bridge detection
        try:
            from memora.core.bridge_discovery import BridgeDiscovery

            bridge_detector = BridgeDiscovery(
                repo=repo,
                vector_store=vector_store,
                embedding_engine=embedding_engine,
            )
            for node_row in nodes:
                bridge_detector.discover_bridges_for_node(node_row[0])
        except Exception:
            logger.warning("Bridge detection in post-commit failed", exc_info=True)

        logger.info("Post-commit processing completed for proposal %s", proposal_id)

    except Exception:
        logger.warning("Post-commit processing failed for proposal %s", proposal_id, exc_info=True)
