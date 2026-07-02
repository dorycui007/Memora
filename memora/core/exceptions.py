"""Custom exception hierarchy for Memora.

Provides domain-specific exceptions so callers can catch and handle
failures at the right level of abstraction instead of broad Exception catches.
"""

from __future__ import annotations


class MemoraError(Exception):
    """Base exception for all Memora-specific errors."""


class PipelineError(MemoraError):
    """Raised when the extraction pipeline fails at any stage."""


class GraphCommitError(MemoraError):
    """Raised when an atomic graph commit fails."""


class EntityResolutionError(MemoraError):
    """Raised when entity deduplication/resolution fails."""


class ConnectorError(MemoraError):
    """Raised when a data connector fails during sync/transform."""


class EmbeddingError(MemoraError):
    """Raised when embedding generation or lookup fails."""


class AgentError(MemoraError):
    """Raised when an AI agent (Archivist, Strategist, Researcher) fails."""


class ConfigError(MemoraError):
    """Raised when configuration is invalid or missing."""
