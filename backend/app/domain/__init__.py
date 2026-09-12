"""Domain models for Intentra.

This package contains all domain models used throughout the application.
All models use Pydantic v2 for validation and serialization.
"""

from app.domain.intent import IntentType, InputMethod, IntentFrame
from app.domain.communication import (
    EffortMode,
    CommunicationInput,
    ConfidenceBand,
    CommunicationOutcome,
)
from app.domain.identity import IdentityResult
from app.domain.repair import RepairStrategy, RepairRequest, RepairOption, RepairPlan
from app.domain.passport import PersonProfile, CommunicationPassport

__all__ = [
    "IntentType",
    "InputMethod",
    "IntentFrame",
    "EffortMode",
    "CommunicationInput",
    "ConfidenceBand",
    "CommunicationOutcome",
    "IdentityResult",
    "RepairStrategy",
    "RepairRequest",
    "RepairOption",
    "RepairPlan",
    "PersonProfile",
    "CommunicationPassport",
]
