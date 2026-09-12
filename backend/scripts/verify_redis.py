#!/usr/bin/env python3
"""Verify the Redis Stack integration (sponsor: Redis) — beyond caching.

Run from the backend dir (Redis Stack must be running locally):
    .venv/bin/python scripts/verify_redis.py

Uses an ISOLATED Redis logical DB (db 15) and a test prefix so it never touches
real app data; it FLUSHDBs that database on exit.

Checks:
  A. VECTOR SEARCH parity — Redis FLAT/COSINE KNN returns the SAME nearest nodes
     (ids and order) as the in-process cosine, over many random queries.
  B. RetrievalService routing — uses Redis KNN when available (and the ids match
     in-process), falls back to in-process when no store / store unavailable.
  C. AUDIO CACHE — /speak-style cache round-trips through Redis; disk-hit warms
     Redis; with Redis off it still works from disk (fallback).
  D. AGENT MEMORY — latest_trace and recent confirmed utterances round-trip
     through Redis; a dead Redis URL degrades gracefully (available=False).

Exit code is non-zero if any check fails.
"""

from __future__ import annotations

import os
import sys
import tempfile

import numpy as np

sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

from app.config import settings  # noqa: E402

PASS, FAIL = "PASS", "FAIL"
_failures: list[str] = []
DIM = 384
# RediSearch only indexes db 0, so isolate via a dedicated key prefix instead
# (the real app uses prefix "lucid"); we delete only "lucidverify:*" on teardown.
TEST_URL = "redis://localhost:6379/0"


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  [{PASS if ok else FAIL}] {name}{(' — ' + detail) if detail else ''}")
    if not ok:
        _failures.append(name)


def inproc_topk(query, embs, k):
    def cos(a, b):
        d = float(np.linalg.norm(a) * np.linalg.norm(b))
        return 0.0 if d == 0 else float(np.dot(a, b) / d)
    scored = [(nid, max(0.0, cos(query, v))) for nid, v in embs.items()]
    scored.sort(key=lambda t: t[1], reverse=True)
    return scored[:k]


# Configure an isolated Redis for the whole script.
_orig = (settings.redis_enabled, settings.redis_url, settings.redis_prefix)
settings.redis_enabled = True
settings.redis_url = TEST_URL
settings.redis_prefix = "lucidverify"

from app.services.redis_store import RedisStore, reset_redis_store  # noqa: E402

store = RedisStore()
if not store.available:
    print("  [FAIL] Could not connect to local Redis at", TEST_URL)
    print("RESULT: FAIL — start Redis Stack (redis-stack-server) and re-run.")
    sys.exit(1)
if not store.has_search:
    print("  [FAIL] RediSearch module not loaded — need Redis STACK, not plain Redis.")
    sys.exit(1)
store.clear_index()  # fresh index

PERSON = "elena:demo"  # contains a colon to exercise TAG escaping
rng = np.random.default_rng(7)
nodes = [
    {"id": f"{PERSON}:n{i}", "embedding": rng.standard_normal(DIM).astype(np.float32)}
    for i in range(60)
]
embs = {n["id"]: n["embedding"] for n in nodes}

# ---------------------------------------------------------------------------
print("A) Vector search parity (Redis FLAT/COSINE KNN == in-process cosine)")
ok_sync = store.sync_person(PERSON, nodes)
check("sync_person indexed the node embeddings", ok_sync)

K = 8
matches, total = 0, 0
worst = ""
for t in range(25):
    q = rng.standard_normal(DIM).astype(np.float32)
    redis_ids = [nid for nid, _ in (store.knn(PERSON, q, K) or [])]
    inproc_ids = [nid for nid, _ in inproc_topk(q, embs, K)]
    total += 1
    if redis_ids == inproc_ids:
        matches += 1
    elif not worst:
        worst = f"redis={redis_ids[:3]}... vs inproc={inproc_ids[:3]}..."
check(f"top-{K} ids+order identical across {total} random queries",
      matches == total, f"{matches}/{total} matched" + (f"; {worst}" if worst else ""))

# Similarity values also align with cosine (sim = 1 - distance).
q = rng.standard_normal(DIM).astype(np.float32)
redis_hits = store.knn(PERSON, q, K) or []
inproc_hits = dict(inproc_topk(q, embs, K))
sim_ok = bool(redis_hits) and all(
    abs(sim - inproc_hits.get(nid, -9)) < 1e-3 for nid, sim in redis_hits
)
check("returned similarities match cosine (within 1e-3)", sim_ok, f"{len(redis_hits)} hits")

