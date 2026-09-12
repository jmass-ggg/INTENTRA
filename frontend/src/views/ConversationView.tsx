// ConversationView — the unified Lucid Voice surface (the primary interface).
//
// One screen, two roles side by side:
//   • LEFT  — the conversation SPINE: partner turns and the user's spoken turns,
//     interleaved chronologically like an accessible chat. The user's turns are
//     the sentences they actually chose + spoke (coral, serif). Below it sits the
//     PARTNER capture bar: the mic (→ /stt) plus quick "Heard" lines that ADVANCE
//     as the conversation flows. The assisted user NEVER types — composition is
//     tiles + AI reconstruction only.
//   • RIGHT — the composing WORKSPACE: vocab tiles, the construction strip,
//     predictive next words (which ADAPT to what the partner just said), the
//     "Speak" action + tone dial, the candidate cards, and quick phrases.
//
// FLOW (one turn): capture the partner (mic / Heard line) → it lands in the
// transcript and becomes the current context → tap fragments → "Speak" calls
// /generate WITH the latest partner utterance as `context` → the user selects a
// candidate → it plays in the cloned voice (useSpeak), fires /confirm, and is
// appended as the user's turn. After the user replies, the Heard lines + next
// words update for the next exchange. The app NEVER auto-speaks — audio only
// plays from an explicit selection or quick-phrase tap. Each /generate also
// updates the backend trace, so the separate Graph view lights up per turn.

import { useEffect, useMemo, useRef, useState } from "react";
import { AnimatePresence, motion, useReducedMotion } from "framer-motion";
import {
  Microphone,
  MicrophoneSlash,
  Ear,
  Sparkle,
  CircleNotch,
  SpeakerHigh,
  Info,
  ChatsCircle,
  Lightning,
} from "@phosphor-icons/react";
import { DUR, EASE_OUT, SPRING } from "../lib/motion";
import VocabBoard, { type VocabTile } from "../components/VocabBoard";
import ConstructionStrip from "../components/ConstructionStrip";
import CandidateCard from "../components/CandidateCard";
import StateIndicator, { type SpeakerState } from "../components/StateIndicator";
import QuickPhrases from "../components/QuickPhrases";
import NextFragments from "../components/NextFragments";
import ToneDial, { type Tone } from "../components/ToneDial";
import useSpeak from "../hooks/useSpeak";
import { confirm, generate, stt } from "../lib/api";
import type { Candidate, Register } from "../lib/api";
import { demoGenerate } from "../lib/demo";

// Matches the demo persona.
const PERSON_ID = "elena";
const ME_NAME = "Elena";

interface TranscriptEntry {
  id: string;
  speaker: "partner" | "me";
  name: string;
  text: string;
  time: string;
}

interface PartnerLine {
  id: string;
  name: string;
  text: string;
}

const norm = (s: string) => s.trim().toLowerCase();

// Opening "Heard" lines, shown before the conversation has started.
const OPENERS: PartnerLine[] = [
  { id: "sofia-dinner", name: "Sofia", text: "Mom, do you want to come for dinner Sunday?" },
  { id: "mateo-play", name: "Mateo", text: "Grandma, will you play with me?" },
];

// After Elena replies to a given partner line, the likely NEXT partner lines.
// A small scripted dialogue tree keyed by the partner utterance she answered.
const FOLLOWUPS: Record<string, PartnerLine[]> = {
  [norm("Mom, do you want to come for dinner Sunday?")]: [
    { id: "sofia-ok", name: "Sofia", text: "Okay — maybe another weekend then?" },
    { id: "sofia-okayq", name: "Sofia", text: "Are you feeling okay, Mom?" },
    { id: "sofia-bring", name: "Sofia", text: "Can I bring some dinner over to you?" },
  ],
  [norm("Grandma, will you play with me?")]: [
    { id: "mateo-later", name: "Mateo", text: "Okay! Can we play later instead?" },
    { id: "mateo-sad", name: "Mateo", text: "Are you sad, Grandma?" },
    { id: "mateo-love", name: "Mateo", text: "I love you, Grandma!" },
  ],
  [norm("Are you feeling okay, Mom?")]: [
    { id: "sofia-rest", name: "Sofia", text: "You should get some rest, Mom." },
    { id: "sofia-call", name: "Sofia", text: "Want me to call you tomorrow?" },
  ],
  [norm("Can I bring some dinner over to you?")]: [
    { id: "sofia-soup", name: "Sofia", text: "I'll bring your favorite soup." },
    { id: "sofia-when", name: "Sofia", text: "What time works for you?" },
  ],
  [norm("Okay! Can we play later instead?")]: [
    { id: "mateo-nap", name: "Mateo", text: "After your nap, okay?" },
    { id: "mateo-what", name: "Mateo", text: "What do you want to play?" },
  ],
  [norm("Are you sad, Grandma?")]: [
    { id: "mateo-hug", name: "Mateo", text: "Do you want a hug?" },
    { id: "mateo-stay", name: "Mateo", text: "I can stay here with you." },
  ],
};

