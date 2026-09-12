"""Intent interpretation service."""

from __future__ import annotations

import json
import logging
from typing import TYPE_CHECKING

from pydantic import ValidationError

from app.domain.intent import IntentFrame, IntentType
from app.domain.communication import CommunicationInput
from app.prompts.intent import INTENT_SYSTEM_PROMPT

if TYPE_CHECKING:
    from app.providers.llm import LLMProvider

logger = logging.getLogger("intentra.intent")


class IntentService:
    """Interprets multimodal signals into an IntentFrame.
    
    Uses deterministic rules first, falls back to LLM when needed.
    Always returns a valid IntentFrame (never raises on bad input).
    """

    # Confidence thresholds
    HIGH = 0.75
    MEDIUM = 0.45

    # Known patterns for deterministic classification
    KNOWN_PATTERNS = {
        # Request patterns
        "help": IntentType.request,
        "need": IntentType.request,
        "want": IntentType.request,
        "please": IntentType.request,
        
        # Question patterns
        "what": IntentType.question,
        "where": IntentType.question,
        "when": IntentType.question,
        "who": IntentType.question,
        "why": IntentType.question,
        "how": IntentType.question,
        
        # Answer patterns
        "yes": IntentType.answer,
        "no": IntentType.answer,
        "maybe": IntentType.answer,
        "ok": IntentType.answer,
        "okay": IntentType.answer,
        
        # Emotion patterns
        "happy": IntentType.emotion,
        "sad": IntentType.emotion,
        "angry": IntentType.emotion,
        "tired": IntentType.emotion,
        "pain": IntentType.emotion,
        "hurt": IntentType.emotion,
        
        # Emergency patterns
        "emergency": IntentType.emergency,
        "urgent": IntentType.emergency,
        "911": IntentType.emergency,
        
        # Social patterns
        "hello": IntentType.social,
        "hi": IntentType.social,
        "goodbye": IntentType.social,
        "bye": IntentType.social,
        "thanks": IntentType.social,
        "thank": IntentType.social,
    }

    def __init__(self, llm: LLMProvider | None = None):
        """Initialize the IntentService.
        
        Args:
            llm: Optional LLM provider for complex intent interpretation
        """
        self.llm = llm

    def interpret(self, input: CommunicationInput) -> IntentFrame:
        """Interpret a CommunicationInput into an IntentFrame.
        
        Pipeline:
        1. Deterministic: if intent_type is set, use it directly
        2. Deterministic: classify single-fragment inputs to known patterns
        3. LLM: structured call with Pydantic validation
        4. Fallback: deterministic IntentFrame on any failure
        
        Args:
            input: The multimodal communication input
            
        Returns:
            A valid IntentFrame with confidence in [0.0, 1.0]
        """
        # Step 1: Deterministic passthrough if intent_type provided
        if input.intent_type is not None:
            logger.info(f"Using explicit intent_type: {input.intent_type}")
            return IntentFrame(
                action=input.intent_type,
                concepts=input.fragments,
                listener_name=input.listener,
                emotional_state=input.emotion,
                confidence=0.95,  # High confidence for explicit intent
                evidence=["explicit_intent_type"],
            )

        # Step 2: Deterministic classification for simple known patterns
        if len(input.fragments) == 1:
            fragment = input.fragments[0].lower().strip()
            if fragment in self.KNOWN_PATTERNS:
                intent_type = self.KNOWN_PATTERNS[fragment]
                logger.info(f"Deterministic classification: {fragment} -> {intent_type}")
                return IntentFrame(
                    action=intent_type,
                    concepts=input.fragments,
                    listener_name=input.listener,
                    emotional_state=input.emotion,
                    confidence=0.85,  # Good confidence for known patterns
                    evidence=[f"known_pattern:{fragment}"],
                )

        # Step 3: Empty fragments case
        if not input.fragments and not input.partial_speech:
            logger.info("Empty input -> unknown intent with low confidence")
            return IntentFrame(
                action=IntentType.unknown,
                concepts=[],
                confidence=0.1,
                unresolved=["no_input"],
                evidence=[],
            )

        # Step 4: LLM interpretation
        if self.llm is not None:
            try:
                frame = self._llm_interpret(input)
                if frame is not None:
                    # Clamp confidence to [0.0, 1.0]
                    frame.confidence = max(0.0, min(1.0, frame.confidence))
                    logger.info(f"LLM interpretation successful: {frame.action}, confidence={frame.confidence}")
                    return frame
            except Exception as exc:
                logger.warning(f"LLM interpretation failed: {exc}")

        # Step 5: Fallback - create deterministic IntentFrame from fragments
        logger.info("Using deterministic fallback IntentFrame")
        return self._deterministic_fallback(input)

    def _llm_interpret(self, input: CommunicationInput) -> IntentFrame | None:
        """Use LLM to interpret the input into an IntentFrame.
        
        Makes a single structured call, validates with Pydantic.
        On parse failure, attempts one repair, then returns None.
        
        Args:
            input: The communication input
            
        Returns:
            IntentFrame if successful, None on failure
        """
        if self.llm is None:
            return None

        # Build the user prompt
        prompt = self._build_llm_prompt(input)

        try:
            # First attempt: structured JSON call
            response = self.llm.generate_json(prompt, system=INTENT_SYSTEM_PROMPT)
            return self._parse_llm_response(response)
        except (json.JSONDecodeError, ValidationError, KeyError) as exc:
            logger.warning(f"LLM response parse failed (attempt 1): {exc}")
            
            # One repair attempt: try again with explicit JSON instruction
            try:
                repair_prompt = prompt + "\n\nIMPORTANT: Return ONLY valid JSON matching the schema."
                response = self.llm.generate_json(repair_prompt, system=INTENT_SYSTEM_PROMPT)
                return self._parse_llm_response(response)
            except Exception as repair_exc:
                logger.warning(f"LLM repair attempt failed: {repair_exc}")
                return None

    def _build_llm_prompt(self, input: CommunicationInput) -> str:
        """Build the user prompt for LLM interpretation."""
        parts = []
        
        if input.fragments:
            parts.append(f"fragments={input.fragments}")
        
        if input.partial_speech:
            parts.append(f"partial_speech=\"{input.partial_speech}\"")
        
        if input.listener:
            parts.append(f"listener=\"{input.listener}\"")
        
        if input.emotion:
            parts.append(f"emotion=\"{input.emotion}\"")
        
        if input.selected_symbols:
            parts.append(f"symbols={input.selected_symbols}")
        
        if input.conversation_context:
            parts.append(f"context=\"{input.conversation_context}\"")
        
        return "Input: " + ", ".join(parts)

    def _parse_llm_response(self, response: dict) -> IntentFrame:
        """Parse and validate LLM response into IntentFrame.
        
        Args:
            response: The LLM JSON response
            
        Returns:
            Validated IntentFrame
            
        Raises:
            ValidationError: If response doesn't match schema
        """
        # Pydantic will validate and raise ValidationError if invalid
        frame = IntentFrame(**response)
        
        # Ensure confidence is bounded (Pydantic ge/le should handle this)
        frame.confidence = max(0.0, min(1.0, frame.confidence))
        
        return frame

    def _deterministic_fallback(self, input: CommunicationInput) -> IntentFrame:
        """Create a deterministic fallback IntentFrame when LLM fails.
        
        Args:
            input: The communication input
            
        Returns:
            A conservative IntentFrame with low confidence
        """
        # Try to infer intent from multiple fragments
        action = IntentType.unknown
        confidence = 0.3
        
        # Check if any fragment matches known patterns
        for fragment in input.fragments:
            fragment_lower = fragment.lower().strip()
            if fragment_lower in self.KNOWN_PATTERNS:
                action = self.KNOWN_PATTERNS[fragment_lower]
                confidence = 0.5  # Moderate confidence for partial match
                break
        
        return IntentFrame(
            action=action,
            concepts=input.fragments,
            listener_name=input.listener,
            emotional_state=input.emotion,
            confidence=confidence,
            unresolved=["llm_unavailable"] if self.llm is None else ["interpretation_uncertain"],
            evidence=["deterministic_fallback"],
        )
