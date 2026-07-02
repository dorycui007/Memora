"""Tests for the YAML-driven ontology registry."""

from __future__ import annotations

from pathlib import Path

import pytest

from memora.graph.ontology_registry import OntologyRegistry, reset_registry


@pytest.fixture
def registry():
    """Create a registry from the default ontology."""
    reset_registry()
    return OntologyRegistry()


class TestEntityTypes:
    def test_loads_all_entity_types(self, registry):
        names = registry.get_all_entity_type_names()
        # Should have at least the original 12 + 5 new = 17
        assert len(names) >= 17
        assert "PERSON" in names
        assert "ORGANIZATION" in names
        assert "POSITION" in names
        assert "ELECTION" in names
        assert "COURSE" in names
        assert "METRIC" in names

    def test_get_entity_schema(self, registry):
        schema = registry.get_entity_schema("PERSON")
        assert schema is not None
        assert "name" in schema
        assert "aliases" in schema

    def test_get_entity_schema_unknown(self, registry):
        assert registry.get_entity_schema("NONEXISTENT") is None

    def test_get_display_config(self, registry):
        config = registry.get_display_config("PERSON")
        assert "icon" in config
        assert "color" in config
        assert config["color"].startswith("#")

    def test_get_entity_category(self, registry):
        assert registry.get_entity_category("PERSON") == "core"
        assert registry.get_entity_category("ORGANIZATION") == "strategic"
        assert registry.get_entity_category("COURSE") == "academic"
        assert registry.get_entity_category("METRIC") == "intelligence"

    def test_is_valid_entity_type(self, registry):
        assert registry.is_valid_entity_type("PERSON")
        assert registry.is_valid_entity_type("ORGANIZATION")
        assert not registry.is_valid_entity_type("NONEXISTENT")


class TestEdgeTypes:
    def test_loads_all_edge_types(self, registry):
        names = registry.get_all_edge_type_names()
        # Should have at least the original 29 + 7 new = 36
        assert len(names) >= 36
        assert "RELATED_TO" in names
        assert "HOLDS_POSITION" in names
        assert "CANDIDATE_IN" in names
        assert "PREREQUISITE_OF" in names

    def test_get_edge_constraint(self, registry):
        sources, targets = registry.get_edge_constraint("HOLDS_POSITION")
        assert sources == {"PERSON"}
        assert targets == {"POSITION"}

    def test_get_edge_constraint_unconstrained(self, registry):
        sources, targets = registry.get_edge_constraint("RELATED_TO")
        assert sources is None
        assert targets is None

    def test_validate_edge_valid(self, registry):
        assert registry.validate_edge("PERSON", "POSITION", "HOLDS_POSITION")
        assert registry.validate_edge("PERSON", "ELECTION", "CANDIDATE_IN")
        assert registry.validate_edge("COURSE", "COURSE", "PREREQUISITE_OF")

    def test_validate_edge_invalid(self, registry):
        assert not registry.validate_edge("EVENT", "POSITION", "HOLDS_POSITION")
        assert not registry.validate_edge("PERSON", "PERSON", "HOLDS_POSITION")

    def test_validate_edge_unknown_type(self, registry):
        assert not registry.validate_edge("PERSON", "PERSON", "NONEXISTENT")

    def test_get_edge_category(self, registry):
        assert registry.get_edge_category("HOLDS_POSITION") == "STRATEGIC"
        assert registry.get_edge_category("RELATED_TO") == "ASSOCIATIVE"
        assert registry.get_edge_category("PREREQUISITE_OF") == "STRUCTURAL"


class TestNetworks:
    def test_loads_all_networks(self, registry):
        names = registry.get_all_network_names()
        assert len(names) >= 9  # 7 original + GOVERNANCE + CLUBS
        assert "ACADEMIC" in names
        assert "GOVERNANCE" in names
        assert "CLUBS" in names

    def test_get_network_keywords(self, registry):
        keywords = registry.get_network_keywords("GOVERNANCE")
        assert "election" in keywords
        assert "vote" in keywords

    def test_get_network_decay_lambda(self, registry):
        lam = registry.get_network_decay_lambda("ACADEMIC")
        assert lam == 0.05

    def test_get_all_decay_lambdas(self, registry):
        lambdas = registry.get_all_decay_lambdas()
        assert "GOVERNANCE" in lambdas
        assert lambdas["GOVERNANCE"] == 0.04


class TestPromptGeneration:
    def test_generate_extraction_prompt(self, registry):
        prompt = registry.generate_extraction_prompt_section()
        assert "PERSON" in prompt
        assert "ORGANIZATION" in prompt
        assert "HOLDS_POSITION" in prompt
        assert "GOVERNANCE" in prompt
        assert "Node Types" in prompt
        assert "Edge Types" in prompt


class TestMissingFile:
    def test_missing_ontology_file(self):
        """Registry should handle missing YAML file gracefully."""
        reg = OntologyRegistry(Path("/nonexistent/path.yaml"))
        assert reg.get_all_entity_type_names() == []
        assert reg.get_all_edge_type_names() == []
