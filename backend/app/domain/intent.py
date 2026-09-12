"""Intent-related domain models."""

from enum import Enum
from pydantic import BaseModel, Field


class IntentType(str, Enum):
    """Type of communicative intent."""

    request = "request"
    answer = "answer"
    question = "question"
    explain = "explain"
    emotion = "emotion"
    social = "social"
    emergency = "emergency"
    unknown = "unknown"


class InputMethod(str, Enum):
    """Method used to provide input."""

    word = "word"
    speech = "speech"
    symbol = "symbol"
    choice = "choice"
    yes_no = "yes_no"
    typed_text = "typed_text"


class IntentFrame(BaseModel):
    """Structured representation of probable communicative intent.

    Separates the meaning/intent from any generated language.
    """

    action: IntentType = IntentType.unknown
    concepts: list[str] = Field(default_factory=list)
    listener_id: str | None = None
    listener_name: str | None = None
    emotional_state: str | None = None
    temporal_reference: str | None = None
    location_reference: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    unresolved: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
