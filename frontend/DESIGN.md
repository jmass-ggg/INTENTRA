# Lucid Voice — Design System (Speaker view)

> Design lead: **🖌️ Gigi**. Implemented by **🎨 Fiona** in `frontend/`.
> Direction chosen by the CEO: **bold & premium showpiece**, accessible for a user with
> aphasia, impressive for hackathon judges. Surface for this build: **the Speaker view**
> (the full AAC loop) with an integrated **reasoning rail**. Data: **live backend + demo fallback**.

## Thesis — "The Console of a Returning Voice"

A few tapped fragments become a full sentence, spoken in the person's own voice. The UI
dramatizes exactly that transformation and makes the AI's reasoning legible. Every choice
encodes the product's core duality:

- **Warm amber = the human** — their words, their cloned voice, the primary actions.
- **Cool aqua = the machine's mind** — the reasoning trail, confidence, the "thinking" state.

This two‑tone semantic (not decoration) is the spine of the whole design.

## Color tokens (dark "ink" canvas)

Deep, warm indigo‑black — premium and calm, never clinical, never pure black.

| Token | Hex | Use |
|---|---|---|
| `ink` | `#14121C` | app canvas |
| `ink-raised` | `#1E1B29` | cards, strip, rail surfaces |
| `ink-sunken` | `#100E16` | wells (vocab board, transcript) |
| `ink-line` | `#2C2838` | hairline borders/dividers |
| `text` | `#F4EFE9` | primary text (warm off‑white, "paper") |
| `text-muted` | `#A39DB0` | secondary text/labels (lavender‑grey) |
| `text-faint` | `#6E6880` | placeholders, disabled |
| **`voice`** | `#FF9E5E` | THE HUMAN — primary CTAs, speak, chosen utterance glow |
| `voice-deep` | `#F0743E` | voice gradient end / pressed |
| `voice-soft` | `#3A2A24` | voice tint on dark (selected card bg) |
| **`mind`** | `#5FE3D2` | THE MACHINE — reasoning rail accents, confidence, "thinking" |
| `mind-soft` | `#1B2E30` | mind tint on dark (rail panel bg) |

**Register triad** (tone of a candidate sentence — always paired with a text label, never color‑only):

| Register | Hex | Feel |
|---|---|---|
| `warm` | `#FFB778` | amber — affectionate |
| `neutral` | `#B9A8FF` | soft violet — even |
| `direct` | `#6FE3D2` | aqua — concise |

Contrast: `text` on `ink` ≈ 14:1; dark text (`ink`) on `voice` ≈ 8:1. All AA+.

## Typography — a tri‑face system (each face means something)

Load via Google Fonts (no npm deps). `<link>` in `index.html`.

- **Fraunces** (`opsz`, weights 400/500/600, soft optical) → **the human utterance**: candidate
  sentences, the live "now speaking" line. Literary, warm, emotional. `font-utter`.
- **Bricolage Grotesque** (400/500/600/700) → **the interface**: headings, tiles, labels, body. `font-ui`.
- **IBM Plex Mono** (400/500) → **the machine**: reasoning rail, confidence %, trace, eyebrows/kbd. `font-mono`.

### Type scale
| Role | Family | Size (clamp) | Weight | Notes |
|---|---|---|---|---|
| Stage utterance (speaking) | Fraunces | `clamp(2rem, 4.5vw, 3.25rem)` | 500 | line-height 1.15 |
| Candidate sentence | Fraunces | `clamp(1.5rem, 2.4vw, 2rem)` | 500 | line-height 1.25 |
| Tile label | Bricolage | `1.5rem` | 600 | — |
| H1 / wordmark | Bricolage | `1.5rem` | 700 | tight tracking `-0.02em` |
| Body / rationale | Bricolage | `1.0625rem` | 400 | — |
| Eyebrow / label | IBM Plex Mono | `0.8125rem` | 500 | uppercase, tracking `0.12em` |
| Reasoning line | IBM Plex Mono | `0.95rem` | 400 | line-height 1.5 |

## Shape, spacing, depth
- Radii: `xl` 24px (cards), `lg` 18px (tiles/strip), `md` 12px (chips/buttons), pill 999px.
- Touch targets: tiles ≥ 96px tall, CTAs ≥ 64px, secondary ≥ 48px (preserve AAC ergonomics).
- Depth from **light, not heavy shadow**: cards = `ink-raised` + 1px `ink-line` + soft ambient
  `0 1px 0 rgba(255,255,255,0.03) inset, 0 20px 50px -30px rgba(0,0,0,0.8)`.
- **Ambient glow**: a faint warm radial behind the stage (`voice` at ~6% alpha), which
  intensifies during the speaking state. Pure CSS; respects reduced‑motion.

## Layout — the Speaker console

Responsive two‑zone. Desktop/tablet‑landscape: **stage** (flex) + **reasoning rail** (380px).
Below `lg`: rail collapses under the stage. Vocab board is a full‑width well at the bottom.

