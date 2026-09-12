// QuickPhrases — a pinned horizontal rail of one-tap ready utterances at the
// top of the stage. Tapping a pill speaks it immediately (explicit user click =
// the only place audio is allowed) and surfaces it on the stage. Plain,
// AAC-appropriate phrases; horizontal scroll on overflow.

import type { ComponentType } from "react";
import { motion, useReducedMotion } from "framer-motion";
import {
  PushPin,
  ThumbsUp,
  ThumbsDown,
  HandHeart,
  Drop,
  Hourglass,
  HandsClapping,
  type IconProps,
} from "@phosphor-icons/react";
import { DUR, EASE_OUT } from "../lib/motion";

type PhosphorIcon = ComponentType<IconProps>;

export interface QuickPhrase {
  id: string;
  text: string;
  icon: PhosphorIcon;
}

// Seed set — plain, polite, high-frequency AAC utterances.
const QUICK_PHRASES: QuickPhrase[] = [
  { id: "qp-yes", text: "Yes, please.", icon: ThumbsUp },
  { id: "qp-no", text: "No, thank you.", icon: ThumbsDown },
  { id: "qp-thanks", text: "Thank you.", icon: HandsClapping },
  { id: "qp-help", text: "I need help.", icon: HandHeart },
  { id: "qp-water", text: "Could I have some water?", icon: Drop },
  { id: "qp-moment", text: "Give me a moment.", icon: Hourglass },
];

export interface QuickPhrasesProps {
  // Called on explicit tap. The view both speaks and stages the phrase.
  onSpeak: (text: string) => void;
  disabled?: boolean;
}

export default function QuickPhrases({ onSpeak, disabled = false }: QuickPhrasesProps) {
  const reduce = useReducedMotion();

  return (
    <div className="relative z-10 flex flex-col gap-2">
      <span className="eyebrow inline-flex items-center gap-1.5">
        <PushPin size={14} weight="fill" aria-hidden className="text-voice" />
        Quick phrases
      </span>
      <div
        role="list"
        aria-label="Quick phrases"
        className="flex snap-x snap-mandatory gap-2 overflow-x-auto pb-1 pr-2 [scrollbar-width:thin]"
      >
        {QUICK_PHRASES.map((p) => {
          const Icon = p.icon;
          return (
            <motion.button
              key={p.id}
              type="button"
              role="listitem"
              disabled={disabled}
              whileHover={reduce || disabled ? undefined : { y: -2 }}
              whileTap={reduce || disabled ? undefined : { scale: 0.97 }}
              transition={{ duration: DUR.fast, ease: EASE_OUT }}
              onClick={() => onSpeak(p.text)}
              className="inline-flex min-h-touch shrink-0 snap-start items-center gap-2 rounded-full border border-ink-line bg-ink-raised px-4 font-ui text-[0.9rem] text-text shadow-card transition-[color,border-color,box-shadow] duration-fast enabled:hover:border-voice/45 enabled:hover:text-voice-deep enabled:hover:shadow-lift disabled:cursor-default disabled:opacity-40"
            >
              <Icon size={18} weight="duotone" aria-hidden className="text-voice" />
              {p.text}
            </motion.button>
          );
        })}
      </div>
    </div>
  );
}
