"""Pydantic v2 models implementing the shared Lucid Voice API contract.

These models are the SOURCE OF TRUTH and must match the frontend TypeScript
types in aac/frontend/src/lib/api.ts exactly (same field names, optionality).
"""

from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field

# --- Shared helper models ---------------------------------------------------


class Situation(BaseModel):
    """Optional situational context for a generation request."""

    time: Optional[str] = None
    place: Optional[str] = None
    present_people: Optional[list[str]] = None


class Candidate(BaseModel):
    """A single generated utterance candidate."""

    text: str
    register: Literal["warm", "neutral", "direct"]
    length_label: Literal["short", "medium", "full"]
    rationale: str
    grounded_node_ids: list[str] = Field(default_factory=list)


class RetrievalInfo(BaseModel):
    """Information about the subgraph retrieved to ground a generation."""

    anchor_ids: list[str] = Field(default_factory=list)
    subgraph_node_ids: list[str] = Field(default_factory=list)
    subgraph_edge_ids: list[str] = Field(default_factory=list)
    confidence: float = 0.0


class GraphNode(BaseModel):
    """A node in the personal knowledge graph."""

    id: str
    label: str
    type: str
    salience: float
    last_seen: str
    group: Optional[str] = None


class GraphEdge(BaseModel):
    """An edge in the personal knowledge graph."""

    id: str
    source: str
    target: str
    type: str
    weight: float
    count: int
    last_reinforced: str


# --- /generate --------------------------------------------------------------


class GenerateRequest(BaseModel):
    person_id: str
    fragments: list[str] = Field(default_factory=list)
    context: str = ""
    situation: Optional[Situation] = None


class GenerateResponse(BaseModel):
    candidates: list[Candidate] = Field(default_factory=list)
    retrieval: RetrievalInfo
    trace: dict = Field(default_factory=dict)
    abstain: bool = False
    abstain_reason: Optional[str] = None


# --- /speak -----------------------------------------------------------------


class SpeakRequest(BaseModel):
    person_id: str
    text: str


class SpeakResponse(BaseModel):
    audio_base64: str
    cached: bool


# --- Personal Communication-Style Model -------------------------------------


class StyleProfile(BaseModel):
    """A person's learned communication-style profile."""

    person_id: str
    length_pref: str = "medium"            # short | medium | long
    directness_pref: str = "polite-elaborate"  # direct | polite-elaborate
    language_mix: str = "english-only"     # english-only | spanish-with-family
    endearment_use: str = "low"            # low | high
    # Continuous learned centers in [0,1] (length, directness, endearment, spanish)
    weights: dict[str, float] = Field(default_factory=dict)
    idiolect_markers: list[str] = Field(default_factory=list)
    exemplars: list[str] = Field(default_factory=list)
    updates: int = 0


# --- /confirm ---------------------------------------------------------------


class ConfirmRequest(BaseModel):
    person_id: str
    text: str
    context: Optional[str] = None
    partner: Optional[str] = None


class NewNode(BaseModel):
    """A node CREATED by a confirmation (for live incremental graph growth)."""

    id: str
    kind: str
    label: str
    salience: float = 1.0


class NewEdge(BaseModel):
    """An edge CREATED by a confirmation (for live incremental graph growth)."""

    source: str
    target: str
    type: str
    weight: float = 1.0


class ConfirmResponse(BaseModel):
    # Existing elements that were REINFORCED this turn (frontend pulses them).
    changed_node_ids: list[str] = Field(default_factory=list)
    changed_edge_ids: list[str] = Field(default_factory=list)
    # Additive: the updated learned style summary after this confirmation.
    style: Optional[StyleProfile] = None
    # Additive: elements CREATED this turn so the frontend can insert + bloom them
    # without re-fetching/relaying out the whole graph.
    new_nodes: list[NewNode] = Field(default_factory=list)
    new_edges: list[NewEdge] = Field(default_factory=list)


# --- /consolidate -----------------------------------------------------------


class ConsolidateRequest(BaseModel):
    person_id: str


class ConsolidateResponse(BaseModel):
    new_node_ids: list[str] = Field(default_factory=list)
    new_edge_ids: list[str] = Field(default_factory=list)


# --- /assistant_turn (Build Your Brain) -------------------------------------


class AssistantTurnMessage(BaseModel):
    """One turn in the Build-Your-Brain interview transcript."""

    role: Literal["assistant", "user"]
    text: str


class AssistantTurnRequest(BaseModel):
    person_id: str
    history: list[AssistantTurnMessage] = Field(default_factory=list)


class AssistantTurnResponse(BaseModel):
    text: str
    # Short, question-specific answer words the UI offers as "Next" suggestions.
    suggestions: list[str] = Field(default_factory=list)


# --- /stt -------------------------------------------------------------------


class STTRequest(BaseModel):
    audio_base64: str


class STTResponse(BaseModel):
    text: str


# --- /enroll ----------------------------------------------------------------


class EnrollRequest(BaseModel):
    person_id: str
    audio_base64: str


class EnrollResponse(BaseModel):
    ok: bool
    voice_ref: str


# --- /graph/{person_id} -----------------------------------------------------


class GraphResponse(BaseModel):
    nodes: list[GraphNode] = Field(default_factory=list)
    edges: list[GraphEdge] = Field(default_factory=list)


# --- /health ----------------------------------------------------------------


class HealthResponse(BaseModel):
    status: str
    demo_mode: bool
    providers: dict = Field(default_factory=dict)
