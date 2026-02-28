"""Sentence-transformers embedding engine wrapper.

Lazy-loads the model on first use and provides text/batch embedding.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

EMBEDDING_DIM = 768


class EmbeddingEngine:
    """Wrapper around sentence-transformers for dense embeddings."""

    def __init__(self, model_name: str = "all-mpnet-base-v2", cache_dir: str | Path | None = None):
        self._model_name = model_name
        self._cache_dir = str(cache_dir) if cache_dir else None
        self._model: Any = None

    def _load_model(self) -> None:
        """Lazy-load the sentence-transformers model."""
        if self._model is not None:
            return
        from sentence_transformers import SentenceTransformer

        logger.info("Loading sentence-transformers model %s...", self._model_name)
        kwargs = {}
        if self._cache_dir:
            kwargs["cache_folder"] = self._cache_dir
        self._model = SentenceTransformer(self._model_name, **kwargs)
        logger.info("sentence-transformers model loaded")

    def embed_text(self, text: str) -> dict[str, Any]:
        """Embed a single text, returning dense vector.

        Returns:
            {"dense": list[float], "sparse": dict[int, float]}
        """
        self._load_model()
        vec = self._model.encode(text).tolist()
        return {"dense": vec, "sparse": {}}

    def embed_batch(self, texts: list[str]) -> list[dict[str, Any]]:
        """Embed a batch of texts for efficiency."""
        self._load_model()
        vecs = self._model.encode(texts).tolist()
        return [{"dense": vec, "sparse": {}} for vec in vecs]
