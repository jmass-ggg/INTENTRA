// BuildBrainPanel — the "Build your brain" interview dock for the Graph view.
//
// A warm AI assistant interviews the person (driven by /assistant_turn, which is
// graph-aware and asks about gaps). The person answers using the EXISTING
// composition components — vocab tiles, construction strip, candidate cards,
// select — exactly like the Conversation view (no new input UI, no free-typing).
// On select we call /confirm and hand the created/reinforced graph elements up to
// the Graph view via onConfirmed, which blooms them onto the brain live. Speaking
// is intentionally skipped here: the payoff is the graph growing, not playback.

import { useEffect, useRef, useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { Brain, Sparkle, CircleNotch, X } from "@phosphor-icons/react";
import VocabBoard, { type VocabTile } from "./VocabBoard";
import ConstructionStrip from "./ConstructionStrip";
import NextFragments from "./NextFragments";
import CandidateCard from "./CandidateCard";
import { assistantTurn, generate, confirm } from "../lib/api";
import type { Candidate, ConfirmResponse, AssistantTurnMessage } from "../lib/api";

interface Props {
  personId: string;
  // Called after a confirmed answer with the created/reinforced graph elements
  // plus the answer text (for the live stats / reconstruction overlay).
  onConfirmed: (result: ConfirmResponse, answer: string) => void;
  // Called after each /generate so the overlay can show the reconstruction.
  onGenerated?: (info: { candidates: Candidate[]; confidence: number; latency: number }) => void;
  onExit: () => void;
}

type Phase = "asking" | "ready" | "thinking" | "candidates" | "saving";

const FALLBACK_FIRST = "Tell me about someone important in your life.";

// A single transcript turn — assistant (teal, left) vs the user (coral, right).
function TurnBubble({ role, text }: { role: "assistant" | "user"; text: string }) {
  const isAI = role === "assistant";
  return (
    <div className={["flex w-full gap-2", isAI ? "flex-row" : "flex-row-reverse"].join(" ")}>
      <span
        aria-hidden
        className={[
          "mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full border font-mono text-[0.68rem] font-semibold",
          isAI
            ? "border-mind/30 bg-mind-soft text-mind-deep"
            : "border-voice/30 bg-voice-soft text-voice-deep",
        ].join(" ")}
      >
        {isAI ? "AI" : "E"}
      </span>
      <div
        className={[
          "max-w-[82%] rounded-xl border px-3.5 py-2",
          isAI
            ? "rounded-tl-md border-mind/25 bg-mind-soft"
            : "rounded-tr-md border-voice/25 bg-voice-soft",
        ].join(" ")}
      >
        <p className="m-0 font-ui text-[0.92rem] leading-snug text-text text-pretty">{text}</p>
      </div>
    </div>
  );
}

function ThinkingBubble() {
  return (
    <div className="flex w-full gap-2">
      <span
        aria-hidden
        className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-mind/30 bg-mind-soft font-mono text-[0.68rem] font-semibold text-mind-deep"
      >
        AI
      </span>
      <div className="rounded-xl rounded-tl-md border border-mind/25 bg-mind-soft px-3.5 py-2">
        <span className="inline-flex items-center gap-2 font-ui text-[0.9rem] text-mind-deep">
          <CircleNotch size={14} weight="bold" className="animate-spin" aria-hidden />
          Thinking…
        </span>
      </div>
    </div>
  );
}

export default function BuildBrainPanel({ personId, onConfirmed, onGenerated, onExit }: Props) {
  const [history, setHistory] = useState<AssistantTurnMessage[]>([]);
  const [question, setQuestion] = useState<string>("");
  const [phase, setPhase] = useState<Phase>("asking");
  const [fragments, setFragments] = useState<string[]>([]);
  const [candidates, setCandidates] = useState<Candidate[]>([]);
  const [selectedIdx, setSelectedIdx] = useState<number | null>(null);
  const [answered, setAnswered] = useState(0);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const askedRef = useRef(false);
  const busyRef = useRef(false);
  const transcriptRef = useRef<HTMLDivElement | null>(null);

  // The assistant opens with the first question.
  useEffect(() => {
    if (askedRef.current) return;
    askedRef.current = true;
    void askNext([]);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Keep the transcript pinned to the newest turn.
  useEffect(() => {
    const el = transcriptRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [history.length, phase]);

  async function askNext(hist: AssistantTurnMessage[]) {
    setPhase("asking");
    setSuggestions([]);
    let text = "";
    let sugg: string[] = [];
    try {
      const res = await assistantTurn({ person_id: personId, history: hist });
      text = (res.text || "").trim();
      sugg = res.suggestions ?? [];
    } catch {
      text = "";
    }
    if (!text) text = hist.length ? "What else would you like me to know?" : FALLBACK_FIRST;
    setQuestion(text);
    setSuggestions(sugg);
    setHistory([...hist, { role: "assistant", text }]);
    setPhase("ready");
  }

  function tap(tile: VocabTile) {
    setFragments((p) => [...p, tile.label]);
    setCandidates([]);
    setSelectedIdx(null);
    if (phase === "candidates") setPhase("ready");
  }
  function removeFrag(i: number) {
    setFragments((p) => p.filter((_, j) => j !== i));
    setCandidates([]);
    setSelectedIdx(null);
    if (phase === "candidates") setPhase("ready");
  }
  function clearFrag() {
    setFragments([]);
    setCandidates([]);
    setSelectedIdx(null);
    if (phase === "candidates") setPhase("ready");
  }

  async function answer() {
    if (!fragments.length || phase === "thinking" || phase === "saving") return;
    setPhase("thinking");
    setCandidates([]);
    setSelectedIdx(null);
    let cands: Candidate[] = [];
    let confidence = 0;
    let latency = 0;
    try {
      // Frame the context as the question being answered so the reconstruction
      // is shaped as a direct answer (not just a generic reply). The transcript
      // and /confirm still use the clean question text.
      const askedContext = `The assistant is getting to know you and asked: "${question}" Answer it about your life.`;
      const res = await generate({ person_id: personId, fragments, context: askedContext });
      confidence = res.retrieval?.confidence ?? 0;
      latency = Number((res.trace as Record<string, unknown>)?.latency_ms ?? 0);
      if (!res.abstain) cands = res.candidates ?? [];
    } catch {
      cands = [];
    }
    if (!cands.length) {
      // Build Your Brain should always let the person answer — synthesize one
      // candidate from the raw fragments if the model abstains.
      cands = [
        {
          text: fragments.join(" "),
          register: "neutral",
          length_label: "short",
          rationale: "",
          grounded_node_ids: [],
        },
      ];
    }
    onGenerated?.({ candidates: cands, confidence, latency });
    setCandidates(cands);
    setPhase("candidates");
  }

  async function select(cand: Candidate, i: number) {
    if (busyRef.current || phase !== "candidates") return;
    busyRef.current = true;
    setSelectedIdx(i);
    setPhase("saving");
    try {
      const result = await confirm({ person_id: personId, text: cand.text, context: question });
      onConfirmed(result, cand.text);
    } catch {
      /* the bloom just won't happen; keep the interview flowing */
    } finally {
      busyRef.current = false;
    }
    const nextHist: AssistantTurnMessage[] = [...history, { role: "user", text: cand.text }];
    setFragments([]);
    setCandidates([]);
    setSelectedIdx(null);
    setAnswered((n) => n + 1);
    await askNext(nextHist);
  }

  const composing = phase === "asking";

  return (
    <div className="flex h-full min-h-0 flex-col gap-3 bg-ink p-4 text-text">
      <header className="flex items-center justify-between gap-3">
        <div className="flex items-center gap-2.5">
          <span className="flex h-8 w-8 items-center justify-center rounded-full bg-mind-soft text-mind">
            <Brain size={20} weight="duotone" aria-hidden />
          </span>
          <div className="leading-tight">
            <h2 className="m-0 font-ui text-aac-base font-semibold text-text">Build your brain</h2>
            <p className="m-0 font-ui text-[0.8rem] text-text-muted">
              Answer with tiles — your memory graph grows as you go.
            </p>
          </div>
        </div>
        <div className="flex items-center gap-2.5">
          {answered > 0 && (
            <span className="eyebrow text-mind-deep">{answered} answered</span>
          )}
          <button
            type="button"
            onClick={onExit}
            className="inline-flex h-9 items-center gap-1.5 rounded-full border border-ink-line bg-ink-raised px-3.5 font-ui text-[0.85rem] text-text-muted transition-colors duration-fast hover:bg-ink-sunken hover:text-text"
          >
            <X size={14} weight="bold" aria-hidden />
            Done
          </button>
        </div>
      </header>

      <div className="scroll-ink flex min-h-0 flex-1 flex-col gap-3 overflow-y-auto pr-1">
          {/* Conversation transcript — the interview so far; scrolls on its own. */}
          <div
            ref={transcriptRef}
            aria-label="Interview conversation"
            aria-live="polite"
            className="scroll-ink flex max-h-[34vh] min-h-[92px] shrink-0 flex-col gap-2.5 overflow-y-auto rounded-xl border border-ink-line bg-ink-sunken p-3"
          >
            {history.map((m, i) => (
              <TurnBubble key={i} role={m.role} text={m.text} />
            ))}
            {composing && <ThinkingBubble />}
          </div>

          {/* Construction strip — tap tiles or type words directly. */}
          <ConstructionStrip
            fragments={fragments}
            onRemove={removeFrag}
            onClear={clearFrag}
            onAddWord={(w) => tap({ id: `typed-${w}`, label: w })}
          />

          {/* Predictive next words — question-specific suggestions from the
              assistant (keyword categories as the offline fallback). */}
          <div className="shrink-0">
            <NextFragments
              fragments={fragments}
              context={question}
              suggestions={suggestions}
              onSuggest={tap}
            />
          </div>

          {/* Answer CTA. */}
          <div className="flex shrink-0 items-center gap-3">
            <motion.button
              type="button"
              onClick={answer}
              disabled={fragments.length === 0 || phase === "thinking" || phase === "saving"}
              whileTap={fragments.length === 0 ? undefined : { scale: 0.98 }}
              className={[
                "btn-cta rounded-md font-ui text-[1.02rem] font-semibold transition-colors duration-base",
                fragments.length === 0 || phase === "thinking" || phase === "saving"
                  ? "cursor-default bg-ink-raised text-text-faint"
                  : "bg-mind text-on-voice hover:bg-mind-deep",
              ].join(" ")}
            >
              {phase === "thinking" ? (
                <>
                  <CircleNotch size={18} weight="bold" aria-hidden className="animate-spin" />
                  Thinking…
                </>
              ) : (
                <>
                  <Sparkle size={18} weight="fill" aria-hidden />
                  Suggest answers
                </>
              )}
            </motion.button>
            {fragments.length === 0 && phase !== "thinking" && (
              <span className="font-ui text-[0.85rem] text-text-faint">Tap words below to answer.</span>
            )}
          </div>

          {/* Candidate cards (reused) — CandidateCard owns its own enter/exit
              motion; an extra wrapper here deadlocks the exit and leaves stale
              cards (whose onSay closure is stale), so render it directly. */}
          <section aria-label="Answer options" className="flex shrink-0 flex-col gap-3">
            <AnimatePresence>
              {(phase === "candidates" || phase === "saving") &&
                candidates.map((c, i) => (
                  <CandidateCard
                    key={`${c.text}-${i}`}
                    candidate={c}
                    index={i}
                    selected={selectedIdx === i}
                    rejected={selectedIdx != null && selectedIdx !== i}
                    disabled={phase === "saving"}
                    onSay={(cand) => select(cand, i)}
                  />
                ))}
            </AnimatePresence>
          </section>

          {/* Vocabulary tiles (reused) — tap to add words. */}
          <section
            aria-label="Vocabulary"
            className="shrink-0 rounded-xl border border-ink-line bg-ink-sunken p-3 sm:p-4"
          >
            <VocabBoard onTileTap={tap} />
          </section>
      </div>
    </div>
  );
}
