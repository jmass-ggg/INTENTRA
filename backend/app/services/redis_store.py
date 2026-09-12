"""RedisStore — on-device agent memory + vector search (sponsor: Redis).

Backs three capabilities with a LOCAL Redis Stack (RediSearch) instance, each
selected by ``settings.redis_enabled`` and each with a transparent fallback so
nothing breaks when Redis is off or unreachable (airplane mode stays intact):

  a. VECTOR SEARCH — node embeddings are indexed in a Redis FLAT vector index
     (COSINE). The retrieval step's nearest-node lookup is served by Redis KNN.
     FLAT (brute force) + COSINE makes the result set identical to the in-process
     cosine ranking — this is real vector search, not a cache.
  b. AUDIO CACHE — the /speak base64-audio cache is mirrored into Redis.
  c. AGENT MEMORY — the latest /generate trace and recent confirmed utterances
     are stored in Redis (session memory the laptop view / agent can read back).

``redis`` is imported lazily. Any connection/command failure flips
``available`` off (or returns a sentinel) so callers degrade gracefully.

Keys (namespaced by ``settings.redis_prefix``, default "lucid"):
    {prefix}:node:{node_id}        HASH  {person: TAG, vector: FLOAT32[dim]}
    {prefix}:nodes:idx             RediSearch index over {prefix}:node:*
    {prefix}:tts:{sha}             STRING base64 audio
    {prefix}:trace:latest          STRING json trace
    {prefix}:confirmed:{person}    LIST   recent confirmed utterances
"""

from __future__ import annotations

import json
import logging
from typing import Any

import numpy as np

logger = logging.getLogger("lucid_voice.redis")

# Must match GraphService.EMB_DIM / the embedding model (bge-small -> 384).
EMB_DIM = 384

# RediSearch TAG special characters that must be escaped inside a {tag} filter.
_TAG_SPECIAL = set(r"""\,.<>{}[]"':;!@#$%^&*()-+=~ /""")


def _escape_tag(value: str) -> str:
    """Escape a value for use inside a RediSearch TAG filter ``@field:{value}``."""
    return "".join(("\\" + ch) if ch in _TAG_SPECIAL else ch for ch in str(value))


