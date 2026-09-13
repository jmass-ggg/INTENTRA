"""FastAPI application entrypoint for Intentra.

This is the Phase 1 SCAFFOLD. Every endpoint returns a correctly-SHAPED
placeholder response so the app is runnable end-to-end. Real logic lands in
later phases (see BUILD ORDER). Heavy/optional providers and services are
imported and instantiated lazily so the app starts even when on-device
dependencies (kuzu, sentence-transformers, TTS/coqui, faster-whisper) or
optional cloud SDKs are missing.
"""

from __future__ import annotations

import logging
import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.observability import init_sentry, add_breadcrumb, set_tag, span
from app.tracing import init_tracing
from app.models import (
    AssistantTurnRequest,
    AssistantTurnResponse,
    ConfirmRequest,
    ConfirmResponse,
    ConsolidateRequest,
    ConsolidateResponse,
    EnrollRequest,
    EnrollResponse,
    GenerateRequest,
    GenerateResponse,
    GraphResponse,
    HealthResponse,
    SpeakRequest,
    SpeakResponse,
    STTRequest,
    STTResponse,
    StyleProfile,
    Candidate,
    RetrievalInfo,
)
from app.domain.communication import CommunicationInput
from app.domain.intent import IntentFrame, IntentType
from app.domain.passport import CommunicationPassport
from app.security import validate_person_id

logger = logging.getLogger("intentra")

# Initialize Sentry as early as possible (before the app/middleware are built) so
# the FastAPI/Starlette integrations capture every request. No-op without a DSN.
init_sentry()

# Initialize Phoenix/OpenInference LLM tracing. No-op unless PHOENIX_ENABLED.
init_tracing()

app = FastAPI(title="Intentra")

# CORS for the Vite dev server.
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Most recent /generate trace, served by GET /trace/latest. Kept in-process as
# the fallback; mirrored to Redis (agent/session memory) when Redis is enabled.
latest_trace: dict = {}


def _store_trace(trace: dict) -> None:
    """Persist the latest trace in-process AND in Redis (when available)."""
    global latest_trace
    latest_trace = trace
    rs = _get("redis")
    if rs is not None and getattr(rs, "available", False):
        try:
            rs.set_latest_trace(trace)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("redis set_latest_trace failed: %s", exc)


def _read_trace() -> dict:
    """Read the latest trace from Redis when available, else in-process."""
    rs = _get("redis")
    if rs is not None and getattr(rs, "available", False):
        try:
            v = rs.get_latest_trace()
            if v is not None:
                return v
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("redis get_latest_trace failed: %s", exc)
    return latest_trace


# --- Lazy service / provider wiring -----------------------------------------
#
# Services and providers are built lazily so a missing heavy dependency never
# crashes import. Each helper caches its result in `_services` and degrades to
# None (with a warning) on failure; endpoints stay shaped regardless.

_singletons: dict = {}


def _get(name: str):
    """Lazily construct and cache a provider/service with its dependencies.

    Returns the instance, or None if construction fails (logged). Endpoints
    degrade to correctly-shaped placeholders in the None case, so a missing
    heavy dependency never crashes the API.
    """
    if name in _singletons:
        return _singletons[name]

    inst = None
    try:
        if name == "graph":
            from app.services.graph import GraphService

            inst = GraphService()
            inst.connect()  # opens/creates Kuzu + schema
        elif name == "embedding":
            from app.providers import get_embedding_provider

            inst = get_embedding_provider()
        elif name == "llm":
            from app.providers import get_llm_provider

            inst = get_llm_provider()
        elif name == "redis":
            from app.services.redis_store import get_redis_store

            inst = get_redis_store()
        elif name == "retrieval":
            from app.services.retrieval import RetrievalService

            inst = RetrievalService(
                _get("graph"), _get("llm"), _get("embedding"), redis_store=_get("redis")
            )
        elif name == "generation":
            from app.services.generation import GenerationService

            inst = GenerationService(_get("llm"))
        elif name == "learning":
            from app.services.learning import LearningService

            inst = LearningService(_get("graph"), _get("llm"), _get("embedding"))
        elif name == "cache":
            from app.services.cache import CacheService

            inst = CacheService()
        elif name == "tts":
            from app.providers import get_tts_provider

            inst = get_tts_provider()
        elif name == "stt":
            from app.providers import get_stt_provider

            inst = get_stt_provider()
        elif name == "style":
            from app.services.style import StyleService

            inst = StyleService(_get("graph"))
        elif name == "intent":
            from app.services.intent import IntentService

            inst = IntentService(_get("llm"))
        elif name == "passport":
            from app.services.passport import PassportService

            inst = PassportService(_get("graph"), _get("style"), _get("learning"))
        elif name == "identity_guard":
            from app.services.identity_guard import IdentityGuard

            inst = IdentityGuard(_get("style"))
        elif name == "confidence_router":
            from app.services.confidence import ConfidenceRouter

            inst = ConfidenceRouter()
        elif name == "communication":
            from app.services.communication import CommunicationService

            inst = CommunicationService(
                _get("intent"),
                _get("retrieval"),
                _get("generation"),
                _get("identity_guard"),
                _get("passport"),
                _get("confidence_router"),
            )
        elif name == "effort":
            from app.services.effort import EffortService

            inst = EffortService(_get("graph"), _get("passport"))
        elif name == "fast_response":
            from app.services.fast_response import FastResponseEngine

            inst = FastResponseEngine()
    except Exception as exc:  # pragma: no cover - defensive guard
        logger.warning("Could not initialize %r: %s", name, exc)
        inst = None

    _singletons[name] = inst
    return inst


