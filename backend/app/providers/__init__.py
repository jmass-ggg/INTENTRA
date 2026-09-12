"""Provider abstraction layer for Lucid Voice.

This package exposes env-selected factory functions that read
``app.config.settings`` and return the configured provider instance for each
capability (LLM, embeddings, STT, TTS).

Local-first by default: every factory defaults to an on-device provider so the
app survives airplane mode. Cloud providers are opt-in via env vars only.

Providers are constructed lazily and heavy/optional dependencies are imported
INSIDE provider methods, so importing this package (and ``app.main``) never
pulls in kuzu, sentence-transformers, TTS/coqui, faster-whisper or anthropic.
"""

from __future__ import annotations

from .llm import LLMProvider, LMStudioProvider, ClaudeProvider
from .embedding import EmbeddingProvider, LocalEmbeddingProvider
from .stt import STTProvider, WhisperLocalProvider, DeepgramProvider
from .tts import TTSProvider, XTTSProvider, ElevenLabsProvider

__all__ = [
    # base classes
    "LLMProvider",
    "EmbeddingProvider",
    "STTProvider",
    "TTSProvider",
    # concrete providers
    "LMStudioProvider",
    "ClaudeProvider",
    "LocalEmbeddingProvider",
    "WhisperLocalProvider",
    "DeepgramProvider",
    "XTTSProvider",
    "ElevenLabsProvider",
    # factories
    "get_llm_provider",
    "get_embedding_provider",
    "get_stt_provider",
    "get_tts_provider",
]


def _settings():
    """Lazily fetch the singleton settings object.

    Imported inside the factories so this package does not require config at
    import time and so tests can patch settings easily.
    """
    from app.config import settings

    return settings


def get_llm_provider() -> LLMProvider:
    """Return the configured LLM provider (default: local LM Studio)."""
    settings = _settings()
    provider = (getattr(settings, "llm_provider", None) or "lmstudio").lower()
    mapping = {
        "lmstudio": LMStudioProvider,
        "lm_studio": LMStudioProvider,
        "local": LMStudioProvider,
        "claude": ClaudeProvider,
        "anthropic": ClaudeProvider,
    }
    cls = mapping.get(provider, LMStudioProvider)
    return cls()


def get_embedding_provider() -> EmbeddingProvider:
    """Return the configured embedding provider (default: local)."""
    settings = _settings()
    provider = (getattr(settings, "embedding_provider", None) or "local").lower()
    mapping = {
        "local": LocalEmbeddingProvider,
        "sentence-transformers": LocalEmbeddingProvider,
        "sentence_transformers": LocalEmbeddingProvider,
    }
    cls = mapping.get(provider, LocalEmbeddingProvider)
    return cls()


def get_stt_provider() -> STTProvider:
    """Return the configured STT provider (default: local faster-whisper).

    Cloud Deepgram is opt-in via STT_PROVIDER=deepgram. If it is selected but no
    DEEPGRAM_API_KEY is configured, we fall back to local Whisper rather than
    returning empty transcripts — this keeps the offline/airplane path intact
    even when someone flips the provider env without supplying a key.
    """
    import logging

    settings = _settings()
    provider = (getattr(settings, "stt_provider", None) or "whisper").lower()
    mapping = {
        "whisper": WhisperLocalProvider,
        "whisper_local": WhisperLocalProvider,
        "faster-whisper": WhisperLocalProvider,
        "local": WhisperLocalProvider,
        "deepgram": DeepgramProvider,
    }
    cls = mapping.get(provider, WhisperLocalProvider)
    if cls is DeepgramProvider and not (getattr(settings, "deepgram_api_key", "") or "").strip():
        logging.getLogger("lucid_voice.stt").warning(
            "STT_PROVIDER=deepgram but DEEPGRAM_API_KEY is empty; "
            "falling back to local Whisper (offline)."
        )
        cls = WhisperLocalProvider
    return cls()


def get_tts_provider() -> TTSProvider:
    """Return the configured TTS provider (default: local XTTS-v2)."""
    settings = _settings()
    provider = (getattr(settings, "tts_provider", None) or "xtts").lower()
    mapping = {
        "xtts": XTTSProvider,
        "coqui": XTTSProvider,
        "local": XTTSProvider,
        "elevenlabs": ElevenLabsProvider,
        "eleven_labs": ElevenLabsProvider,
    }
    cls = mapping.get(provider, XTTSProvider)
    return cls()