# TAG isolation: a different person's query must not return this person's nodes.
other_nodes = [{"id": "mateo:demo:x", "embedding": rng.standard_normal(DIM).astype(np.float32)}]
store.sync_person("mateo:demo", other_nodes)
cross = store.knn("mateo:demo", q, K) or []
check("person TAG filter isolates KNN (no cross-person leak)",
      all(nid.startswith("mateo:demo") for nid, _ in cross), str([n for n, _ in cross]))

# ---------------------------------------------------------------------------
print("B) RetrievalService vector routing + fallback")
from app.services.retrieval import RetrievalService  # noqa: E402

svc = RetrievalService(graph=None, llm=None, embedding=None, redis_store=store)
q = rng.standard_normal(DIM).astype(np.float32)
backed = [nid for nid, _ in svc.vector_retrieve_backed(PERSON, q, embs, K, pnode_list=nodes)]
inproc = [nid for nid, _ in inproc_topk(q, embs, K)]
check("vector_retrieve_backed uses Redis when available", svc.last_vector_backend == "redis-knn",
      svc.last_vector_backend)
check("Redis-backed ids match in-process", backed == inproc)

svc_no = RetrievalService(graph=None, llm=None, embedding=None, redis_store=None)
backed_no = [nid for nid, _ in svc_no.vector_retrieve_backed(PERSON, q, embs, K)]
check("falls back to in-process with no store", svc_no.last_vector_backend == "in-process")
check("fallback ids also correct", backed_no == inproc)

# ---------------------------------------------------------------------------
print("C) Audio cache round-trip (Redis mirror + disk fallback)")
from app.services.cache import CacheService  # noqa: E402

tmpdir = tempfile.mkdtemp(prefix="lucid-cache-")
cache = CacheService(cache_dir=tmpdir, redis_store=store)
key = cache.put("elena", "I would like some water please", "QUJDREVG=")  # fake b64
got = cache.get("elena", "I would like some water please")
check("put then get returns the audio", got == "QUJDREVG=")
check("value is actually stored in Redis", store.cache_get(key) == "QUJDREVG=")
check("value is also on disk (durable/offline tier)",
      (os.path.exists(os.path.join(tmpdir, key + ".b64"))))

# disk-hit warms redis: delete redis copy, get() should re-warm from disk.
store._client.delete(f"{store.prefix}:tts:{key}")
got2 = cache.get("elena", "I would like some water please")
check("disk hit re-warms the Redis mirror",
      got2 == "QUJDREVG=" and store.cache_get(key) == "QUJDREVG=")

# fallback: cache with Redis OFF still works from disk.
off_store = type("Off", (), {"available": False})()
cache_off = CacheService(cache_dir=tmpdir, redis_store=off_store)
check("cache works with Redis off (disk only)",
      cache_off.get("elena", "I would like some water please") == "QUJDREVG=")

# ---------------------------------------------------------------------------
print("D) Agent / session memory")
trace = {"confidence": 0.81, "candidates": [{"text": "Yes please."}],
         "latency_ms": 1234, "ts": __import__("datetime").datetime.now()}  # datetime -> default=str
check("set_latest_trace ok", store.set_latest_trace(trace))
rt = store.get_latest_trace()
check("get_latest_trace round-trips", rt is not None and rt.get("confidence") == 0.81,
      str(rt)[:60] if rt else "None")

store._client.delete(f"{store.prefix}:confirmed:elena")
store.push_confirmed("elena", "I love you too.")
store.push_confirmed("elena", "Maybe later.")
recent = store.recent_confirmed("elena", 5)
check("recent confirmed utterances stored newest-first",
      recent[:2] == ["Maybe later.", "I love you too."], str(recent))

# dead Redis -> graceful degrade
settings.redis_url = "redis://localhost:6399/0"  # nothing listening
dead = RedisStore()
check("dead Redis URL degrades gracefully (available=False)", dead.available is False)
check("dead store knn returns None (fallback signal)", dead.knn("x", q, K) is None)

# ---------------------------------------------------------------------------
# teardown — only remove our own "lucidverify:*" keys + index (leave real data).
try:
    settings.redis_url = TEST_URL  # dead-redis test above repointed it
    tstore = RedisStore()
    tstore.clear_index()  # FT.DROPINDEX ... DD removes the node hashes too
    cur = 0
    while True:
        cur, keys = tstore._client.scan(cur, match=b"lucidverify:*", count=500)
        if keys:
            tstore._client.delete(*keys)
        if cur == 0:
            break
except Exception as exc:
    print("  (teardown note:", exc, ")")
settings.redis_enabled, settings.redis_url, settings.redis_prefix = _orig
reset_redis_store()

print()
if _failures:
    print(f"RESULT: FAIL ({len(_failures)} failed: {', '.join(_failures)})")
    sys.exit(1)
print("RESULT: PASS — Redis vector KNN matches in-process; cache + memory + fallback verified.")
