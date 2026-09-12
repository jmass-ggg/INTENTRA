"""Enroll a person's voice reference from a local wav file.

Usage (from the backend directory):

    python -m data.enroll_voice <person_id> <path-to-wav>

Example:

    python -m data.enroll_voice elena samples/elena.wav

This stores the wav as the person's reference (under settings.voices_dir), which
XTTSProvider then uses as the speaker reference for zero-shot cloning.
"""

from __future__ import annotations

import base64
import sys


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(__doc__)
        return 1
    person_id, wav_path = argv[1], argv[2]
    from app.providers.tts import save_reference

    with open(wav_path, "rb") as f:
        audio_b64 = base64.b64encode(f.read()).decode("ascii")
    path = save_reference(person_id, audio_b64)
    print(f"enrolled {person_id!r} from {wav_path} -> {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
