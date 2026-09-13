"""RepairService — conversation repair strategies.

When a listener does not understand, this service selects and executes
a structured repair strategy to help the user re-attempt communication.
"""

from __future__ import annotations

import re
from typing import Any

from app.domain.intent import IntentFrame
from app.domain.repair import (
    RepairOption,
    RepairPlan,
    RepairRequest,
    RepairStrategy,
)


class RepairService:
    """Handles conversation repair after communication failure."""

    # Strategy priority order — YES_NO is tried first for fastest recovery
    STRATEGIES_BY_PRIORITY = [
        RepairStrategy.YES_NO,
        RepairStrategy.SHOW_CHOICES,
        RepairStrategy.SIMPLIFY,
        RepairStrategy.TIME_SELECTION,
        RepairStrategy.BODY_LOCATION,
        RepairStrategy.KEYWORD_ONLY,
    ]

    def __init__(self, learning_service: Any = None) -> None:
        """Initialize RepairService.
        
        Args:
            learning_service: Optional LearningService for recording outcomes
        """
        self.learning_service = learning_service

    def create_plan(self, req: RepairRequest) -> RepairPlan:
        """Create a repair plan based on the failed communication attempt.
        
        Args:
            req: RepairRequest containing context about the failure
            
        Returns:
            RepairPlan with selected strategy and options
        """
        # Select strategy based on context and what has already failed
        strategy = self._select_strategy(req)
        
        # Build the plan based on the selected strategy
        if strategy == RepairStrategy.YES_NO:
            return self._create_yes_no_plan(req)
        elif strategy == RepairStrategy.SHOW_CHOICES:
            return self._create_show_choices_plan(req)
        elif strategy == RepairStrategy.SIMPLIFY:
            return self._create_simplify_plan(req)
        elif strategy == RepairStrategy.TIME_SELECTION:
            return self._create_time_selection_plan(req)
        elif strategy == RepairStrategy.BODY_LOCATION:
            return self._create_body_location_plan(req)
        elif strategy == RepairStrategy.KEYWORD_ONLY:
            return self._create_keyword_only_plan(req)
        else:
            # Fallback to simplify if no other strategy matches
            return self._create_simplify_plan(req)

    def _select_strategy(self, req: RepairRequest) -> RepairStrategy:
        """Select the best repair strategy based on context.
        
        Args:
            req: RepairRequest containing failure context
            
        Returns:
            Selected RepairStrategy
        """
        intent = req.original_intent
        
        # Context-aware selection first (check specific conditions)
        # Skip any strategy that has already failed
        
        # YES_NO is always tried first unless it already failed
        if req.failed_strategy != RepairStrategy.YES_NO:
            return RepairStrategy.YES_NO
        
        # TIME_SELECTION for temporal references
        if (req.failed_strategy != RepairStrategy.TIME_SELECTION and 
            intent.temporal_reference):
            return RepairStrategy.TIME_SELECTION
            
        # BODY_LOCATION for pain/medical intents
        if (req.failed_strategy != RepairStrategy.BODY_LOCATION and
            (intent.action.value in ["request", "emergency"] or
             any(c in ["pain", "hurt", "ache", "sore"] 
                 for c in intent.concepts))):
            return RepairStrategy.BODY_LOCATION
            
        # SHOW_CHOICES when we have clear concepts
        if (req.failed_strategy != RepairStrategy.SHOW_CHOICES and 
            len(intent.concepts) >= 2):
            return RepairStrategy.SHOW_CHOICES
        
        # Fall back to priority list for remaining strategies
        for strategy in self.STRATEGIES_BY_PRIORITY:
            if strategy != req.failed_strategy:
                return strategy
            
        # If all strategies have been tried, cycle back to SIMPLIFY
        return RepairStrategy.SIMPLIFY

    def _create_yes_no_plan(self, req: RepairRequest) -> RepairPlan:
        """Create a YES_NO repair plan.
        
        Simplifies the expression and asks for confirmation.
        """
        simplified = self._simplify_expression(req.original_expression)
        question = f"Did you mean: {simplified}?"
        
        return RepairPlan(
            strategy=RepairStrategy.YES_NO,
            question=question,
            options=[
                RepairOption(label="Yes", value="yes"),
                RepairOption(label="No", value="no"),
            ],
        )

    def _create_show_choices_plan(self, req: RepairRequest) -> RepairPlan:
        """Create a SHOW_CHOICES repair plan.
        
        Extracts key concepts from IntentFrame and offers them as buttons.
        """
        concepts = req.original_intent.concepts[:6]  # Limit to 6 for UI
        
        if not concepts:
            # Fallback to simplify if no concepts
            return self._create_simplify_plan(req)
            
        question = "What did you want to say?"
        options = [
            RepairOption(label=concept.capitalize(), value=concept)
            for concept in concepts
        ]
        
        # Add "Something else" option
        options.append(RepairOption(label="Something else", value="other"))
        
        return RepairPlan(
            strategy=RepairStrategy.SHOW_CHOICES,
            question=question,
            options=options,
        )

    def _create_simplify_plan(self, req: RepairRequest) -> RepairPlan:
        """Create a SIMPLIFY repair plan.
        
        Extracts only the core concept keywords.
        """
        # Extract core keywords from concepts and expression
        concepts = req.original_intent.concepts[:3]
        
        # Build keyword-only expression
        if concepts:
            rebuilt = " ".join(concepts)
        else:
            # Fall back to extracting key words from original expression
            words = self._extract_keywords(req.original_expression)
            rebuilt = " ".join(words[:3])
            
        return RepairPlan(
            strategy=RepairStrategy.SIMPLIFY,
            question="Try this simpler version?",
            options=[
                RepairOption(label="Yes, say this", value="accept"),
                RepairOption(label="No, try again", value="reject"),
            ],
            rebuilt_expression=rebuilt,
        )

    def _create_time_selection_plan(self, req: RepairRequest) -> RepairPlan:
        """Create a TIME_SELECTION repair plan."""
        return RepairPlan(
            strategy=RepairStrategy.TIME_SELECTION,
            question="When did you mean?",
            options=[
                RepairOption(label="Today", value="today"),
                RepairOption(label="Yesterday", value="yesterday"),
                RepairOption(label="This week", value="this_week"),
                RepairOption(label="Earlier", value="earlier"),
            ],
        )

    def _create_body_location_plan(self, req: RepairRequest) -> RepairPlan:
        """Create a BODY_LOCATION repair plan."""
        return RepairPlan(
            strategy=RepairStrategy.BODY_LOCATION,
            question="Where does it hurt?",
            options=[
                RepairOption(label="Head", value="head"),
                RepairOption(label="Shoulder", value="shoulder"),
                RepairOption(label="Chest", value="chest"),
                RepairOption(label="Stomach", value="stomach"),
                RepairOption(label="Other", value="other"),
            ],
        )

    def _create_keyword_only_plan(self, req: RepairRequest) -> RepairPlan:
        """Create a KEYWORD_ONLY repair plan.
        
        Similar to SIMPLIFY but more aggressive — only essential words.
        """
        concepts = req.original_intent.concepts[:2]
        
        if not concepts:
            words = self._extract_keywords(req.original_expression)
            concepts = words[:2]
            
        rebuilt = " ".join(concepts) if concepts else req.original_expression.split()[0]
        
        return RepairPlan(
            strategy=RepairStrategy.KEYWORD_ONLY,
            question="Just the key words?",
            options=[
                RepairOption(label="Yes", value="accept"),
                RepairOption(label="No", value="reject"),
            ],
            rebuilt_expression=rebuilt,
        )

    def _simplify_expression(self, expression: str) -> str:
        """Simplify an expression to core meaning.
        
        Args:
            expression: Original expression text
            
        Returns:
            Simplified version
        """
        # Remove filler words and simplify grammar
        text = expression.lower()
        
        # Remove common filler patterns
        text = re.sub(r'\b(could|would|might|maybe|perhaps|possibly)\b', '', text)
        text = re.sub(r'\b(please|thank you|thanks)\b', '', text)
        text = re.sub(r'\s+', ' ', text).strip()
        
        # Keep it short — first 50 chars or first sentence
        if len(text) > 50:
            # Try to break at sentence boundary
            match = re.search(r'^[^.!?]+[.!?]', text)
            if match:
                text = match.group(0)
            else:
                text = text[:50].rsplit(' ', 1)[0] + '...'
                
        return text.capitalize()

    def _extract_keywords(self, text: str) -> list[str]:
        """Extract meaningful keywords from text.
        
        Args:
            text: Text to extract keywords from
            
        Returns:
            List of keywords
        """
        # Simple keyword extraction — filter out common stop words
        stopwords = {
            'a', 'an', 'the', 'and', 'or', 'but', 'is', 'are', 'was', 'were',
            'be', 'been', 'being', 'have', 'has', 'had', 'do', 'does', 'did',
            'will', 'would', 'should', 'could', 'can', 'may', 'might',
            'i', 'you', 'he', 'she', 'it', 'we', 'they', 'me', 'him', 'her',
            'us', 'them', 'my', 'your', 'his', 'her', 'its', 'our', 'their',
            'to', 'from', 'in', 'on', 'at', 'by', 'for', 'with', 'about',
        }
        
        # Extract words, filter stopwords, keep capitalized or >3 chars
        words = re.findall(r'\b[a-zA-Z]+\b', text.lower())
        keywords = [
            w for w in words 
            if w not in stopwords and len(w) > 3
        ]
        
        return keywords

    def rebuild_expression(
        self, 
        plan: RepairPlan, 
        selections: dict[str, str]
    ) -> str:
        """Rebuild an expression from repair plan selections.
        
        Args:
            plan: RepairPlan with strategy and options
            selections: User's selections from the repair options
            
        Returns:
            Rebuilt expression text
        """
        # If plan already has a rebuilt expression, use it
        if plan.rebuilt_expression:
            return plan.rebuilt_expression
            
        # Build expression from selections based on strategy
        if plan.strategy == RepairStrategy.TIME_SELECTION:
            time_val = selections.get("time", "")
            base = selections.get("base_concept", "")
            if time_val and base:
                return f"{base} {time_val}"
            return time_val or base
            
        elif plan.strategy == RepairStrategy.BODY_LOCATION:
            location = selections.get("location", "")
            action = selections.get("action", "pain")
            if location:
                return f"{location} {action}"
            return action
            
        elif plan.strategy == RepairStrategy.SHOW_CHOICES:
            # Combine selected concepts
            selected = [v for k, v in selections.items() if v != "other"]
            return " ".join(selected) if selected else ""
            
        else:
            # Generic fallback — join all selection values
            return " ".join(selections.values())

    def record_outcome(
        self, 
        req: RepairRequest, 
        success: bool
    ) -> None:
        """Record the outcome of a repair attempt.
        
        Args:
            req: RepairRequest that was attempted
            success: Whether the repair succeeded
        """
        # Record event with LearningService if available
        if self.learning_service:
            try:
                # Build event description
                strategy_name = req.failed_strategy.value if req.failed_strategy else "initial"
                outcome = "succeeded" if success else "failed"
                
                # We could extend LearningService to handle repair events
                # For now, we'll just make a note that we'd call it
                # self.learning_service.record_repair_event(req, success)
                pass
            except Exception:
                # Don't let logging failure break the flow
                pass
