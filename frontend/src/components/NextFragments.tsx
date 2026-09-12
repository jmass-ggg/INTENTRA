// NextFragments — predictive "next word" suggestions directly under the
// construction strip. A small local co-occurrence map proposes 3-4 likely next
// fragments from the LAST tapped word; tapping one appends it (same contract as
// a vocab tile). Calm and clearly secondary to the vocab board; the row morphs
// (AnimatePresence) as fragments change.

import { motion } from "framer-motion";
import { Lightning } from "@phosphor-icons/react";
import type { VocabTile } from "./VocabBoard";

// How many predictive words to show (wraps to ~2 rows; quick access).
const COUNT = 8;

// Local co-occurrence map: last fragment -> likely continuations.
const NEXT_MAP: Record<string, string[]> = {
  tired: ["maybe", "later", "rest", "not sure", "sorry"],
  cold: ["window", "blanket", "please"],
  maybe: ["later", "tomorrow", "not sure", "soon"],
  window: ["cold", "open", "please"],
  help: ["please", "now", "thank you"],
  yes: ["please", "thank you", "soon"],
  no: ["sorry", "thank you", "maybe"],
  later: ["maybe", "tomorrow", "soon"],
  okay: ["thank you", "love", "soon"],
  rest: ["later", "soon", "thank you"],
  love: ["you too", "soon", "always"],
  happy: ["thank you", "love", "yes"],
};

// Always-useful AAC words, used to pad the row up to COUNT.
const POOL = [
  "yes", "no", "maybe", "thank you", "please", "tired", "okay", "later",
  "love", "help", "water", "rest", "sorry", "soon",
];

// Generic answers when the partner context gives no keyword signal.
const GENERIC_ANSWERS = ["yes", "no", "maybe", "thank you", "please", "tired", "okay", "later"];

// Intent categories — the partner's line can match SEVERAL; words from every
// match are combined (in order) so the suggestions reflect the whole utterance,
// not just the first keyword hit. Words are reply-oriented (how Elena answers).
const CONTEXT_STARTERS: { match: RegExp; words: string[] }[] = [
  // --- Build-Your-Brain interview questions: content words that answer them ---
  {
    // "what do you call / your nickname for / how do you address …"
    match: /\bnicknames?\b|\bnamed?\b|\baddress(?:es)?\b|what do you call|usually call|do you call/i,
    words: ["dear", "love", "honey", "sweetie", "buddy", "friend", "pal", "mom"],
  },
  {
    // who / family / friends / relationships
    match: /\b(who|people|family|families|relative|relatives|friend|friends|partner|spouse|married|kids|children|grandchild|grandchildren|important people)\b/i,
    words: ["sister", "brother", "friend", "daughter", "son", "neighbor", "wife", "husband"],
  },
  {
    // daily routine / time of day (kept off food words so dinner replies are unaffected)
    match: /\b(routine|usually|typical|normal day|your day|every ?day|each day|wake|woke|get up|spend your|morning|afternoon|evening|mornings|evenings)\b/i,
    words: ["morning", "garden", "walk", "rest", "tea", "coffee", "reading", "family"],
  },
  {
    // places
    match: /\b(where|place|places|go|going|gone|live|living|spend|visit|visiting|town|outside|nearby)\b/i,
    words: ["home", "garden", "park", "church", "store", "kitchen", "outside", "downtown"],
  },
  {
    // interests / hobbies / likes
    match: /\b(like|likes|enjoy|enjoys|favorite|favourite|hobby|hobbies|interest|interests|fun|love to|cherish|passion)\b/i,
    words: ["reading", "music", "cooking", "gardening", "walking", "family", "painting", "tv"],
  },
  // --- Conversation-mode replies to a partner statement ---
  {
    match: /\b(dinner|eat|eating|food|meal|lunch|breakfast|hungry|cook|come over|over)\b/i,
    words: ["yes", "maybe", "tired", "later", "love", "thank you", "not sure", "hungry"],
  },
  {
    match: /\b(play|playing|game|games|toy|toys|fun)\b/i,
    words: ["maybe", "later", "tired", "soon", "love", "yes", "after", "nap"],
  },
  {
    match: /\b(feeling|feel|okay|ok|alright|how are you|sad|sick|hurt|pain|sleepy)\b/i,
    words: ["okay", "tired", "fine", "happy", "love", "thank you", "better", "resting"],
  },
  {
    match: /\b(bring|need|want|anything|something|soup|water|drink|blanket)\b/i,
    words: ["yes", "no", "water", "thank you", "please", "rest", "soup", "blanket"],
  },
  {
    match: /\b(rest|nap|sleep|lie down|relax)\b/i,
    words: ["yes", "later", "thank you", "okay", "tired", "soon", "please", "now"],
  },
  {
    match: /\b(love|miss|hug|kiss|care)\b/i,
    words: ["love", "yes", "happy", "thank you", "you too", "always", "soon", "okay"],
  },
  {
    match: /\b(time|when|tomorrow|today|tonight|call|phone|weekend|morning|evening|later|soon)\b/i,
    words: ["tomorrow", "later", "maybe", "okay", "soon", "yes", "weekend", "morning"],
  },
];

