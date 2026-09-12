"""CacheService — TTS audio cache (Phase 4; Redis-backed, sponsor: Redis).

Caches synthesized speech so repeated utterances are instant and work
offline. The cache key is a sha256 of ``person_id + text``.

Two tiers, both LOCAL:
  * On-disk files under ``settings.cache_dir`` — the durable, offline tier. The
    pre-rendered DEMO_MODE fixtures live here, so this tier always works in
    airplane mode.
  * Redis (when ``settings.redis_enabled`` and reachable) — a fast in-memory
    mirror in front of disk. On a Redis miss we fall back to disk and warm Redis;
    on a Redis outage everything still works from disk.

The actual audio synthesis is the TTS provider's job; this service only
stores/retrieves the base64 audio it is given.
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from app.config import settings

logger = logging.getLogger("lucid_voice.cache")


class CacheService:
    """Cache mapping (person_id, text) -> base64 audio, on disk + Redis mirror."""

    def __init__(self, cache_dir: str | None = None, redis_store=None) -> None:
        """Create the cache directory if needed.

        Args:
            cache_dir: Directory for cached audio. Defaults to
                ``settings.cache_dir``.
            redis_store: Optional RedisStore for the in-memory mirror tier.
                Defaults to the shared singleton; a no-op when Redis is off.
        """
        self.cache_dir = Path(cache_dir or settings.cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        if redis_store is None:
            try:
                from app.services.redis_store import get_redis_store

                redis_store = get_redis_store()
            except Exception:  # pragma: no cover - defensive
                redis_store = None
        self.redis = redis_store

    def key(self, person_id: str, text: str) -> str:
        """Return the cache key: sha256 hex of ``person_id + text``.

        Args:
            person_id: Owning person's id.
            text: The utterance text to be synthesized.

        Returns:
            A hex sha256 digest used as the cache filename stem.
        """
        digest = hashlib.sha256(f"{person_id}\x00{text}".encode("utf-8"))
        return digest.hexdigest()

    def _path(self, person_id: str, text: str) -> Path:
        """Return the on-disk path for a (person_id, text) cache entry."""
        return self.cache_dir / f"{self.key(person_id, text)}.b64"

    def _redis_ok(self) -> bool:
        return self.redis is not None and getattr(self.redis, "available", False)

    def get(self, person_id: str, text: str) -> str | None:
        """Return cached base64 audio for an utterance, or ``None`` on miss.

        Checks the Redis mirror first (when enabled), then on-disk. A disk hit
        warms Redis so the next request is served from memory.
        """
        key = self.key(person_id, text)

        if self._redis_ok():
            try:
                hit = self.redis.cache_get(key)
                if hit is not None:
                    return hit
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("redis cache get failed: %s", exc)

        path = self._path(person_id, text)
        if path.exists():
            audio_b64 = path.read_text(encoding="utf-8")
            if self._redis_ok():
                try:
                    self.redis.cache_put(key, audio_b64)  # warm the mirror
                except Exception:  # pragma: no cover - defensive
                    pass
            return audio_b64
        return None

    def put(self, person_id: str, text: str, audio_b64: str) -> str:
        """Store base64 audio for an utterance and return its cache key.

        Writes the durable on-disk copy AND the Redis mirror (when enabled).
        """
        key = self.key(person_id, text)
        path = self._path(person_id, text)
        path.write_text(audio_b64, encoding="utf-8")
        if self._redis_ok():
            try:
                self.redis.cache_put(key, audio_b64)
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("redis cache put failed: %s", exc)
        return key
