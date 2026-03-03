"""Connector framework — base classes for multi-source data fusion.

Connectors produce Capture objects that feed into the existing 9-stage
pipeline unchanged. Each connector manages its own sync state via SyncRecord.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from memora.graph.models import Capture

logger = logging.getLogger(__name__)


@dataclass
class SyncRecord:
    """Tracks sync state for a connector instance."""

    id: str = field(default_factory=lambda: str(uuid4()))
    connector_name: str = ""
    connector_type: str = ""
    last_sync: str | None = None
    items_synced: int = 0
    errors: int = 0
    cursor: str | None = None
    config: dict = field(default_factory=dict)
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class BaseConnector(ABC):
    """Abstract base class for all data connectors.

    Subclasses must implement:
    - connect(): Validate configuration and establish connection
    - get_items(since): Fetch raw items since a timestamp
    - transform(raw): Convert raw items to Capture objects
    """

    connector_type: str = "base"

    def __init__(self, name: str, config: dict | None = None) -> None:
        self.name = name
        self.config = config or {}
        self._connected = False

    @abstractmethod
    def connect(self) -> bool:
        """Validate configuration and establish connection.

        Returns True if connection successful.
        """
        ...

    @abstractmethod
    def get_items(self, since: datetime | None = None) -> list[dict]:
        """Fetch raw items from the source.

        Args:
            since: Only fetch items created/modified after this timestamp.
                   If None, fetch all available items.

        Returns list of raw item dicts (source-specific format).
        """
        ...

    @abstractmethod
    def transform(self, raw_items: list[dict]) -> list[Capture]:
        """Transform raw source items into Capture objects.

        Args:
            raw_items: Raw items from get_items().

        Returns list of Capture objects ready for the pipeline.
        """
        ...

    def sync(self, since: datetime | None = None) -> SyncRecord:
        """Run a full sync cycle: connect, fetch, transform.

        Returns a SyncRecord with results.
        """
        record = SyncRecord(
            connector_name=self.name,
            connector_type=self.connector_type,
        )

        try:
            if not self._connected:
                if not self.connect():
                    record.errors = 1
                    return record
                self._connected = True

            raw_items = self.get_items(since=since)
            captures = self.transform(raw_items)

            record.items_synced = len(captures)
            record.last_sync = datetime.now(timezone.utc).isoformat()
            record.updated_at = record.last_sync

            # Store captures attribute for caller to process through pipeline
            record.config["captures"] = captures

        except Exception as e:
            logger.error("Connector '%s' sync failed: %s", self.name, e)
            record.errors += 1

        return record

    def validate_config(self) -> list[str]:
        """Validate connector configuration. Returns list of error messages."""
        return []


class ConnectorRegistry:
    """Registry for managing connector instances."""

    def __init__(self) -> None:
        self._connector_types: dict[str, type[BaseConnector]] = {}
        self._instances: dict[str, BaseConnector] = {}

    def register_type(self, connector_type: str, cls: type[BaseConnector]) -> None:
        """Register a connector class by type name."""
        self._connector_types[connector_type] = cls

    def get_types(self) -> dict[str, type[BaseConnector]]:
        """Get all registered connector types."""
        return dict(self._connector_types)

    def create(self, name: str, connector_type: str, config: dict | None = None) -> BaseConnector:
        """Create and register a connector instance."""
        cls = self._connector_types.get(connector_type)
        if not cls:
            raise ValueError(
                f"Unknown connector type '{connector_type}'. "
                f"Available: {list(self._connector_types.keys())}"
            )
        instance = cls(name=name, config=config)
        self._instances[name] = instance
        return instance

    def get(self, name: str) -> BaseConnector | None:
        """Get a connector instance by name."""
        return self._instances.get(name)

    def list_instances(self) -> dict[str, BaseConnector]:
        """List all connector instances."""
        return dict(self._instances)

    def remove(self, name: str) -> bool:
        """Remove a connector instance."""
        return self._instances.pop(name, None) is not None

    def sync_all(self, since: datetime | None = None) -> list[SyncRecord]:
        """Sync all registered connector instances."""
        records = []
        for name, connector in self._instances.items():
            logger.info("Syncing connector '%s'", name)
            record = connector.sync(since=since)
            records.append(record)
        return records


def get_default_registry() -> ConnectorRegistry:
    """Build a registry with all built-in connector types."""
    registry = ConnectorRegistry()

    try:
        from memora.connectors.calendar_connector import CalendarConnector
        registry.register_type("calendar", CalendarConnector)
    except ImportError:
        logger.debug("Calendar connector unavailable (missing icalendar)")

    try:
        from memora.connectors.markdown_connector import MarkdownConnector
        registry.register_type("markdown", MarkdownConnector)
    except ImportError:
        logger.debug("Markdown connector unavailable (missing python-frontmatter)")

    return registry
