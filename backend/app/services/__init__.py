"""Service layer for Lucid Voice.

Re-exports the core services so callers can do::

    from app.services import GraphService, RetrievalService, ...

All heavy/optional dependencies (kuzu, sentence-transformers, TTS/coqui,
faster-whisper, anthropic) are LAZY-imported inside methods, never at module
top-level, so ``import app.services`` succeeds even when those packages are
not installed.
"""

from app.services.cache import CacheService
from app.services.generation import GenerationService
from app.services.graph import GraphService
from app.services.learning import LearningService
from app.services.retrieval import RetrievalService

__all__ = [
    "RetrievalService",
    "GenerationService",
    "GraphService",
    "LearningService",
    "CacheService",
]
