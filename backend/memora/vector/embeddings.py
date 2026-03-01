"""Sentence-transformers embedding engine wrapper.

Lazy-loads the model on first use and provides text/batch embedding.
"""

from __future__ import annotations

import atexit
import logging
import math
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

EMBEDDING_DIM = 768


def cosine_similarity(vec_a: list[float], vec_b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return dot / (norm_a * norm_b)


class EmbeddingEngine:
    """Wrapper around sentence-transformers for dense embeddings."""

    def __init__(self, model_name: str = "all-mpnet-base-v2", cache_dir: str | Path | None = None):
        self._model_name = model_name
        self._cache_dir = str(cache_dir) if cache_dir else None
        self._model: Any = None
        self._cache: dict[str, dict[str, Any]] = {}

    def _load_model(self) -> None:
        """Lazy-load the sentence-transformers model."""
        if self._model is not None:
            return
        from sentence_transformers import SentenceTransformer

        logger.info("Loading sentence-transformers model %s...", self._model_name)
        kwargs = {}
        if self._cache_dir:
            kwargs["cache_folder"] = self._cache_dir

        # Load from local cache only — no HuggingFace network calls
        prev_offline = os.environ.get("HF_HUB_OFFLINE")
        os.environ["HF_HUB_OFFLINE"] = "1"
        try:
            self._model = SentenceTransformer(self._model_name, **kwargs)
        except Exception:
            # Model not cached yet — allow one-time download
            if prev_offline is None:
                del os.environ["HF_HUB_OFFLINE"]
            else:
                os.environ["HF_HUB_OFFLINE"] = prev_offline
            logger.info("Model not cached locally, downloading...")
            self._model = SentenceTransformer(self._model_name, **kwargs)
        finally:
            if prev_offline is None:
                os.environ.pop("HF_HUB_OFFLINE", None)
            else:
                os.environ["HF_HUB_OFFLINE"] = prev_offline
        logger.info("sentence-transformers model loaded")
        atexit.register(self._cleanup)

    def _cleanup(self) -> None:
        """Shut down loky worker pool to avoid leaked semaphore warnings."""
        try:
            from loky import get_reusable_executor
            get_reusable_executor().shutdown(wait=False)
        except Exception:
            pass

    def embed_text(self, text: str) -> dict[str, Any]:
        """Embed a single text, returning dense vector.

        Returns:
            {"dense": list[float], "sparse": dict[int, float]}
        """
        if text in self._cache:
            return self._cache[text]
        self._load_model()
        vec = self._model.encode(text).tolist()
        result = {"dense": vec, "sparse": {}}
        self._cache[text] = result
        return result

    def embed_batch(self, texts: list[str]) -> list[dict[str, Any]]:
        """Embed a batch of texts for efficiency.

        Uses cache to avoid re-encoding already-seen texts.
        """
        results: list[dict[str, Any] | None] = [None] * len(texts)
        uncached_indices: list[int] = []
        uncached_texts: list[str] = []

        for i, text in enumerate(texts):
            if text in self._cache:
                results[i] = self._cache[text]
            else:
                uncached_indices.append(i)
                uncached_texts.append(text)

        if uncached_texts:
            self._load_model()
            vecs = self._model.encode(uncached_texts).tolist()
            for idx, vec in zip(uncached_indices, vecs):
                entry = {"dense": vec, "sparse": {}}
                self._cache[texts[idx]] = entry
                results[idx] = entry

        return results  # type: ignore[return-value]

    def clear_cache(self) -> None:
        """Clear the embedding cache."""
        self._cache.clear()
