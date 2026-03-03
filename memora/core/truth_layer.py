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

# Source-specific confidence calibration weights (P5).
# Applied as a multiplier to raw confidence when depositing facts.
# A weight of 1.0 means no adjustment; < 1.0 discounts the source.
SOURCE_CONFIDENCE_WEIGHTS: dict[str, float] = {
    "pipeline_auto": 0.85,
    "archivist": 0.85,
    "researcher": 0.75,
    "outcome_tracker": 1.0,
    "action_engine": 0.90,
    "user": 1.0,
}

# Similarity threshold above which a new fact is considered a duplicate
DUPLICATE_SIMILARITY_THRESHOLD = 0.92


class TruthLayer:
    """Manages verified facts with lifecycle tracking and contradiction detection."""

    def __init__(self, conn, embedding_engine=None, *, nli_model=None) -> None:
        """Initialize with a DuckDB connection (from GraphRepository._conn).

        Args:
            conn: DuckDB connection.
            embedding_engine: Optional EmbeddingEngine for semantic contradiction detection.
            nli_model: Optional pre-loaded NLI CrossEncoder model. If not provided,
                       NLI-based contradiction detection will attempt lazy loading.
        """
        self._conn = conn
        self._embedding_engine = embedding_engine
        self._nli_model = nli_model
        self._nli_load_failed = False
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        """Create truth layer tables if they don't exist."""
        for stmt in TRUTH_LAYER_SQL.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                self._conn.execute(stmt)

    # ── P5: Source-calibrated confidence ──────────────────────────────

    @staticmethod
    def calibrate_confidence(raw_confidence: float, source: str) -> float:
        """Apply source-specific calibration to a raw confidence score.

        Different depositors produce confidence values on incomparable scales.
        This normalizes them by applying a source-specific weight.
        """
        weight = SOURCE_CONFIDENCE_WEIGHTS.get(source, 0.80)
        return round(min(1.0, max(0.0, raw_confidence * weight)), 4)

    # ── Fact deposit (with P4 duplicate detection & P5 calibration) ──

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
        *,
        calibrate: bool = True,
    ) -> str | None:
        """Create a new verified fact. Returns fact ID, or None if duplicate detected.

        Args:
            calibrate: If True (default), apply source-specific confidence calibration
                       using ``verified_by`` as the source key.
        """
        # P5: calibrate confidence by source
        if calibrate:
            confidence = self.calibrate_confidence(confidence, verified_by)

        # P4: duplicate detection — skip if a near-identical fact already exists
        duplicate = self._find_duplicate(node_id, statement)
        if duplicate is not None:
            logger.info(
                "Skipping duplicate fact for node %s (matches fact %s)",
                node_id, duplicate["id"],
            )
            return None

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

    # ── P4: Duplicate detection ──────────────────────────────────────

    def _find_duplicate(
        self, node_id: str, statement: str
    ) -> dict[str, Any] | None:
        """Check if a near-identical fact already exists for this node.

        Returns the existing fact dict if a duplicate is found, else None.
        """
        existing = self.query_facts(node_id=node_id, status=FactStatus.ACTIVE.value)
        if not existing:
            return None

        # Exact match (case-insensitive)
        lower = statement.lower().strip()
        for fact in existing:
            if fact["statement"].lower().strip() == lower:
                return fact

        # Semantic similarity check if embedding engine is available
        if self._embedding_engine:
            try:
                from memora.vector.embeddings import cosine_similarity

                new_emb = self._embedding_engine.embed_text(statement)["dense"]
                for fact in existing:
                    fact_emb = self._embedding_engine.embed_text(fact["statement"])["dense"]
                    if cosine_similarity(new_emb, fact_emb) >= DUPLICATE_SIMILARITY_THRESHOLD:
                        return fact
            except Exception:
                logger.debug("Semantic duplicate check failed", exc_info=True)

        return None

    # ── Fact retrieval ───────────────────────────────────────────────

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

    # ── P0 + P1: Contradiction detection ─────────────────────────────

    # Semantic similarity above this threshold flags a potential contradiction
    CONTRADICTION_SIMILARITY_THRESHOLD = 0.75

    def check_contradiction(
        self,
        statement: str,
        node_id: str,
        *,
        cross_node: bool = False,
    ) -> list[dict[str, Any]]:
        """Find existing active facts that might contradict ``statement``.

        Args:
            statement: The new claim to check.
            node_id: The node this fact belongs to.
            cross_node: If True, search ALL active facts instead of only
                        those on the same ``node_id``. This catches
                        contradictions across different entities.
        """
        if cross_node:
            existing = self.query_facts(status=FactStatus.ACTIVE.value, limit=500)
        else:
            existing = self.query_facts(node_id=node_id, status=FactStatus.ACTIVE.value)

        if not existing:
            return []

        # Identical statement is not a contradiction
        existing = [f for f in existing if f["statement"].lower() != statement.lower()]
        if not existing:
            return []

        # P1: try NLI first (most accurate)
        nli_result = self._check_contradiction_nli(statement, existing)
        if nli_result is not None:
            return nli_result

        # Fall back to embedding similarity
        if self._embedding_engine:
            return self._check_contradiction_semantic(statement, existing)

        # Last resort: keyword overlap heuristic
        return self._check_contradiction_keyword(statement, existing)

    # ── P1: NLI-based contradiction detection ────────────────────────

    def _get_nli_model(self):
        """Lazy-load the NLI cross-encoder model."""
        if self._nli_model is not None:
            return self._nli_model
        if self._nli_load_failed:
            return None
        try:
            from sentence_transformers import CrossEncoder

            self._nli_model = CrossEncoder("cross-encoder/nli-deberta-v3-small")
            logger.info("Loaded NLI model cross-encoder/nli-deberta-v3-small")
            return self._nli_model
        except Exception:
            logger.info("NLI model not available, falling back to similarity-based detection")
            self._nli_load_failed = True
            return None

    def _check_contradiction_nli(
        self,
        statement: str,
        existing: list[dict[str, Any]],
    ) -> list[dict[str, Any]] | None:
        """Use an NLI model to classify statement pairs as contradiction/entailment/neutral.

        Returns a list of contradicting facts, or None if NLI is unavailable.
        The NLI model outputs scores for [contradiction, entailment, neutral].
        """
        model = self._get_nli_model()
        if model is None:
            return None

        try:
            import math

            pairs = [(statement, f["statement"]) for f in existing]
            scores = model.predict(pairs)

            contradictions = []
            for i, fact in enumerate(existing):
                score_row = scores[i]
                # Label ordering for nli-deberta-v3: [contradiction, entailment, neutral]
                # Model outputs raw logits; apply softmax to get probabilities
                logits = [float(s) for s in score_row]
                max_logit = max(logits)
                exp_scores = [math.exp(s - max_logit) for s in logits]
                total = sum(exp_scores)
                probs = [e / total for e in exp_scores]
                contradiction_score = probs[0]
                if contradiction_score > 0.5:
                    fact_copy = dict(fact)
                    fact_copy["_contradiction_score"] = round(contradiction_score, 4)
                    contradictions.append(fact_copy)

            return contradictions
        except Exception:
            logger.warning("NLI contradiction check failed", exc_info=True)
            return None

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

    # ── P3: Confidence decay for stale facts ─────────────────────────

    def decay_stale_confidence(
        self,
        decay_rate: float = 0.10,
        stale_threshold: float = 0.4,
    ) -> int:
        """Reduce confidence for dynamic facts that have missed their recheck date.

        For each overdue fact, confidence is reduced by ``decay_rate`` per missed
        recheck interval. Facts whose confidence drops below ``stale_threshold``
        are automatically marked STALE.

        Returns the number of facts updated.
        """
        stale_facts = self.get_stale_facts()
        if not stale_facts:
            return 0

        now = datetime.now(timezone.utc)
        updated = 0

        for fact in stale_facts:
            next_check = fact["next_check"]
            if isinstance(next_check, str):
                next_check = datetime.fromisoformat(next_check)
            if next_check.tzinfo is None:
                next_check = next_check.replace(tzinfo=timezone.utc)

            interval_days = fact.get("recheck_interval_days", 90)
            if interval_days <= 0:
                interval_days = 90

            # How many full intervals have been missed
            overdue_days = (now - next_check).total_seconds() / 86400
            missed_intervals = max(1, int(overdue_days / interval_days) + 1)

            old_confidence = fact["confidence"]
            new_confidence = round(
                max(0.0, old_confidence * ((1 - decay_rate) ** missed_intervals)), 4
            )

            updates: dict[str, Any] = {
                "confidence": new_confidence,
                "updated_at": now.isoformat(),
            }

            if new_confidence < stale_threshold:
                updates["status"] = FactStatus.STALE.value

            set_parts = []
            vals: list[Any] = []
            for k, v in updates.items():
                set_parts.append(f"{k} = ?")
                vals.append(v)
            vals.append(fact["id"])

            self._conn.execute(
                f"UPDATE verified_facts SET {', '.join(set_parts)} WHERE id = ?",
                vals,
            )

            self.record_check(
                fact_id=fact["id"],
                check_type="confidence_decay",
                result="decayed" if new_confidence >= stale_threshold else "stale",
                evidence=(
                    f"Missed {missed_intervals} interval(s). "
                    f"Confidence {old_confidence:.4f} -> {new_confidence:.4f}"
                ),
                checked_by="system",
            )
            updated += 1

        logger.info("Confidence decay applied to %d fact(s)", updated)
        return updated

    # ── Fact checks & lifecycle ──────────────────────────────────────

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
