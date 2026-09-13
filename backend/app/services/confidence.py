"""Confidence routing service for communication pipeline."""

from app.domain.communication import ConfidenceBand
from app.domain.intent import IntentFrame
from app.domain.identity import IdentityResult


class ConfidenceRouter:
    """Routes communication based on confidence bands and builds API responses."""

    # Thresholds from requirements 7.1-7.5
    HIGH_THRESHOLD = 0.75
    MEDIUM_THRESHOLD = 0.45

    def band(self, confidence: float) -> ConfidenceBand:
        """Classify confidence into a band.

        Args:
            confidence: Float in [0.0, 1.0]

        Returns:
            HIGH if >= 0.75, MEDIUM if >= 0.45, LOW if < 0.45
        """
        if confidence >= self.HIGH_THRESHOLD:
            return ConfidenceBand.HIGH
        elif confidence >= self.MEDIUM_THRESHOLD:
            return ConfidenceBand.MEDIUM
        else:
            return ConfidenceBand.LOW

    def route(
        self,
        intent: IntentFrame,
        expression: dict | None,
        identity: IdentityResult | None,
        band: ConfidenceBand,
    ) -> dict:
        """Build API response based on confidence band.

        Args:
            intent: The interpreted intent frame
            expression: Generated expression dict with "text" and "used_evidence"
            identity: Identity verification result
            band: The confidence band

        Returns:
            Structured API response dict
        """
        base_response = {
            "intent": intent.model_dump(),
            "confidence_band": band.value,
            "requires_confirmation": True,
        }

        if band == ConfidenceBand.LOW:
            # LOW band: clarification required, no expression
            return {
                **base_response,
                "status": "clarification_required",
                "question": self._generate_clarification_question(intent),
                "options": self._generate_clarification_options(intent),
            }

        elif band == ConfidenceBand.MEDIUM:
            # MEDIUM band: alternatives provided
            return {
                **base_response,
                "status": "ready",
                "expression": expression,
                "identity": identity.model_dump() if identity else None,
                "alternatives_available": True,
            }

        else:  # HIGH band
            # HIGH band: single expression
            return {
                **base_response,
                "status": "ready",
                "expression": expression,
                "identity": identity.model_dump() if identity else None,
            }

    def _generate_clarification_question(self, intent: IntentFrame) -> str:
        """Generate a clarifying question based on unresolved concepts.

        Args:
            intent: The intent frame with potentially unresolved concepts

        Returns:
            A clarifying question string
        """
        if intent.unresolved:
            # Ask about the first unresolved concept
            concept = intent.unresolved[0]
            return f"Could you clarify what you mean by '{concept}'?"

        # Generic fallback
        if intent.action.value != "unknown":
            return f"You want to {intent.action.value}. Can you tell me more?"

        return "I'm not sure what you're trying to say. Could you give me more details?"

    def _generate_clarification_options(self, intent: IntentFrame) -> list[str]:
        """Generate clarification options based on intent.

        Args:
            intent: The intent frame

        Returns:
            List of option strings for the user to select
        """
        # Default options for clarification
        options = ["Yes", "No", "Something else"]

        # Add context-specific options based on concepts
        if intent.concepts:
            # Offer the concepts as selectable options
            options = intent.concepts[:3] + ["Something else"]

        return options