class RedisStore:
    """Local Redis Stack layer (vector KNN + audio cache + agent memory)."""

    def __init__(self, dim: int = EMB_DIM) -> None:
        from app.config import settings

        self.enabled: bool = bool(getattr(settings, "redis_enabled", False))
        self.url: str = getattr(settings, "redis_url", "redis://localhost:6379/0")
        self.prefix: str = getattr(settings, "redis_prefix", "lucid")
        self.timeout: float = float(getattr(settings, "redis_socket_timeout", 0.5))
        self.dim: int = int(dim)

        self._client: Any = None
        self.available: bool = False
        self.has_search: bool = False
        self._index_ready: bool = False
        self.index_name: str = f"{self.prefix}:nodes:idx"
        self._node_prefix: str = f"{self.prefix}:node:"

        if self.enabled:
            self._connect()

    # --- connection ---------------------------------------------------------

    def _connect(self) -> None:
        try:
            import redis  # lazy

            client = redis.Redis.from_url(
                self.url,
                socket_timeout=self.timeout,
                socket_connect_timeout=self.timeout,
                decode_responses=False,
            )
            client.ping()
            self._client = client
            self.available = True
            self.has_search = self._check_search()
            logger.info(
                "Redis connected at %s (RediSearch=%s).", self.url, self.has_search
            )
        except Exception as exc:
            logger.warning(
                "Redis unavailable (%s); falling back to in-process/on-disk.", exc
            )
            self._client = None
            self.available = False

    def _check_search(self) -> bool:
        try:
            self._client.execute_command("FT._LIST")
            return True
        except Exception:
            logger.warning("RediSearch module not loaded; vector KNN disabled.")
            return False

    def status(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "available": self.available,
            "has_search": self.has_search,
            "url": self.url,
        }

    # --- (a) vector search --------------------------------------------------

    def _ensure_index(self) -> bool:
        """Create the FLAT/COSINE vector index if it does not exist."""
        if self._index_ready:
            return True
        if not (self.available and self.has_search):
            return False
        try:
            self._client.execute_command(
                "FT.CREATE", self.index_name,
                "ON", "HASH",
                "PREFIX", "1", self._node_prefix,
                "SCHEMA",
                "person", "TAG",
                "vector", "VECTOR", "FLAT", "6",
                "TYPE", "FLOAT32",
                "DIM", str(self.dim),
                "DISTANCE_METRIC", "COSINE",
            )
            self._index_ready = True
        except Exception as exc:
            # Already-exists is the common, benign case.
            if "Index already exists" in str(exc):
                self._index_ready = True
            else:
                logger.warning("FT.CREATE failed: %s", exc)
                return False
        return self._index_ready

    def sync_person(self, person_id: str, nodes: list[dict[str, Any]]) -> bool:
        """Upsert a person's node embeddings into the Redis vector index.

        ``nodes`` is a list of dicts with at least ``id`` and ``embedding``.
        Idempotent; cheap for the small per-person graphs here. Returns False if
        the index/connection is unavailable (caller falls back).
        """
        if not self._ensure_index():
            return False
        try:
            pipe = self._client.pipeline(transaction=False)
            person_b = str(person_id).encode("utf-8")
            for n in nodes:
                vec = np.asarray(n["embedding"], dtype=np.float32)
                if vec.size != self.dim:
                    continue
                key = self._node_prefix + str(n["id"])
                pipe.hset(key, mapping={b"person": person_b, b"vector": vec.tobytes()})
            pipe.execute()
            return True
        except Exception as exc:
            logger.warning("Redis sync_person failed: %s", exc)
            return False

    def knn(
        self, person_id: str, query_emb: np.ndarray, top_n: int
    ) -> list[tuple[str, float]] | None:
        """Top-N (node_id, cosine_similarity) for a person via Redis KNN.

        Returns None on any failure so the caller can fall back to in-process
        cosine. FLAT + COSINE => identical nearest-node ordering to in-process.
        """
        if not (self.available and self.has_search and self._index_ready):
            return None
        try:
            vec = np.asarray(query_emb, dtype=np.float32).tobytes()
            tag = _escape_tag(person_id)
            q = f"(@person:{{{tag}}})=>[KNN {int(top_n)} @vector $vec AS score]"
            raw = self._client.execute_command(
                "FT.SEARCH", self.index_name, q,
                "PARAMS", "2", "vec", vec,
                "SORTBY", "score",
                "RETURN", "1", "score",
                "DIALECT", "2",
                "LIMIT", "0", str(int(top_n)),
            )
            return self._parse_knn(raw)
        except Exception as exc:
            logger.warning("Redis KNN failed: %s", exc)
            return None

    def _parse_knn(self, raw: list) -> list[tuple[str, float]]:
        """Parse FT.SEARCH RESP2 reply -> [(node_id, similarity)] (sim = 1 - dist)."""
        out: list[tuple[str, float]] = []
        if not raw:
            return out
        # raw = [total, key1, [f1, v1, ...], key2, [...], ...]
        i = 1
        plen = len(self._node_prefix)
        while i < len(raw):
            key = raw[i]
            fields = raw[i + 1] if i + 1 < len(raw) else []
            i += 2
            key_s = key.decode("utf-8") if isinstance(key, (bytes, bytearray)) else str(key)
            node_id = key_s[plen:] if key_s.startswith(self._node_prefix) else key_s
            dist = 0.0
            for j in range(0, len(fields) - 1, 2):
                fname = fields[j]
                fname_s = fname.decode() if isinstance(fname, (bytes, bytearray)) else str(fname)
                if fname_s == "score":
                    fval = fields[j + 1]
                    fval_s = fval.decode() if isinstance(fval, (bytes, bytearray)) else str(fval)
                    dist = float(fval_s)
            out.append((node_id, max(0.0, 1.0 - dist)))
        return out

    def clear_index(self) -> None:
        """Drop the index AND its node hashes (used by verification/teardown)."""
        if not self.available:
            return
        try:
            if self.has_search:
                self._client.execute_command("FT.DROPINDEX", self.index_name, "DD")
        except Exception:
            pass
        self._index_ready = False

    # --- (b) audio cache ----------------------------------------------------

    def cache_get(self, key: str) -> str | None:
        if not self.available:
            return None
        try:
            v = self._client.get(f"{self.prefix}:tts:{key}")
            return v.decode("utf-8") if v is not None else None
        except Exception as exc:
            logger.warning("Redis cache_get failed: %s", exc)
            return None

    def cache_put(self, key: str, audio_b64: str) -> bool:
        if not self.available:
            return False
        try:
            self._client.set(f"{self.prefix}:tts:{key}", audio_b64.encode("utf-8"))
            return True
        except Exception as exc:
            logger.warning("Redis cache_put failed: %s", exc)
            return False

    # --- (c) agent / session memory ----------------------------------------

    def set_latest_trace(self, trace: dict) -> bool:
        if not self.available:
            return False
        try:
            blob = json.dumps(trace, default=str).encode("utf-8")
            self._client.set(f"{self.prefix}:trace:latest", blob)
            return True
        except Exception as exc:
            logger.warning("Redis set_latest_trace failed: %s", exc)
            return False

    def get_latest_trace(self) -> dict | None:
        if not self.available:
            return None
        try:
            v = self._client.get(f"{self.prefix}:trace:latest")
            return json.loads(v) if v is not None else None
        except Exception as exc:
            logger.warning("Redis get_latest_trace failed: %s", exc)
            return None

    def push_confirmed(self, person_id: str, text: str, keep: int = 50) -> bool:
        if not self.available or not text:
            return False
        try:
            k = f"{self.prefix}:confirmed:{person_id}"
            self._client.lpush(k, text.encode("utf-8"))
            self._client.ltrim(k, 0, keep - 1)
            return True
        except Exception as exc:
            logger.warning("Redis push_confirmed failed: %s", exc)
            return False

    def recent_confirmed(self, person_id: str, n: int = 10) -> list[str]:
        if not self.available:
            return []
        try:
            vals = self._client.lrange(f"{self.prefix}:confirmed:{person_id}", 0, n - 1)
            return [v.decode("utf-8") for v in vals]
        except Exception as exc:
            logger.warning("Redis recent_confirmed failed: %s", exc)
            return []


# Module-level singleton (mirrors the provider/service pattern in main.py).
_store: RedisStore | None = None


def get_redis_store() -> RedisStore:
    """Return the shared RedisStore (constructed once from settings)."""
    global _store
    if _store is None:
        _store = RedisStore()
    return _store


def reset_redis_store() -> None:
    """Drop the cached singleton (used by tests/verification after env changes)."""
    global _store
    _store = None