def get_retrieval_service():
    return _get("retrieval")


def get_generation_service():
    return _get("generation")


def get_graph_service():
    return _get("graph")


def get_learning_service():
    return _get("learning")


def get_cache_service():
    return _get("cache")


def _provider_status() -> dict:
    """Best-effort report of the configured providers for /health.

    Reflects the env-selected provider names without instantiating heavy
    providers, so this stays cheap and import-safe.
    """
    status = {
        "llm": settings.llm_provider,
        "embedding": settings.embedding_provider,
        "stt": settings.stt_provider,
        "tts": settings.tts_provider,
        "sentry": "on" if getattr(settings, "sentry_dsn", "") else "off",
    }
    # Redis (vector KNN + cache + agent memory) — reflect live availability.
    if getattr(settings, "redis_enabled", False):
        rs = _get("redis")
        status["redis"] = rs.status() if rs is not None else {"enabled": True, "available": False}
    else:
        status["redis"] = {"enabled": False, "available": False}
    return status


# --- Endpoints --------------------------------------------------------------


@app.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    """Liveness + configuration report."""
    return HealthResponse(
        status="ok",
        demo_mode=settings.demo_mode,
        providers=_provider_status(),
    )


@app.post("/intent/interpret", response_model=IntentFrame)
def interpret_intent(req: CommunicationInput) -> IntentFrame:
    """Interpret multimodal communication signals into an IntentFrame.
    
    Pipeline: deterministic rules → LLM interpretation → deterministic fallback.
    Always returns a valid IntentFrame with confidence in [0.0, 1.0].
    """
    # Validate person_id before processing
    try:
        validate_person_id(req.person_id)
    except ValueError as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail=str(exc))
    
    intent_svc = _get("intent")
    
    # Degraded mode: service unavailable
    if intent_svc is None:
        logger.warning("IntentService unavailable, returning low-confidence unknown intent")
        return IntentFrame(
            action=IntentType.unknown,
            concepts=req.fragments,
            confidence=0.1,
            unresolved=["service_unavailable"],
            evidence=[],
        )
    
    return intent_svc.interpret(req)


