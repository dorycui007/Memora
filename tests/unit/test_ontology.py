"""Tests for graph ontology — edge validation, category mapping, network suggestions."""

from __future__ import annotations

import pytest

from memora.graph.models import EdgeCategory, EdgeType, NodeType
from memora.graph.ontology import (
    EDGE_TYPE_CATEGORY,
    get_category_for_edge_type,
    get_valid_edge_types,
    suggest_networks,
    validate_edge,
    validate_edge_category,
)


class TestEdgeTypeCategoryMapping:
    def test_all_edge_types_have_category(self):
        for et in EdgeType:
            assert et in EDGE_TYPE_CATEGORY, f"{et} missing from EDGE_TYPE_CATEGORY"

    def test_structural_edges(self):
        assert EDGE_TYPE_CATEGORY[EdgeType.PART_OF] == EdgeCategory.STRUCTURAL
        assert EDGE_TYPE_CATEGORY[EdgeType.CONTAINS] == EdgeCategory.STRUCTURAL
        assert EDGE_TYPE_CATEGORY[EdgeType.SUBTASK_OF] == EdgeCategory.STRUCTURAL

    def test_social_edges(self):
        assert EDGE_TYPE_CATEGORY[EdgeType.KNOWS] == EdgeCategory.SOCIAL
        assert EDGE_TYPE_CATEGORY[EdgeType.COLLABORATES_WITH] == EdgeCategory.SOCIAL

    def test_get_category(self):
        assert get_category_for_edge_type(EdgeType.BRIDGES) == EdgeCategory.NETWORK


class TestEdgeValidation:
    def test_knows_requires_person_to_person(self):
        assert validate_edge(NodeType.PERSON, NodeType.PERSON, EdgeType.KNOWS) is True
        assert validate_edge(NodeType.EVENT, NodeType.PERSON, EdgeType.KNOWS) is False
        assert validate_edge(NodeType.PERSON, NodeType.EVENT, EdgeType.KNOWS) is False

    def test_related_to_allows_any(self):
        assert validate_edge(NodeType.EVENT, NodeType.PERSON, EdgeType.RELATED_TO) is True
        assert validate_edge(NodeType.NOTE, NodeType.CONCEPT, EdgeType.RELATED_TO) is True

    def test_committed_to_requires_person_to_commitment(self):
        assert validate_edge(NodeType.PERSON, NodeType.COMMITMENT, EdgeType.COMMITTED_TO) is True
        assert validate_edge(NodeType.EVENT, NodeType.COMMITMENT, EdgeType.COMMITTED_TO) is False

    def test_subtask_of_valid_types(self):
        assert validate_edge(NodeType.COMMITMENT, NodeType.GOAL, EdgeType.SUBTASK_OF) is True
        assert validate_edge(NodeType.PROJECT, NodeType.PROJECT, EdgeType.SUBTASK_OF) is True
        assert validate_edge(NodeType.PERSON, NodeType.GOAL, EdgeType.SUBTASK_OF) is False

    def test_verified_by_target_constraint(self):
        assert validate_edge(NodeType.NOTE, NodeType.REFERENCE, EdgeType.VERIFIED_BY) is True
        assert validate_edge(NodeType.NOTE, NodeType.PERSON, EdgeType.VERIFIED_BY) is True
        assert validate_edge(NodeType.NOTE, NodeType.EVENT, EdgeType.VERIFIED_BY) is False


class TestEdgeCategoryValidation:
    def test_correct_category(self):
        assert validate_edge_category(EdgeType.KNOWS, EdgeCategory.SOCIAL) is True

    def test_wrong_category(self):
        assert validate_edge_category(EdgeType.KNOWS, EdgeCategory.STRUCTURAL) is False


class TestGetValidEdgeTypes:
    def test_person_to_person_has_social_edges(self):
        valid = get_valid_edge_types(NodeType.PERSON, NodeType.PERSON)
        assert EdgeType.KNOWS in valid
        assert EdgeType.COLLABORATES_WITH in valid
        assert EdgeType.REPORTS_TO in valid

    def test_person_to_person_also_has_generic_edges(self):
        valid = get_valid_edge_types(NodeType.PERSON, NodeType.PERSON)
        assert EdgeType.RELATED_TO in valid
        assert EdgeType.SIMILAR_TO in valid


class TestNetworkSuggestions:
    def test_academic_keywords(self):
        results = suggest_networks("I need to study for my exam next week")
        networks = [n for n, _ in results]
        assert "ACADEMIC" in networks

    def test_financial_keywords(self):
        results = suggest_networks("Payment of $500 invoice from client")
        networks = [n for n, _ in results]
        assert "FINANCIAL" in networks

    def test_social_keywords(self):
        results = suggest_networks("Birthday party with friends this weekend")
        networks = [n for n, _ in results]
        assert "SOCIAL" in networks

    def test_no_matches(self):
        results = suggest_networks("xyz abc 123")
        assert len(results) == 0

    def test_multiple_networks(self):
        results = suggest_networks("Meeting with client about project budget and money")
        networks = [n for n, _ in results]
        assert len(networks) >= 2
