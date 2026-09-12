// useSpeak — owns playback for the Speaker view.
//
// Chain (never silent): call speak({ person_id, text }); if the backend returns
// a non-empty audio_base64 (the cloned voice) we decode + play it; otherwise we
// speak via the browser SpeechSynthesis API using the best available on-device
// voice. Browser TTS is the PRIMARY path today (the backend cloned-voice path
// is wired and ready, so it takes over automatically once a voice is enrolled).
//
// The hook NEVER auto-speaks — it only plays when speak() is called explicitly
// (the Speaker view calls it from the "Say this" click only).

import { useCallback, useEffect, useRef, useState } from "react";
import { speak as apiSpeak } from "../lib/api";

export interface UseSpeak {
  speak: (text: string) => Promise<void>;
  playing: boolean;
}

// --- best available system voice -------------------------------------------
// Prefer a warm, natural, on-device English voice (Elena = warm retired
// teacher). macOS "Enhanced/Premium" voices and known-natural female voices
// score highest; on-device (localService) voices are preferred so playback
// stays airplane-safe and low-latency.
const PREFERRED_NAMES = [
  "ava", "allison", "samantha", "serena", "joelle", "nora", "zoe", "moira", "tessa", "karen", "fiona",
];

function scoreVoice(v: SpeechSynthesisVoice): number {
  const lang = v.lang.toLowerCase();
  if (!lang.startsWith("en")) return -Infinity;
  const name = v.name.toLowerCase();
  let s = lang === "en-us" ? 5 : 2;
  if (v.localService) s += 4; // on-device → airplane-safe, usually higher quality on macOS
  if (/(enhanced|premium)/.test(name)) s += 10;
  const idx = PREFERRED_NAMES.findIndex((n) => name.includes(n));
  if (idx >= 0) s += 8 - idx * 0.4; // earlier in the list = warmer female pick
  if (name.includes("google")) s += 3; // Chrome's Google voices are natural (online)
  return s;
}

let cachedVoice: SpeechSynthesisVoice | null = null;
function pickBestVoice(): SpeechSynthesisVoice | null {
  if (typeof window === "undefined" || !window.speechSynthesis) return null;
  const voices = window.speechSynthesis.getVoices();
  if (!voices.length) return cachedVoice; // not loaded yet; voiceschanged will retry
  let best: SpeechSynthesisVoice | null = null;
  let bestScore = -Infinity;
  for (const v of voices) {
    const sc = scoreVoice(v);
    if (sc > bestScore) {
      bestScore = sc;
      best = v;
    }
  }
  if (best) cachedVoice = best;
  return cachedVoice;
}

// Decode a base64 string into an ArrayBuffer for the Audio element.
function base64ToBlobUrl(b64: string): string {
  const binary = atob(b64);
  const len = binary.length;
  const bytes = new Uint8Array(len);
  for (let i = 0; i < len; i++) bytes[i] = binary.charCodeAt(i);
  // WAV is the safe default for XTTS output; the browser sniffs anyway.
  const blob = new Blob([bytes], { type: "audio/wav" });
  return URL.createObjectURL(blob);
}

export function useSpeak(personId: string): UseSpeak {
  const [playing, setPlaying] = useState(false);
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const urlRef = useRef<string | null>(null);

  // Warm the voice cache (the list often loads async) + clean up on unmount.
  useEffect(() => {
    pickBestVoice();
    const onVoices = () => pickBestVoice();
    window.speechSynthesis?.addEventListener?.("voiceschanged", onVoices);
    return () => {
      window.speechSynthesis?.removeEventListener?.("voiceschanged", onVoices);
      // Stop any in-flight cloned-voice playback before revoking its URL, else
      // the sentence keeps playing after navigating away from the view.
      try {
        audioRef.current?.pause();
      } catch {
        /* no-op */
      }
      audioRef.current = null;
      if (urlRef.current) URL.revokeObjectURL(urlRef.current);
      try {
        window.speechSynthesis?.cancel();
      } catch {
        /* no-op */
      }
    };
  }, []);

  const playBrowserTTS = useCallback((text: string) => {
    return new Promise<void>((resolve) => {
      if (typeof window === "undefined" || !window.speechSynthesis) {
        resolve();
        return;
      }
      window.speechSynthesis.cancel();
      const utter = new SpeechSynthesisUtterance(text);
      const voice = pickBestVoice();
      if (voice) {
        utter.voice = voice;
        utter.lang = voice.lang;
      } else {
        utter.lang = "en-US";
      }
      utter.rate = 0.96; // a touch unhurried → warm, natural delivery (Elena)
      utter.pitch = 1.0;
      utter.volume = 1.0;
      utter.onend = () => resolve();
      utter.onerror = () => resolve();
      window.speechSynthesis.speak(utter);
    });
  }, []);

  const playAudioUrl = useCallback((url: string) => {
    return new Promise<void>((resolve) => {
      const audio = new Audio(url);
      audioRef.current = audio;
      audio.onended = () => resolve();
      audio.onerror = () => resolve();
      void audio.play().catch(() => resolve());
    });
  }, []);

  const speak = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed) return;

      // Stop any prior playback so a rapid second utterance doesn't overlap.
      try {
        audioRef.current?.pause();
        window.speechSynthesis?.cancel();
      } catch {
        /* no-op */
      }

      setPlaying(true);
      try {
        let audioB64 = "";
        try {
          const res = await apiSpeak({ person_id: personId, text: trimmed });
          audioB64 = res.audio_base64 ?? "";
        } catch {
          audioB64 = "";
        }

        if (audioB64) {
          if (urlRef.current) URL.revokeObjectURL(urlRef.current);
          const url = base64ToBlobUrl(audioB64);
          urlRef.current = url;
          await playAudioUrl(url);
        } else {
          // Fallback so the demo is never silent.
          await playBrowserTTS(trimmed);
        }
      } finally {
        setPlaying(false);
      }
    },
    [personId, playAudioUrl, playBrowserTTS],
  );

  return { speak, playing };
}

export default useSpeak;