@app.post("/generate", response_model=GenerateResponse)
def generate(req: GenerateRequest) -> GenerateResponse:
    """Reconstruct grounded utterance candidates from fragments + context.

    Pipeline: hybrid retrieval (anchor → graph expand → vector → rerank →
    confidence gate) then LLM generation. On low confidence, ABSTAIN and ask for
    one more word instead of guessing.
    """
    # Validate person_id before processing
    try:
        validate_person_id(req.person_id)
    except ValueError as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail=str(exc))
    
    global latest_trace
    t0 = time.time()

    set_tag("person_id", req.person_id)
    add_breadcrumb(
        "generation", "generate() called", level="info",
        fragment_count=len(req.fragments or []), has_context=bool(req.context),
    )

    retrieval = get_retrieval_service()
    generation = get_generation_service()

    # Degraded mode: services unavailable (e.g. kuzu/LLM missing) -> shaped empty.
    if retrieval is None or generation is None:
        info = RetrievalInfo()
        trace = {"phase": "degraded", "reason": "retrieval/generation unavailable",
                 "person_id": req.person_id, "fragments": req.fragments}
        _store_trace(trace)
        return GenerateResponse(candidates=[], retrieval=info, trace=trace,
                                abstain=True,
                                abstain_reason="The local engine is not available right now.")

    with span("retrieval.retrieve", "hybrid GraphRAG grounding"):
        r = retrieval.retrieve(req.person_id, req.fragments, req.context or "", req.situation)
    info = RetrievalInfo(**r["retrieval"])
    add_breadcrumb(
        "generation", "retrieval complete", level="info",
        confidence=r.get("confidence"), abstain=bool(r.get("abstain")),
        subgraph_nodes=len(r["retrieval"]["subgraph_node_ids"]),
    )

    if r.get("abstain"):
        trace = {
            "anchors": r["retrieval"]["anchor_ids"],
            "subgraph_node_ids": r["retrieval"]["subgraph_node_ids"],
            "subgraph_edge_ids": r["retrieval"]["subgraph_edge_ids"],
            "confidence": r["confidence"],
            "latency_ms": int((time.time() - t0) * 1000),
            "provider": {"llm": settings.llm_provider, "model": settings.lm_studio_model},
            "abstain": True,
            "rationales": [],
            "candidates": [],
            "topk": r.get("topk", []),
        }
        _store_trace(trace)
        return GenerateResponse(candidates=[], retrieval=info, trace=trace,
                                abstain=True, abstain_reason=r.get("abstain_reason"))

    # Personal style: inject the learned profile + exemplars into the prompt,
    # then re-rank the candidates by style-fit so the preferred style ranks first.
    style_svc = _get("style")
    style_prompt = ""
    if style_svc is not None:
        try:
            style_prompt = style_svc.style_prompt(req.person_id)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("style_prompt failed: %s", exc)

    with span("generation.generate_candidates", "LLM candidate reconstruction"):
        candidates = generation.generate_candidates(
            req.fragments, req.context or "", r["context_block"],
            valid_node_ids=r["grounded_ids"], style_prompt=style_prompt,
        )
    add_breadcrumb(
        "generation", "candidates generated", level="info",
        candidate_count=len(candidates),
    )

    style_fit_info: list = []
    style_summary = None
    if style_svc is not None:
        try:
            if candidates:
                candidates, style_fit_info = style_svc.rank_candidates(req.person_id, candidates)
            style_summary = style_svc.get_profile(req.person_id)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("style ranking failed: %s", exc)

    trace = {
        "anchors": r["retrieval"]["anchor_ids"],
        "subgraph_node_ids": r["retrieval"]["subgraph_node_ids"],
        "subgraph_edge_ids": r["retrieval"]["subgraph_edge_ids"],
        "confidence": r["confidence"],
        "latency_ms": int((time.time() - t0) * 1000),
        "provider": {"llm": settings.llm_provider, "model": settings.lm_studio_model},
        "abstain": False,
        "rationales": [c.get("rationale", "") for c in candidates],
        # Candidates are added to the (free-form) trace dict so the laptop
        # GraphView — which only observes /trace/latest — can render the
        # candidate panel and emphasize grounded nodes. This is NOT an API
        # contract change (trace is typed `dict`).
        "candidates": [
            {
                "text": c.get("text", ""),
                "register": c.get("register", "neutral"),
                "length_label": c.get("length_label", "medium"),
                "rationale": c.get("rationale", ""),
                "grounded_node_ids": c.get("grounded_node_ids", []),
            }
            for c in candidates
        ],
        "style": style_summary,        # current learned profile (free-form trace)
        "style_fit": style_fit_info,   # per-candidate style-fit, in ranked order
        "selection": r.get("selection"),          # submodular vs top-k A/B + metrics
        "candidate_pool_ids": r.get("candidate_pool_ids", []),
        "topk": r.get("topk", []),
        "vector_backend": r.get("vector_backend", "in-process"),
    }
    _store_trace(trace)

    return GenerateResponse(
        candidates=[Candidate(**c) for c in candidates],
        retrieval=info,
        trace=trace,
        abstain=False,
        abstain_reason=None,
    )


