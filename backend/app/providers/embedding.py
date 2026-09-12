"""Embedding providers.

Default is a local sentence-transformers model. The model is loaded lazily on
first use so importing this module is cheap and dependency-free.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import numpy as np


class EmbeddingProvider(ABC):
    """Abstract base for text embedding models."""

    @abstractmethod
    def embed(self, text: str) -> list[float]:
        """Embed a single string into a vector of floats."""
        raise NotImplementedError

    @abstractmethod
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Embed a batch of strings into a list of vectors."""
        raise NotImplementedError

    @staticmethod
    def cosine_similarity(a, b) -> float:
        """Cosine similarity between two vectors (lists or arrays)."""
        va = np.asarray(a, dtype=np.float32)
        vb = np.asarray(b, dtype=np.float32)
        denom = float(np.linalg.norm(va) * np.linalg.norm(vb))
        if denom == 0.0:
            return 0.0
        return float(np.dot(va, vb) / denom)


# Process-wide cache of loaded SentenceTransformer models, keyed by model name.
# A model load is expensive (hundreds of MB), so seeding and retrieval share a
# single in-memory instance per model name across all provider instances.
_MODEL_CACHE: dict[str, object] = {}


def _load_model(model_name: str):
    """Load (or return the cached) SentenceTransformer for ``model_name``.

    LAZY-imports ``sentence-transformers`` so importing this module stays cheap.
    The loaded model is memoized module-wide so it behaves as a singleton.
    """
    model = _MODEL_CACHE.get(model_name)
    if model is None:
        from sentence_transformers import SentenceTransformer

        model = SentenceTransformer(model_name)
        _MODEL_CACHE[model_name] = model
    return model


class LocalEmbeddingProvider(EmbeddingProvider):
    """Local sentence-transformers embedding provider (DEFAULT).

    Defaults to BAAI/bge-small-en-v1.5 (384-dim). The underlying model is a
    process-wide singleton (see :func:`_load_model`), so constructing many
    providers never reloads the weights.
    """

    def __init__(self) -> None:
        from app.config import settings

        self.model_name: str = settings.embedding_model
        self._model = None  # resolved from the shared cache on first use

    def _ensure_model(self):
        if self._model is None:
            self._model = _load_model(self.model_name)
        return self._model

    def embed(self, text: str) -> list[float]:
        model = self._ensure_model()
        vec = model.encode(text, normalize_embeddings=True)
        return np.asarray(vec, dtype=np.float32).tolist()

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        model = self._ensure_model()
        vecs = model.encode(texts, normalize_embeddings=True)
        return np.asarray(vecs, dtype=np.float32).tolist()
