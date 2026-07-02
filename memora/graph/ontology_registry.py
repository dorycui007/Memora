"""YAML-driven ontology registry for flexible entity and edge type management.

Loads entity types, edge types, and network definitions from ontology.yaml,
providing runtime lookups for validation, extraction prompts, and dashboard rendering.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

_DEFAULT_ONTOLOGY_PATH = Path(__file__).resolve().parent.parent.parent / "ontology_default.yaml"


class OntologyRegistry:
    """YAML-driven flexible ontology for the knowledge graph.

    Loads entity types, edge types, and networks from a YAML file.
    Provides type lookups, validation, and display configuration.
    """

    def __init__(self, ontology_path: Path | None = None) -> None:
        self._path = ontology_path or _DEFAULT_ONTOLOGY_PATH
        self._entity_types: dict[str, dict[str, Any]] = {}
        self._edge_types: dict[str, dict[str, Any]] = {}
        self._networks: dict[str, dict[str, Any]] = {}
        self._version: int = 1
        self._load()

    def _load(self) -> None:
        """Load and validate the ontology YAML."""
        if not self._path.exists():
            logger.warning("Ontology file not found at %s, using empty ontology", self._path)
            return

        with open(self._path) as f:
            data = yaml.safe_load(f) or {}

        self._version = data.get("version", 1)
        self._entity_types = data.get("entity_types", {})
        self._edge_types = data.get("edge_types", {})
        self._networks = data.get("networks", {})

        logger.info(
            "Loaded ontology v%d: %d entity types, %d edge types, %d networks",
            self._version,
            len(self._entity_types),
            len(self._edge_types),
            len(self._networks),
        )

    @property
    def version(self) -> int:
        return self._version

    # ── Entity type lookups ──────────────────────────────────────

    def get_all_entity_type_names(self) -> list[str]:
        """Return all registered entity type names."""
        return list(self._entity_types.keys())

    def get_entity_schema(self, type_name: str) -> dict[str, Any] | None:
        """Return property definitions for an entity type."""
        entry = self._entity_types.get(type_name)
        if entry is None:
            return None
        return entry.get("properties", {})

    def get_entity_config(self, type_name: str) -> dict[str, Any] | None:
        """Return full config for an entity type (category, icon, color, properties)."""
        return self._entity_types.get(type_name)

    def get_display_config(self, type_name: str) -> dict[str, str]:
        """Return icon and color for dashboard rendering."""
        entry = self._entity_types.get(type_name, {})
        return {
            "icon": entry.get("icon", "circle"),
            "color": entry.get("color", "#94a3b8"),
        }

    def get_entity_category(self, type_name: str) -> str:
        """Return the category (core, strategic, academic, intelligence) for a type."""
        entry = self._entity_types.get(type_name, {})
        return entry.get("category", "core")

    def is_valid_entity_type(self, type_name: str) -> bool:
        """Check if an entity type is registered."""
        return type_name in self._entity_types

    # ── Edge type lookups ────────────────────────────────────────

    def get_all_edge_type_names(self) -> list[str]:
        """Return all registered edge type names."""
        return list(self._edge_types.keys())

    def get_edge_constraint(self, edge_type: str) -> tuple[set[str] | None, set[str] | None]:
        """Return (allowed_sources, allowed_targets) for an edge type.

        None means any entity type is allowed.
        """
        entry = self._edge_types.get(edge_type, {})
        source = entry.get("source")
        target = entry.get("target")

        source_set = set(source) if isinstance(source, list) else None
        target_set = set(target) if isinstance(target, list) else None

        return source_set, target_set

    def get_edge_category(self, edge_type: str) -> str:
        """Return the category for an edge type."""
        entry = self._edge_types.get(edge_type, {})
        return entry.get("category", "ASSOCIATIVE")

    def validate_edge(
        self, source_type: str, target_type: str, edge_type: str
    ) -> bool:
        """Check if an edge type is valid between given entity types."""
        if edge_type not in self._edge_types:
            return False

        allowed_sources, allowed_targets = self.get_edge_constraint(edge_type)

        if allowed_sources is not None and source_type not in allowed_sources:
            return False
        if allowed_targets is not None and target_type not in allowed_targets:
            return False

        return True

    def is_valid_edge_type(self, edge_type: str) -> bool:
        """Check if an edge type is registered."""
        return edge_type in self._edge_types

    # ── Network lookups ──────────────────────────────────────────

    def get_all_network_names(self) -> list[str]:
        """Return all registered network names."""
        return list(self._networks.keys())

    def get_network_keywords(self, network: str) -> list[str]:
        """Return keywords for a network."""
        entry = self._networks.get(network, {})
        return entry.get("keywords", [])

    def get_network_decay_lambda(self, network: str) -> float:
        """Return decay lambda for a network."""
        entry = self._networks.get(network, {})
        return entry.get("decay_lambda", 0.04)

    def get_all_network_keywords(self) -> dict[str, list[str]]:
        """Return keyword lists for all networks."""
        return {
            name: cfg.get("keywords", [])
            for name, cfg in self._networks.items()
        }

    def get_all_decay_lambdas(self) -> dict[str, float]:
        """Return decay lambdas for all networks."""
        return {
            name: cfg.get("decay_lambda", 0.04)
            for name, cfg in self._networks.items()
        }

    # ── Prompt generation ────────────────────────────────────────

    def generate_extraction_prompt_section(self) -> str:
        """Generate the entity type section for LLM extraction prompts.

        Returns a formatted string listing all entity types with their properties,
        suitable for inclusion in the Archivist system prompt.
        """
        lines = ["### Node Types ({} types)\n".format(len(self._entity_types))]
        lines.append("| Type | Category | Key Properties |")
        lines.append("|------|----------|----------------|")

        for type_name, config in self._entity_types.items():
            props = config.get("properties", {})
            prop_names = ", ".join(props.keys())
            category = config.get("category", "core")
            lines.append(f"| {type_name} | {category} | {prop_names} |")

        lines.append("\n### Edge Types ({} types)\n".format(len(self._edge_types)))
        lines.append("| Type | Category | Source Constraint | Target Constraint |")
        lines.append("|------|----------|-------------------|-------------------|")

        for edge_name, config in self._edge_types.items():
            category = config.get("category", "ASSOCIATIVE")
            source = config.get("source")
            target = config.get("target")
            src_str = ", ".join(source) if isinstance(source, list) else "any"
            tgt_str = ", ".join(target) if isinstance(target, list) else "any"
            lines.append(f"| {edge_name} | {category} | {src_str} | {tgt_str} |")

        lines.append("\n### Networks ({} networks)\n".format(len(self._networks)))
        for net_name in self._networks:
            lines.append(f"- {net_name}")

        return "\n".join(lines)


# ── Module-level singleton ───────────────────────────────────────

_registry: OntologyRegistry | None = None


def get_ontology_registry(path: Path | None = None) -> OntologyRegistry:
    """Get or create the module-level OntologyRegistry singleton."""
    global _registry
    if _registry is None:
        _registry = OntologyRegistry(path)
    return _registry


def reset_registry() -> None:
    """Reset the singleton (for testing)."""
    global _registry
    _registry = None
