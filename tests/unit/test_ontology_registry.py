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
        assert registry.get_edge_category("BRIDGES") == "NETWORK"
        assert registry.get_edge_category("KNOWS") == "SOCIAL"

    def test_knows_requires_person_to_person(self, registry):
        assert registry.validate_edge("PERSON", "PERSON", "KNOWS") is True
        assert registry.validate_edge("EVENT", "PERSON", "KNOWS") is False
        assert registry.validate_edge("PERSON", "EVENT", "KNOWS") is False

    def test_committed_to_requires_person_to_commitment(self, registry):
        assert registry.validate_edge("PERSON", "COMMITMENT", "COMMITTED_TO") is True
        assert registry.validate_edge("EVENT", "COMMITMENT", "COMMITTED_TO") is False

    def test_subtask_of_valid_types(self, registry):
        assert registry.validate_edge("COMMITMENT", "GOAL", "SUBTASK_OF") is True
        assert registry.validate_edge("PROJECT", "PROJECT", "SUBTASK_OF") is True
        assert registry.validate_edge("PERSON", "GOAL", "SUBTASK_OF") is False

    def test_verified_by_target_constraint(self, registry):
        assert registry.validate_edge("NOTE", "REFERENCE", "VERIFIED_BY") is True
        assert registry.validate_edge("NOTE", "PERSON", "VERIFIED_BY") is True
        assert registry.validate_edge("NOTE", "EVENT", "VERIFIED_BY") is False

    def test_validate_edge_category(self, registry):
        assert registry.validate_edge_category("KNOWS", "SOCIAL") is True
        assert registry.validate_edge_category("KNOWS", "STRUCTURAL") is False
        assert registry.validate_edge_category("NONEXISTENT", "SOCIAL") is False

    def test_get_valid_edge_types(self, registry):
        valid = registry.get_valid_edge_types("PERSON", "PERSON")
        assert "KNOWS" in valid
        assert "COLLABORATES_WITH" in valid
        assert "RELATED_TO" in valid  # unconstrained edges are valid for any pair

    def test_get_edge_cardinality(self, registry):
        assert registry.get_edge_cardinality("SUBTASK_OF") == "MANY_TO_ONE"
        assert registry.get_edge_cardinality("PART_OF") == "MANY_TO_ONE"
        assert registry.get_edge_cardinality("HOLDS_POSITION") == "ONE_TO_MANY"
        assert registry.get_edge_cardinality("RELATED_TO") is None


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


class TestNetworkSuggestions:
    def test_academic_keywords(self, registry):
        results = registry.suggest_networks("I need to study for my exam next week")
        assert "ACADEMIC" in [n for n, _ in results]

    def test_financial_keywords(self, registry):
        results = registry.suggest_networks("Payment of $500 invoice from client")
        assert "FINANCIAL" in [n for n, _ in results]

    def test_no_matches(self, registry):
        assert registry.suggest_networks("xyz abc 123") == []

    def test_multiple_networks(self, registry):
        results = registry.suggest_networks("Meeting with client about project budget and money")
        assert len({n for n, _ in results}) >= 2


class TestValueTypes:
    def test_url_value_type_valid(self, registry):
        assert registry.validate_property_value("REFERENCE", "url", "https://example.com") is None

    def test_url_value_type_invalid(self, registry):
        error = registry.validate_property_value("REFERENCE", "url", "not-a-url")
        assert error is not None

    def test_empty_value_skipped(self, registry):
        assert registry.validate_property_value("REFERENCE", "url", "") is None

    def test_currency_code_value_type(self, registry):
        assert registry.validate_property_value("FINANCIAL_ITEM", "currency", "USD") is None
        assert registry.validate_property_value("FINANCIAL_ITEM", "currency", "us-dollars") is not None

    def test_percentage_range(self, registry):
        assert registry.validate_property_value("GOAL", "progress", 0.5) is None
        assert registry.validate_property_value("GOAL", "progress", 1.5) is not None

    def test_property_without_value_type_always_valid(self, registry):
        assert registry.validate_property_value("PERSON", "name", "anything") is None


class TestInterfaces:
    def test_get_types_implementing(self, registry):
        types = registry.get_types_implementing("SCHEDULABLE")
        assert "COMMITMENT" in types
        assert "GOAL" in types
        assert "EVENT" in types

    def test_get_interfaces_for_type(self, registry):
        interfaces = registry.get_interfaces_for_type("GOAL")
        assert "SCHEDULABLE" in interfaces
        assert "TRACKABLE" in interfaces

    def test_unknown_interface_returns_empty(self, registry):
        assert registry.get_types_implementing("NONEXISTENT") == []


class TestActionTypes:
    def test_get_action_type_config(self, registry):
        config = registry.get_action_type_config("COMPLETE_COMMITMENT")
        assert config is not None
        assert config["node_types"] == ["COMMITMENT"]

    def test_unknown_action_type(self, registry):
        assert registry.get_action_type_config("NONEXISTENT") is None


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