```
┌───────────────────────────────────────────────────────────────┐
│  ◐ LUCID VOICE        Elena ▾        ● on‑device · airplane‑ok │  top bar
├───────────────────────────────────────────┬───────────────────┤
│  STAGE                                     │  REASONING RAIL    │
│   ┌ construction strip ───────────┐        │  (font-mono, mind) │
│   │ cold · window         clear ✕ │        │  HEARD ────────    │
│   └───────────────────────────────┘        │  “Mom, dinner…”    │
│   [  ▸ Suggest replies  ]  ← voice CTA      │  TAPS SIGNAL ──    │
│                                            │   • cold • window  │
│   ── candidates bloom (stagger) ──         │  PROFILE ──        │
│   ┌───────────────────────────────┐ warm   │   • sweetie (Sofia)│
│   │ Could you close the window?    │  ▸     │  CONFIDENCE        │
│   │ I'm getting cold.              │        │   ▓▓▓▓▓▓▓░░ 0.82   │
│   └───────────────────────────────┘        │                    │
│   ┌ neutral … ┐  ┌ direct … ┐               │  grounded in 4 mem │
├───────────────────────────────────────────┴───────────────────┤
│  VOCAB · People  Feelings  Needs  Social                        │  well
│  [ Sofia ] [ Mateo ] [ Marco ] [ tired ] [ maybe ] [ water ]…   │
└───────────────────────────────────────────────────────────────┘
```

## State machine (drives stage + rail + indicator)
`idle → listening → thinking → candidates → speaking → idle`
- **idle**: dim ambient; strip empty placeholder "Tap words to begin." StateIndicator `mind` dot, steady.
- **listening**: fragments present; CTA enabled (`voice`); indicator pulses.
- **thinking**: CTA shows spinner; reasoning rail **streams in** line‑by‑line (mono), confidence
  bar fills; candidates area shows 3 shimmer skeletons.
- **candidates**: 3 cards bloom (stagger 60ms, y+8→0, opacity). Escape hatches below.
- **speaking**: chosen card **rises + voice glow**; the other two **desaturate, shrink to 0.96,
  drop to 0.35 opacity** (visible rejection = the authorship beat). Waveform bars animate while
  audio plays; ambient glow intensifies. On end → idle (chosen utterance lingers on the stage).

## Components (build these in `frontend/src`)

1. **`App.tsx` shell** — dark `ink` canvas, top bar with wordmark (◐ mark + "Lucid Voice"),
   person pill ("Elena ▾", static for now), and an honest status chip "on‑device · airplane‑ok"
   (`mind` dot). Nav (Speak / Conversation / Graph) restyled as quiet pill tabs; Speak active.
   Route transitions keep the existing 0.18s fade.
2. **`VocabBoard.tsx`** — category sections, tiles `ink-raised` → hover lift + `voice`-tinted
   ring, `whileTap` 0.96. Tile flings its label up to the strip on tap (motion handled in view).
3. **`ConstructionStrip.tsx`** — `ink-raised`, chips with a small ✕ to remove each fragment
   (add per‑chip remove — improvement over current clear‑all‑only). Clear button at right.
4. **`CandidateCard.tsx`** — Fraunces sentence, register pill (triad color + label), length chip,
   mono rationale (the "why"), and a `voice` "Say this ▸" action. Props add: `selected`,
   `rejected`, `playing` to drive the speaking‑state choreography; waveform bars when `playing`.
5. **`ReasoningRail.tsx`** (NEW) — the laptop "decision trail." Sections HEARD / TAPS SIGNAL /
   PROFILE / CONFIDENCE / GROUNDED, all `font-mono`, `mind` accents. Reads from the `/generate`
   response (`trace`, `retrieval.confidence`, fragments, context). Confidence = animated bar +
   numeric. Empty state: "Waiting for your words." Streams in during `thinking`.
6. **`StateIndicator.tsx`** — pill with colored dot per state (idle=`mind`, listening=`voice`,
   thinking=`mind` pulse, candidates=register‑violet, speaking=`voice`), label in mono.
7. **`PlaybackButton.tsx` / waveform** — the speak control + a reusable `<Waveform playing/>`
   (animated bars in `voice`). Keep the component; restyle to `voice`.
8. **`Stage`** (can live inside SpeakerView) — hosts strip, CTA, candidates, and the
   speaking utterance; owns the ambient glow.

## Data wiring (live + demo fallback)
- `generate({person_id, fragments, context, situation})` → render candidates + feed the rail.
  On network error, empty candidates, or `abstain`, fall back to bundled **demo content**.
- Add `frontend/src/lib/demo.ts`: rich, deterministic content for the three demo inputs from the
  Idea Lab synthesis, keyed by the same signature the backend uses
  (`frag1|frag2|...||context`):
  - `cold|window||` → 3 candidates; chosen line *"Could you close the window? I'm getting cold."*
  - `tired|maybe||Mom, do you want to come for dinner Sunday?` → chosen *"I'm a little tired, sweetie, so maybe."*
  - `tired|maybe||Grandma, will you play with me?` → chosen *"I'm a bit tired, mijo, but maybe we can play."*
  Each candidate has register, length_label, a human rationale, and trace‑like reasoning lines
  (heard / taps signal / profile facts / confidence) so the rail is alive offline.
