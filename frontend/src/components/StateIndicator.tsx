// StateIndicator — a quiet status pill. The dot changes color per state and the
// label crossfades on change; NO infinite pulse (motion conveys the transition,
// not a decorative loop). aria-live announces state to both people. Coral is
// reserved for the USER's own voice (speaking); machine states use teal.

import { AnimatePresence, motion } from "framer-motion";
import { DUR, EASE_OUT } from "../lib/motion";

export type SpeakerState =
  | "idle"
  | "listening"
  | "thinking"
  | "candidates"
  | "speaking";

export interface StateIndicatorProps {
  state: SpeakerState;
}

const STATE_META: Record<SpeakerState, { label: string; dot: string }> = {
  idle: { label: "Ready", dot: "bg-text-faint" },
  listening: { label: "Listening", dot: "bg-mind" }, // machine capturing the partner
  thinking: { label: "Composing", dot: "bg-mind" },
  candidates: { label: "Choose a reply", dot: "bg-register-neutral" },
  speaking: { label: "Speaking", dot: "bg-voice" }, // the user's own voice
};

// Longest label locks the pill width so it can't snap during the crossfade.
const LONGEST = Object.values(STATE_META).reduce(
  (a, m) => (m.label.length > a.length ? m.label : a),
  "",
);

const LABEL_CLASS = "font-mono text-[0.74rem] uppercase tracking-[0.14em]";

export default function StateIndicator({ state }: StateIndicatorProps) {
  const meta = STATE_META[state];
  const speaking = state === "speaking";

  return (
    <div
      role="status"
      aria-live="polite"
      className={[
        "inline-flex items-center gap-2.5 rounded-full border py-1.5 pl-3 pr-4 transition-colors duration-base",
        speaking ? "border-voice/30 bg-ink-raised shadow-card" : "border-ink-line bg-ink-raised/70",
      ].join(" ")}
    >
      <span
        aria-hidden
        className={`h-2 w-2 shrink-0 rounded-full transition-colors duration-base ${meta.dot} ${
          speaking ? "ring-2 ring-voice-soft" : ""
        }`}
      />
      <span className="relative grid">
        {/* Invisible sizer reserves the width of the longest label. */}
        <span aria-hidden className={`invisible [grid-area:1/1] ${LABEL_CLASS}`}>
          {LONGEST}
        </span>
        <AnimatePresence mode="wait" initial={false}>
          <motion.span
            key={state}
            initial={{ opacity: 0, y: 4 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -4 }}
            transition={{ duration: DUR.fast, ease: EASE_OUT }}
            className={`[grid-area:1/1] text-text-muted ${LABEL_CLASS}`}
          >
            {meta.label}
          </motion.span>
        </AnimatePresence>
      </span>
    </div>
  );
}
