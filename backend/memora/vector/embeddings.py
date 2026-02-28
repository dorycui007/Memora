"""BGE-M3 embedding engine wrapper.

Lazy-loads the model on first use and provides text/batch embedding.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

EMBEDDING_DIM = 1024


class EmbeddingEngine:
    """Wrapper around BGE-M3 for dense + sparse embeddings."""

    def __init__(self, model_name: str = "BAAI/bge-m3", cache_dir: str | Path | None = None):
        self._model_name = model_name
        self._cache_dir = str(cache_dir) if cache_dir else None
        self._model: Any = None

    def _load_model(self) -> None:
        """Lazy-load the BGE-M3 model."""
        if self._model is not None:
            return
        try:
            from FlagEmbedding import BGEM3FlagModel

            logger.info("Loading BGE-M3 model (first use may download ~2GB)...")
            kwargs: dict[str, Any] = {"use_fp16": False}
            if self._cache_dir:
                Path(self._cache_dir).mkdir(parents=True, exist_ok=True)
            self._model = BGEM3FlagModel(self._model_name, **kwargs)
            logger.info("BGE-M3 model loaded successfully")
        except ImportError:
            logger.warning(
                "FlagEmbedding not installed. Falling back to sentence-transformers."
            )
            self._load_sentence_transformers_fallback()

    def _load_sentence_transformers_fallback(self) -> None:
        """Fallback to sentence-transformers if FlagEmbedding isn't available."""
        from sentence_transformers import SentenceTransformer

        logger.info("Loading sentence-transformers model...")
        kwargs = {}
        if self._cache_dir:
            kwargs["cache_folder"] = self._cache_dir
        self._model = SentenceTransformer(self._model_name, **kwargs)
        logger.info("sentence-transformers model loaded")

    def embed_text(self, text: str) -> dict[str, Any]:
        """Embed a single text, returning dense and sparse vectors.

        Returns:
            {"dense": list[float], "sparse": dict[int, float]}
        """
        self._load_model()

        if hasattr(self._model, "encode") and hasattr(self._model, "model"):
            # FlagEmbedding BGEM3FlagModel
            result = self._model.encode(
                [text],
                return_dense=True,
                return_sparse=True,
            )
            dense = result["dense_vecs"][0].tolist()
            sparse = {}
            if "lexical_weights" in result:
                sparse = {int(k): float(v) for k, v in result["lexical_weights"][0].items()}
            return {"dense": dense, "sparse": sparse}
        else:
            # sentence-transformers fallback (dense only)
            vec = self._model.encode(text).tolist()
            # Pad or truncate to EMBEDDING_DIM
            if len(vec) < EMBEDDING_DIM:
                vec.extend([0.0] * (EMBEDDING_DIM - len(vec)))
            elif len(vec) > EMBEDDING_DIM:
                vec = vec[:EMBEDDING_DIM]
            return {"dense": vec, "sparse": {}}

    def embed_batch(self, texts: list[str]) -> list[dict[str, Any]]:
        """Embed a batch of texts for efficiency."""
        self._load_model()

        if hasattr(self._model, "encode") and hasattr(self._model, "model"):
            result = self._model.encode(
                texts,
                return_dense=True,
                return_sparse=True,
            )
            outputs = []
            for i in range(len(texts)):
                dense = result["dense_vecs"][i].tolist()
                sparse = {}
                if "lexical_weights" in result:
                    sparse = {
                        int(k): float(v)
                        for k, v in result["lexical_weights"][i].items()
                    }
                outputs.append({"dense": dense, "sparse": sparse})
            return outputs
        else:
            vecs = self._model.encode(texts).tolist()
            outputs = []
            for vec in vecs:
                if len(vec) < EMBEDDING_DIM:
                    vec.extend([0.0] * (EMBEDDING_DIM - len(vec)))
                elif len(vec) > EMBEDDING_DIM:
                    vec = vec[:EMBEDDING_DIM]
                outputs.append({"dense": vec, "sparse": {}})
            return outputs