def _synthesize_with_fallback(person_id: str, text: str) -> str:
    """Synthesize via the configured provider, with fallbacks so we never raise.

    Order: configured provider (XTTS) -> ElevenLabs if a key is present and not
    already the primary -> "" (cache-only). Returns base64 wav, or "" on total
    failure (the caller then serves cache-only / empty so /speak never throws).
    """
    from app.providers.tts import voice_ref_path, ElevenLabsProvider

    ref = voice_ref_path(person_id)
    provider = _get("tts")
    if provider is not None:
        try:
            return provider.synthesize(text, ref)
        except Exception as exc:
            logger.error("primary TTS (%s) failed: %s", settings.tts_provider, exc)
    if settings.elevenlabs_api_key and settings.tts_provider != "elevenlabs":
        try:
            logger.warning("falling back to ElevenLabs for synthesis")
            return ElevenLabsProvider().synthesize(text, ref)
        except Exception as exc:
            logger.error("ElevenLabs fallback failed: %s", exc)
    logger.warning("no TTS available; serving cache-only for %r", person_id)
    return ""


@app.post("/speak", response_model=SpeakResponse)
def speak(req: SpeakRequest) -> SpeakResponse:
    """Speak `text` in the person's cloned voice (cache-first; never hard-fails).

    Cache-first also makes DEMO_MODE instant: pre-rendered demo lines (see
    data/prerender_demo.py) live in the same cache, so they return immediately.
    """
    # Validate person_id before processing
    try:
        validate_person_id(req.person_id)
    except ValueError as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail=str(exc))
    
    cache = get_cache_service()
    if cache is not None:
        try:
            hit = cache.get(req.person_id, req.text)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("cache get failed: %s", exc)
            hit = None
        if hit is not None:
            return SpeakResponse(audio_base64=hit, cached=True)

    audio_b64 = _synthesize_with_fallback(req.person_id, req.text)
    if audio_b64 and cache is not None:
        try:
            cache.put(req.person_id, req.text, audio_b64)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("cache put failed: %s", exc)
    return SpeakResponse(audio_base64=audio_b64 or "", cached=False)


@app.post("/confirm", response_model=ConfirmResponse)
def confirm(req: ConfirmRequest) -> ConfirmResponse:
    """Confirm an utterance was spoken; reinforce the graph (online learning)."""
    # Validate person_id before processing
    try:
        validate_person_id(req.person_id)
    except ValueError as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail=str(exc))
    
    learning = get_learning_service()
    if learning is None:
        return ConfirmResponse(changed_node_ids=[], changed_edge_ids=[])
    try:
        result = learning.on_confirm(
            req.person_id, req.text, req.context or "", req.partner, None
        )
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("confirm(%r) failed: %s", req.person_id, exc)
        result = {"changed_node_ids": [], "changed_edge_ids": [], "new_nodes": [], "new_edges": []}

    # Implicit-feedback style update: contrast the chosen utterance against the
    # rejected alternatives from the last /generate (carried in latest_trace).
    style = None
    style_svc = _get("style")
    if style_svc is not None:
        try:
            cands = latest_trace.get("candidates", []) if isinstance(latest_trace, dict) else []
            style = style_svc.observe_confirm(req.person_id, req.text, cands, req.partner)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("style update failed: %s", exc)

    # Agent/session memory: remember recently confirmed utterances (Redis-backed).
    rs = _get("redis")
    if rs is not None and getattr(rs, "available", False):
        try:
            rs.push_confirmed(req.person_id, req.text)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("redis push_confirmed failed: %s", exc)

    return ConfirmResponse(
        changed_node_ids=result["changed_node_ids"],
        changed_edge_ids=result["changed_edge_ids"],
        style=style,
        new_nodes=result.get("new_nodes", []),
        new_edges=result.get("new_edges", []),
    )


