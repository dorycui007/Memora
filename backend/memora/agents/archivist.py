"""Archivist Agent — LLM-powered extraction from text to GraphProposal.

Uses GPT-5-nano to extract structured knowledge graph proposals from
unstructured text, with RAG context from existing nodes.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import openai
from pydantic import ValidationError

from memora.core.retry import async_call_with_retry
from memora.graph.models import GraphProposal
from memora.vector.embeddings import EmbeddingEngine
from memora.vector.store import VectorStore

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gpt-5-nano"


def _build_graph_proposal_schema() -> dict[str, Any]:
    """Generate a JSON Schema from GraphProposal, stripping schema-level `title` annotations
    and adding `additionalProperties: false` for Responses API compatibility."""
    schema = GraphProposal.model_json_schema()

    def _strip_titles(obj: Any, inside_properties: bool = False) -> Any:
        if isinstance(obj, dict):
            result = {}
            for k, v in obj.items():
                # Only strip "title" when it's a schema annotation (not inside "properties")
                if k == "title" and not inside_properties:
                    continue
                result[k] = _strip_titles(v, inside_properties=(k == "properties"))
            # Add additionalProperties: false to all object types for strict mode
            if result.get("type") == "object" and "properties" in result:
                result.setdefault("additionalProperties", False)
            return result
        if isinstance(obj, list):
            return [_strip_titles(item, inside_properties=False) for item in obj]
        return obj

    return _strip_titles(schema)


GRAPH_PROPOSAL_SCHEMA = _build_graph_proposal_schema()

_RESPONSE_FORMAT = {
    "format": {
        "type": "json_schema",
        "name": "graph_proposal",
        "schema": GRAPH_PROPOSAL_SCHEMA,
        "strict": False,
    }
}


@dataclass
class ExtractionContext:
    """Context passed to the archivist for a single extraction."""

    current_date: str = ""
    existing_nodes: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class ArchivistResult:
    """Result from the archivist extraction."""

    proposal: GraphProposal | None = None
    clarification_needed: bool = False
    clarification_message: str = ""
    raw_response: str = ""
    token_usage: dict[str, int] = field(default_factory=dict)


class ArchivistAgent:
    """LLM-powered extraction agent that converts text to GraphProposal."""

    def __init__(
        self,
        api_key: str,
        vector_store: VectorStore | None = None,
        embedding_engine: EmbeddingEngine | None = None,
        model: str = DEFAULT_MODEL,
    ) -> None:
        self._client = openai.AsyncOpenAI(api_key=api_key)
        self._model = model
        self._vector_store = vector_store
        self._embedding_engine = embedding_engine
        self._system_prompt = self._load_system_prompt()

    def _load_system_prompt(self) -> str:
        """Load the archivist system prompt from the prompts directory."""
        prompt_path = Path(__file__).parent / "prompts" / "archivist_system.md"
        return prompt_path.read_text(encoding="utf-8")

    def _retrieve_rag_context(self, text: str, top_k: int = 10) -> list[dict[str, Any]]:
        """Embed input text and query LanceDB for similar existing nodes."""
        if not self._vector_store or not self._embedding_engine:
            return []

        try:
            embedding = self._embedding_engine.embed_text(text)
            results = self._vector_store.dense_search(
                embedding["dense"], top_k=top_k
            )
            return [r.to_dict() for r in results]
        except Exception:
            logger.warning("RAG context retrieval failed", exc_info=True)
            return []

    def _format_existing_nodes(self, nodes: list[dict[str, Any]]) -> str:
        """Format existing nodes for injection into the system prompt."""
        if not nodes:
            return "No existing nodes found in the graph yet."

        lines = []
        for node in nodes:
            lines.append(
                f"- [{node.get('node_type', '?')}] \"{node.get('content', '')}\" "
                f"(id: {node.get('node_id', '?')}, networks: {node.get('networks', [])})"
            )
        return "\n".join(lines)

    def _build_dynamic_context(
        self,
        context: ExtractionContext,
        capture_id: str,
    ) -> str:
        """Build the dynamic context section injected alongside the static prompt."""
        nodes_text = self._format_existing_nodes(context.existing_nodes)
        return (
            f"Current Date: {context.current_date}\n\n"
            f"Capture ID: {capture_id}\n\n"
            f"Existing Nodes in Graph:\n{nodes_text}"
        )

    def _inject_placeholders(self, prompt: str, context: ExtractionContext) -> str:
        """Replace placeholders in the system prompt with actual values."""
        prompt = prompt.replace("{{CURRENT_DATE}}", context.current_date or datetime.utcnow().date().isoformat())
        prompt = prompt.replace("{{EXISTING_NODES}}", self._format_existing_nodes(context.existing_nodes))
        return prompt

    async def extract(self, text: str, capture_id: str) -> ArchivistResult:
        """Run extraction: RAG context -> LLM call -> parse -> validate.

        Args:
            text: The preprocessed capture text.
            capture_id: The capture's UUID string.

        Returns:
            ArchivistResult with the proposal or clarification request.
        """
        # 1. Retrieve similar existing nodes for RAG context
        rag_nodes = self._retrieve_rag_context(text)

        # 2. Build extraction context
        context = ExtractionContext(
            current_date=datetime.utcnow().date().isoformat(),
            existing_nodes=rag_nodes,
        )

        # 3. Prepare system prompt with dynamic context injected
        system_prompt = self._inject_placeholders(self._system_prompt, context)

        # 4. Call OpenAI Responses API with json_schema format
        try:
            response = await async_call_with_retry(
                self._client.responses.create,
                model=self._model,
                instructions=system_prompt,
                input=(
                    f"Extract knowledge graph data from this text. "
                    f"Respond with a single JSON object matching the GraphProposal schema. "
                    f"Use capture ID: {capture_id}\n\n"
                    f"Text:\n{text}"
                ),
                text=_RESPONSE_FORMAT,
                max_output_tokens=16384,
            )
        except openai.APIError as e:
            logger.error("OpenAI API error: %s", e)
            return ArchivistResult(
                raw_response=str(e),
                clarification_needed=False,
            )

        logger.debug(
            "Archivist response — status=%s, output_items=%d",
            getattr(response, "status", "?"),
            len(getattr(response, "output", [])),
        )
        raw_text = response.output_text
        token_usage = {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        }

        # 5. Parse JSON — json_schema mode guarantees valid JSON
        if not raw_text or not raw_text.strip():
            # Inspect the full response for diagnostics
            status = getattr(response, "status", "unknown")
            output_items = getattr(response, "output", [])
            logger.error(
                "Empty output_text from archivist LLM — status=%s, "
                "output_items=%d, model=%s",
                status, len(output_items), self._model,
            )
            for i, item in enumerate(output_items):
                item_type = getattr(item, "type", "unknown")
                logger.error("  output[%d] type=%s content=%s", i, item_type, str(item)[:300])

            # Try to extract text from output items directly
            for item in output_items:
                if getattr(item, "type", None) == "message":
                    for content_part in getattr(item, "content", []):
                        text_val = getattr(content_part, "text", None)
                        if text_val and text_val.strip():
                            raw_text = text_val
                            logger.info("Recovered text from output message item")
                            break
                    if raw_text:
                        break

            if not raw_text or not raw_text.strip():
                return ArchivistResult(
                    raw_response=raw_text or "",
                    token_usage=token_usage,
                )

        try:
            raw_json = json.loads(raw_text)
        except json.JSONDecodeError as e:
            logger.error("JSON decode error (truncated response?): %s", e)
            return ArchivistResult(
                raw_response=raw_text,
                token_usage=token_usage,
            )

        # 6. Inject capture_id and validate into GraphProposal
        raw_json["source_capture_id"] = capture_id

        try:
            proposal = GraphProposal(**raw_json)
        except ValidationError as e:
            logger.warning("GraphProposal validation failed, retrying API call: %s", e)
            retry_response = await self._retry_api_call(system_prompt, text, capture_id)
            if retry_response is None:
                return ArchivistResult(
                    raw_response=raw_text,
                    token_usage=token_usage,
                )
            # Parse the retry response
            retry_text = retry_response.output_text
            retry_usage = {
                "input_tokens": retry_response.usage.input_tokens,
                "output_tokens": retry_response.usage.output_tokens,
            }
            try:
                retry_json = json.loads(retry_text)
                retry_json["source_capture_id"] = capture_id
                proposal = GraphProposal(**retry_json)
            except (json.JSONDecodeError, ValidationError) as retry_err:
                logger.error("Retry also failed: %s", retry_err)
                return ArchivistResult(
                    raw_response=retry_text,
                    token_usage=retry_usage,
                )
            raw_text = retry_text
            token_usage = retry_usage

        # 7. Check for clarification protocol
        if proposal.confidence == 0.0 and not proposal.nodes_to_create:
            return ArchivistResult(
                proposal=None,
                clarification_needed=True,
                clarification_message=proposal.human_summary,
                raw_response=raw_text,
                token_usage=token_usage,
            )

        return ArchivistResult(
            proposal=proposal,
            clarification_needed=False,
            raw_response=raw_text,
            token_usage=token_usage,
        )

    async def _retry_api_call(
        self,
        system_prompt: str,
        text: str,
        capture_id: str,
    ) -> Any | None:
        """Re-issue the same API call once on validation failure.

        Returns the raw response object or None on failure.
        """
        try:
            return await async_call_with_retry(
                self._client.responses.create,
                model=self._model,
                instructions=system_prompt,
                input=(
                    f"Extract knowledge graph data from this text. "
                    f"Respond with a single JSON object matching the GraphProposal schema. "
                    f"Use capture ID: {capture_id}\n\n"
                    f"Text:\n{text}"
                ),
                text=_RESPONSE_FORMAT,
                max_output_tokens=16384,
            )
        except Exception:
            logger.error("Retry API call failed", exc_info=True)
            return None