// Generic follow-ups for anything unscripted (e.g. a mic-transcribed line).
const GENERIC_FOLLOWUPS: PartnerLine[] = [
  { id: "gen-ok", name: "Partner", text: "Okay, that sounds good." },
  { id: "gen-need", name: "Partner", text: "Do you need anything?" },
  { id: "gen-later", name: "Partner", text: "I'll check on you in a bit." },
];

function followupsFor(partnerText: string): PartnerLine[] {
  if (!partnerText.trim()) return OPENERS;
  return FOLLOWUPS[norm(partnerText)] ?? GENERIC_FOLLOWUPS;
}

// Tone → preferred register order. Candidates are sorted (stably) so the
// emphasized register floats to the top; "even" preserves the original order.
const TONE_REGISTER_PRIORITY: Record<Tone, Register[]> = {
  warm: ["warm", "neutral", "direct"],
  even: [],
  direct: ["direct", "neutral", "warm"],
  playful: ["warm", "neutral", "direct"],
};

function orderByTone(candidates: Candidate[], tone: Tone): Candidate[] {
  const priority = TONE_REGISTER_PRIORITY[tone];
  if (priority.length === 0) return candidates;
  const rank = (r: Register) => {
    const idx = priority.indexOf(r);
    return idx === -1 ? priority.length : idx;
  };
  return candidates
    .map((c, i) => ({ c, i }))
    .sort((a, b) => rank(a.c.register) - rank(b.c.register) || a.i - b.i)
    .map((x) => x.c);
}

function wordCount(text: string): number {
  return text.trim().split(/\s+/).filter(Boolean).length;
}

function nowLabel(): string {
  return new Date().toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
}

// ArrayBuffer/Blob -> base64 (chunked to avoid call-stack limits on big buffers).
async function blobToBase64(blob: Blob): Promise<string> {
  const bytes = new Uint8Array(await blob.arrayBuffer());
  let binary = "";
  const CHUNK = 0x8000;
  for (let i = 0; i < bytes.length; i += CHUNK) {
    binary += String.fromCharCode(...bytes.subarray(i, i + CHUNK));
  }
  return btoa(binary);
}

// ── transcript bubble ───────────────────────────────────────────────────────
function TurnBubble({ entry }: { entry: TranscriptEntry }) {
  const isMe = entry.speaker === "me";
  const initial = entry.name.charAt(0).toUpperCase();

  return (
    <motion.div
      layout
      initial={{ opacity: 0, y: 10 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: 8 }}
      transition={{ duration: DUR.base, ease: EASE_OUT }}
      className={["flex w-full items-end gap-2.5", isMe ? "flex-row-reverse" : "flex-row"].join(" ")}
    >
      <div
        aria-hidden
        className={[
          "flex h-9 w-9 shrink-0 items-center justify-center rounded-full border font-mono text-[0.9rem] font-semibold",
          isMe
            ? "border-voice/30 bg-voice-soft text-voice-deep"
            : "border-ink-line bg-ink-raised text-text-muted",
        ].join(" ")}
      >
        {initial}
      </div>

      <div
        className={["flex min-w-0 max-w-[80%] flex-col gap-1", isMe ? "items-end" : "items-start"].join(" ")}
      >
        <div className={["flex items-center gap-2 px-1", isMe ? "flex-row-reverse" : "flex-row"].join(" ")}>
          <span className={`eyebrow ${isMe ? "text-voice-deep" : "text-text-muted"}`}>{entry.name}</span>
          <span className="font-mono text-[0.72rem] text-text-muted">{entry.time}</span>
        </div>

        <div
          className={[
            "rounded-xl border px-4 py-2.5",
            isMe
              ? "rounded-br-md border-voice/25 bg-voice-soft shadow-utter"
              : "rounded-bl-md border-ink-line bg-ink-raised shadow-card",
          ].join(" ")}
        >
          <p
            className={[
              "m-0",
              isMe ? "font-utter text-[1.2rem] leading-snug text-pretty" : "font-ui text-aac-base",
            ].join(" ")}
          >
            {entry.text}
          </p>
          {isMe && (
            <span className="mt-1.5 inline-flex items-center gap-1 font-mono text-[0.66rem] uppercase tracking-[0.12em] text-voice-deep/80">
              <SpeakerHigh size={11} weight="fill" aria-hidden />
              Elena’s voice
            </span>
          )}
        </div>
      </div>
    </motion.div>
  );
}