@app.post("/assistant_turn", response_model=AssistantTurnResponse)
def assistant_turn(req: AssistantTurnRequest) -> AssistantTurnResponse:
    """Build Your Brain: return the assistant's next interview question.

    One graph-aware LLM call (thinking disabled like the others). The assistant
    sees a summary of what the graph already holds and where it is thin, and asks
    one warm question targeting a gap. Degrades to a fallback question offline.
    """
    # Validate person_id before processing
    try:
        validate_person_id(req.person_id)
    except ValueError as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail=str(exc))
    
    learning = get_learning_service()
    fallback = "Tell me about the people who matter most to you."
    if learning is None:
        return AssistantTurnResponse(text=fallback)
    try:
        history = [{"role": m.role, "text": m.text} for m in req.history]
        result = learning.interview_question(req.person_id, history)
        text = result.get("question") or fallback
        suggestions = result.get("suggestions", [])
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("assistant_turn(%r) failed: %s", req.person_id, exc)
        text, suggestions = fallback, []
    return AssistantTurnResponse(text=text, suggestions=suggestions)


@app.post("/consolidate", response_model=ConsolidateResponse)
def consolidate(req: ConsolidateRequest) -> ConsolidateResponse:
    """Consolidate recent Events into durable Preferences (scheduled/offline)."""
    # Validate person_id before processing
    try:
        validate_person_id(req.person_id)
    except ValueError as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail=str(exc))
    
    learning = get_learning_service()
    if learning is None:
        return ConsolidateResponse(new_node_ids=[], new_edge_ids=[])
    try:
        result = learning.consolidate(req.person_id)
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("consolidate(%r) failed: %s", req.person_id, exc)
        return ConsolidateResponse(new_node_ids=[], new_edge_ids=[])
    return ConsolidateResponse(
        new_node_ids=result["new_node_ids"],
        new_edge_ids=result["new_edge_ids"],
    )


@app.get("/style/{person_id}", response_model=StyleProfile)
def style(person_id: str) -> StyleProfile:
    """Return the person's current learned communication-style profile."""
    # Validate person_id before processing
    try:
        validate_person_id(person_id)
    except ValueError as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail=str(exc))
    
    svc = _get("style")
    if svc is None:
        return StyleProfile(person_id=person_id)
    try:
        return StyleProfile(**svc.get_profile(person_id))
    except Exception as exc:  # pragma: no cover - defensive
        logger.error("style(%r) failed: %s", person_id, exc)
        return StyleProfile(person_id=person_id)


@app.post("/stt", response_model=STTResponse)
def stt(req: STTRequest) -> STTResponse:
    """Transcribe base64-encoded audio to text (never throws -> "" on failure)."""
    provider = _get("stt")
    if provider is None:
        return STTResponse(text="")
    try:
        return STTResponse(text=provider.transcribe(req.audio_base64))
    except Exception as exc:  # pragma: no cover - provider already guards
        logger.error("stt failed: %s", exc)
        return STTResponse(text="")


@app.post("/enroll", response_model=EnrollResponse)
def enroll(req: EnrollRequest) -> EnrollResponse:
    """Store a person's reference wav (base64) for later voice cloning."""
    # Validate person_id before processing
    try:
        validate_person_id(req.person_id)
    except ValueError as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail=str(exc))
    
    try:
        from app.providers.tts import save_reference

        path = save_reference(req.person_id, req.audio_base64)
        return EnrollResponse(ok=True, voice_ref=path)
    except Exception as exc:
        logger.error("enroll(%r) failed: %s", req.person_id, exc)
        return EnrollResponse(ok=False, voice_ref="")


@app.get("/graph/{person_id}", response_model=GraphResponse)
def graph(person_id: str) -> GraphResponse:
    """Return the person's knowledge graph (nodes + edges)."""
    # Validate person_id before processing
    try:
        validate_person_id(person_id)
    except ValueError as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail=str(exc))
    
    svc = get_graph_service()
    if svc is None:
        return GraphResponse(nodes=[], edges=[])
    try:
        data = svc.get_graph(person_id)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("get_graph(%r) failed: %s", person_id, exc)
        return GraphResponse(nodes=[], edges=[])
    # Pydantic coerces the GraphNode/GraphEdge-shaped dicts into models.
    return GraphResponse(nodes=data["nodes"], edges=data["edges"])


@app.get("/trace/latest")
def trace_latest() -> dict:
    """Return the trace produced by the most recent /generate call."""
    return _read_trace()