- **Selection (authorship beat):** clicking "Say this" sets `selected`, marks the rest `rejected`,
  calls `confirm(...)` (fire‑and‑forget), then **plays audio** — and only then. The app **NEVER
  auto‑speaks**; nothing plays without an explicit click.
- **Playback chain (never silent):** `speak({person_id, text})` → if `audio_base64` present,
  play it; **else** fall back to the browser `SpeechSynthesis` API so the demo always speaks,
  even with no XTTS/network. A `useSpeak()` hook owns this + the playing state.
- A demo persona's vocab tiles should include the demo people (Sofia, Mateo, Marco) and the demo
  words (cold, window, tired, maybe) so all three rounds are tappable.

## Accessibility (non‑negotiable)
- Contrast AA+ (values above). Color never the only signal (register + length always labeled).
- Visible focus ring: `3px solid voice`, offset 2px, on every interactive element.
- Full keyboard path: tiles, CTA, cards, escape hatches, remove‑chip all reachable & operable.
- `prefers-reduced-motion`: disable bloom/glow/waveform animation → instant, calm states.
- `aria-live="polite"` on the StateIndicator and on the candidates region.
- Large targets retained (tiles ≥96px, CTA ≥64px). Body base stays ≥1.0625rem.

## Motion budget (Framer Motion, already installed)
Page settle (stagger), tile tap (0.96), fragment fly‑in, reasoning stream, candidate bloom
(stagger 60ms), selection choreography (chosen rise + reject recede), waveform. Nothing else —
spend the boldness on the **speak moment**; keep all else quiet.

— 🖌️ Gigi (Graphic / UX Designer)

---

## Elevation v2 (current — supersedes the specifics above)

Pass applying **design-motion-principles + taste + impeccable** (product register: a calm, trustworthy
console with ONE crafted moment; not decoration everywhere).

- **Type** — one sans/mono superfamily + one reading serif (replaces Fraunces/Bricolage/Plex):
  `font-ui` = **Geist**, `font-mono` = **Geist Mono**, `font-utter` = **Newsreader** (the human
  utterance ONLY). Fraunces dropped — it's a saturated AI-tell serif.
- **Color** — same ink canvas + warm(`voice`)/cool(`mind`) semantic; register violet desaturated away
  from "AI purple". **All neon/outer glows removed.**
- **Material** — depth via TINTED shadows: `shadow-card` / `shadow-lift`, and `shadow-utter` (warm
  tinted shadow = the speak moment's warmth). Radius lock: cards `xl`=20, tiles/strip/inputs `lg`=14,
  small `md`=10, pills full.
- **Motion** (`src/lib/motion.ts`: `EASE_OUT` cubic-bezier(0.16,1,0.3,1), low-bounce `SPRING`, `DUR`).
  Conveys state, never decorates. Removed: StateIndicator pulse, `glowPulse` loop, the 3 pulsing
  skeletons. Now: dot-color + label crossfade; ONE calm shimmer skeleton; the candidate bloom is the
  ONE staggered blur-in moment; chosen rises on a soft spring, others recede; Waveform only during real
  audio; `stage-wash` is a faint static state tint. All gated by `<MotionConfig reducedMotion="user">`.
- **Icons** — **Phosphor** (`@phosphor-icons/react`) replace the text glyphs (▸ ✕ ▾): SpeakerHigh,
  Sparkle, Ear, CircleNotch, X, CaretRight, CaretDown.
- **Reasoning rail confidence** — a slim **segmented meter** (12 ticks), not a chunky filled track.
- **Data wiring** — prefers the curated demo unless the live model truly answered (≥2 non-abstain
  candidates); a single degraded backend candidate no longer loses the divergence demo.

— 🖌️ Gigi

---

## Elevation v3 (current) — LIGHT theme

Per the CEO's call, flipped to a bright, airy **light** interface (token names kept; values flipped):
- Canvas `ink` = soft cool off-white `#F5F7FA` (not cream, not pure white); surfaces `ink-raised` =
  white; wells `ink-sunken` = `#E9EDF3`; lines `#D6DEE8`. Text near-black `#161A21` / muted `#566273`.
- **Accents:** the human = **vivid coral** `voice #E14826` (white text on fills via `on-voice`); the
  machine = **teal** `mind #0C8276`. Register tags re-tuned for AA on light (warm `#C2410C`, neutral
  indigo `#5B45C9`, direct teal). Shadows are soft ink-tinted (no heavy black drops); the speak
  moment keeps a coral-tinted `shadow-utter`. `stage-wash` is a faint coral wash.
- All contrast re-checked for AA on light; dark-overlay hover assumptions fixed.
- Anti-slop review fixes folded in: em-dashes removed from user-facing strings; faint text on
  meaningful copy bumped to `text-muted`.

Note: Tailwind config (token) changes require a dev-server restart to take effect.

— 🖌️ Gigi
