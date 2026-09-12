"""Application settings for Lucid Voice.

Loads configuration from environment variables / a `.env` file using
pydantic-settings. All defaults are local-first so the app survives airplane
mode; cloud providers are opt-in via env vars only.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed application settings. Env names are read case-insensitively."""

    # --- Provider selection ---
    llm_provider: str = "lmstudio"
    embedding_provider: str = "local"
    stt_provider: str = "whisper"
    tts_provider: str = "xtts"

    # --- Mode ---
    demo_mode: bool = False

    # --- LM Studio (local LLM) ---
    lm_studio_base_url: str = "http://localhost:1234/v1"
    lm_studio_model: str = "local-model"
    lm_studio_api_key: str = "not-needed"
    llm_timeout: float = 120.0
    # Reasoning control. Gemma-4 ignores the Qwen-style enable_thinking/no_think
    # flags but honors OpenAI's reasoning_effort: "none" fully disables its
    # chain-of-thought (~24s -> ~3s per call with valid output). Set to "low"/
    # "medium"/"high" to trade latency for more deliberation, or "" to omit.
    lm_studio_reasoning_effort: str = "none"
    # Optional hard cap on generated tokens (0 = omit). With reasoning off the
    # answer is small; a cap is a backstop, not the primary lever.
    lm_studio_max_tokens: int = 0

    # --- Cloud (opt-in) ---
    claude_model: str = "claude-sonnet-4-6"
    anthropic_api_key: str = ""
    deepgram_api_key: str = ""
    elevenlabs_api_key: str = ""

    # --- Sentry (error monitoring; opt-in, offline-safe) ---
    # When sentry_dsn is empty, Sentry initialization is a clean no-op so the app
    # runs fully offline. Set SENTRY_DSN to enable error + performance capture.
    sentry_dsn: str = ""
    sentry_traces_sample_rate: float = 1.0
    sentry_environment: str = "development"

    # --- Redis Stack (on-device agent memory + vector search; opt-in) ---
    # LOCAL Redis Stack (RediSearch) backs vector KNN retrieval, the TTS audio
    # cache, and session/agent memory. When redis_enabled is False OR Redis is
    # unreachable, every consumer falls back to the in-process / on-disk path, so
    # airplane mode is never broken. Keep the URL pointed at a LOCAL server.
    redis_enabled: bool = False
    redis_url: str = "redis://localhost:6379/0"
    redis_prefix: str = "lucid"
    redis_socket_timeout: float = 0.5  # fast-fail so fallback is snappy

    # --- Arize Phoenix (LLM tracing/eval; runs LOCALLY, opt-in) ---
    # When phoenix_enabled is False the tracing helpers are no-ops, so the app
    # has no cloud dependency. Phoenix is open-source and runs on-device; point
    # the collector at a local Phoenix instance (default port 6006).
    phoenix_enabled: bool = False
    phoenix_collector_endpoint: str = "http://localhost:6006/v1/traces"
    phoenix_project_name: str = "lucid-voice"

    # --- Local models ---
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    whisper_model: str = "small.en"
    xtts_model: str = "tts_models/multilingual/multi-dataset/xtts_v2"

    # --- STT knobs ---
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"
    whisper_beam_size: int = 5
    whisper_language: str = "en"
    deepgram_model: str = "nova-2"
    stt_timeout: float = 60.0

    # --- TTS knobs ---
    xtts_language: str = "en"
    tts_timeout: float = 60.0
    elevenlabs_voice_id: str = ""
    elevenlabs_model: str = "eleven_multilingual_v2"

    # --- Paths ---
    kuzu_db_path: str = "./data/kuzu_db"
    data_dir: str = "./data"
    cache_dir: str = "./data/cache"
    voices_dir: str = "./data/voices"
    styles_dir: str = "./data/styles"
    demo_fixtures_path: str = "./data/demo_fixtures.json"

    # --- Retrieval ---
    retrieval_hops: int = 2
    retrieval_top_k: int = 8
    confidence_threshold: float = 0.35

    # --- Context selection (submodular facility-location vs plain top-k) ---
    selection_mode: str = "submodular"  # "submodular" | "topk"
    context_budget: int = 8             # max facts (cardinality budget B)
    context_lambda: float = 2.0         # relevance weight in f(S)

    # --- Ranking weights ---
    rank_alpha: float = 0.4  # graph_proximity
    rank_beta: float = 0.3  # edge_weight
    rank_gamma: float = 0.2  # recency
    rank_delta: float = 0.3  # semantic_sim

    # --- Decay ---
    decay_factor: float = 0.98

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


# Module-level singleton.
settings = Settings()


def get_settings() -> Settings:
    """Return the shared Settings singleton."""
    return settings
