// CandidateCard — one generated Candidate, set up for the speak moment.
//
// The sentence is the human utterance (Newsreader serif). A register pill (color
// + a real text label, never color-only), a length chip, the mono rationale, and
// the `voice` "Say this" action. `selected` / `rejected` / `playing` drive the
// authorship beat: the chosen card rises on a soft spring and gains a warm
// TINTED SHADOW (not a neon glow); the others recede. Blur-in is the one
// production-polish entrance, gated on reduced motion.

import { motion, useReducedMotion } from "framer-motion";
import { SpeakerHigh } from "@phosphor-icons/react";
import type { Candidate, Register } from "../lib/api";
import { DUR, EASE_OUT, SPRING } from "../lib/motion";
import Waveform from "./Waveform";

export interface CandidateCardProps {
  candidate: Candidate;
  index: number;
  selected?: boolean;
  rejected?: boolean;
  playing?: boolean;
  // Locks the "Say this" action during the speak beat (prevents double-commit).
  disabled?: boolean;
  onSay: (candidate: Candidate) => void;
}

// Register triad — color dot + a real text label (color is never the only cue).
const REGISTER_META: Record<Register, { dot: string; text: string }> = {
  warm: { dot: "bg-register-warm", text: "text-register-warm" },
  neutral: { dot: "bg-register-neutral", text: "text-register-neutral" },
  direct: { dot: "bg-register-direct", text: "text-register-direct" },
};

export default function CandidateCard({
  candidate,
  index,
  selected = false,
  rejected = false,
  playing = false,
  disabled = false,
  onSay,
}: CandidateCardProps) {
  const reg = REGISTER_META[candidate.register];
  const reduce = useReducedMotion();

  return (
    <motion.div
      layout
      initial={reduce ? { opacity: 0 } : { opacity: 0, y: 12, filter: "blur(6px)" }}
      animate={{
        opacity: rejected ? 0.4 : 1,
        y: selected ? -5 : 0,
        scale: rejected ? 0.975 : 1,
        filter: rejected ? "saturate(0.45) blur(0px)" : "saturate(1) blur(0px)",
      }}
      transition={
        selected || rejected
          ? SPRING
          : { delay: reduce ? 0 : index * 0.07, duration: DUR.moment, ease: EASE_OUT }
      }
      className={[
        "relative flex flex-col gap-4 rounded-xl border p-6 transition-colors duration-base",
        selected
          ? "border-voice/55 bg-voice-soft shadow-utter"
          : "border-ink-line bg-ink-raised shadow-card",
      ].join(" ")}
    >
      <p className="m-0 font-utter text-candidate font-medium leading-snug text-text text-pretty">
        {candidate.text}
      </p>

      {/* Metadata cluster: register pill (dot + label) leads; length is quieter
          plain metadata so it doesn't read as a broken dotless register pill. */}
      <div className="-mt-1.5 flex flex-wrap items-center gap-2.5">
        <span className="inline-flex items-center gap-2 rounded-full border border-ink-line bg-ink-raised px-3 py-1">
          <span aria-hidden className={`h-1.5 w-1.5 rounded-full ${reg.dot}`} />
          <span className={`font-mono text-[0.72rem] uppercase tracking-[0.12em] ${reg.text}`}>
            {candidate.register}
          </span>
        </span>
        <span className="font-mono text-[0.72rem] uppercase tracking-[0.12em] text-text-muted">
          {candidate.length_label}
        </span>
      </div>

      {candidate.rationale && (
        <p className="m-0 font-mono text-[0.84rem] leading-relaxed text-text-muted">
          {candidate.rationale}
        </p>
      )}

      <div className="flex items-center gap-4">
        <motion.button
          type="button"
          whileTap={reduce || disabled ? undefined : { scale: 0.97 }}
          onClick={() => onSay(candidate)}
          disabled={disabled}
          className="btn-cta rounded-md bg-voice font-ui text-[1.05rem] font-semibold text-on-voice transition-colors duration-base hover:bg-voice-deep disabled:cursor-default disabled:opacity-50 disabled:hover:bg-voice"
        >
          <SpeakerHigh size={20} weight="fill" aria-hidden />
          Say this
        </motion.button>
        {/* Speaking affordance — slot is ALWAYS reserved (opacity toggles) so the
            row never shifts width when playback starts. */}
        <span
          aria-hidden
          className={`ml-auto inline-flex items-center gap-2 transition-opacity duration-base ${
            playing ? "opacity-100" : "opacity-0"
          }`}
        >
          <Waveform playing={playing} size="sm" />
          <span className="font-mono text-[0.72rem] uppercase tracking-[0.12em] text-voice-deep">
            Speaking
          </span>
        </span>
      </div>
    </motion.div>
  );
}
