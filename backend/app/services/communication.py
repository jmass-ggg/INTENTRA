"""CommunicationService — orchestrates the full Intentra pipeline.

Coordinates:
1. IntentService → interpret multimodal signals into IntentFrame
2. RetrievalService → retrieve grounded context from Communication Passport
3. GenerationService → generate expression from intent + context
4. IdentityGuard → verify expression matches identity and intent
5. ConfidenceRouter → route response based on confidence band

Requirements: 9.1, 9.2, 9.3, 9.4
"""

from __future__ import annotations

import logging
from typing import Any

from app.domain.communication import CommunicationInput, ConfidenceBand
from app.domain.intent import IntentFrame
from app.services.confidence import ConfidenceRouter
from app.services.intent import IntentService
from app.services.retrieval import RetrievalService
from app.services.generation import GenerationService
from app.services.identity_guard import IdentityGuard
from app.services.passport import PassportService

logger = logging.getLogger("intentra.communication")


class CommunicationService:
    """Orchestrates the full Intentra communication pipeline."""

    def __init__(
        self,
        intent_service: IntentService,
        retrieval_service: RetrievalService,
        generation_service: GenerationService,
        identity_guard: IdentityGuard,
        passport_service: PassportService,
        confidence_router: ConfidenceRouter,
    ) -> None:
        """Initialize CommunicationService with all required services.

        Args:
            intent_service: Service for interpreting multimodal input into intent
            retrieval_service: Service for retrieving grounded context
            generation_service: Service for generating expressions
            identity_guard: Service for verifying expression identity
            passport_service: Service for accessing Communication Passport
            confidence_router: Service for routing based on confidence bands
        """
        self.intent_service = intent_service
        self.retrieval_service = retrieval_service
        self.generation_service = generation_service
        self.identity_guard = identity_guard
        self.passport_service = passport_service
        self.confidence_router = confidence_router

    def process(self, request: CommunicationInput) -> dict[str, Any]:
        """Process a communication request through the full pipeline.

        Pipeline flow:
        1. IntentService → interpret intent
        2. ConfidenceRouter → determine confidence band
        3. If LOW: return clarification immediately (no generation)
        4. If MEDIUM: generate alternatives using generate_candidates()
        5. If HIGH: generate_expression() + identity check + single response
        6. One silent regeneration if identity.safe_to_present is False
        7. Always set requires_confirmation: true

        Args:
            request: CommunicationInput with all multimodal signals

        Returns:
            API response dict with status, intent, expression, identity, etc.
        """
        # Step 1: Interpret intent from multimodal signals
        logger.info(f"Processing communication request for {request.person_id}")
        intent = self.intent_service.interpret(request)
        logger.info(
            f"Intent interpreted: action={intent.action}, confidence={intent.confidence}"
        )

        # Step 2: Route by confidence band
        band = self.confidence_router.band(intent.confidence)
        logger.info(f"Confidence band: {band}")

        # Step 3: LOW band → clarification required, no generation
        if band == ConfidenceBand.LOW:
            logger.info("LOW confidence - returning clarification request")
            return self.confidence_router.route(
                intent=intent,
                expression=None,
                identity=None,
                band=band,
            )

        # Step 4: Retrieve passport context
        passport = self.passport_service.get_passport(request.person_id)
        logger.info(
            f"Retrieved passport: {len(passport.people)} people, "
            f"{len(passport.avoided_expressions)} avoided expressions"
        )

        # Step 5: Retrieve grounded evidence
        conversation_context = request.conversation_context or ""
        retrieval_result = self.retrieval_service.retrieve_for_intent(
            person_id=request.person_id,
            intent_frame=intent,
            conversation_context=conversation_context,
        )
        logger.info(
            f"Retrieved evidence: confidence={retrieval_result['confidence']}, "
            f"grounded_ids={len(retrieval_result['grounded_ids'])}"
        )

        # Step 6: Generate expression based on confidence band
        if band == ConfidenceBand.MEDIUM:
            # MEDIUM band: generate alternatives using generate_candidates()
            logger.info("MEDIUM confidence - generating alternatives")
            expression = self._generate_alternatives(
                request, intent, passport, retrieval_result
            )
            identity = None  # Skip identity check for alternatives
        else:
            # HIGH band: generate single expression + identity check
            logger.info("HIGH confidence - generating single expression")
            expression = self._generate_high_confidence(
                request, intent, passport, retrieval_result
            )
            if expression is None:
                # Generation failed - return error or fallback
                logger.warning("Expression generation failed - returning fallback")
                return self._fallback_response(intent, band)

            # Step 7: Identity Lock verification
            identity = self.identity_guard.verify(
                intent=intent,
                expression=expression["text"],
                passport=passport,
                evidence_ids=retrieval_result["grounded_ids"],
            )
            logger.info(
                f"Identity check: safe_to_present={identity.safe_to_present}, "
                f"violated_rules={len(identity.violated_rules)}"
            )

            # Step 8: One silent regeneration if identity check fails
            if not identity.safe_to_present:
                logger.info("Identity check failed - attempting regeneration")
                expression = self._regenerate_expression(
                    request, intent, passport, retrieval_result, identity
                )
                if expression is not None:
                    # Re-check identity
                    identity = self.identity_guard.verify(
                        intent=intent,
                        expression=expression["text"],
                        passport=passport,
                        evidence_ids=retrieval_result["grounded_ids"],
                    )
                    logger.info(
                        f"Regenerated expression identity check: "
                        f"safe_to_present={identity.safe_to_present}"
                    )

        # Step 9: Build final response
        return self.confidence_router.route(
            intent=intent,
            expression=expression,
            identity=identity,
            band=band,
        )

    def _generate_high_confidence(
        self,
        request: CommunicationInput,
        intent: IntentFrame,
        passport: Any,
        retrieval_result: dict,
    ) -> dict[str, Any] | None:
        """Generate single best expression for HIGH confidence.

        Uses GenerationService.generate_expression() which focuses on
        wording a verified intent.

        Args:
            request: The original communication input
            intent: The interpreted intent frame
            passport: The user's Communication Passport
            retrieval_result: Retrieved grounded context

        Returns:
            Expression dict with {"text": str, "used_evidence": list[str]} or None
        """
        try:
            expression = self.generation_service.generate_expression(
                intent_frame=intent,
                passport_context=passport,
                conversation_context=request.conversation_context or "",
            )
            return expression
        except Exception as exc:
            logger.error(f"Expression generation failed: {exc}")
            return None

    def _generate_alternatives(
        self,
        request: CommunicationInput,
        intent: IntentFrame,
        passport: Any,
        retrieval_result: dict,
    ) -> dict[str, Any]:
        """Generate two alternatives for MEDIUM confidence.

        Uses GenerationService.generate_candidates() to create multiple options.

        Args:
            request: The original communication input
            intent: The interpreted intent frame
            passport: The user's Communication Passport
            retrieval_result: Retrieved grounded context

        Returns:
            Expression dict with {"alternatives": list[dict]} containing 2 candidates
        """
        try:
            # Use fragments from intent concepts
            fragments = intent.concepts or request.fragments or []
            context = request.conversation_context or ""
            retrieved_facts = retrieval_result.get("context_block", "")
            valid_node_ids = retrieval_result.get("grounded_ids", [])

            # Generate 3 candidates but only return top 2 for MEDIUM confidence
            candidates = self.generation_service.generate_candidates(
                fragments=fragments,
                context=context,
                retrieved_facts=retrieved_facts,
                valid_node_ids=valid_node_ids,
                style_prompt="",
            )

            # Return top 2 alternatives
            alternatives = candidates[:2]
            return {
                "alternatives": alternatives,
                "used_evidence": retrieval_result.get("grounded_ids", []),
            }
        except Exception as exc:
            logger.error(f"Alternative generation failed: {exc}")
            # Fallback: build simple expressions from fragments
            fragments = intent.concepts or request.fragments or []
            text = " ".join(fragments).strip() or "I need a moment."
            text = text[0].upper() + text[1:] if text else "I need a moment."
            if text[-1] not in ".?!":
                text += "."

            return {
                "alternatives": [
                    {"text": text, "register": "neutral", "length_label": "short"}
                ],
                "used_evidence": [],
            }

    def _regenerate_expression(
        self,
        request: CommunicationInput,
        intent: IntentFrame,
        passport: Any,
        retrieval_result: dict,
        identity_result: Any,
    ) -> dict[str, Any] | None:
        """Attempt to regenerate expression after identity check failure.

        This is the one silent regeneration attempt when safe_to_present is False.

        Args:
            request: The original communication input
            intent: The interpreted intent frame
            passport: The user's Communication Passport
            retrieval_result: Retrieved grounded context
            identity_result: The failed identity check result

        Returns:
            New expression dict or None if regeneration fails
        """
        logger.info(
            f"Regenerating due to violated rules: {identity_result.violated_rules}"
        )

        # Try generate_candidates as fallback
        try:
            fragments = intent.concepts or request.fragments or []
            context = request.conversation_context or ""
            retrieved_facts = retrieval_result.get("context_block", "")
            valid_node_ids = retrieval_result.get("grounded_ids", [])

            candidates = self.generation_service.generate_candidates(
                fragments=fragments,
                context=context,
                retrieved_facts=retrieved_facts,
                valid_node_ids=valid_node_ids,
                style_prompt="",
            )

            if candidates:
                # Return the first candidate in expression format
                return {
                    "text": candidates[0]["text"],
                    "used_evidence": candidates[0].get("grounded_node_ids", []),
                }
        except Exception as exc:
            logger.error(f"Regeneration failed: {exc}")

        return None

    def _fallback_response(
        self, intent: IntentFrame, band: ConfidenceBand
    ) -> dict[str, Any]:
        """Build a fallback response when generation fails entirely.

        Args:
            intent: The interpreted intent frame
            band: The confidence band

        Returns:
            Fallback API response dict
        """
        # Build a simple fallback expression from intent concepts
        concepts = intent.concepts or []
        text = " ".join(concepts).strip() or "I need a moment."
        text = text[0].upper() + text[1:] if text else "I need a moment."
        if text[-1] not in ".?!":
            text += "."

        expression = {"text": text, "used_evidence": []}

        return {
            "status": "ready",
            "intent": intent.model_dump(),
            "expression": expression,
            "identity": None,
            "confidence_band": band.value,
            "requires_confirmation": True,
            "fallback": True,
        }
