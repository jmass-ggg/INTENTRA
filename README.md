# Lucid Voice

Lucid Voice is a local-first AAC (augmentative and alternative communication) web app. The person types or speaks a few fragments; the AI proposes a handful of complete, context-grounded utterance candidates; the person reviews and explicitly selects one — the app **NEVER auto-speaks** anything without explicit selection — and only then does it speak the chosen utterance aloud in the person's own cloned voice. Everything that matters runs on-device, so it keeps working in airplane mode.

## Core Differentiators

- **Local-first / offline.** Generation (LM Studio), speech-to-text (faster-whisper), text-to-speech and voice cloning (Coqui XTTS-v2), the knowledge graph (Kuzu), and embeddings (sentence-transformers) all run on-device. The app survives airplane mode. Cloud providers are strictly opt-in via environment variables.
- **Personal Knowledge Graph (PKG).** Each person has their own graph of people, places, topics, routines, and preferences, stored locally in Kuzu. Utterances are grounded in this graph rather than hallucinated.
- **Hybrid GraphRAG.** Retrieval combines semantic embedding search with graph traversal over the PKG to assemble a grounded subgraph, which conditions generation and is surfaced for transparency.
- **Online learning loop.** When the person confirms an utterance, the graph reinforces the nodes and edges that were used; a periodic consolidation step promotes recurring patterns into durable structure.
- **Multi-modal input.** Fragments can be typed, dictated (STT), or assembled from context (time, place, present people), and the spoken output uses the person's cloned voice.

## Tech Stack

**Backend**

- [FastAPI](https://fastapi.tiangolo.com/) — HTTP API
- [Kuzu](https://kuzudb.com/) — embedded graph database (the PKG)
- [sentence-transformers](https://www.sbert.net/) — local embeddings
- [LM Studio](https://lmstudio.ai/) — local LLM server, OpenAI-compatible API at `http://localhost:1234/v1`
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) — local speech-to-text
- [Coqui XTTS-v2](https://github.com/coqui-ai/TTS) — local text-to-speech and voice cloning

**Frontend**

- [Vite](https://vitejs.dev/) + [React](https://react.dev/) + [TypeScript](https://www.typescriptlang.org/)
- [Tailwind CSS](https://tailwindcss.com/) — styling
- [Framer Motion](https://www.framer.com/motion/) — animation
- [react-force-graph](https://github.com/vasturiano/react-force-graph) — graph visualization

## Provider Abstraction

Every external capability goes through a provider interface so the local default can be swapped for a cloud provider by setting an environment variable. **With zero API keys and zero configuration, every provider defaults to a fully local implementation** — the app runs offline out of the box.

| Capability | Env var | Default (local) | Opt-in cloud alternative |
| --- | --- | --- | --- |
| LLM | `LLM_PROVIDER` | `lmstudio` (`http://localhost:1234/v1`) | `anthropic` (requires `ANTHROPIC_API_KEY`) |
| Embedding | `EMBEDDING_PROVIDER` | `sentence-transformers` (on-device) | cloud embeddings (requires API key) |
| STT | `STT_PROVIDER` | `faster-whisper` (on-device) | cloud STT (requires API key) |
| TTS | `TTS_PROVIDER` | `xtts` (Coqui XTTS-v2, on-device) | cloud TTS (requires API key) |

Related env vars: `LLM_BASE_URL` (defaults to `http://localhost:1234/v1`), `LLM_MODEL`, `ANTHROPIC_API_KEY` (only read when `LLM_PROVIDER=anthropic`), `DEMO_MODE`. See `backend/.env.example` for the full list.

## Prerequisites

- **Python 3.11+**
- **Node 18+**
- **FFmpeg** — required by local voice synthesis (Coqui XTTS-v2 → torchcodec). macOS: `brew install ffmpeg`. Without it, `/speak` still serves cached audio and falls back gracefully.
- **LM Studio** running and serving any instruct model on `http://localhost:1234` (use the LM Studio "Local Server" feature).

> Note: the local-first ML dependencies (Kuzu, sentence-transformers, faster-whisper, Coqui XTTS-v2) are heavy and may take a while to install and to download model weights on first run (XTTS-v2 fetches ~1.8GB).

### Voice setup (XTTS-v2)

The local TTS is the maintained **`coqui-tts`** (idiap fork) running XTTS-v2 for zero-shot voice cloning. To give a person a cloned voice:

```bash
cd backend
# Enroll a reference wav (a short, clean ~10s recording works best):
python -m data.enroll_voice elena path/to/elena.wav
# Pre-render the demo's chosen lines into the audio cache (instant in DEMO_MODE):
python -m data.prerender_demo elena
```

`/speak` is cache-first (sha256 of person+text), so repeated lines and the pre-rendered demo lines return instantly. On Apple Silicon XTTS runs on CPU (MPS is unreliable for XTTS); first-call synthesis of a sentence takes ~15–20s, then it's cached.

## Quickstart

```bash
cd aac
./run.sh
```

`run.sh` creates/reuses a virtualenv, installs backend and frontend dependencies if needed, copies `.env.example` to `.env` if missing, then starts both servers together.

### Manual steps

**Backend**

```bash
cd aac/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

**Frontend** (in a second terminal)

```bash
cd aac/frontend
npm install
npm run dev
```

- Backend API: **http://localhost:8000**
- Frontend: **http://localhost:5173** (the dev server proxies `/api` to the backend)

## DEMO_MODE and the Offline Guarantee

Set `DEMO_MODE=true` in `backend/.env` to run the app against deterministic, bundled fixtures — no LM Studio, no model downloads, no network. This is useful for development, CI, demos, and presentations where reproducible output matters.

The **offline guarantee**: with the default configuration, Lucid Voice never makes a network call off-device. The LLM, STT, TTS/voice-clone, graph, and embeddings all run locally, so the app keeps functioning in airplane mode. Cloud providers are only reached when you explicitly opt in by setting a provider env var (and supplying the corresponding API key). `DEMO_MODE` is even stricter: it touches no external service at all.

## Build Order (8 Phases)

1. **Scaffold** — runnable project skeleton, API contract, stubbed endpoints, frontend shell.
2. **Graph + seed** — Kuzu schema and seed data for the Personal Knowledge Graph.
3. **Retrieval + `/generate` + SpeakerView** — hybrid GraphRAG and the candidate-generation UI.
4. **`/speak` (XTTS) + cache** — voice-cloned TTS with an on-disk audio cache.
5. **GraphView** — interactive visualization of the PKG.
6. **Learning** — `/confirm` reinforcement and `/consolidate` promotion of recurring patterns.
7. **`/stt` + ConversationView** — dictation and the conversation interface.
8. **DEMO_MODE fixtures** — deterministic fixtures for offline demos and CI.

### Routes

- `/` — SpeakerView (compose fragments, review candidates, select, and speak).
- `/conversation` — ConversationView (dictation and turn-by-turn conversation).
- `/graph` — GraphView (explore the Personal Knowledge Graph).
