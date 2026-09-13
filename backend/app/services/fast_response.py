"""FastResponseEngine — detects simple partner questions for immediate responses.

Provides quick answer options for binary and choice questions without full AI pipeline.
Uses pure regex/pattern matching — no LLM calls.

Requirements: 16.1, 16.2, 16.3
"""

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger("intentra.fast_response")


class FastResponseEngine:
    """Detects simple question patterns and provides immediate answer options.
    
    This engine short-circuits the full communication pipeline for common
    conversational patterns like "Do you want tea or coffee?" by detecting
    the structure and offering quick answer buttons.
    """

    # Binary question patterns
    BINARY_PATTERNS = [
        r"\bare you\b",
        r"\bdo you\b",
        r"\bdoes it\b",
        r"\bwould you\b",
        r"\bwill you\b",
        r"\bcan you\b",
        r"\bcould you\b",
        r"\bshould you\b",
        r"\bis it\b",
        r"\bis that\b",
        r"\bwas it\b",
        r"\bhave you\b",
        r"\bhas it\b",
        r"\bdid you\b",
    ]

    # Choice question pattern: "X or Y"
    # Improved to avoid capturing verb phrases before the choices
    # Look for nouns/noun phrases separated by "or"
    CHOICE_PATTERN = r"\b([\w\s]+?)\s+or\s+([\w\s]+?)(?:\?|$)"

    # Default options for each type
    BINARY_OPTIONS = ["Yes", "No", "A little", "Explain"]
    FALLBACK_CHOICE_OPTIONS = ["Neither", "Something else"]

    def __init__(self) -> None:
        """Initialize FastResponseEngine."""
        # Compile patterns for efficiency
        self.binary_regex = re.compile(
            "|".join(self.BINARY_PATTERNS), re.IGNORECASE
        )
        self.choice_regex = re.compile(self.CHOICE_PATTERN, re.IGNORECASE)

    def analyze(self, partner_speech: str) -> dict[str, Any]:
        """Analyze partner speech and return appropriate response structure.

        Detection order:
        1. Choice questions (X or Y?) - checked first as they're more specific
        2. Binary questions (Are you...?, Do you...?, etc.)
        3. Complex (route to full pipeline)

        Args:
            partner_speech: The transcribed speech from conversation partner

        Returns:
            Dict with one of:
            - {"type": "binary", "options": ["Yes", "No", "A little", "Explain"]}
            - {"type": "choice", "options": [X, Y, "Neither", "Something else"]}
            - {"type": "pipeline"} for complex inputs
        """
        if not partner_speech or not partner_speech.strip():
            logger.info("Empty partner speech - routing to pipeline")
            return {"type": "pipeline"}

        speech = partner_speech.strip()
        logger.info(f"Analyzing partner speech: '{speech[:50]}...'")

        # Check for choice questions FIRST (more specific than binary)
        choice_result = self._extract_choice_question(speech)
        if choice_result is not None:
            logger.info(f"Detected choice question: {choice_result['options']}")
            return choice_result

        # Check for binary questions
        if self._is_binary_question(speech):
            logger.info("Detected binary question")
            return {
                "type": "binary",
                "options": self.BINARY_OPTIONS,
            }

        # Complex input - route to full pipeline
        logger.info("Complex input - routing to full pipeline")
        return {"type": "pipeline"}

    def _is_binary_question(self, speech: str) -> bool:
        """Check if speech matches binary question patterns.

        Args:
            speech: The partner's speech

        Returns:
            True if binary question detected
        """
        # Must have a binary pattern
        has_pattern = self.binary_regex.search(speech) is not None
        if not has_pattern:
            return False
        
        # Check if it's a simple question
        has_question_mark = speech.rstrip().endswith("?")
        word_count = len(speech.split())
        
        # Binary questions should be:
        # - Have a question mark AND be relatively short (< 15 words), OR
        # - Be very short (< 8 words) even without question mark
        is_simple = (has_question_mark and word_count < 15) or (word_count < 8)
        
        # Exclude if it has "what", "when", "where", "why", "how" - these are open-ended
        has_open_ended_word = any(
            word in speech.lower() 
            for word in ["what ", "when ", "where ", "why ", "how ", "which ", "who "]
        )
        
        return is_simple and not has_open_ended_word

    def _extract_choice_question(self, speech: str) -> dict[str, Any] | None:
        """Extract choices from "X or Y?" pattern.

        Args:
            speech: The partner's speech

        Returns:
            Choice response dict or None if no valid choice detected
        """
        # Look for "in the X or Y" pattern (time/place choices)
        time_place_match = re.search(
            r"\b(?:in the|at the|this|on)\s+([\w\s]+?)\s+or\s+(?:in the|at the|this|on\s+)?([\w\s]+?)(?:\?|$)",
            speech,
            re.IGNORECASE
        )
        
        if time_place_match:
            choice_x = time_place_match.group(1).strip()
            choice_y = time_place_match.group(2).strip()
        else:
            # Try pattern after common question verbs
            verb_match = re.search(
                r"(?:like|want|prefer|choose|have)\s+([\w\s]+?)\s+or\s+([\w\s]+?)(?:\?|$)",
                speech,
                re.IGNORECASE
            )
            
            if verb_match:
                choice_x = verb_match.group(1).strip()
                choice_y = verb_match.group(2).strip()
            else:
                # Try direct pattern: "X or Y?"
                direct_match = re.search(
                    r"\b([\w\s]{1,15}?)\s+or\s+([\w\s]{1,15}?)(?:\?|$)",
                    speech,
                    re.IGNORECASE
                )
                
                if not direct_match:
                    return None
                    
                choice_x = direct_match.group(1).strip()
                choice_y = direct_match.group(2).strip()
        
        # Clean up common prefixes/suffixes
        for prefix in ["the ", "a ", "an "]:
            if choice_x.lower().startswith(prefix):
                choice_x = choice_x[len(prefix):].strip()
            if choice_y.lower().startswith(prefix):
                choice_y = choice_y[len(prefix):].strip()
        
        # Validate choices aren't too long (should be 1-3 words typically)
        if len(choice_x.split()) > 4 or len(choice_y.split()) > 4:
            return None
        
        # Validate choices aren't empty
        if not choice_x or not choice_y:
            return None

        # Capitalize first letter of each choice
        choice_x = choice_x[0].upper() + choice_x[1:] if choice_x else choice_x
        choice_y = choice_y[0].upper() + choice_y[1:] if choice_y else choice_y

        # Build options list: [X, Y, "Neither", "Something else"]
        options = [choice_x, choice_y] + self.FALLBACK_CHOICE_OPTIONS

        return {
            "type": "choice",
            "options": options,
        }
