"""Truth Layer — verified fact storage with lifecycle management.

Manages verified facts, contradiction detection, and fact-check audit trails.
Tables are created lazily without modifying the core graph schema.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

logger = logging.getLogger(__name__)


class FactStatus(str, Enum):
    ACTIVE = "active"
    STALE = "stale"
    CONTRADICTED = "contradicted"
    RETIRED = "retired"


class FactLifecycle(str, Enum):
    STATIC = "static"
    DYNAMIC = "dynamic"


TRUTH_LAYER_SQL = """
CREATE TABLE IF NOT EXISTS verified_facts (
    id                    VARCHAR PRIMARY KEY,
    node_id               VARCHAR NOT NULL,
    statement             TEXT NOT NULL,
    confidence            DOUBLE CHECK (confidence >= 0 AND confidence <= 1),
    status                VARCHAR DEFAULT 'active',
    lifecycle             VARCHAR DEFAULT 'dynamic',
    source_capture_id     VARCHAR,
    verified_at           TIMESTAMP,
    verified_by           VARCHAR,
    recheck_interval_days INTEGER DEFAULT 90,
    last_checked          TIMESTAMP,
    next_check            TIMESTAMP,
    metadata              JSON,
    created_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS fact_checks (
    id              VARCHAR PRIMARY KEY,
    fact_id         VARCHAR NOT NULL,
    check_type      VARCHAR NOT NULL,
    result          VARCHAR NOT NULL,
    evidence        TEXT,
    checked_by      VARCHAR,
    checked_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_facts_node ON verified_facts(node_id);
CREATE INDEX IF NOT EXISTS idx_facts_status ON verified_facts(status);
"""


class TruthLayer:
    """Manages verified facts with lifecycle tracking and contradiction detection."""

    def __init__(self, conn, embedding_engine=None) -> None:
        """Initialize with a DuckDB connection (from GraphRepository._conn).

        Args:
            conn: DuckDB connection.
            embedding_engine: Optional EmbeddingEngine for semantic contradiction detection.
        """
        self._conn = conn
        self._embedding_engine = embedding_engine
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        """Create truth layer tables if they don't exist."""
        for stmt in TRUTH_LAYER_SQL.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                self._conn.execute(stmt)

    def deposit_fact(
        self,
        node_id: str,
        statement: str,
        confidence: float = 0.8,
        lifecycle: FactLifecycle = FactLifecycle.DYNAMIC,
        source_capture_id: str | None = None,
        verified_by: str = "archivist",
        recheck_interval_days: int = 90,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        """Create a new verified fact. Returns fact ID."""
        fact_id = str(uuid4())
        now = datetime.now(timezone.utc)

        next_check = None
        if lifecycle == FactLifecycle.DYNAMIC:
            next_check = now + timedelta(days=recheck_interval_days)

        self._conn.execute(
            """INSERT INTO verified_facts
               (id, node_id, statement, confidence, status, lifecycle,
                source_capture_id, verified_at, verified_by,
                recheck_interval_days, last_checked, next_check,
                metadata, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            [
                fact_id,
                node_id,
                statement,
                confidence,
                FactStatus.ACTIVE.value,
                lifecycle.value,
                source_capture_id,
                now.isoformat(),
                verified_by,
                recheck_interval_days,
                now.isoformat(),
                next_check.isoformat() if next_check else None,
                json.dumps(metadata or {}),
                now.isoformat(),
                now.isoformat(),
            ],
        )
        logger.info("Deposited fact %s for node %s", fact_id, node_id)
        return fact_id

    def get_fact(self, fact_id: str) -> dict[str, Any] | None:
        """Retrieve a fact by ID."""
        row = self._conn.execute(
            "SELECT * FROM verified_facts WHERE id = ?", [fact_id]
        ).fetchone()
        if row is None:
            return None
        return self._row_to_fact(row)

    def query_facts(
        self,
        node_id: str | None = None,
        status: str | None = None,
        lifecycle: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Query facts with optional filters."""
        conditions = []
        params: list[Any] = []

        if node_id:
            conditions.append("node_id = ?")
            params.append(node_id)
        if status:
            conditions.append("status = ?")
            params.append(status)
        if lifecycle:
            conditions.append("lifecycle = ?")
            params.append(lifecycle)

        where = " AND ".join(conditions) if conditions else "1=1"
        query = f"SELECT * FROM verified_facts WHERE {where} ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        rows = self._conn.execute(query, params).fetchall()
        return [self._row_to_fact(row) for row in rows]

    def get_stale_facts(self) -> list[dict[str, Any]]:
        """Get DYNAMIC facts past their next_check date."""
        now = datetime.now(timezone.utc).isoformat()
        rows = self._conn.execute(
            """SELECT * FROM verified_facts
               WHERE lifecycle = 'dynamic'
               AND status = 'active'
               AND next_check IS NOT NULL
               AND next_check <= ?
               ORDER BY next_check ASC""",
            [now],
        ).fetchall()
        return [self._row_to_fact(row) for row in rows]

    # Semantic similarity above this threshold flags a potential contradiction
    CONTRADICTION_SIMILARITY_THRESHOLD = 0.75

    def check_contradiction(
        self,
        statement: str,
        node_id: str,
    ) -> list[dict[str, Any]]:
        """Find existing active facts for the same node that might contradict.

        Uses embedding cosine similarity when an embedding engine is available,
        falling back to keyword overlap heuristic.
        """
        existing = self.query_facts(node_id=node_id, status=FactStatus.ACTIVE.value)
        if not existing:
            return []

        # Identical statement is not a contradiction
        existing = [f for f in existing if f["statement"].lower() != statement.lower()]
        if not existing:
            return []

        # Try semantic similarity first
        if self._embedding_engine:
            return self._check_contradiction_semantic(statement, existing)

        # Fallback: keyword overlap heuristic
        return self._check_contradiction_keyword(statement, existing)

    def _check_contradiction_semantic(
        self,
        statement: str,
        existing: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Use embedding cosine similarity to detect potential contradictions.

        High semantic similarity + different statement text suggests the new
        fact is about the same topic but says something different.
        """
        try:
            from memora.vector.embeddings import cosine_similarity

            texts = [statement] + [f["statement"] for f in existing]
            embeddings = self._embedding_engine.embed_batch(texts)

            new_vec = embeddings[0]["dense"]
            contradictions = []

            for i, fact in enumerate(existing):
                fact_vec = embeddings[i + 1]["dense"]
                sim = cosine_similarity(new_vec, fact_vec)

                if sim >= self.CONTRADICTION_SIMILARITY_THRESHOLD:
                    contradictions.append(fact)

            return contradictions
        except Exception:
            logger.warning("Semantic contradiction check failed, falling back to keyword", exc_info=True)
            return self._check_contradiction_keyword(statement, existing)

    def _check_contradiction_keyword(
        self,
        statement: str,
        existing: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        """Keyword overlap heuristic for contradiction detection."""
        new_words = set(statement.lower().split())
        # Filter out very common words to reduce false positives
        stopwords = {"i", "the", "a", "an", "is", "was", "to", "and", "of", "in", "my", "for", "it", "on", "at"}
        new_words -= stopwords
        contradictions = []

        for fact in existing:
            existing_words = set(fact["statement"].lower().split()) - stopwords
            overlap = new_words & existing_words
            # Require significant overlap relative to the shorter statement
            min_len = min(len(new_words), len(existing_words))
            if min_len > 0 and len(overlap) >= max(3, min_len * 0.5):
                contradictions.append(fact)

        return contradictions

    def record_check(
        self,
        fact_id: str,
        check_type: str,
        result: str,
        evidence: str = "",
        checked_by: str = "system",
    ) -> str:
        """Record a fact check result and update the fact's status."""
        check_id = str(uuid4())
        now = datetime.now(timezone.utc)

        self._conn.execute(
            """INSERT INTO fact_checks (id, fact_id, check_type, result, evidence, checked_by, checked_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            [check_id, fact_id, check_type, result, evidence, checked_by, now.isoformat()],
        )

        # Update fact based on result
        updates: dict[str, Any] = {
            "last_checked": now.isoformat(),
            "updated_at": now.isoformat(),
        }

        if result == "contradicted":
            updates["status"] = FactStatus.CONTRADICTED.value
        elif result == "confirmed":
            updates["status"] = FactStatus.ACTIVE.value
            # Reset next_check for dynamic facts
            fact = self.get_fact(fact_id)
            if fact and fact["lifecycle"] == FactLifecycle.DYNAMIC.value:
                interval = fact.get("recheck_interval_days", 90)
                updates["next_check"] = (now + timedelta(days=interval)).isoformat()

        set_parts = []
        vals = []
        for k, v in updates.items():
            set_parts.append(f"{k} = ?")
            vals.append(v)
        vals.append(fact_id)

        self._conn.execute(
            f"UPDATE verified_facts SET {', '.join(set_parts)} WHERE id = ?",
            vals,
        )

        return check_id

    def retire_fact(self, fact_id: str, reason: str = "") -> None:
        """Mark a fact as retired."""
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "UPDATE verified_facts SET status = ?, updated_at = ? WHERE id = ?",
            [FactStatus.RETIRED.value, now, fact_id],
        )
        if reason:
            self.record_check(fact_id, "retirement", "retired", evidence=reason)

    def get_checks_for_fact(self, fact_id: str) -> list[dict[str, Any]]:
        """Get all check records for a fact."""
        rows = self._conn.execute(
            "SELECT * FROM fact_checks WHERE fact_id = ? ORDER BY checked_at DESC",
            [fact_id],
        ).fetchall()
        cols = ["id", "fact_id", "check_type", "result", "evidence", "checked_by", "checked_at"]
        return [dict(zip(cols, row)) for row in rows]

    def _row_to_fact(self, row: tuple) -> dict[str, Any]:
        """Convert a database row to a fact dict."""
        cols = [
            "id", "node_id", "statement", "confidence", "status", "lifecycle",
            "source_capture_id", "verified_at", "verified_by",
            "recheck_interval_days", "last_checked", "next_check",
            "metadata", "created_at", "updated_at",
        ]
        data = dict(zip(cols, row))
        if isinstance(data.get("metadata"), str):
            data["metadata"] = json.loads(data["metadata"])
        elif data.get("metadata") is None:
            data["metadata"] = {}
        return data
