"""Conversation repair domain models."""

from enum import Enum
from pydantic import BaseModel, Field

from app.domain.intent import IntentFrame


class RepairStrategy(str, Enum):
    """Strategy for repairing a failed communication attempt."""

    SIMPLIFY = "SIMPLIFY"
    REPHRASE = "REPHRASE"
    EXPAND = "EXPAND"
    YES_NO = "YES_NO"
    SHOW_CHOICES = "SHOW_CHOICES"
    KEYWORD_ONLY = "KEYWORD_ONLY"
    TIME_SELECTION = "TIME_SELECTION"
    BODY_LOCATION = "BODY_LOCATION"


class RepairRequest(BaseModel):
    """Request to create a repair plan after communication failure."""

    person_id: str
    original_intent: IntentFrame
    original_expression: str
    listener_response: str | None = None
    failed_strategy: RepairStrategy | None = None


class RepairOption(BaseModel):
    """A single option in a repair plan."""

    label: str
    value: str


class RepairPlan(BaseModel):
    """Plan for repairing a failed communication attempt."""

    strategy: RepairStrategy
    question: str | None = None
    options: list[RepairOption] = Field(default_factory=list)
    rebuilt_expression: str | None = None
