"""Communication Passport domain models."""

from pydantic import BaseModel, Field


class PersonProfile(BaseModel):
    """Profile of an important person in the user's life."""

    id: str
    name: str
    relationship: str | None = None
    address_term: str | None = None


class CommunicationPassport(BaseModel):
    """User-facing representation of a person's linguistic identity.

    Backed internally by the Kuzu graph, embeddings, and style profile.
    """

    person_id: str
    people: list[PersonProfile] = Field(default_factory=list)
    vocabulary: list[str] = Field(default_factory=list)
    preferred_expressions: list[str] = Field(default_factory=list)
    avoided_expressions: list[str] = Field(default_factory=list)
    communication_rules: list[str] = Field(default_factory=list)
    routines: list[str] = Field(default_factory=list)
    emergency_phrases: list[str] = Field(default_factory=list)
    repair_preferences: list[str] = Field(default_factory=list)
    accessibility_preferences: dict = Field(default_factory=dict)
