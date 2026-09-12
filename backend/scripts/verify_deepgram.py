#!/usr/bin/env python3
"""Verify the Deepgram STT integration (sponsor: Deepgram).

Run from the backend dir:  .venv/bin/python scripts/verify_deepgram.py

Checks, in order:
  1. Provider factory selection:
       - STT_PROVIDER=local            -> WhisperLocalProvider
       - STT_PROVIDER=deepgram + key   -> DeepgramProvider
       - STT_PROVIDER=deepgram, NO key -> WhisperLocalProvider (offline fallback)
  2. DeepgramProvider.transcribe builds a correct /v1/listen request and parses
     a real-shaped Deepgram response (httpx is intercepted, no network needed).
  3. If DEEPGRAM_API_KEY is set in the environment, a LIVE call is made against a
     freshly-synthesized demo line and the transcript is printed (judge demo).

Exit code is non-zero if any non-live check fails.
"""

from __future__ import annotations

import base64
import os
import sys

# Make `app` importable when run from the backend directory.
sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

from app.config import settings  # noqa: E402
from app.providers import get_stt_provider  # noqa: E402
from app.providers.stt import DeepgramProvider, WhisperLocalProvider  # noqa: E402
import app.providers.stt as stt_mod  # noqa: E402

DEMO_LINE = "I would like some water please"
PASS, FAIL = "PASS", "FAIL"
_failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  [{PASS if ok else FAIL}] {name}{(' — ' + detail) if detail else ''}")
    if not ok:
        _failures.append(name)


# ---------------------------------------------------------------------------
# 1) Factory selection + offline fallback
# ---------------------------------------------------------------------------
print("1) Provider factory selection")
orig_provider, orig_key = settings.stt_provider, settings.deepgram_api_key
try:
    settings.stt_provider, settings.deepgram_api_key = "local", ""
    check("STT_PROVIDER=local -> Whisper",
          isinstance(get_stt_provider(), WhisperLocalProvider))

    settings.stt_provider, settings.deepgram_api_key = "deepgram", "dummy-key-123"
    check("STT_PROVIDER=deepgram + key -> Deepgram",
          isinstance(get_stt_provider(), DeepgramProvider))

    settings.stt_provider, settings.deepgram_api_key = "deepgram", ""
    p = get_stt_provider()
    check("STT_PROVIDER=deepgram + NO key -> Whisper (offline fallback)",
          isinstance(p, WhisperLocalProvider), type(p).__name__)
finally:
    settings.stt_provider, settings.deepgram_api_key = orig_provider, orig_key


# ---------------------------------------------------------------------------
# 2) Real request construction + response parse (httpx intercepted)
# ---------------------------------------------------------------------------
print("2) Deepgram request shape + response parse (mocked transport)")

captured: dict = {}

# A real-shaped Deepgram pre-recorded response.
DG_RESPONSE = {
    "metadata": {"model_info": {"name": "nova-2"}},
    "results": {
        "channels": [
            {"alternatives": [{"transcript": DEMO_LINE, "confidence": 0.998}]}
        ]
    },
}


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


class _FakeClient:
    def __init__(self, *a, **kw):
        captured["timeout"] = kw.get("timeout")

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def post(self, url, headers=None, params=None, content=None):
        captured.update(url=url, headers=headers, params=params, content=content)
        return _FakeResp(DG_RESPONSE)


_orig_client = stt_mod.httpx.Client
stt_mod.httpx.Client = _FakeClient  # type: ignore[assignment]
try:
    settings.deepgram_api_key = "dummy-key-123"
    prov = DeepgramProvider()
    audio_b64 = base64.b64encode(b"\x1aE\xdf\xa3fake-webm-bytes").decode()
    text = prov.transcribe(audio_b64)

    check("hits the real Deepgram endpoint",
          captured.get("url") == "https://api.deepgram.com/v1/listen",
          captured.get("url", ""))
    check("Authorization: Token <key> header",
          (captured.get("headers") or {}).get("Authorization") == "Token dummy-key-123")
    check("sends model + smart_format params",
          (captured.get("params") or {}).get("model") == "nova-2"
          and (captured.get("params") or {}).get("smart_format") == "true",
          str(captured.get("params")))
    check("posts the decoded audio bytes (not base64)",
          captured.get("content") == base64.b64decode(audio_b64))
    check("parses transcript from Deepgram response",
          text == DEMO_LINE, repr(text))
finally:
    stt_mod.httpx.Client = _orig_client  # type: ignore[assignment]
    settings.deepgram_api_key = orig_key


# ---------------------------------------------------------------------------
# 3) LIVE call (only if a real key is present in the environment)
# ---------------------------------------------------------------------------
print("3) Live Deepgram call")
live_key = os.environ.get("DEEPGRAM_API_KEY", "").strip()
if not live_key:
    print("  [SKIP] DEEPGRAM_API_KEY not set — set it and re-run to hit the live API.")
else:
    import subprocess
    import tempfile

    # Synthesize the demo line locally (macOS `say`) into a wav Deepgram accepts.
    aiff = tempfile.NamedTemporaryFile(suffix=".aiff", delete=False).name
    wav = tempfile.NamedTemporaryFile(suffix=".wav", delete=False).name
    subprocess.run(["say", "-o", aiff, DEMO_LINE], check=True)
    subprocess.run(["afconvert", "-f", "WAVE", "-d", "LEI16@16000", aiff, wav], check=True)
    with open(wav, "rb") as fh:
        live_b64 = base64.b64encode(fh.read()).decode()
    settings.deepgram_api_key = live_key
    settings.stt_provider = "deepgram"
    try:
        transcript = DeepgramProvider().transcribe(live_b64)
        print(f"  expected ~ {DEMO_LINE!r}")
        print(f"  Deepgram returned: {transcript!r}")
        good = bool(transcript) and "water" in transcript.lower()
        check("live transcript is non-empty and on-topic", good)
    finally:
        settings.deepgram_api_key = orig_key
        settings.stt_provider = orig_provider
        for f in (aiff, wav):
            try:
                os.unlink(f)
            except OSError:
                pass

print()
if _failures:
    print(f"RESULT: FAIL ({len(_failures)} check(s) failed: {', '.join(_failures)})")
    sys.exit(1)
print("RESULT: PASS — Deepgram integration verified (live path runs when a key is set).")