// Composing indicator — a small right-aligned "typing" bubble while /generate runs.
function ComposingBubble() {
  const reduce = useReducedMotion();
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0 }}
      transition={{ duration: DUR.fast, ease: EASE_OUT }}
      className="flex w-full flex-row-reverse items-end gap-2.5"
    >
      <div
        aria-hidden
        className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full border border-voice/30 bg-voice-soft text-voice-deep font-mono text-[0.9rem] font-semibold"
      >
        E
      </div>
      <div className="rounded-xl rounded-br-md border border-voice/20 bg-voice-soft px-4 py-3">
        <span className="flex items-center gap-1.5">
          {[0, 1, 2].map((i) => (
            <motion.span
              key={i}
              className="h-1.5 w-1.5 rounded-full bg-voice-deep/60"
              animate={reduce ? undefined : { opacity: [0.3, 1, 0.3], y: [0, -2, 0] }}
              transition={{ duration: 0.9, repeat: Infinity, ease: "easeInOut", delay: i * 0.15 }}
            />
          ))}
        </span>
      </div>
    </motion.div>
  );
}

// Soft listening rings (recording only; suppressed on reduce).
function ListeningRing({ active }: { active: boolean }) {
  const reduce = useReducedMotion();
  if (!active || reduce) return null;
  return (
    <>
      {[0, 1, 2].map((i) => (
        <motion.span
          key={i}
          aria-hidden
          className="absolute inset-0 rounded-full border border-mind/40"
          initial={{ scale: 1, opacity: 0.35 }}
          animate={{ scale: 1.6, opacity: 0 }}
          transition={{ duration: 1.8, repeat: Infinity, ease: "easeOut", delay: i * 0.6 }}
        />
      ))}
    </>
  );
}

// The mic bar's level strip — animated while recording, quiet at rest.
function LevelStrip({ active }: { active: boolean }) {
  const reduce = useReducedMotion();
  const BARS = 22;
  const cfg = useMemo(
    () =>
      Array.from({ length: BARS }, (_, i) => ({
        peak: 0.32 + 0.6 * Math.abs(Math.sin(i * 1.3 + 0.5)),
        duration: 0.5 + ((i * 7) % 5) * 0.1,
        delay: (i % 7) * 0.05,
      })),
    [],
  );
  return (
    <div aria-hidden className="flex h-8 min-w-0 flex-1 items-center justify-center gap-[3px] overflow-hidden">
      {cfg.map((c, i) => (
        <motion.span
          key={i}
          className={`w-[3px] rounded-full ${active ? "bg-mind" : "bg-ink-line"}`}
          style={{ opacity: active ? 0.7 + (c.peak - 0.32) * 0.5 : 1 }}
          initial={false}
          animate={
            active && !reduce
              ? { height: ["22%", `${c.peak * 100}%`, "34%"] }
              : { height: active ? `${c.peak * 78}%` : "24%" }
          }
          transition={
            active && !reduce
              ? { duration: c.duration, delay: c.delay, repeat: Infinity, ease: "easeInOut" }
              : { duration: 0.22 }
          }
        />
      ))}
    </div>
  );
}

type RecordStatus = "idle" | "recording" | "transcribing";
type Pipeline = "idle" | "thinking" | "candidates" | "speaking";

