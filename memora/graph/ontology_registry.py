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
        self._value_types: dict[str, dict[str, Any]] = {}
        self._interfaces: dict[str, dict[str, Any]] = {}
        self._action_types: dict[str, dict[str, Any]] = {}
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
        self._value_types = data.get("value_types", {})
        self._interfaces = data.get("interfaces", {})
        self._action_types = data.get("action_types", {})

        logger.info(
            "Loaded ontology v%d: %d entity types, %d edge types, %d networks, "
            "%d value types, %d interfaces, %d action types",
            self._version,
            len(self._entity_types),
            len(self._edge_types),
            len(self._networks),
            len(self._value_types),
            len(self._interfaces),
            len(self._action_types),
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

    def validate_edge_category(self, edge_type: str, edge_category: str) -> bool:
        """Check that an edge type belongs to the declared category."""
        if edge_type not in self._edge_types:
            return False
        return self.get_edge_category(edge_type) == edge_category

    def get_valid_edge_types(self, source_type: str, target_type: str) -> list[str]:
        """Return all registered edge types valid between two entity types."""
        return [
            name
            for name in self._edge_types
            if self.validate_edge(source_type, target_type, name)
        ]

    def get_edge_cardinality(self, edge_type: str) -> str | None:
        """Return the declared cardinality for an edge type.

        One of MANY_TO_ONE, ONE_TO_MANY, ONE_TO_ONE, or None (unconstrained
        many-to-many, the default when the edge type declares no cardinality).
        """
        entry = self._edge_types.get(edge_type, {})
        return entry.get("cardinality")

    def suggest_networks(self, text: str) -> list[tuple[str, float]]:
        """Suggest networks based on keyword matching in text.

        Returns list of (network_name, confidence) tuples, sorted by confidence desc.
        """
        text_lower = text.lower()
        scores: list[tuple[str, float]] = []

        for network, keywords in self.get_all_network_keywords().items():
            matches = sum(1 for kw in keywords if kw.lower() in text_lower)
            if matches > 0:
                confidence = min(0.95, 0.3 + (matches * 0.15))
                scores.append((network, confidence))

        scores.sort(key=lambda x: x[1], reverse=True)
        return scores

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

    # ── Value type lookups ───────────────────────────────────────

    def get_all_value_types(self) -> dict[str, dict[str, Any]]:
        """Return all registered value type definitions (regex/min/max)."""
        return self._value_types

    def validate_property_value(
        self, entity_type: str, prop_name: str, value: Any
    ) -> str | None:
        """Validate a property value against its declared value type, if any.

        Returns an error message if invalid, or None if the property has no
        declared value type, its value type is unknown, or the value is valid.
        """
        schema = self.get_entity_schema(entity_type) or {}
        prop_def = schema.get(prop_name)
        if not isinstance(prop_def, dict):
            return None

        value_type_name = prop_def.get("value_type")
        if not value_type_name:
            return None

        value_type = self._value_types.get(value_type_name)
        if value_type is None:
            return None

        if value in (None, ""):
            return None

        regex = value_type.get("regex")
        if regex is not None:
            import re

            if not re.fullmatch(regex, str(value)):
                return (
                    f"{entity_type}.{prop_name} = {value!r} does not match "
                    f"value type {value_type_name} (pattern {regex})"
                )

        minimum = value_type.get("min")
        maximum = value_type.get("max")
        if minimum is not None or maximum is not None:
            try:
                numeric_value = float(value)
            except (TypeError, ValueError):
                return (
                    f"{entity_type}.{prop_name} = {value!r} is not numeric, "
                    f"required by value type {value_type_name}"
                )
            if minimum is not None and numeric_value < minimum:
                return f"{entity_type}.{prop_name} = {value!r} is below minimum {minimum}"
            if maximum is not None and numeric_value > maximum:
                return f"{entity_type}.{prop_name} = {value!r} is above maximum {maximum}"

        return None

    # ── Interface lookups ────────────────────────────────────────

    def get_all_interface_names(self) -> list[str]:
        """Return all registered interface names."""
        return list(self._interfaces.keys())

    def get_all_interfaces(self) -> dict[str, dict[str, Any]]:
        """Return all registered interface definitions."""
        return self._interfaces

    def get_types_implementing(self, interface_name: str) -> list[str]:
        """Return the entity types that implement a given interface."""
        entry = self._interfaces.get(interface_name, {})
        return list(entry.get("implements", []))

    def get_interfaces_for_type(self, type_name: str) -> list[str]:
        """Return the interfaces implemented by a given entity type."""
        return [
            name
            for name, entry in self._interfaces.items()
            if type_name in entry.get("implements", [])
        ]

    # ── Action type lookups ──────────────────────────────────────

    def get_all_action_type_names(self) -> list[str]:
        """Return all registered action type names."""
        return list(self._action_types.keys())

    def get_action_type_config(self, action_type: str) -> dict[str, Any] | None:
        """Return the declared config (label, node_types, precondition) for an action type."""
        return self._action_types.get(action_type)

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
