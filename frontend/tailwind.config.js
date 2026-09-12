/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        // ── Lucid Voice LIGHT palette ─────────────────────────────────────
        // Bright, airy daylight console. Token NAMES kept ("ink"/"text") so all
        // components re-theme by value; canvas is a soft cool off-white (not the
        // AI cream, not pure white). Accents: vivid coral (human) + teal (machine).
        ink: "#F5F7FA", // app canvas (soft cool off-white)
        "ink-raised": "#FFFFFF", // cards, strip, rail surfaces (clean elevation)
        "ink-sunken": "#E9EDF3", // wells (vocab board, inputs)
        "ink-line": "#D6DEE8", // hairline borders / dividers

        text: "#161A21", // primary text (near-black, high contrast)
        "text-muted": "#566273", // secondary text / labels (AA on white, ~6.6:1)
        "text-faint": "#6B7392", // placeholders / disabled only (AA ~4.5:1 on white)

        // THE HUMAN — vivid coral (their words, their voice, primary actions).
        voice: "#E14826",
        "voice-deep": "#C23A1B", // hover / pressed
        "voice-soft": "#FCE9E3", // light coral tint (selected utterance / chips)
        "on-voice": "#FFFFFF", // text/icons on a coral fill

        // THE MACHINE — teal (reasoning, confidence, machine state).
        mind: "#0C8276",
        "mind-deep": "#0A6B61", // AA-safe teal for persistent labels on mind-soft
        "mind-soft": "#DBF1ED", // light teal tint (rail panel)

        // Register triad — tone tags, ALWAYS paired with a text label, AA on light.
        register: {
          warm: "#C2410C", // burnt coral
          neutral: "#5B45C9", // indigo-violet
          direct: "#0C8276", // teal
        },

        // Legacy calm palette retained for non-focus views (Conversation/Graph).
        calm: {
          bg: "#f4f6f8",
          surface: "#ffffff",
          border: "#e2e8ec",
          text: "#2b3440",
          muted: "#6b7785",
          primary: "#5b8a9b",
          "primary-soft": "#cfe2e8",
          accent: "#8aa6b0",
          warm: "#d9b48f",
          neutral: "#9fb3bd",
          direct: "#7e9aa6",
        },
      },
      fontFamily: {
        // One sans/mono superfamily (Geist) for the interface + the machine's
        // data; one reading serif (Newsreader) reserved for the human utterance.
        ui: ['"Geist"', "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ['"Geist Mono"', "ui-monospace", "SFMono-Regular", "monospace"],
        utter: ['"Newsreader"', "ui-serif", "Georgia", "serif"],
      },
      spacing: {
        // Large touch-friendly defaults (preserve AAC ergonomics).
        touch: "3.5rem",
        "touch-lg": "5rem",
        tile: "6rem", // tiles ≥ 96px tall
        cta: "4rem", // CTAs ≥ 64px
      },
      minHeight: {
        touch: "3.5rem",
        tile: "6rem",
        cta: "4rem",
      },
      minWidth: {
        touch: "3.5rem",
        cta: "4rem", // mirrors minHeight.cta so the primary play button stays square-ish
        tile: "6rem",
      },
      borderRadius: {
        // Locked radius scale (one system, applied consistently).
        xl: "20px", // cards, stage, rail
        lg: "14px", // tiles, strip, inputs
        md: "10px", // small buttons / chips
        calm: "1.25rem", // legacy (Conversation/Graph)
      },
      transitionTimingFunction: {
        // Exponential ease-out — confident, no bounce. (impeccable motion rule)
        "out-expo": "cubic-bezier(0.16, 1, 0.3, 1)",
        "out-quart": "cubic-bezier(0.25, 1, 0.5, 1)",
      },
      transitionDuration: {
        // Mirror lib/motion.ts DUR so CSS + Framer share one motion vocabulary.
        fast: "160ms",
        base: "220ms",
        moment: "420ms",
      },
      fontSize: {
        // AAC-readable base sizes (retained).
        "aac-base": ["1.0625rem", { lineHeight: "1.6" }],
        "aac-lg": ["1.5rem", { lineHeight: "1.5" }],
        "aac-xl": ["2.5rem", { lineHeight: "1.3" }],
        // New scale roles (DESIGN.md type scale).
        stage: ["clamp(2rem, 4.5vw, 3.25rem)", { lineHeight: "1.15" }],
        candidate: ["clamp(1.5rem, 2.4vw, 2rem)", { lineHeight: "1.25" }],
        tile: ["1.5rem", { lineHeight: "1.2" }],
        eyebrow: ["0.8125rem", { lineHeight: "1.4", letterSpacing: "0.12em" }],
        reason: ["0.95rem", { lineHeight: "1.5" }],
      },
      boxShadow: {
        // Soft, ink-tinted shadows for a light surface (no heavy black drops).
        card: "0 1px 2px 0 rgba(22,26,33,0.04), 0 10px 24px -14px rgba(22,26,33,0.12)",
        lift: "0 2px 6px 0 rgba(22,26,33,0.07), 0 18px 36px -18px rgba(22,26,33,0.16)",
        // The speak moment's warmth: a coral-tinted shadow, not a neon glow.
        utter: "0 2px 8px 0 rgba(225,72,38,0.12), 0 20px 44px -20px rgba(225,72,38,0.30)",
      },
    },
  },
  plugins: [],
};
