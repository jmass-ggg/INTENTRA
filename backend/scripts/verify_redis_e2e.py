#!/usr/bin/env python3
"""End-to-end: the FULL pipeline running through local Redis (sponsor: Redis).

Runs the real FastAPI app (TestClient) with REDIS_ENABLED against a lock-free
COPY of the kuzu graph, so it does not disturb any already-running server.

Verifies, via the actual HTTP endpoints:
  * /health reports Redis available + RediSearch on.
  * /generate runs end-to-end and its trace shows vector_backend == "redis-knn"
    (the nearest-node lookup was served by Redis KNN).
  * /trace/latest is served from Redis (the key exists there).
  * /speak round-trips through the Redis audio cache (cached=True from Redis).
  * /confirm records the utterance in Redis agent memory.

Run from the backend dir:  .venv/bin/python scripts/verify_redis_e2e.py
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile

# --- configure env BEFORE importing app.config (settings read env at import) --
BACKEND = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
sys.path.insert(0, BACKEND)

SRC_DB = os.path.join(BACKEND, "data", "kuzu_db")
TMP_DB = tempfile.mkdtemp(prefix="lucid-e2e-kuzu-") + "/kuzu_db"
shutil.copytree(SRC_DB, TMP_DB)

os.environ["KUZU_DB_PATH"] = TMP_DB
os.environ["REDIS_ENABLED"] = "true"
os.environ["REDIS_URL"] = "redis://localhost:6379/0"
os.environ["REDIS_PREFIX"] = "lucide2e"  # isolated namespace; cleaned at the end
os.environ["DEMO_MODE"] = "false"

PASS, FAIL = "PASS", "FAIL"
_failures: list[str] = []


def check(name, ok, detail=""):
    print(f"  [{PASS if ok else FAIL}] {name}{(' — ' + detail) if detail else ''}")
    if not ok:
        _failures.append(name)


from fastapi.testclient import TestClient  # noqa: E402
import app.main as main  # noqa: E402
import redis as _redis  # noqa: E402

PERSON = "elena"
rcli = _redis.Redis.from_url("redis://localhost:6379/0", decode_responses=False)
client = TestClient(main.app, raise_server_exceptions=False)

print("E) Full pipeline through local Redis")

# 1) health
h = client.get("/health").json()
rstat = h.get("providers", {}).get("redis", {})
check("/health: Redis available", bool(rstat.get("available")), str(rstat))
check("/health: RediSearch on", bool(rstat.get("has_search")), str(rstat))

# 2) generate -> trace served by Redis KNN
gen = client.post("/generate", json={
    "person_id": PERSON,
    "fragments": ["water"],
    "context": "Sofia: Mom, do you want anything?",
}).json()
backend = (gen.get("trace") or {}).get("vector_backend")
nsub = len((gen.get("retrieval") or {}).get("subgraph_node_ids") or [])
check("/generate ran end-to-end (200, subgraph populated)", nsub > 0, f"{nsub} nodes")
check("vector retrieval served by Redis KNN", backend == "redis-knn", str(backend))

# 3) trace stored in Redis + read back via /trace/latest
trace_key_exists = rcli.exists(b"lucide2e:trace:latest") == 1
latest = client.get("/trace/latest").json()
check("latest_trace stored in Redis", trace_key_exists)
check("/trace/latest reads back the trace", bool(latest) and "vector_backend" in latest,
      f"backend={latest.get('vector_backend')}")

# 4) /speak round-trips through the Redis audio cache
text = "Yes please, some water."
cache = main.get_cache_service()
cache.put(PERSON, text, "QkFTRTY0QVVESU8=")  # prewarm (fake b64 audio)
cache_key = cache.key(PERSON, text)
in_redis = rcli.exists(f"lucide2e:tts:{cache_key}".encode()) == 1
spk = client.post("/speak", json={"person_id": PERSON, "text": text}).json()
check("audio cached in Redis after put", in_redis)
check("/speak returns cached=True from Redis", spk.get("cached") is True
      and spk.get("audio_base64") == "QkFTRTY0QVVESU8=")

# 5) /confirm records utterance in Redis agent memory
rcli.delete(b"lucide2e:confirmed:elena")
client.post("/confirm", json={"person_id": PERSON, "text": "I love you too.",
                              "context": "", "partner": "Sofia"})
recent = [v.decode() for v in rcli.lrange(b"lucide2e:confirmed:elena", 0, 5)]
check("/confirm stored utterance in Redis memory", "I love you too." in recent, str(recent))

# --- teardown: drop our index + keys, remove the temp DB copy ----------------
try:
    rs = main._get("redis")
    if rs is not None:
        rs.clear_index()
    cur = 0
    while True:
        cur, keys = rcli.scan(cur, match=b"lucide2e:*", count=500)
        if keys:
            rcli.delete(*keys)
        if cur == 0:
            break
except Exception as exc:
    print("  (teardown note:", exc, ")")
shutil.rmtree(os.path.dirname(TMP_DB), ignore_errors=True)

print()
if _failures:
    print(f"RESULT: FAIL ({len(_failures)} failed: {', '.join(_failures)})")
    sys.exit(1)
print("RESULT: PASS — full pipeline runs through local Redis (KNN + cache + memory).")
