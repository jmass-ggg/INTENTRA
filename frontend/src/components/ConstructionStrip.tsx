// ConstructionStrip — the fragments tapped so far. Each chip carries its own ✕
// to remove a single fragment; Clear wipes all. Chips fly in as a state change
// (a word was added), with a subtler exit than enter.

import { useState } from "react";
import { AnimatePresence, motion } from "framer-motion";
import { X } from "@phosphor-icons/react";
import { DUR, EASE_OUT } from "../lib/motion";

export interface ConstructionStripProps {
  fragments: string[];
  onRemove: (index: number) => void;
  onClear: () => void;
  // When provided, an inline text input lets the user TYPE straight into the
  // answer box; each Enter adds the typed word/phrase as a fragment.
  onAddWord?: (word: string) => void;
}

export default function ConstructionStrip({
  fragments,
  onRemove,
  onClear,
  onAddWord,
}: ConstructionStripProps) {
  const empty = fragments.length === 0;
  const [draft, setDraft] = useState("");

  const submitDraft = () => {
    const w = draft.trim();
    if (!w || !onAddWord) return;
    onAddWord(w);
    setDraft("");
  };

  return (
    <div className="flex min-h-[64px] shrink-0 items-center gap-3 rounded-lg border border-ink-line bg-ink-raised px-4 py-3 shadow-card">
      <div className="flex min-w-0 flex-1 flex-wrap items-center gap-2">
        {empty && !onAddWord ? (
          <span className="text-aac-base text-text-faint">Tap words to begin.</span>
        ) : (
          <AnimatePresence initial={false}>
            {fragments.map((fragment, i) => (
              <motion.span
                key={`${fragment}-${i}`}
                layout
                initial={{ opacity: 0, y: 8, scale: 0.9 }}
                animate={{ opacity: 1, y: 0, scale: 1 }}
                exit={{ opacity: 0, scale: 0.92 }}
                transition={{ duration: DUR.base, ease: EASE_OUT }}
                className="inline-flex max-w-full items-center gap-1.5 break-words rounded-full border border-voice/30 bg-voice-soft py-2 pl-4 pr-1.5 text-aac-base font-medium text-text"
              >
                {fragment}
                <button
                  type="button"
                  onClick={() => onRemove(i)}
                  aria-label={`Remove ${fragment}`}
                  className="grid h-9 w-9 place-items-center rounded-full text-text-muted transition-colors duration-fast hover:bg-text/10 hover:text-text"
                >
                  <X size={14} weight="bold" aria-hidden />
                </button>
              </motion.span>
            ))}
          </AnimatePresence>
        )}
        {onAddWord && (
          <input
            type="text"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") {
                e.preventDefault();
                submitDraft();
              }
            }}
            onBlur={submitDraft}
            placeholder={empty ? "Tap or type a word…" : "type a word…"}
            aria-label="Type a word to add to the answer"
            className="min-w-[7rem] flex-1 border-0 bg-transparent px-1 font-ui text-aac-base text-text outline-none placeholder:text-text-faint"
          />
        )}
      </div>

      <button
        type="button"
        onClick={onClear}
        disabled={empty}
        className="inline-flex items-center gap-1.5 rounded-md px-3 py-2 font-mono text-[0.78rem] uppercase tracking-[0.12em] text-text-muted transition-colors duration-fast enabled:hover:text-text disabled:cursor-default disabled:opacity-30"
      >
        <X size={13} weight="bold" aria-hidden />
        Clear
      </button>
    </div>
  );
}
