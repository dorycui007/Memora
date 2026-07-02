"""Ontology route — expose type schemas for dashboard rendering."""

from __future__ import annotations

from fastapi import APIRouter

from memora.graph.ontology_registry import get_ontology_registry

router = APIRouter()


@router.get("/ontology")
async def get_ontology():
    """Get the full ontology schema for dashboard rendering."""
    registry = get_ontology_registry()
    entity_types = {}
    for name in registry.get_all_entity_type_names():
        config = registry.get_entity_config(name)
        entity_types[name] = {
            "category": config.get("category", "core") if config else "core",
            "icon": config.get("icon", "circle") if config else "circle",
            "color": config.get("color", "#94a3b8") if config else "#94a3b8",
            "properties": list((config.get("properties", {}) if config else {}).keys()),
        }

    edge_types = {}
    for name in registry.get_all_edge_type_names():
        sources, targets = registry.get_edge_constraint(name)
        edge_types[name] = {
            "category": registry.get_edge_category(name),
            "sources": list(sources) if sources else None,
            "targets": list(targets) if targets else None,
        }

    return {
        "version": registry.version,
        "entity_types": entity_types,
        "edge_types": edge_types,
        "networks": registry.get_all_network_names(),
    }
