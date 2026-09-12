// Lucid Voice — deterministic demo fallback.
//
// When the live backend is unreachable, abstains, or returns zero candidates,
// ConversationView's handleGenerate falls back to this bundled content so the
// demo ALWAYS has rich, divergent candidates. Content is keyed by the same
// signature the backend uses: `frag1|frag2|...||context`.

import type { Candidate, GenerateResponse } from "./api";

// Reasoning lines that feed the ReasoningRail in offline / fallback mode.
export interface DemoReasoning {
  heard: string;
  tapsSignal: string[];
  profile: string[];
  confidence: number;
  grounded: string[];
}

export interface DemoEntry {
  candidates: Candidate[];
  reasoning: DemoReasoning;
  // The "chosen" line that prerendered audio (if any) matches.
  chosen: string;
}

// Build the canonical signature from a request's fragments + context.
export function demoSignature(fragments: string[], context?: string): string {
  return `${fragments.join("|")}||${context ?? ""}`;
}

// Normalize a signature for case-insensitive / trimmed matching.
function normalize(sig: string): string {
  return sig.trim().toLowerCase();
}

const DEMO: Record<string, DemoEntry> = {
  // ── Round 1 — no heard context ──────────────────────────────────────────
  "cold|window||": {
    chosen: "Could you close the window? I'm getting cold.",
    candidates: [
      {
        text: "Could you close the window? I'm getting cold.",
        register: "warm",
        length_label: "full",
        rationale: "A polite request with a reason, in Elena's warm default.",
        grounded_node_ids: [],
      },
      {
        text: "Please close the window. I'm cold.",
        register: "neutral",
        length_label: "medium",
        rationale: "Even and clear.",
        grounded_node_ids: [],
      },
      {
        text: "Close the window? I'm cold.",
        register: "direct",
        length_label: "short",
        rationale: "Fewest words.",
        grounded_node_ids: [],
      },
    ],
    reasoning: {
      heard: "",
      tapsSignal: ["cold → discomfort", "window → the cause"],
      profile: ["Elena: warm, former teacher", "polite by default"],
      confidence: 0.86,
      grounded: ["window", "comfort routine"],
    },
  },

  // ── Round 2 — speaker = Sofia (daughter) ────────────────────────────────
  "tired|maybe||mom, do you want to come for dinner sunday?": {
    chosen: "I'm a little tired, sweetie, so maybe.",
    candidates: [
      {
        text:
          "I'd love to, sweetie, but I've been so tired lately. Can I tell you Saturday?",
        register: "warm",
        length_label: "full",
        rationale: "Warm, uses 'sweetie', defers instead of committing.",
        grounded_node_ids: [],
      },
      {
        text: "I'm a little tired, sweetie, so maybe.",
        register: "neutral",
        length_label: "medium",
        rationale: "Soft maybe, keeps the address term.",
        grounded_node_ids: [],
      },
      {
        text: "Maybe, sweetie. I'm tired.",
        register: "direct",
        length_label: "short",
        rationale: "Short, still warm.",
        grounded_node_ids: [],
      },
    ],
    reasoning: {
      heard: "Mom, do you want to come for dinner Sunday?",
      tapsSignal: ["tired → low energy", "maybe → not committing"],
      profile: [
        "Sofia = daughter, called 'sweetie'",
        "register: warm-adult",
        "Elena avoids committing early",
      ],
      confidence: 0.82,
      grounded: ["Sofia (daughter)", '"sweetie"', "commitment-averse"],
    },
  },

  // ── Round 3 — speaker = Mateo (grandson). SAME taps, different register. ─
  "tired|maybe||grandma, will you play with me?": {
    chosen: "I'm a bit tired, mijo, but maybe we can play.",
    candidates: [
      {
        text:
          "I'm a little tired right now, mijo. Maybe after my nap? I love you.",
        register: "warm",
        length_label: "full",
        rationale:
          "Playful-gentle, uses 'mijo', reassures with a promise of later.",
        grounded_node_ids: [],
      },
      {
        text: "I'm a bit tired, mijo, but maybe we can play.",
        register: "neutral",
        length_label: "medium",
        rationale: "Gentle maybe, keeps 'mijo'.",
        grounded_node_ids: [],
      },
      {
        text: "Tired now, mijo. Maybe later?",
        register: "direct",
        length_label: "short",
        rationale: "Short, still tender.",
        grounded_node_ids: [],
      },
    ],
    reasoning: {
      heard: "Grandma, will you play with me?",
      tapsSignal: ["tired → low energy", "maybe → soft yes / defer"],
      profile: [
        "Mateo = grandson, age 4, called 'mijo'",
        "register: playful-gentle",
        "reassure + promise of later",
      ],
      confidence: 0.8,
      grounded: ["Mateo (grandson)", '"mijo"', "playful-gentle"],
    },
  },
};

// Pre-normalized lookup table built once at module load.
const DEMO_NORMALIZED: Record<string, DemoEntry> = Object.fromEntries(
  Object.entries(DEMO).map(([k, v]) => [normalize(k), v]),
);

// Look up a demo entry by fragments + context (case-insensitive / trimmed).
export function demoLookup(
  fragments: string[],
  context?: string,
): DemoEntry | null {
  const sig = normalize(demoSignature(fragments, context));
  return DEMO_NORMALIZED[sig] ?? null;
}

// Build a GenerateResponse from a demo entry, or null if no match.
export function demoGenerate(req: {
  fragments: string[];
  context?: string;
}): GenerateResponse | null {
  const entry = demoLookup(req.fragments, req.context);
  if (!entry) return null;
  return {
    candidates: entry.candidates,
    retrieval: {
      anchor_ids: [],
      subgraph_node_ids: [],
      subgraph_edge_ids: [],
      confidence: entry.reasoning.confidence,
    },
    trace: { source: "demo", reasoning: entry.reasoning },
    abstain: false,
  };
}

// Expose reasoning for the rail (used by both live + demo paths).
export function demoReasoning(
  fragments: string[],
  context?: string,
): DemoReasoning | null {
  const entry = demoLookup(fragments, context);
  return entry ? entry.reasoning : null;
}
