"""Archivist Agent — LLM-powered extraction from text to GraphProposal.

Uses GPT-5-nano to extract structured knowledge graph proposals from
unstructured text, with RAG context from existing nodes.
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
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
        you_node_id: str | None = None,
    ) -> None:
        self._client = openai.AsyncOpenAI(api_key=api_key)
        self._model = model
        self._vector_store = vector_store
        self._embedding_engine = embedding_engine
        self._you_node_id = you_node_id
        self._system_prompt = self._load_system_prompt()

    def _load_system_prompt(self) -> str:
        """Load the archivist system prompt from the prompts directory."""
        prompt_path = Path(__file__).parent / "prompts" / "archivist_system.md"
        return prompt_path.read_text(encoding="utf-8")

    async def _retrieve_rag_context(self, text: str, top_k: int = 10) -> list[dict[str, Any]]:
        """Embed input text and query LanceDB for similar existing nodes.

        Runs embedding + search in a thread to avoid blocking the event loop.
        """
        if not self._vector_store or not self._embedding_engine:
            return []

        def _search() -> list[dict[str, Any]]:
            embedding = self._embedding_engine.embed_text(text)
            results = self._vector_store.dense_search(
                embedding["dense"], top_k=top_k
            )
            return [r.to_dict() for r in results]

        try:
            return await asyncio.to_thread(_search)
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

    def _get_static_system_prompt(self) -> str:
        """Return system prompt with only the stable YOU_NODE_ID injected.

        This keeps the instructions parameter constant across calls,
        enabling OpenAI's automatic prompt caching.
        """
        if not hasattr(self, "_cached_static_prompt"):
            prompt = self._system_prompt.replace("{{YOU_NODE_ID}}", self._you_node_id or "")
            # Remove leftover dynamic placeholders (now provided in input)
            prompt = prompt.replace("{{CURRENT_DATE}}", "[see dynamic context in user message]")
            prompt = prompt.replace("{{EXISTING_NODES}}", "[see dynamic context in user message]")
            self._cached_static_prompt = prompt
        return self._cached_static_prompt

    def _inject_placeholders(self, prompt: str, context: ExtractionContext) -> str:
        """Replace placeholders in the system prompt with actual values."""
        prompt = prompt.replace("{{CURRENT_DATE}}", context.current_date or datetime.now(timezone.utc).date().isoformat())
        prompt = prompt.replace("{{EXISTING_NODES}}", self._format_existing_nodes(context.existing_nodes))
        prompt = prompt.replace("{{YOU_NODE_ID}}", self._you_node_id or "")
        return prompt

    async def extract(
        self,
        text: str,
        capture_id: str,
        metadata: dict | None = None,
    ) -> ArchivistResult:
        """Run extraction: RAG context -> LLM call -> parse -> validate.

        Args:
            text: The raw capture text (not mutated by preprocessing).
            capture_id: The capture's UUID string.
            metadata: Optional preprocessing metadata (resolved dates, currencies)
                      to provide alongside the raw text.

        Returns:
            ArchivistResult with the proposal or clarification request.
        """
        import time as _time

        # 1. Retrieve similar existing nodes for RAG context
        t0 = _time.perf_counter()
        rag_nodes = await self._retrieve_rag_context(text)
        logger.info("Archivist RAG retrieval took %.2fs (%d nodes)", _time.perf_counter() - t0, len(rag_nodes))

        # 2. Build extraction context
        context = ExtractionContext(
            current_date=datetime.now(timezone.utc).date().isoformat(),
            existing_nodes=rag_nodes,
        )

        # 3. Use static system prompt (cacheable) + dynamic context in input
        system_prompt = self._get_static_system_prompt()
        dynamic_context = self._build_dynamic_context(context, capture_id)

        # Build metadata hint for the LLM
        metadata_hint = ""
        if metadata:
            parts = []
            if metadata.get("resolved_dates"):
                date_info = ", ".join(
                    f'"{d["phrase"]}" = {d["resolved"]}'
                    for d in metadata["resolved_dates"]
                )
                parts.append(f"Date references: {date_info}")
            if metadata.get("resolved_currencies"):
                curr_info = ", ".join(
                    f'"{c["phrase"]}" = {c["resolved"]}'
                    for c in metadata["resolved_currencies"]
                )
                parts.append(f"Currency references: {curr_info}")
            if parts:
                metadata_hint = "\n\nPreprocessing context:\n" + "\n".join(parts)

        # 4. Call OpenAI Responses API with json_schema format
        t1 = _time.perf_counter()
        try:
            response = await async_call_with_retry(
                self._client.responses.create,
                model=self._model,
                instructions=system_prompt,
                input=(
                    f"{dynamic_context}\n\n---\n\n"
                    f"Extract knowledge graph data from this text. "
                    f"Respond with a single JSON object matching the GraphProposal schema. "
                    f"Use capture ID: {capture_id}{metadata_hint}\n\n"
                    f"Text:\n{text}"
                ),
                text=_RESPONSE_FORMAT,
                reasoning={"effort": "low"},
                max_output_tokens=16384,
            )
        except openai.APIError as e:
            logger.error("OpenAI API error: %s", e)
            return ArchivistResult(
                raw_response=str(e),
                clarification_needed=False,
            )

        logger.info("Archivist LLM call took %.2fs", _time.perf_counter() - t1)

        response_status = getattr(response, "status", "unknown")
        logger.debug(
            "Archivist response — status=%s, output_items=%d",
            response_status,
            len(getattr(response, "output", [])),
        )

        # Check for truncated response (incomplete status means output was cut off)
        if response_status == "incomplete":
            incomplete_reason = getattr(response, "incomplete_details", None)
            logger.warning(
                "Archivist response truncated (incomplete): %s — "
                "input may be too long for single extraction",
                incomplete_reason,
            )

        raw_text = response.output_text
        cached_tokens = getattr(response.usage, "input_tokens_details", None)
        cached_count = getattr(cached_tokens, "cached_tokens", 0) if cached_tokens else 0
        token_usage = {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        }
        logger.info(
            "Archivist tokens — input=%d (cached=%d), output=%d",
            response.usage.input_tokens, cached_count, response.usage.output_tokens,
        )

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
            retry_response = await self._retry_api_call(system_prompt, text, capture_id, dynamic_context)
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
        dynamic_context: str = "",
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
                    f"{dynamic_context}\n\n---\n\n"
                    f"Extract knowledge graph data from this text. "
                    f"Respond with a single JSON object matching the GraphProposal schema. "
                    f"Use capture ID: {capture_id}\n\n"
                    f"Text:\n{text}"
                ),
                text=_RESPONSE_FORMAT,
                reasoning={"effort": "low"},
                max_output_tokens=16384,
            )
        except Exception:
            logger.error("Retry API call failed", exc_info=True)
            return None
