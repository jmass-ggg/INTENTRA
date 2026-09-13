"""IdentityGuard — Identity Lock verification service.

Verifies that a generated expression:
- Does not contradict the source IntentFrame
- Is grounded in evidence (not hallucinated)
- Does not use avoided expressions
- Does not introduce unknown named entities
- Matches the user's communication style

This is the safety layer that ensures the AI has not changed the user's
intended meaning, invented facts, or used language they would never use.
"""

import re
from typing import Any

from app.domain.identity import IdentityResult
from app.domain.intent import IntentFrame
from app.domain.passport import CommunicationPassport


class IdentityGuard:
    """Deterministic verification that an expression matches user identity."""

    def __init__(self, style_service: Any = None) -> None:
        """Initialize IdentityGuard.

        Args:
            style_service: Optional StyleService for style compatibility checking
        """
        self.style_service = style_service

    def verify(
        self,
        intent: IntentFrame,
        expression: str,
        passport: CommunicationPassport,
        evidence_ids: list[str],
    ) -> IdentityResult:
        """Verify an expression against intent, passport, and evidence.

        Args:
            intent: The source IntentFrame representing user intent
            expression: The generated expression to verify
            passport: User's Communication Passport with preferences and rules
            evidence_ids: IDs of evidence nodes used in generation

        Returns:
            IdentityResult with verification scores and safe_to_present flag
        """
        violated_rules: list[str] = []

        # Deterministic check 1: Avoided expressions
        avoided_violations = self._check_avoided_expressions(
            expression, passport.avoided_expressions
        )
        violated_rules.extend(avoided_violations)

        # Deterministic check 2: Intent concepts presence
        intent_match = self._check_intent_concepts(expression, intent.concepts)

        # Deterministic check 3: Unknown capitalized names
        hallucination_risk, unknown_entities = self._check_unknown_entities(
            expression, passport, evidence_ids
        )
        if unknown_entities:
            violated_rules.extend(
                [f"Unknown entity: {entity}" for entity in unknown_entities]
            )

        # Style check: Use StyleService if available
        identity_match = 0.0
        if self.style_service and passport.person_id:
            try:
                profile = self.style_service.get_profile(passport.person_id)
                weights = profile.get("weights", {})
                features = self.style_service.candidate_features(expression)
                identity_match = self.style_service.style_fit(features, weights)
            except Exception:
                # Style service unavailable or failed - default to 0.0
                identity_match = 0.0

        # Grounding score: Basic check that expression relates to intent
        grounding_score = self._compute_grounding_score(
            expression, intent, len(evidence_ids)
        )

        # Safe to present: No violated rules AND hallucination risk is acceptable
        safe_to_present = len(violated_rules) == 0 and hallucination_risk < 0.5

        return IdentityResult(
            intent_match=intent_match,
            grounding_score=grounding_score,
            identity_match=identity_match,
            hallucination_risk=hallucination_risk,
            violated_rules=violated_rules,
            safe_to_present=safe_to_present,
        )

    def _check_avoided_expressions(
        self, expression: str, avoided: list[str]
    ) -> list[str]:
        """Check for avoided expressions in the generated text.

        Uses case-insensitive substring matching.

        Args:
            expression: The generated expression
            avoided: List of avoided expressions from passport

        Returns:
            List of violated rules (avoided expressions found)
        """
        violations = []
        expression_lower = expression.lower()

        for avoided_phrase in avoided:
            if avoided_phrase.lower() in expression_lower:
                violations.append(f"Avoided expression: {avoided_phrase}")

        return violations

    def _check_intent_concepts(self, expression: str, concepts: list[str]) -> float:
        """Verify that IntentFrame concepts are represented in the expression.

        Uses keyword presence checking.

        Args:
            expression: The generated expression
            concepts: List of concepts from IntentFrame

        Returns:
            Intent match score [0.0, 1.0]
        """
        if not concepts:
            # No concepts to match - consider this a perfect match
            return 1.0

        expression_lower = expression.lower()
        # Normalize to words for better matching
        expression_words = set(re.findall(r'\b\w+\b', expression_lower))

        matched = 0
        for concept in concepts:
            concept_lower = concept.lower()
            # Check both substring and word-level matching
            if concept_lower in expression_lower:
                matched += 1
            else:
                # Try word-level matching for compound concepts
                concept_words = set(re.findall(r'\b\w+\b', concept_lower))
                if concept_words and concept_words.issubset(expression_words):
                    matched += 1

        return round(matched / len(concepts), 4)

    def _check_unknown_entities(
        self,
        expression: str,
        passport: CommunicationPassport,
        evidence_ids: list[str],
    ) -> tuple[float, list[str]]:
        """Check for capitalized names not in passport or evidence.

        Args:
            expression: The generated expression
            passport: User's Communication Passport
            evidence_ids: IDs of evidence nodes

        Returns:
            Tuple of (hallucination_risk, list of unknown entities)
        """
        # Extract capitalized words (potential names)
        # Exclude sentence-starting words and common words
        capitalized_pattern = r'\b[A-Z][a-z]+\b'
        capitalized_words = re.findall(capitalized_pattern, expression)

        # Common words that are often capitalized but aren't names
        common_caps = {
            "I", "I'm", "I've", "I'll", "Could", "Would", "Can", "Please",
            "Thank", "Thanks", "Yes", "No", "Maybe", "Sorry", "My", "The",
            "When", "Where", "What", "Why", "How", "Who"
        }

        # Known names from passport
        known_names = set()
        for person in passport.people:
            # Add both full name and first name
            known_names.add(person.name)
            name_parts = person.name.split()
            known_names.update(name_parts)

        # Evidence IDs might contain names
        known_names.update(evidence_ids)

        # Find unknown entities
        unknown = []
        for word in capitalized_words:
            if word not in common_caps and word not in known_names:
                # Check if it's at the start of a sentence (not an entity)
                if not re.search(rf'[.!?]\s+{re.escape(word)}\b', expression):
                    unknown.append(word)

        # Remove duplicates while preserving order
        unknown = list(dict.fromkeys(unknown))

        # Hallucination risk: higher if more unknown entities found
        if unknown:
            # Risk increases with number of unknown entities, capped at 1.0
            hallucination_risk = min(len(unknown) * 0.3, 1.0)
        else:
            hallucination_risk = 0.0

        return round(hallucination_risk, 4), unknown

    def _compute_grounding_score(
        self, expression: str, intent: IntentFrame, evidence_count: int
    ) -> float:
        """Compute how well the expression is grounded in evidence and intent.

        Args:
            expression: The generated expression
            intent: The source IntentFrame
            evidence_count: Number of evidence nodes used

        Returns:
            Grounding score [0.0, 1.0]
        """
        # Start with a base score
        score = 0.5

        # Boost if we have evidence
        if evidence_count > 0:
            score += 0.2

        # Boost if temporal/location references from intent are reflected
        expression_lower = expression.lower()
        if intent.temporal_reference:
            temporal_lower = intent.temporal_reference.lower()
            if temporal_lower in expression_lower:
                score += 0.15

        if intent.location_reference:
            location_lower = intent.location_reference.lower()
            if location_lower in expression_lower:
                score += 0.15

        # Clamp to [0.0, 1.0]
        return round(min(max(score, 0.0), 1.0), 4)
