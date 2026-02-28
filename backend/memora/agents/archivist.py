"""Archivist Agent — LLM-powered extraction from text to GraphProposal.

Uses GPT-5-nano to extract structured knowledge graph proposals from
unstructured text, with RAG context from existing nodes.
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import openai

from memora.core.retry import async_call_with_retry
from memora.graph.models import GraphProposal
from memora.vector.embeddings import EmbeddingEngine
from memora.vector.store import VectorStore

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gpt-5-nano"


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

        # 4. Call OpenAI Responses API
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
                text={"format": {"type": "json_object"}},
                max_output_tokens=4096,
            )
        except openai.APIError as e:
            logger.error("OpenAI API error: %s", e)
            return ArchivistResult(
                raw_response=str(e),
                clarification_needed=False,
            )

        raw_text = response.output_text
        token_usage = {
            "input_tokens": response.usage.input_tokens,
            "output_tokens": response.usage.output_tokens,
        }

        # 5. Parse JSON from response
        try:
            raw_json = self._extract_json(raw_text)
        except ValueError as e:
            logger.error("Failed to parse JSON from archivist response: %s", e)
            # Retry once with feedback
            retry_result = await self._retry_extraction(text, capture_id, raw_text, str(e))
            if retry_result:
                return retry_result
            return ArchivistResult(
                raw_response=raw_text,
                token_usage=token_usage,
            )

        # 6. Inject capture_id and validate into GraphProposal
        raw_json["source_capture_id"] = capture_id

        try:
            proposal = GraphProposal(**raw_json)
        except Exception as e:
            logger.error("GraphProposal validation failed: %s", e)
            return ArchivistResult(
                raw_response=raw_text,
                token_usage=token_usage,
            )

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

    def _extract_json(self, text: str) -> dict[str, Any]:
        """Extract JSON object from LLM response.

        Handles both raw JSON and markdown code blocks.
        """
        text = text.strip()

        # Try direct JSON parse
        if text.startswith("{"):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                pass

        # Try to find ```json ... ``` blocks
        pattern = r"```(?:json)?\s*\n?(.*?)\n?\s*```"
        matches = re.findall(pattern, text, re.DOTALL)
        for match in matches:
            try:
                return json.loads(match.strip())
            except json.JSONDecodeError:
                continue

        # Try to find any JSON object in the text
        brace_start = text.find("{")
        if brace_start >= 0:
            # Find matching closing brace
            depth = 0
            for i in range(brace_start, len(text)):
                if text[i] == "{":
                    depth += 1
                elif text[i] == "}":
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(text[brace_start:i + 1])
                        except json.JSONDecodeError:
                            break

        raise ValueError(f"No valid JSON found in response: {text[:200]}...")

    async def _retry_extraction(
        self,
        text: str,
        capture_id: str,
        previous_response: str,
        error: str,
    ) -> ArchivistResult | None:
        """Retry extraction with feedback about the parsing error."""
        try:
            response = await async_call_with_retry(
                self._client.responses.create,
                model=self._model,
                instructions=self._system_prompt,
                input=[
                    {
                        "role": "user",
                        "content": f"Extract knowledge graph data from this text as JSON. Use capture ID: {capture_id}\n\nText:\n{text}",
                    },
                    {
                        "role": "assistant",
                        "content": previous_response,
                    },
                    {
                        "role": "user",
                        "content": (
                            f"Your previous response could not be parsed as valid JSON. "
                            f"Error: {error}\n\n"
                            f"Please respond with ONLY a valid JSON object matching the GraphProposal schema. "
                            f"No markdown, no explanation — just the JSON."
                        ),
                    },
                ],
                text={"format": {"type": "json_object"}},
                max_output_tokens=4096,
            )

            raw_text = response.output_text
            raw_json = self._extract_json(raw_text)
            raw_json["source_capture_id"] = capture_id
            proposal = GraphProposal(**raw_json)

            token_usage = {
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            }

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
                raw_response=raw_text,
                token_usage=token_usage,
            )

        except Exception:
            logger.error("Retry extraction also failed", exc_info=True)
            return None
