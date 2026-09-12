"""Identity verification domain models."""

from pydantic import BaseModel, Field


class IdentityResult(BaseModel):
    """Result of Identity Lock verification.

    Checks whether a generated expression matches the user's intent,
    grounding evidence, and personal communication identity.
    """

    intent_match: float = Field(default=0.0, ge=0.0, le=1.0)
    grounding_score: float = Field(default=0.0, ge=0.0, le=1.0)
    identity_match: float = Field(default=0.0, ge=0.0, le=1.0)
    hallucination_risk: float = Field(default=0.0, ge=0.0, le=1.0)
    violated_rules: list[str] = Field(default_factory=list)
    safe_to_present: bool = True
