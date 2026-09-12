"""Communication-related domain models."""

from enum import Enum
from pydantic import BaseModel, Field

from app.domain.intent import IntentType, InputMethod, IntentFrame


class EffortMode(str, Enum):
    """Adaptive interaction mode based on user's current effort level."""

    full = "full"
    assist = "assist"
    low_effort = "low_effort"
    emergency = "emergency"


class CommunicationInput(BaseModel):
    """All multimodal signals from the user for a communication attempt."""

    person_id: str
    fragments: list[str] = Field(default_factory=list)
    intent_type: IntentType | None = None
    listener: str | None = None
    emotion: str | None = None
    partial_speech: str | None = None
    selected_symbols: list[str] = Field(default_factory=list)
    conversation_context: str | None = None
    effort_mode: EffortMode = EffortMode.full
    input_methods: list[InputMethod] = Field(default_factory=list)


class ConfidenceBand(str, Enum):
    """Categorical routing label derived from intent confidence."""

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class CommunicationOutcome(BaseModel):
    """Result of a communication attempt including success/failure."""

    session_id: str
    person_id: str
    success: bool
    intent_frame: IntentFrame | None = None
    expression: str | None = None
    repair_needed: bool = False
