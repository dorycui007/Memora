"""Schema migration utilities for the graph database.

Tracks schema versions and applies incremental migrations with rollback support.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import duckdb

logger = logging.getLogger(__name__)

# Each migration is a tuple of (version, description, up_statements, down_statements)
MIGRATIONS: list[tuple[int, str, list[str], list[str]]] = [
    # Version 1 is the initial schema (applied by repository._init_schema)
    (2, "Add indexes for dossier performance",
     [
         "CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_id)",
         "CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_id)",
     ],
     [
         "DROP INDEX IF EXISTS idx_edges_source",
         "DROP INDEX IF EXISTS idx_edges_target",
     ]),
    (3, "Create actions table for kinetic operations",
     [
         """CREATE TABLE IF NOT EXISTS actions (
                id              VARCHAR PRIMARY KEY,
                action_type     VARCHAR NOT NULL,
                status          VARCHAR DEFAULT 'completed',
                source_node_id  VARCHAR,
                target_node_id  VARCHAR,
                params          JSON,
                result          JSON,
                executed_at     TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""",
     ],
     [
         "DROP TABLE IF EXISTS actions",
     ]),
    (4, "Create outcomes table for feedback loop",
     [
         """CREATE TABLE IF NOT EXISTS outcomes (
                id           VARCHAR PRIMARY KEY,
                node_id      VARCHAR NOT NULL,
                node_type    VARCHAR NOT NULL,
                outcome_text TEXT NOT NULL,
                rating       VARCHAR NOT NULL,
                evidence     JSON,
                recorded_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""",
         "CREATE INDEX IF NOT EXISTS idx_outcomes_node ON outcomes(node_id)",
     ],
     [
         "DROP INDEX IF EXISTS idx_outcomes_node",
         "DROP TABLE IF EXISTS outcomes",
     ]),
    (5, "Create detected_patterns table for pattern detection",
     [
         """CREATE TABLE IF NOT EXISTS detected_patterns (
                id              VARCHAR PRIMARY KEY,
                pattern_type    VARCHAR NOT NULL,
                description     TEXT NOT NULL,
                evidence        JSON,
                confidence      DOUBLE,
                suggested_action VARCHAR,
                networks        JSON,
                first_detected  TIMESTAMP,
                last_confirmed  TIMESTAMP,
                status          VARCHAR DEFAULT 'active',
                created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )""",
     ],
     [
         "DROP TABLE IF EXISTS detected_patterns",
     ]),
    (6, "Add severity and trend fields to detected_patterns",
     [
         "ALTER TABLE detected_patterns ADD COLUMN IF NOT EXISTS severity VARCHAR DEFAULT 'info'",
         "ALTER TABLE detected_patterns ADD COLUMN IF NOT EXISTS previous_value DOUBLE",
         "ALTER TABLE detected_patterns ADD COLUMN IF NOT EXISTS current_value DOUBLE",
         "CREATE INDEX IF NOT EXISTS idx_patterns_type_status ON detected_patterns(pattern_type, status)",
     ],
     [
         "DROP INDEX IF EXISTS idx_patterns_type_status",
         "ALTER TABLE detected_patterns DROP COLUMN IF EXISTS current_value",
         "ALTER TABLE detected_patterns DROP COLUMN IF EXISTS previous_value",
         "ALTER TABLE detected_patterns DROP COLUMN IF EXISTS severity",
     ]),
]


# DDL for the enhanced schema_version table
SCHEMA_VERSION_DDL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version     INTEGER PRIMARY KEY,
    description VARCHAR DEFAULT '',
    applied_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


def _ensure_schema_version_table(conn: duckdb.DuckDBPyConnection) -> None:
    """Create or upgrade the schema_version table to the enhanced format."""
    try:
        conn.execute("SELECT version FROM schema_version LIMIT 0")
    except duckdb.CatalogException:
        conn.execute(SCHEMA_VERSION_DDL)
        return

    # Check if the enhanced columns exist; add them if missing
    try:
        conn.execute("SELECT description FROM schema_version LIMIT 0")
    except (duckdb.BinderException, duckdb.CatalogException):
        conn.execute("ALTER TABLE schema_version ADD COLUMN description VARCHAR DEFAULT ''")

    try:
        conn.execute("SELECT applied_at FROM schema_version LIMIT 0")
    except (duckdb.BinderException, duckdb.CatalogException):
        conn.execute(
            "ALTER TABLE schema_version ADD COLUMN applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
        )


def get_current_version(conn: duckdb.DuckDBPyConnection) -> int:
    """Get the current schema version from the database."""
    try:
        result = conn.execute(
            "SELECT MAX(version) FROM schema_version"
        ).fetchone()
        return result[0] if result and result[0] is not None else 0
    except duckdb.CatalogException:
        return 0


def get_migration_history(conn: duckdb.DuckDBPyConnection) -> list[dict[str, Any]]:
    """List all applied migrations with timestamps."""
    _ensure_schema_version_table(conn)
    try:
        rows = conn.execute(
            "SELECT version, description, applied_at "
            "FROM schema_version ORDER BY version"
        ).fetchall()
        return [
            {
                "version": row[0],
                "description": row[1] or "",
                "applied_at": row[2],
            }
            for row in rows
        ]
    except duckdb.CatalogException:
        return []


def apply_migrations(conn: duckdb.DuckDBPyConnection) -> int:
    """Apply any pending migrations. Returns the final version number."""
    _ensure_schema_version_table(conn)
    current = get_current_version(conn)
    applied = 0

    for version, description, up_statements, _down_statements in MIGRATIONS:
        if version <= current:
            continue
        logger.info("Applying migration v%d: %s", version, description)
        try:
            for sql in up_statements:
                conn.execute(sql)
            conn.execute(
                "INSERT INTO schema_version (version, description, applied_at) "
                "VALUES (?, ?, ?)",
                [version, description, datetime.now(timezone.utc)],
            )
            applied += 1
            logger.info("Migration v%d applied successfully", version)
        except Exception:
            logger.exception("Migration v%d failed", version)
            raise

    if applied:
        logger.info(
            "Applied %d migration(s), now at v%d", applied, get_current_version(conn)
        )
    return get_current_version(conn)


def rollback_migration(conn: duckdb.DuckDBPyConnection, target_version: int = 0) -> int:
    """Roll back migrations down to target_version (exclusive).

    Args:
        conn: Database connection.
        target_version: Roll back to this version (0 = initial schema only).

    Returns:
        The version after rollback.
    """
    _ensure_schema_version_table(conn)
    current = get_current_version(conn)

    if current <= target_version:
        logger.info("Already at version %d, nothing to roll back", current)
        return current

    # Find migrations to reverse, in descending order
    to_reverse = [
        (v, desc, down)
        for v, desc, _up, down in MIGRATIONS
        if v > target_version and v <= current
    ]
    to_reverse.sort(key=lambda x: x[0], reverse=True)

    for version, description, down_statements in to_reverse:
        logger.info("Rolling back migration v%d: %s", version, description)
        try:
            for sql in down_statements:
                conn.execute(sql)
            conn.execute(
                "DELETE FROM schema_version WHERE version = ?", [version]
            )
            logger.info("Migration v%d rolled back successfully", version)
        except Exception:
            logger.exception("Rollback of v%d failed", version)
            raise

    final = get_current_version(conn)
    logger.info("Rolled back to v%d", final)
    return final