export default function ConversationView() {
  const [transcript, setTranscript] = useState<TranscriptEntry[]>([]);
  const [recordStatus, setRecordStatus] = useState<RecordStatus>("idle");
  const [pipeline, setPipeline] = useState<Pipeline>("idle");

  const [fragments, setFragments] = useState<string[]>([]);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [selectedIdx, setSelectedIdx] = useState<number | null>(null);
  const [abstainMsg, setAbstainMsg] = useState<string>("");
  const [tone, setTone] = useState<Tone>("even");

  // The Heard quick-lines, which advance as the conversation flows.
  const [partnerOptions, setPartnerOptions] = useState<PartnerLine[]>(OPENERS);
  const [hint, setHint] = useState<string | null>(null);

  // Cumulative leverage across confirmed turns (the AAC value metric).
  const [sessionTaps, setSessionTaps] = useState(0);
  const [sessionWords, setSessionWords] = useState(0);

  const { speak, playing } = useSpeak(PERSON_ID);

  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const streamRef = useRef<MediaStream | null>(null);
  const wellRef = useRef<HTMLDivElement | null>(null);
  const trayRef = useRef<HTMLElement | null>(null);
  const micBtnRef = useRef<HTMLButtonElement | null>(null);
  // Generation token — a late /generate that resolves after the user has moved
  // on (new partner turn, cleared fragments, committed a turn) is discarded
  // rather than resurrecting candidates against a now-stale context.
  const genRef = useRef(0);
  // Synchronous re-entry lock for the speak/commit beat (AAC users double-tap).
  const busyRef = useRef(false);

  const recording = recordStatus === "recording";

  // Context = the most recent PARTNER utterance (or "" — a turn can start cold).
  const lastPartner = useMemo(() => {
    for (let i = transcript.length - 1; i >= 0; i--) {
      if (transcript[i].speaker === "partner") return transcript[i];
    }
    return null;
  }, [transcript]);
  const context = lastPartner?.text ?? "";

  // Don't re-offer the exact line that's already the current partner turn.
  const heardOptions = useMemo(
    () => partnerOptions.filter((p) => norm(p.text) !== norm(context)),
    [partnerOptions, context],
  );

  // Status pill reflects the whole pipeline; recording/transcribing read as "listening".
  const displayState: SpeakerState = recordStatus !== "idle" ? "listening" : pipeline;

  // Auto-scroll the transcript to the newest turn.
  useEffect(() => {
    const el = wellRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [transcript.length, pipeline]);

  // When candidates render, move focus to the first "Say this" for keyboard /
  // switch users — this is the core selection moment.
  useEffect(() => {
    if (pipeline === "candidates" && candidates.length > 0) {
      const btn = trayRef.current?.querySelector(
        "button:not([disabled])",
      ) as HTMLButtonElement | null;
      btn?.focus();
    }
  }, [pipeline, candidates.length]);

  function stopTracks() {
    streamRef.current?.getTracks().forEach((t) => t.stop());
    streamRef.current = null;
  }

  function appendTurn(entry: Omit<TranscriptEntry, "id" | "time">) {
    setTranscript((t) => [
      ...t,
      { ...entry, id: `t-${t.length}-${entry.text.slice(0, 8)}`, time: nowLabel() },
    ]);
  }

  function appendPartner(text: string, name = "Partner") {
    const clean = text.trim();
    if (!clean) return;
    // A fresh partner utterance starts a new reply — cancel any in-flight
    // generate and clear the draft so a late result can't overwrite it.
    genRef.current += 1;
    appendTurn({ speaker: "partner", name, text: clean });
    setCandidates([]);
    setSelectedIdx(null);
    setAbstainMsg("");
    setPipeline("idle");
  }

  // ── partner capture: mic → /stt ─────────────────────────────────────────
  async function startRecording() {
    setHint(null);
    let stream: MediaStream;
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
      setHint("Microphone access was blocked — allow mic permission to transcribe.");
      return;
    }
    streamRef.current = stream;
    chunksRef.current = [];
    const recorder = new MediaRecorder(stream);
    recorderRef.current = recorder;
    recorder.ondataavailable = (e) => {
      if (e.data.size > 0) chunksRef.current.push(e.data);
    };
    recorder.onstop = async () => {
      stopTracks();
      const blob = new Blob(chunksRef.current, { type: recorder.mimeType || "audio/webm" });
      chunksRef.current = [];
      if (blob.size === 0) {
        setRecordStatus("idle");
        return;
      }
      setRecordStatus("transcribing");
      try {
        const { text } = await stt({ audio_base64: await blobToBase64(blob) });
        const clean = text.trim();
        if (clean) appendPartner(clean, "Partner");
        else setHint("Didn't catch that — try again, a little closer to the mic.");
      } catch {
        setHint("Couldn't reach transcription — is the backend running?");
      } finally {
        setRecordStatus("idle");
      }
    };
    recorder.start();
    setRecordStatus("recording");
  }

  function handleToggleRecord() {
    if (pipeline === "speaking") return;
    if (recordStatus === "recording") recorderRef.current?.stop();
    else if (recordStatus === "idle") void startRecording();
  }

  function handleHeard(line: PartnerLine) {
    if (pipeline === "thinking" || pipeline === "speaking" || recordStatus !== "idle") return;
    appendPartner(line.text, line.name);
  }

  // ── composing the reply ──────────────────────────────────────────────────
  function handleTileTap(tile: VocabTile) {
    // Any edit to the draft cancels an in-flight generate.
    genRef.current += 1;
    setFragments((prev) => [...prev, tile.label]);
    setCandidates([]);
    setSelectedIdx(null);
    setAbstainMsg("");
    setPipeline("idle");
  }

  function handleRemove(index: number) {
    genRef.current += 1;
    setFragments((prev) => prev.filter((_, i) => i !== index));
    setCandidates([]);
    setSelectedIdx(null);
    setAbstainMsg("");
    setPipeline("idle");
  }

  function handleClear() {
    genRef.current += 1;
    setFragments([]);
    setCandidates([]);
    setSelectedIdx(null);
    setAbstainMsg("");
    setPipeline("idle");
  }

  async function handleGenerate() {
    if (fragments.length === 0 || recordStatus !== "idle") return;
    const myGen = (genRef.current += 1);
    setPipeline("thinking");
    setCandidates([]);
    setSelectedIdx(null);
    setAbstainMsg("");

    // Spec: /generate is called with the latest partner utterance as `context`
    // (kept raw so the backend trace anchors on the real line). Tone is applied
    // client-side via orderByTone, not smuggled into the wire context.
    const req = { person_id: PERSON_ID, fragments, context };

    let live = null as Awaited<ReturnType<typeof generate>> | null;
    try {
      live = await generate(req);
    } catch {
      live = null;
    }

    // Discard a stale result: the user changed context/draft while we waited.
    if (genRef.current !== myGen) return;

    // The live model "actually answered" only with a real choice set (>=2
    // non-abstain candidates). A single degraded candidate isn't enough to lose
    // the curated multi-register divergence — prefer demo content on a signature
    // match; live still wins whenever the LLM is up and divergent.
    const liveStrong = !!live && !live.abstain && live.candidates.length >= 2;
    const demo = demoGenerate(req);

    let result: Awaited<ReturnType<typeof generate>> | null = null;
    if (liveStrong) result = live;
    else if (demo) result = demo;
    else if (live && !live.abstain && live.candidates.length > 0) result = live;

    if (!result || result.candidates.length === 0) {
      setAbstainMsg(live?.abstain_reason || "Add one more word so I can be sure.");
      setPipeline("candidates");
      return;
    }

    setCandidates(orderByTone(result.candidates, tone));
    setPipeline("candidates");
  }

  // ── selection = authorship beat ──────────────────────────────────────────
  async function handleSay(candidate: Candidate, index: number) {
    if (busyRef.current || pipeline !== "candidates") return;
    busyRef.current = true;
    genRef.current += 1;
    const taps = fragments.length;
    const repliedTo = context; // snapshot — context will change after we commit
    setSelectedIdx(index);
    setPipeline("speaking");

    try {
      try {
        void confirm({ person_id: PERSON_ID, text: candidate.text, context: repliedTo });
      } catch {
        /* ignore */
      }
      // Play (the only place audio is ever triggered for a candidate).
      await speak(candidate.text);

      // Commit the chosen sentence as the user's turn; advance the conversation.
      appendTurn({ speaker: "me", name: ME_NAME, text: candidate.text });
      setSessionTaps((t) => t + taps);
      setSessionWords((w) => w + wordCount(candidate.text));
      setPartnerOptions(followupsFor(repliedTo));
      setFragments([]);
      setCandidates([]);
      setSelectedIdx(null);
      setAbstainMsg("");
      setPipeline("idle");
    } finally {
      busyRef.current = false;
    }
    micBtnRef.current?.focus();
  }

  // ── quick phrases — explicit one-tap speak + commit ──────────────────────
  async function handleQuickPhrase(text: string) {
    if (busyRef.current || pipeline !== "idle") return;
    busyRef.current = true;
    genRef.current += 1;
    const repliedTo = context;
    setPipeline("speaking");
    try {
      try {
        void confirm({ person_id: PERSON_ID, text, context: repliedTo });
      } catch {
        /* ignore */
      }
      await speak(text);
      appendTurn({ speaker: "me", name: ME_NAME, text });
      setSessionTaps((t) => t + 1);
      setSessionWords((w) => w + wordCount(text));
      setPartnerOptions(followupsFor(repliedTo));
      setFragments([]);
      setCandidates([]);
      setSelectedIdx(null);
      setAbstainMsg("");
      setPipeline("idle");
    } finally {
      busyRef.current = false;
    }
  }

  // Stop the mic + recorder if we leave the view mid-capture.
  useEffect(
    () => () => {
      try {
        recorderRef.current?.stop();
      } catch {
        /* no-op */
      }
      stopTracks();
    },
    [],
  );

  const ctaDisabled =
    fragments.length === 0 ||
    pipeline === "thinking" ||
    pipeline === "speaking" ||
    recordStatus !== "idle";
  const partnerLocked = pipeline === "thinking" || pipeline === "speaking";
  const hasTurns = transcript.length > 0;
  const micStatusText =
    recordStatus === "recording"
      ? "Listening…"
      : recordStatus === "transcribing"
      ? "Transcribing…"
      : "Listen to partner";

  return (
    <div className="flex min-h-full flex-col gap-4 p-4 lg:h-full lg:p-5">
      {/* Header. */}
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <h2 className="m-0 font-ui text-aac-lg font-semibold text-text">Conversation</h2>
          <StateIndicator state={displayState} />
        </div>
        <div className="flex items-center gap-2.5">
          {sessionTaps > 0 && (
            <span className="inline-flex items-center gap-1.5 rounded-full border border-voice/25 bg-voice-soft px-3 py-1 font-mono text-[0.72rem] uppercase tracking-[0.1em] text-voice-deep">
              <Lightning size={13} weight="fill" aria-hidden />
              {sessionWords} words · {sessionTaps} taps
            </span>
          )}
          <span className="eyebrow">{hasTurns ? `${transcript.length} turns` : "no turns yet"}</span>
        </div>
      </header>

      {/* Screen-reader announcer — reads only a genuinely new partner turn back
          to the user (their own turns were already heard via TTS). */}
      <p className="sr-only" aria-live="polite">
        {lastPartner ? `${lastPartner.name} said: ${lastPartner.text}` : ""}
      </p>

      {/* Two zones: conversation spine (left) · composing workspace (right). */}
      <div className="grid grid-cols-1 gap-4 lg:min-h-0 lg:flex-1 lg:grid-cols-[1.05fr_0.95fr] lg:gap-5">
        {/* LEFT — spine. */}
        <section className="flex flex-col gap-3 lg:min-h-0">
          <div
            ref={wellRef}
            aria-label="Conversation transcript"
            className="scroll-ink flex min-h-[200px] max-h-[50vh] flex-col gap-4 overflow-y-auto rounded-xl border border-ink-line bg-ink-sunken p-4 sm:p-5 lg:max-h-none lg:flex-1"
          >
            {hasTurns || pipeline === "thinking" ? (
              <AnimatePresence initial={false}>
                {transcript.map((entry) => (
                  <TurnBubble key={entry.id} entry={entry} />
                ))}
                {pipeline === "thinking" && <ComposingBubble key="composing" />}
              </AnimatePresence>
            ) : (
              <div className="m-auto flex max-w-[320px] flex-col items-center gap-4 text-center">
                <div
                  aria-hidden
                  className="flex h-16 w-16 items-center justify-center rounded-full bg-voice-soft text-voice"
                >
                  <ChatsCircle size={36} weight="duotone" />
                </div>
                <p className="m-0 font-ui text-aac-base text-text-muted">
                  Listen to your partner, or just start building a sentence — your turns appear here.
                </p>
              </div>
            )}
          </div>

          {/* Partner capture bar — mic (real /stt) + advancing "Heard" lines. */}
          <div className="shrink-0 flex flex-col gap-3 rounded-xl border border-ink-line bg-ink-raised p-3 shadow-card sm:p-4">
            <div className="flex items-center gap-3">
              <div className="relative flex h-12 w-12 shrink-0 items-center justify-center">
                <ListeningRing active={recording} />
                <motion.button
                  ref={micBtnRef}
                  type="button"
                  whileTap={{ scale: 0.94 }}
                  transition={SPRING}
                  onClick={handleToggleRecord}
                  disabled={recordStatus === "transcribing" || pipeline === "speaking"}
                  aria-pressed={recording}
                  aria-label={recording ? "Stop listening" : "Listen to partner"}
                  className={[
                    "relative z-10 flex h-12 w-12 items-center justify-center rounded-full text-on-voice shadow-card transition-colors duration-base disabled:opacity-50",
                    recordStatus === "transcribing"
                      ? "cursor-wait bg-mind/60"
                      : recording
                      ? "bg-mind-deep"
                      : "bg-mind hover:bg-mind-deep",
                  ].join(" ")}
                >
                  {recording ? (
                    <MicrophoneSlash size={24} weight="fill" />
                  ) : (
                    <Microphone size={24} weight="fill" />
                  )}
                </motion.button>
              </div>

              <LevelStrip active={recording} />

              <span
                aria-live="polite"
                className={`eyebrow w-[11rem] shrink-0 whitespace-nowrap pr-6 text-right ${
                  recordStatus !== "idle" ? "text-mind-deep" : "text-text-muted"
                }`}
              >
                {micStatusText}
              </span>
            </div>

            <div className="flex flex-wrap items-center gap-2">
              <span className="eyebrow inline-flex items-center gap-1.5">
                <Ear size={14} weight="bold" aria-hidden className="text-text-faint" />
                Heard
              </span>
              {/* Plain buttons — the Heard set swaps as the conversation flows;
                  enter/exit animations deadlock under that churn. */}
              {heardOptions.map((p) => (
                <motion.button
                  key={p.id}
                  type="button"
                  whileTap={partnerLocked ? undefined : { scale: 0.96 }}
                  onClick={() => handleHeard(p)}
                  disabled={partnerLocked}
                  className="inline-flex h-10 items-center justify-center rounded-full border border-ink-line bg-ink-sunken px-3.5 font-ui text-[0.88rem] text-text-muted transition-colors duration-fast hover:bg-ink-raised hover:text-text disabled:cursor-default disabled:opacity-40"
                >
                  {p.name}: “{p.text.length > 30 ? `${p.text.slice(0, 30)}…` : p.text}”
                </motion.button>
              ))}
            </div>

            {hint && (
              <p aria-live="polite" className="m-0 px-1 font-ui text-[0.84rem] text-text-muted">
                {hint}
              </p>
            )}
          </div>
        </section>

        {/* RIGHT — composing workspace. */}
        <section className="scroll-ink flex flex-col gap-3 lg:min-h-0 lg:overflow-y-auto lg:pr-1">
          {/* Context line — what this reply is answering. */}
          <div className="flex items-center gap-2 rounded-lg border border-ink-line bg-ink-raised/60 px-3.5 py-2">
            <Ear size={15} weight="bold" aria-hidden className="shrink-0 text-text-faint" />
            {lastPartner ? (
              <p className="m-0 min-w-0 flex-1 truncate font-ui text-[0.9rem] text-text-muted">
                Replying to <span className="text-text">{lastPartner.name}</span>: “{lastPartner.text}”
              </p>
            ) : (
              <p className="m-0 font-ui text-[0.9rem] text-text-faint">
                No partner turn yet — you can still start a sentence.
              </p>
            )}
          </div>

          {/* Construction strip — tap tiles or type words directly. */}
          <ConstructionStrip
            fragments={fragments}
            onRemove={handleRemove}
            onClear={handleClear}
            onAddWord={(w) => handleTileTap({ id: `typed-${w}`, label: w })}
          />

          {/* Predictive next fragments — adapt to the partner's last utterance. */}
          <NextFragments fragments={fragments} context={context} onSuggest={handleTileTap} />

          {/* Speak CTA · tone · live taps. */}
          <div className="flex flex-wrap items-center gap-x-4 gap-y-3">
            <motion.button
              type="button"
              onClick={handleGenerate}
              disabled={ctaDisabled}
              whileTap={ctaDisabled ? undefined : { scale: 0.98 }}
              className={[
                "btn-cta rounded-md font-ui text-[1.05rem] font-semibold transition-colors duration-base",
                ctaDisabled
                  ? "cursor-default bg-ink-raised text-text-faint"
                  : "bg-voice text-on-voice hover:bg-voice-deep",
              ].join(" ")}
            >
              {pipeline === "thinking" ? (
                <>
                  <CircleNotch size={20} weight="bold" aria-hidden className="animate-spin" />
                  Composing…
                </>
              ) : (
                <>
                  <Sparkle size={20} weight="fill" aria-hidden />
                  Speak
                </>
              )}
            </motion.button>
            <ToneDial value={tone} onChange={setTone} />
            {fragments.length > 0 && (
              <span className="ml-auto font-mono text-[0.74rem] uppercase tracking-[0.12em] text-text-muted">
                {fragments.length} {fragments.length === 1 ? "tap" : "taps"}
              </span>
            )}
          </div>

          {/* Candidate tray — skeletons · cards · abstain. */}
          <section ref={trayRef} aria-label="Suggested replies" className="flex flex-col gap-3">
            {pipeline === "thinking" && (
              <div
                aria-hidden
                className="relative overflow-hidden rounded-xl border border-ink-line bg-ink-raised p-5"
              >
                <div className="flex flex-col gap-3">
                  <div className="h-5 w-4/5 rounded bg-ink-line/70" />
                  <div className="h-5 w-2/5 rounded bg-ink-line/45" />
                  <div className="mt-2 h-9 w-32 rounded-md bg-ink-line/35" />
                </div>
                <motion.div
                  className="pointer-events-none absolute inset-y-0 -left-1/2 w-1/2"
                  style={{
                    background:
                      "linear-gradient(90deg, transparent, rgba(12,130,118,0.08), transparent)",
                  }}
                  animate={{ x: ["0%", "300%"] }}
                  transition={{ duration: 1.3, repeat: Infinity, ease: "linear" }}
                />
              </div>
            )}

            {(pipeline === "candidates" || pipeline === "speaking") &&
              (abstainMsg ? (
                <div className="flex items-start gap-3 rounded-xl border border-ink-line bg-ink-raised p-5">
                  <Info size={20} weight="fill" aria-hidden className="mt-0.5 shrink-0 text-mind" />
                  <p className="m-0 font-ui text-aac-base text-text">{abstainMsg}</p>
                </div>
              ) : (
                <AnimatePresence>
                  {candidates.map((c, i) => (
                    <CandidateCard
                      key={`${c.text}-${i}`}
                      candidate={c}
                      index={i}
                      selected={selectedIdx === i}
                      rejected={selectedIdx != null && selectedIdx !== i}
                      playing={selectedIdx === i && playing}
                      disabled={pipeline === "speaking"}
                      onSay={(cand) => handleSay(cand, i)}
                    />
                  ))}
                </AnimatePresence>
              ))}
          </section>

          {/* Quick phrases. */}
          <QuickPhrases
            onSpeak={handleQuickPhrase}
            disabled={playing || pipeline !== "idle" || recordStatus !== "idle"}
          />

          {/* Vocab well. */}
          <section
            aria-label="Vocabulary"
            className="rounded-xl border border-ink-line bg-ink-sunken p-4 sm:p-5"
          >
            <VocabBoard onTileTap={handleTileTap} />
          </section>
        </section>
      </div>
    </div>
  );
}
