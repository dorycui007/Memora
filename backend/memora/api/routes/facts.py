"""Facts API routes — query verified facts and stale facts."""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query, Request

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/facts", tags=["facts"])


def _get_truth_layer(request: Request):
    """Get or lazily initialize the truth layer."""
    truth = getattr(request.app.state, "truth_layer", None)
    if truth is None:
        repo = request.app.state.repo
        from memora.core.truth_layer import TruthLayer
        truth = TruthLayer(conn=repo._conn)
        request.app.state.truth_layer = truth
    return truth


@router.get("")
async def list_facts(
    request: Request,
    node_id: str | None = None,
    status: str | None = None,
    lifecycle: str | None = None,
    limit: int = Query(default=50, le=200),
    offset: int = 0,
):
    """Query verified facts with optional filters."""
    truth = _get_truth_layer(request)
    facts = truth.query_facts(
        node_id=node_id,
        status=status,
        lifecycle=lifecycle,
        limit=limit,
        offset=offset,
    )
    return facts


@router.get("/stale")
async def get_stale_facts(request: Request):
    """Get DYNAMIC facts past their next_check date (due for rechecking)."""
    truth = _get_truth_layer(request)
    return truth.get_stale_facts()


@router.get("/{fact_id}")
async def get_fact(fact_id: str, request: Request):
    """Get a single fact with full provenance."""
    truth = _get_truth_layer(request)
    fact = truth.get_fact(fact_id)
    if fact is None:
        raise HTTPException(status_code=404, detail="Fact not found")

    # Include check history
    checks = truth.get_checks_for_fact(fact_id)
    fact["checks"] = checks

    return fact