@app.get("/passport/{person_id}", response_model=CommunicationPassport)
def get_passport(person_id: str) -> CommunicationPassport:
    """Retrieve the Communication Passport for a person.
    
    Returns the user-facing representation of their linguistic identity,
    backed by the knowledge graph, style profile, and learning service.
    """
    # Validate person_id before processing
    try:
        validate_person_id(person_id)
    except ValueError as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail=str(exc))
    
    passport_svc = _get("passport")
    if passport_svc is None:
        # Graceful degradation: return empty passport
        logger.warning("PassportService unavailable, returning empty passport")
        return CommunicationPassport(person_id=person_id)
    
    try:
        return passport_svc.get_passport(person_id)
    except Exception as exc:
        logger.error("get_passport(%r) failed: %s", person_id, exc)
        return CommunicationPassport(person_id=person_id)


@app.patch("/passport/{person_id}")
def update_passport(person_id: str, updates: dict) -> dict:
    """Update passport fields by dispatching to appropriate graph upserts.
    
    Supports updating:
    - preferred_expressions: list of expressions to add
    - avoided_expressions: list of expressions to add
    - emergency_phrases: list of phrases to add
    """
    # Validate person_id before processing
    try:
        validate_person_id(person_id)
    except ValueError as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail=str(exc))
    
    passport_svc = _get("passport")
    if passport_svc is None:
        logger.warning("PassportService unavailable")
        return {"ok": False, "reason": "service_unavailable"}
    
    try:
        passport_svc.update_passport(person_id, updates)
        return {"ok": True}
    except Exception as exc:
        logger.error("update_passport(%r) failed: %s", person_id, exc)
        return {"ok": False, "reason": str(exc)}


@app.post("/passport/preference")
def add_preference(req: dict) -> dict:
    """Add a preferred expression to the Communication Passport.
    
    Request body: {"person_id": str, "expression": str}
    """
    person_id = req.get("person_id", "")
    expression = req.get("expression", "")
    
    # Validate person_id before processing
    try:
        validate_person_id(person_id)
    except ValueError as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail=str(exc))
    
    if not expression:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail="expression cannot be empty")
    
    passport_svc = _get("passport")
    if passport_svc is None:
        logger.warning("PassportService unavailable")
        return {"ok": False, "reason": "service_unavailable"}
    
    try:
        passport_svc.add_preference(person_id, expression)
        return {"ok": True}
    except Exception as exc:
        logger.error("add_preference(%r) failed: %s", person_id, exc)
        return {"ok": False, "reason": str(exc)}


@app.post("/passport/avoid")
def add_avoided(req: dict) -> dict:
    """Add an avoided expression to the Communication Passport.
    
    Request body: {"person_id": str, "expression": str}
    """
    person_id = req.get("person_id", "")
    expression = req.get("expression", "")
    
    # Validate person_id before processing
    try:
        validate_person_id(person_id)
    except ValueError as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail=str(exc))
    
    if not expression:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail="expression cannot be empty")
    
    passport_svc = _get("passport")
    if passport_svc is None:
        logger.warning("PassportService unavailable")
        return {"ok": False, "reason": "service_unavailable"}
    
    try:
        passport_svc.add_avoided(person_id, expression)
        return {"ok": True}
    except Exception as exc:
        logger.error("add_avoided(%r) failed: %s", person_id, exc)
        return {"ok": False, "reason": str(exc)}


@app.post("/communication/generate")
def communication_generate(req: CommunicationInput) -> dict:
    """Process a full communication request through the Intentra pipeline.
    
    Pipeline flow:
    1. IntentService → interpret intent
    2. ConfidenceRouter → determine confidence band
    3. If LOW: return clarification immediately (no generation)
    4. If MEDIUM: generate alternatives
    5. If HIGH: generate expression + identity check + single response
    6. One silent regeneration if identity.safe_to_present is False
    
    Always sets requires_confirmation: true
    Requirements: 9.1, 9.2, 9.3, 9.4
    """
    # Validate person_id before processing
    try:
        validate_person_id(req.person_id)
    except ValueError as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail=str(exc))
    
    communication_svc = _get("communication")
    
    # Degraded mode: service unavailable
    # The individual services (IntentService, GenerationService, etc.) handle None
    # dependencies internally and provide graceful degradation, so a None
    # CommunicationService only happens in extreme cases
    if communication_svc is None:
        logger.warning("CommunicationService unavailable")
        from fastapi import HTTPException
        raise HTTPException(
            status_code=503,
            detail="Communication service is currently unavailable"
        )
    
    try:
        return communication_svc.process(req)
    except Exception as exc:
        logger.error("communication_generate failed: %s", exc)
        from fastapi import HTTPException
        raise HTTPException(
            status_code=500,
            detail=f"Communication processing failed: {str(exc)}"
        )


