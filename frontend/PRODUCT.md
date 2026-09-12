# Lucid Voice — PRODUCT.md

**Register:** product (design serves the task; the tool should disappear, with one crafted moment).

## What it is
A local-first AAC (augmentative & alternative communication) web app. A person who can't speak
fluently taps 2–3 word fragments; on-device AI proposes a few complete, context-correct
sentences; the person **explicitly selects one** (choose-one / reject-two) and only then is it
spoken aloud in their **own cloned voice**. Never auto-speaks.

## Primary user & scene
**Elena, 67**, expressive aphasia after a stroke. Uses it on a tablet at home and in
conversation. Low energy, word-finding difficulty. Needs **large targets, high legibility, calm
pacing, zero surprise.** A care partner or (for the hackathon demo) judges watch a second
"reasoning" surface that makes the AI's choice legible.

## The one moment
**Fragments → a chosen full sentence → spoken in the person's voice.** Everything else is quiet,
trustworthy console; this single transition is where craft and delight concentrate.

## Surfaces
- **Speak** (hero): vocab tiles → construction strip → "Suggest replies" → candidate sentences →
  select → speak. Integrated **reasoning rail** (heard context, what taps signal, profile facts,
  confidence, grounded memories).
- **Graph** (Phase 5, teammate-owned): live PKG visualization with retrieval highlighting.
- **Conversation**: partner transcript / dictation (secondary).

## Constraints
- Accessibility is non-negotiable: WCAG AA+ contrast, visible focus, full keyboard path,
  `prefers-reduced-motion` honored, color never the only signal.
- Local-first / offline; live backend with deterministic demo fallback. Never auto-speak.

## Design direction (see DESIGN.md for tokens)
Dark "ink" console. **Warm = the human** (their words, voice, primary actions); **cool = the
machine** (reasoning, confidence). Calm and familiar (Linear/Raycast-grade trust), with the
single signature speak moment. Type: one sans superfamily for UI + data, one reading serif for
the spoken human utterance only. Motion conveys state, never decorates.