// Dedupe (case-insensitive), drop words already on the strip, then pad from POOL
// up to `count`, so the row is always full and easy to scan.
function fillTo(seed: string[], exclude: Set<string>, count: number): string[] {
  const out: string[] = [];
  const seen = new Set<string>();
  const add = (w: string) => {
    const k = w.toLowerCase().trim();
    if (!k || seen.has(k) || exclude.has(k)) return;
    seen.add(k);
    out.push(w);
  };
  seed.forEach(add);
  for (const w of POOL) {
    if (out.length >= count) break;
    add(w);
  }
  return out.slice(0, count);
}

// Combine the words from EVERY matching intent category (order preserved).
function contextWords(context?: string): string[] {
  const c = (context ?? "").trim();
  if (!c) return GENERIC_ANSWERS;
  const collected: string[] = [];
  for (const { match, words } of CONTEXT_STARTERS) {
    if (match.test(c)) collected.push(...words);
  }
  return collected.length ? collected : GENERIC_ANSWERS;
}

export interface NextFragmentsProps {
  fragments: string[];
  // The latest partner utterance — used to seed the suggestions.
  context?: string;
  // Explicit, question-specific suggestions (e.g. LLM-generated in Build Your
  // Brain). When provided they take precedence over the keyword categories.
  suggestions?: string[];
  // Mirrors the vocab-tile contract so the view can reuse handleTileTap.
  onSuggest: (tile: VocabTile) => void;
}

function suggestionsFor(
  fragments: string[],
  context?: string,
  provided?: string[],
): string[] {
  const have = new Set(fragments.map((f) => f.toLowerCase().trim()));
  const last = fragments[fragments.length - 1]?.toLowerCase().trim() ?? "";
  const cont = fragments.length ? NEXT_MAP[last] ?? [] : [];
  // Explicit (question-specific) suggestions win; continuations of the last
  // tapped word lead once the user starts building.
  if (provided && provided.length) {
    return fillTo([...cont, ...provided], have, COUNT);
  }
  if (fragments.length === 0) {
    return fillTo(contextWords(context), have, COUNT);
  }
  return fillTo([...cont, ...contextWords(context)], have, COUNT);
}

export default function NextFragments({
  fragments,
  context,
  suggestions: provided,
  onSuggest,
}: NextFragmentsProps) {
  const suggestions = suggestionsFor(fragments, context, provided);

  return (
    <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
      <span className="eyebrow inline-flex items-center gap-1.5">
        <Lightning size={12} weight="fill" aria-hidden className="text-mind" />
        Next
      </span>
      <div role="list" aria-label="Suggested next words" className="flex flex-wrap gap-2">
        {/* Plain buttons (tap-press feedback only). These rows re-render on every
            context/fragment change; framer enter/exit transitions deadlock under
            that churn, so the set just swaps instantly. */}
        {suggestions.map((word) => (
          <motion.button
            key={word}
            role="listitem"
            type="button"
            whileTap={{ scale: 0.96 }}
            onClick={() => onSuggest({ id: `next-${word}`, label: word })}
            className="inline-flex min-h-[2.25rem] items-center rounded-full border border-mind/25 bg-mind-soft px-3.5 font-ui text-[0.9rem] text-text transition-colors duration-fast hover:border-mind/55 hover:text-mind"
          >
            {word}
          </motion.button>
        ))}
      </div>
    </div>
  );
}