@app.post("/communication/confirm")
def communication_confirm(req: dict) -> dict:
    """Record that a user confirmed and spoke an expression.
    
    Request body: {
        "person_id": str,
        "text": str,
        "context": str (optional),
        "partner": str (optional),
        "intent_frame": dict (optional)
    }
    
    Reuses existing confirm logic from LearningService.
    Requirements: 9.5
    """
    person_id = req.get("person_id", "")
    text = req.get("text", "")
    context = req.get("context")
    partner = req.get("partner")
    
    # Validate person_id before processing
    try:
        validate_person_id(person_id)
    except ValueError as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail=str(exc))
    
    if not text:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail="text cannot be empty")
    
    # Reuse existing confirm logic
    learning = get_learning_service()
    if learning is None:
        return {"ok": True, "changed_node_ids": [], "changed_edge_ids": []}
    
    try:
        result = learning.on_confirm(person_id, text, context or "", partner, None)
        return {
            "ok": True,
            "changed_node_ids": result.get("changed_node_ids", []),
            "changed_edge_ids": result.get("changed_edge_ids", []),
        }
    except Exception as exc:
        logger.error("communication_confirm failed: %s", exc)
        return {"ok": False, "reason": str(exc)}


@app.post("/communication/repair")
def communication_repair(req: dict) -> dict:
    """Initiate conversation repair after communication failure.
    
    Request body: {
        "person_id": str,
        "original_intent": dict (IntentFrame),
        "original_expression": str,
        "listener_response": str (optional)
    }
    
    Stub until Phase 10 (RepairService implementation).
    Requirements: 9.6
    """
    person_id = req.get("person_id", "")
    
    # Validate person_id before processing
    try:
        validate_person_id(person_id)
    except ValueError as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail=str(exc))
    
    # Stub response until Phase 10
    logger.info("communication_repair called (stub) for person_id=%s", person_id)
    return {
        "status": "stub",
        "message": "Repair service will be implemented in Phase 10",
        "strategy": None,
        "options": [],
    }


@app.post("/conversation/outcome")
def conversation_outcome(req: dict) -> dict:
    """Record the outcome of a conversation attempt (success or failure).
    
    Request body: {
        "person_id": str,
        "session_id": str,
        "success": bool,
        "intent_frame": dict (optional),
        "expression": str (optional),
        "repair_needed": bool (optional)
    }
    
    Records outcome and calls LearningService for adaptive learning.
    Requirements: 9.7, 9.8
    """
    person_id = req.get("person_id", "")
    success = req.get("success", False)
    
    # Validate person_id before processing
    try:
        validate_person_id(person_id)
    except ValueError as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail=str(exc))
    
    logger.info(
        "conversation_outcome: person_id=%s, success=%s",
        person_id,
        success
    )
    
    # Record outcome with LearningService for adaptive learning
    learning = get_learning_service()
    if learning is not None:
        try:
            # Use the learning service to record the outcome
            # This allows the system to learn from successes and failures
            expression = req.get("expression")
            context = req.get("context", "")
            
            if success and expression:
                # Record successful communication
                learning.on_confirm(person_id, expression, context, None, None)
        except Exception as exc:
            logger.warning("Failed to record outcome with learning service: %s", exc)
    
    return {
        "ok": True,
        "recorded": True,
        "repair_needed": req.get("repair_needed", False),
    }


