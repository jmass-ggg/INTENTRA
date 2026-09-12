"""Text-to-speech / voice-clone providers (Phase 4).

Default is local Coqui XTTS-v2 (the MAINTAINED idiap fork, PyPI ``coqui-tts``)
for zero-shot voice cloning from a reference wav. ElevenLabs is the cloud,
opt-in alternative / higher-quality option for the recorded demo.

On Apple Silicon XTTS runs on CPU (MPS is unreliable for XTTS); that is fine
because the demo audio is pre-rendered. The model is loaded once as a
process-wide singleton.

Heavy deps (``TTS``, ``torch``) are imported lazily inside methods so importing
this module stays cheap and dependency-free.
"""

from __future__ import annotations

import base64
import logging
import os
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path

import httpx

logger = logging.getLogger("lucid_voice.tts")


# --- voice reference storage -----------------------------------------------


def _voices_dir() -> Path:
    from app.config import settings

    d = Path(settings.voices_dir)
    d.mkdir(parents=True, exist_ok=True)
    return d


def voice_ref_path(person_id: str) -> str:
    """Path to a person's reference wav (may not exist yet)."""
    return str(_voices_dir() / f"{person_id}.wav")


def has_reference(person_id: str) -> bool:
    return Path(voice_ref_path(person_id)).exists()


def save_reference(person_id: str, audio_base64: str) -> str:
    """Decode base64 audio and store it as the person's reference wav.

    Returns the absolute path written.
    """
    raw = base64.b64decode(audio_base64)
    path = Path(voice_ref_path(person_id))
    path.write_bytes(raw)
    logger.info("saved voice reference for %r (%d bytes) -> %s", person_id, len(raw), path)
    return str(path)


# --- providers --------------------------------------------------------------


class TTSProvider(ABC):
    """Abstract base for text-to-speech / voice-clone engines."""

    @abstractmethod
    def synthesize(self, text: str, voice_ref: str | None) -> str:
        """Synthesize ``text`` (optionally cloning ``voice_ref``) -> base64 wav."""
        raise NotImplementedError


# Process-wide XTTS model singleton, keyed by model name (loading is expensive
# and downloads ~1.8GB on first use).
_XTTS_CACHE: dict[str, object] = {}


class XTTSProvider(TTSProvider):
    """Local Coqui XTTS-v2 provider (DEFAULT). Clones from a reference wav."""

    def __init__(self) -> None:
        from app.config import settings

        self.model_name: str = settings.xtts_model
        self.language: str = getattr(settings, "xtts_language", "en")
        self.device: str = "cpu"  # MPS is unreliable for XTTS on Apple Silicon

    def _ensure_model(self):
        model = _XTTS_CACHE.get(self.model_name)
        if model is None:
            # Accept the Coqui model license non-interactively.
            os.environ.setdefault("COQUI_TOS_AGREED", "1")
            from TTS.api import TTS  # LAZY heavy import

            import time as _t

            t0 = _t.time()
            model = TTS(self.model_name)
            try:
                model.to(self.device)
            except Exception:  # pragma: no cover - device move best-effort
                pass
            logger.info(
                "XTTS-v2 loaded on %s in %.1fs (model=%s)",
                self.device, _t.time() - t0, self.model_name,
            )
            _XTTS_CACHE[self.model_name] = model
        return model

    def synthesize(self, text: str, voice_ref: str | None) -> str:
        if not voice_ref or not Path(voice_ref).exists():
            raise RuntimeError(
                f"XTTS requires a voice reference; none found at {voice_ref!r}. Enroll first."
            )
        tts = self._ensure_model()
        import time as _t

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            out_path = tmp.name
        try:
            t0 = _t.time()
            tts.tts_to_file(
                text=text,
                speaker_wav=voice_ref,
                language=self.language,
                file_path=out_path,
            )
            logger.info("XTTS synth %.1fs (%d chars) on %s", _t.time() - t0, len(text), self.device)
            audio_bytes = Path(out_path).read_bytes()
        finally:
            try:
                os.unlink(out_path)
            except OSError:
                pass
        return base64.b64encode(audio_bytes).decode("ascii")


class ElevenLabsProvider(TTSProvider):
    """Cloud ElevenLabs provider (opt-in) — fallback / high-quality demo voice."""

    def __init__(self) -> None:
        from app.config import settings

        self.api_key: str | None = getattr(settings, "elevenlabs_api_key", None)
        self.voice_id: str | None = getattr(settings, "elevenlabs_voice_id", None)
        self.model: str = getattr(settings, "elevenlabs_model", "eleven_multilingual_v2")
        self.timeout: float = float(getattr(settings, "tts_timeout", 60.0))

    def synthesize(self, text: str, voice_ref: str | None) -> str:
        if not self.api_key:
            raise RuntimeError("ElevenLabs provider requires settings.elevenlabs_api_key")
        # ElevenLabs identifies voices by id (a cloned or preset voice), not a
        # local wav; prefer the configured voice id, fall back to voice_ref if it
        # looks like an id rather than a file path.
        voice = self.voice_id or (voice_ref if voice_ref and "/" not in voice_ref else None)
        if not voice:
            raise RuntimeError("ElevenLabs provider requires settings.elevenlabs_voice_id")
        url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice}"
        headers = {"xi-api-key": self.api_key, "Content-Type": "application/json"}
        payload = {"text": text, "model_id": self.model}
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(url, headers=headers, json=payload)
            resp.raise_for_status()
            audio_bytes = resp.content
        return base64.b64encode(audio_bytes).decode("ascii")
