"""Pre-render the demo's chosen spoken lines into the audio cache (Phase 4).

For a given person + voice reference, synthesizes the exact fixture lines (the
chosen candidate for each demo input) and writes them into the TTS cache, so
DEMO_MODE /speak serves them instantly and offline.

Usage (from the backend directory):

    python -m data.prerender_demo [person_id] [path-to-reference-wav]

If a reference wav is given it is enrolled first. The spoken lines come from the
"speak" map in data/demo_fixtures.json.
"""

from __future__ import annotations

import base64
import json
import sys
from pathlib import Path


def _demo_lines() -> list[str]:
    from app.config import settings

    data = json.loads(Path(settings.demo_fixtures_path).read_text(encoding="utf-8"))
    speak = data.get("speak", {})
    return [v for k, v in speak.items() if k != "_comment" and isinstance(v, str)]


def prerender(person_id: str = "elena", reference: str | None = None) -> list[tuple[str, str]]:
    """Synthesize + cache each demo line for ``person_id``. Returns (line, status)."""
    from app.services.cache import CacheService
    from app.providers import get_tts_provider
    from app.providers.tts import save_reference, voice_ref_path

    if reference:
        with open(reference, "rb") as f:
            save_reference(person_id, base64.b64encode(f.read()).decode("ascii"))

    cache = CacheService()
    provider = get_tts_provider()
    ref = voice_ref_path(person_id)

    results: list[tuple[str, str]] = []
    for line in _demo_lines():
        if cache.get(person_id, line) is not None:
            results.append((line, "already-cached"))
            continue
        audio_b64 = provider.synthesize(line, ref)
        cache.put(person_id, line, audio_b64)
        results.append((line, "rendered"))
    return results


def main(argv: list[str]) -> int:
    person_id = argv[1] if len(argv) > 1 else "elena"
    reference = argv[2] if len(argv) > 2 else None

    results = prerender(person_id, reference)
    from app.services.cache import CacheService

    cache = CacheService()
    print(f"prerender_demo: person={person_id!r}")
    for line, status in results:
        print(f"  [{status}] {line!r}")
    print("cache verification:")
    all_hit = True
    for line in _demo_lines():
        hit = cache.get(person_id, line) is not None
        all_hit = all_hit and hit
        print(f"  {'HIT ' if hit else 'MISS'} {line!r}")
    print("ALL 3 DEMO LINES CACHED" if all_hit else "SOME DEMO LINES MISSING")
    return 0 if all_hit else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