@app.get("/accessibility/{person_id}")
def get_accessibility(person_id: str) -> dict:
    """Get effort mode and emergency phrases for a person.
    
    Returns effort mode configuration and emergency phrases.
    Emergency phrases are returned even when all AI services are None.
    
    Requirements: 11.7
    """
    # Validate person_id before processing
    try:
        validate_person_id(person_id)
    except ValueError as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail=str(exc))
    
    effort_svc = _get("effort")
    
    # Even if service is None, we can return defaults
    if effort_svc is None:
        logger.warning("EffortService unavailable, returning defaults")
        from app.services.effort import EffortService
        return {
            "effort_mode": "full",
            "emergency_phrases": EffortService.DEFAULT_EMERGENCY_PHRASES,
            "low_effort_buttons": [
                "YES",
                "NO",
                "HELP",
                "MORE",
                "STOP",
                "PAIN",
                "HOME",
                "DRINK",
                "TOILET",
            ],
        }
    
    try:
        return effort_svc.get_effort_config(person_id)
    except Exception as exc:
        logger.error("get_accessibility(%r) failed: %s", person_id, exc)
        # Fallback to defaults even on error
        from app.services.effort import EffortService
        return {
            "effort_mode": "full",
            "emergency_phrases": EffortService.DEFAULT_EMERGENCY_PHRASES,
            "low_effort_buttons": [
                "YES",
                "NO",
                "HELP",
                "MORE",
                "STOP",
                "PAIN",
                "HOME",
                "DRINK",
                "TOILET",
            ],
        }


@app.patch("/accessibility/{person_id}")
def update_accessibility(person_id: str, config: dict) -> dict:
    """Save effort mode preference for a person.
    
    Request body: {
        "effort_mode": str ("full" | "assist" | "low_effort" | "emergency")
    }
    
    Requirements: 11.7
    """
    # Validate person_id before processing
    try:
        validate_person_id(person_id)
    except ValueError as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail=str(exc))
    
    effort_svc = _get("effort")
    
    if effort_svc is None:
        logger.warning("EffortService unavailable")
        return {"ok": False, "reason": "service_unavailable"}
    
    try:
        effort_svc.save_effort_config(person_id, config)
        return {"ok": True}
    except Exception as exc:
        logger.error("update_accessibility(%r) failed: %s", person_id, exc)
        return {"ok": False, "reason": str(exc)}


@app.post("/communication/fast-response")
def fast_response(req: dict) -> dict:
    """Analyze partner speech for fast response options.
    
    Detects simple binary and choice questions without full AI pipeline.
    Uses pure regex/pattern matching for immediate response options.
    
    Request body: {
        "partner_speech": str,
        "person_id": str
    }
    
    Returns one of:
    - {"type": "binary", "options": ["Yes", "No", "A little", "Explain"]}
    - {"type": "choice", "options": [X, Y, "Neither", "Something else"]}
    - {"type": "pipeline"} for complex inputs
    
    Requirements: 16.4
    """
    partner_speech = req.get("partner_speech", "")
    person_id = req.get("person_id", "")
    
    # Validate person_id before processing
    try:
        validate_person_id(person_id)
    except ValueError as exc:
        from fastapi import HTTPException
        raise HTTPException(status_code=422, detail=str(exc))
    
    if not partner_speech:
        # Empty speech routes to pipeline
        return {"type": "pipeline"}
    
    fast_response_svc = _get("fast_response")
    
    # Degraded mode: service unavailable (shouldn't happen as it has no dependencies)
    if fast_response_svc is None:
        logger.warning("FastResponseEngine unavailable, routing to pipeline")
        return {"type": "pipeline"}
    
    try:
        result = fast_response_svc.analyze(partner_speech)
        logger.info(
            "Fast response analysis: type=%s, partner_speech='%s'",
            result.get("type"),
            partner_speech[:50]
        )
        return result
    except Exception as exc:
        logger.error("fast_response failed: %s", exc)
        # On error, route to pipeline
        return {"type": "pipeline"}


@app.get("/debug/sentry-error")
def debug_sentry_error() -> dict:
    """Deliberately raise so Sentry (when a DSN is configured) captures it.

    With SENTRY_DSN set, the FastAPI integration reports this unhandled exception
    to Sentry; with no DSN it simply returns a normal 500 and nothing is sent.
    Used to demonstrate error monitoring live.
    
    This endpoint is only available when DEBUG_ENDPOINTS_ENABLED=true in the
    environment. Never enable this in production.
    """
    # Gate behind debug flag for production safety
    if not settings.debug_endpoints_enabled:
        from fastapi import HTTPException
        raise HTTPException(
            status_code=404,
            detail="Not found"
        )
    
    add_breadcrumb("debug", "about to raise a test error", level="warning")
    raise RuntimeError("Intentra test error — Sentry capture check.")
