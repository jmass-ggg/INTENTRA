"""Speech-to-text providers (Phase 7).

Default is local faster-whisper (``small.en``, CPU, int8). Browser MediaRecorder
audio is typically webm/opus, so incoming bytes are decoded to 16 kHz mono
float32 PCM with ffmpeg before transcription. Deepgram is the cloud, opt-in
alternative (env STT_PROVIDER=deepgram).

The Whisper model is loaded once as a process-wide singleton. ``faster_whisper``
is LAZY-imported so importing this module stays cheap.
"""

from __future__ import annotations

import base64
import logging
import os
import shutil
import subprocess
import tempfile
from abc import ABC, abstractmethod

import httpx
import numpy as np

logger = logging.getLogger("lucid_voice.stt")


def _ffmpeg() -> str:
    return shutil.which("ffmpeg") or "ffmpeg"


def decode_to_pcm(audio_bytes: bytes) -> np.ndarray | None:
    """Decode arbitrary encoded audio (webm/opus, wav, m4a, ...) to a 16 kHz
    mono float32 numpy array via ffmpeg. Returns None on empty/failed input.
    """
    if not audio_bytes:
        return None
    tmp_path = None
    try:
        # A seekable temp file is most robust for container formats (webm).
        with tempfile.NamedTemporaryFile(delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = tmp.name
        proc = subprocess.run(
            [_ffmpeg(), "-v", "error", "-i", tmp_path,
             "-f", "f32le", "-ac", "1", "-ar", "16000", "pipe:1"],
            capture_output=True,
        )
        if proc.returncode != 0 or not proc.stdout:
            logger.warning("ffmpeg decode failed (rc=%s): %s",
                           proc.returncode, proc.stderr.decode("utf-8", "ignore")[:200])
            return None
        audio = np.frombuffer(proc.stdout, dtype=np.float32).copy()
        return audio if audio.size else None
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("audio decode error: %s", exc)
        return None
    finally:
        if tmp_path and os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:
                pass


class STTProvider(ABC):
    """Abstract base for speech-to-text engines."""

    @abstractmethod
    def transcribe(self, audio_b64: str) -> str:
        """Transcribe base64-encoded audio bytes into text (never raises)."""
        raise NotImplementedError


# Process-wide faster-whisper model singleton, keyed by (name, device, compute).
_WHISPER_CACHE: dict[tuple[str, str, str], object] = {}


class WhisperLocalProvider(STTProvider):
    """Local faster-whisper provider (DEFAULT)."""

    def __init__(self) -> None:
        from app.config import settings

        self.model_name: str = settings.whisper_model
        self.device: str = getattr(settings, "whisper_device", "cpu")
        self.compute_type: str = getattr(settings, "whisper_compute_type", "int8")
        self.beam_size: int = int(getattr(settings, "whisper_beam_size", 5))
        self.language: str = getattr(settings, "whisper_language", "en")

    def _ensure_model(self):
        key = (self.model_name, self.device, self.compute_type)
        model = _WHISPER_CACHE.get(key)
        if model is None:
            from faster_whisper import WhisperModel  # LAZY heavy import

            import time as _t

            t0 = _t.time()
            model = WhisperModel(self.model_name, device=self.device, compute_type=self.compute_type)
            logger.info("faster-whisper %s loaded on %s/%s in %.1fs",
                        self.model_name, self.device, self.compute_type, _t.time() - t0)
            _WHISPER_CACHE[key] = model
        return model

    def transcribe(self, audio_b64: str) -> str:
        try:
            audio_bytes = base64.b64decode(audio_b64 or "")
        except Exception:
            return ""
        audio = decode_to_pcm(audio_bytes)
        if audio is None:
            return ""
        try:
            import time as _t

            model = self._ensure_model()
            t0 = _t.time()
            segments, _info = model.transcribe(
                audio,
                language=(self.language or None),
                beam_size=self.beam_size,
            )
            text = " ".join(s.text for s in segments).strip()
            logger.info("STT %.2fs (%.2fs audio) -> %r",
                        _t.time() - t0, audio.size / 16000.0, text[:80])
            return text
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("whisper transcription failed: %s", exc)
            return ""


class DeepgramProvider(STTProvider):
    """Cloud Deepgram provider (opt-in, STT_PROVIDER=deepgram).

    Sends the raw encoded audio bytes to Deepgram's pre-recorded ``/v1/listen``
    endpoint. Deepgram auto-detects the container/codec (browser webm/opus, wav,
    m4a, ...), so no client-side ffmpeg decode is needed on this path. The API
    key comes from ``settings.deepgram_api_key`` (env DEEPGRAM_API_KEY); without
    it the factory falls back to local Whisper, so this provider is only ever
    constructed when a key is present.
    """

    LISTEN_URL = "https://api.deepgram.com/v1/listen"

    def __init__(self) -> None:
        from app.config import settings

        self.api_key: str | None = getattr(settings, "deepgram_api_key", None)
        self.model: str = getattr(settings, "deepgram_model", "nova-2")
        self.language: str = getattr(settings, "whisper_language", "en") or ""
        self.timeout: float = float(getattr(settings, "stt_timeout", 60.0))

    def transcribe(self, audio_b64: str) -> str:
        if not self.api_key:
            logger.error("Deepgram provider requires settings.deepgram_api_key")
            return ""
        try:
            audio_bytes = base64.b64decode(audio_b64 or "")
            if not audio_bytes:
                return ""
            headers = {
                "Authorization": f"Token {self.api_key}",
                # Browser MediaRecorder produces webm/opus; declaring it helps
                # Deepgram pick the decoder (it still auto-detects if wrong).
                "Content-Type": "audio/webm",
            }
            params = {"model": self.model, "smart_format": "true", "punctuate": "true"}
            if self.language:
                params["language"] = self.language
            with httpx.Client(timeout=self.timeout) as client:
                resp = client.post(
                    self.LISTEN_URL, headers=headers, params=params, content=audio_bytes
                )
                resp.raise_for_status()
                data = resp.json()
            return (
                data["results"]["channels"][0]["alternatives"][0]["transcript"]
            ).strip()
        except Exception as exc:  # pragma: no cover - cloud path
            logger.error("Deepgram transcription failed: %s", exc)
            return ""
