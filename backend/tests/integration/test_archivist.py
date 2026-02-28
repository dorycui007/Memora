"""Integration tests for the Archivist Agent with mocked OpenAI API."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from memora.agents.archivist import ArchivistAgent, ArchivistResult, ExtractionContext


@pytest.fixture
def mock_openai_response():
    """Create a mock OpenAI API response with a valid GraphProposal JSON."""
    proposal_json = {
        "confidence": 0.88,
        "nodes_to_create": [
            {
                "temp_id": "person_1",
                "node_type": "PERSON",
                "title": "Sam Chen",
                "content": "Investor contact met at Blue Bottle",
                "properties": {"name": "Sam Chen", "role": "Investor"},
                "confidence": 0.9,
                "networks": ["VENTURES"],
            },
            {
                "temp_id": "event_1",
                "node_type": "EVENT",
                "title": "Coffee with Sam",
                "content": "Discussed investment opportunity at Blue Bottle",
                "properties": {"location": "Blue Bottle Coffee"},
                "confidence": 0.85,
                "networks": ["VENTURES"],
            },
        ],
        "edges_to_create": [
            {
                "source_id": "person_1",
                "target_id": "event_1",
                "edge_type": "RELATED_TO",
                "edge_category": "ASSOCIATIVE",
                "confidence": 0.85,
            }
        ],
        "nodes_to_update": [],
        "human_summary": "Adding Sam Chen and coffee meeting event",
    }

    response = MagicMock()
    response.output_text = json.dumps(proposal_json)
    response.usage = MagicMock(
        input_tokens=500,
        output_tokens=200,
    )
    return response


@pytest.fixture
def mock_clarification_response():
    """Create a mock response requesting clarification."""
    proposal_json = {
        "confidence": 0.0,
        "nodes_to_create": [],
        "edges_to_create": [],
        "nodes_to_update": [],
        "human_summary": "Could you clarify what you mean by 'the project'? Which project are you referring to?",
    }

    response = MagicMock()
    response.output_text = json.dumps(proposal_json)
    response.usage = MagicMock(input_tokens=300, output_tokens=50)
    return response


@pytest.fixture
def archivist(mock_openai_response):
    """Create an ArchivistAgent with mocked OpenAI client."""
    with patch("memora.agents.archivist.openai") as mock_module:
        mock_client = MagicMock()
        mock_client.responses.create.return_value = mock_openai_response
        mock_module.OpenAI.return_value = mock_client

        agent = ArchivistAgent(api_key="test-key-xxx")
        agent._client = mock_client
        yield agent


class TestArchivistExtraction:
    def test_successful_extraction(self, archivist, mock_openai_response):
        capture_id = str(uuid4())
        result = archivist.extract(
            "Had coffee with Sam Chen today at Blue Bottle. He wants to see our pitch deck.",
            capture_id,
        )

        assert isinstance(result, ArchivistResult)
        assert result.proposal is not None
        assert result.clarification_needed is False
        assert result.proposal.confidence == 0.88
        assert len(result.proposal.nodes_to_create) == 2
        assert len(result.proposal.edges_to_create) == 1
        assert result.proposal.source_capture_id == capture_id

    def test_token_usage_tracked(self, archivist):
        result = archivist.extract("test text", str(uuid4()))
        assert "input_tokens" in result.token_usage
        assert "output_tokens" in result.token_usage
        assert result.token_usage["input_tokens"] == 500
        assert result.token_usage["output_tokens"] == 200

    def test_node_types_correct(self, archivist):
        result = archivist.extract("test text", str(uuid4()))
        node_types = [n.node_type.value for n in result.proposal.nodes_to_create]
        assert "PERSON" in node_types
        assert "EVENT" in node_types

    def test_networks_assigned(self, archivist):
        result = archivist.extract("test text", str(uuid4()))
        for node in result.proposal.nodes_to_create:
            assert len(node.networks) > 0


class TestArchivistClarification:
    def test_clarification_response(self, mock_clarification_response):
        with patch("memora.agents.archivist.openai") as mock_module:
            mock_client = MagicMock()
            mock_client.responses.create.return_value = mock_clarification_response
            mock_module.OpenAI.return_value = mock_client

            agent = ArchivistAgent(api_key="test-key")
            agent._client = mock_client

            result = agent.extract("Update the project status", str(uuid4()))
            assert result.clarification_needed is True
            assert result.proposal is None
            assert "project" in result.clarification_message.lower()


class TestArchivistJSONParsing:
    def test_parse_raw_json(self, archivist):
        raw = '{"confidence": 0.5, "nodes_to_create": [], "edges_to_create": [], "nodes_to_update": [], "human_summary": "test"}'
        parsed = archivist._extract_json(raw)
        assert parsed["confidence"] == 0.5

    def test_parse_markdown_block(self, archivist):
        raw = '```json\n{"confidence": 0.5, "nodes_to_create": [], "edges_to_create": [], "nodes_to_update": [], "human_summary": "test"}\n```'
        parsed = archivist._extract_json(raw)
        assert parsed["confidence"] == 0.5

    def test_parse_embedded_json(self, archivist):
        raw = 'Here is the result:\n{"confidence": 0.5, "nodes_to_create": [], "edges_to_create": [], "nodes_to_update": [], "human_summary": "test"}\nDone!'
        parsed = archivist._extract_json(raw)
        assert parsed["confidence"] == 0.5

    def test_invalid_json_raises(self, archivist):
        with pytest.raises(ValueError, match="No valid JSON"):
            archivist._extract_json("This is not JSON at all")


class TestArchivistRAGContext:
    def test_no_vector_store_returns_empty(self, archivist):
        result = archivist._retrieve_rag_context("test query")
        assert result == []

    def test_format_no_nodes(self, archivist):
        formatted = archivist._format_existing_nodes([])
        assert "No existing nodes" in formatted

    def test_format_nodes(self, archivist):
        nodes = [
            {"node_type": "PERSON", "content": "Alice", "node_id": "123", "networks": ["SOCIAL"]},
        ]
        formatted = archivist._format_existing_nodes(nodes)
        assert "PERSON" in formatted
        assert "Alice" in formatted


class TestArchivistAPIError:
    def test_api_error_returns_empty_result(self):
        import openai as openai_module

        with patch("memora.agents.archivist.openai") as mock_module:
            mock_client = MagicMock()
            mock_module.OpenAI.return_value = mock_client
            mock_module.APIError = openai_module.APIError

            mock_client.responses.create.side_effect = openai_module.APIError(
                message="Rate limited",
                request=MagicMock(),
                body=None,
            )

            agent = ArchivistAgent(api_key="test-key")
            agent._client = mock_client

            result = agent.extract("test text", str(uuid4()))
            assert result.proposal is None
            assert result.clarification_needed is False
