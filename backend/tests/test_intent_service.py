"""Tests for IntentService.

Includes both unit tests and property-based tests using Hypothesis.
"""

import pytest
from hypothesis import given, strategies as st, settings

from app.domain.communication import CommunicationInput, EffortMode
from app.domain.intent import IntentFrame, IntentType, InputMethod
from app.services.intent import IntentService


# Hypothesis strategies for generating test data

@st.composite
def communication_input_strategy(draw):
    """Generate random CommunicationInput values."""
    # Generate random fragments (0-10 words)
    fragment_count = draw(st.integers(min_value=0, max_value=10))
    fragments = [
        draw(st.text(alphabet=st.characters(whitelist_categories=('Lu', 'Ll')), min_size=1, max_size=20))
        for _ in range(fragment_count)
    ]
    
    # Generate optional fields
    intent_type = draw(st.none() | st.sampled_from(list(IntentType)))
    listener = draw(st.none() | st.text(min_size=1, max_size=50))
    emotion = draw(st.none() | st.text(min_size=1, max_size=20))
    partial_speech = draw(st.none() | st.text(min_size=0, max_size=200))
    
    return CommunicationInput(
        person_id=draw(st.text(alphabet=st.characters(whitelist_categories=('Lu', 'Ll', 'Nd')), min_size=1, max_size=64)),
        fragments=fragments,
        intent_type=intent_type,
        listener=listener,
        emotion=emotion,
        partial_speech=partial_speech,
        selected_symbols=[],
        conversation_context=draw(st.none() | st.text(max_size=200)),
        effort_mode=draw(st.sampled_from(list(EffortMode))),
        input_methods=[],
    )


# Property-based tests

@given(communication_input_strategy())
@settings(max_examples=100)
def test_intent_confidence_bounded(input_data):
    """Property 1: IntentFrame confidence is bounded.
    
    Feature: intentra-refactor, Property 1: For any CommunicationInput,
    the IntentFrame produced by IntentService shall have a confidence
    value in [0.0, 1.0].
    
    Validates: Requirements 3.6
    """
    # Arrange: Create IntentService without LLM (deterministic mode only for speed)
    service = IntentService(llm=None)
    
    # Act: Interpret the input
    frame = service.interpret(input_data)
    
    # Assert: Confidence is bounded
    assert isinstance(frame, IntentFrame), "Service must return IntentFrame"
    assert 0.0 <= frame.confidence <= 1.0, (
        f"Confidence {frame.confidence} not in [0.0, 1.0] for input: {input_data}"
    )


@given(st.text(min_size=0, max_size=1000))
@settings(max_examples=100)
def test_pydantic_validation_fallback(malformed_json):
    """Property 10: Pydantic validation fallback.
    
    Feature: intentra-refactor, Property 10: For any LLM response that fails
    to parse as a valid IntentFrame, the system shall return a deterministic
    fallback (not raise an unhandled exception and not pass raw LLM text to
    the frontend).
    
    Validates: Requirements 2.8, 3.4
    """
    # Arrange: Create a mock LLM that returns malformed output
    class MalformedLLM:
        def generate_json(self, prompt, system=None):
            # Return various forms of malformed data
            import json
            # Try to make it look like JSON but be invalid for IntentFrame
            try:
                # If the input is valid JSON, return it
                return json.loads(malformed_json)
            except:
                # Otherwise return a dict with wrong fields
                return {"invalid_field": malformed_json}
    
    service = IntentService(llm=MalformedLLM())
    
    # Create a simple test input
    input_data = CommunicationInput(
        person_id="test",
        fragments=["help"],
    )
    
    # Act & Assert: Should not raise, should return valid IntentFrame
    try:
        frame = service.interpret(input_data)
        assert isinstance(frame, IntentFrame), "Must return IntentFrame on LLM failure"
        assert 0.0 <= frame.confidence <= 1.0, "Fallback confidence must be bounded"
    except Exception as exc:
        pytest.fail(f"IntentService raised exception instead of falling back: {exc}")


# Unit tests for deterministic paths

def test_explicit_intent_type_passthrough():
    """Test: explicit intent_type is used directly.
    
    Validates: Requirements 3.1, 3.2
    """
    # Arrange
    service = IntentService(llm=None)
    input_data = CommunicationInput(
        person_id="elena",
        fragments=["tired", "tomorrow"],
        intent_type=IntentType.answer,
    )
    
    # Act
    frame = service.interpret(input_data)
    
    # Assert
    assert frame.action == IntentType.answer
    assert frame.confidence == 0.95  # High confidence for explicit intent
    assert "explicit_intent_type" in frame.evidence


def test_known_fragment_pattern_help():
    """Test: single fragment 'help' classified as request.
    
    Validates: Requirements 3.1, 3.2
    """
    # Arrange
    service = IntentService(llm=None)
    input_data = CommunicationInput(
        person_id="elena",
        fragments=["help"],
    )
    
    # Act
    frame = service.interpret(input_data)
    
    # Assert
    assert frame.action == IntentType.request
    assert frame.confidence == 0.85  # Good confidence for known pattern
    assert any("known_pattern" in e for e in frame.evidence)


def test_known_fragment_pattern_yes():
    """Test: single fragment 'yes' classified as answer.
    
    Validates: Requirements 3.1, 3.2
    """
    # Arrange
    service = IntentService(llm=None)
    input_data = CommunicationInput(
        person_id="elena",
        fragments=["yes"],
    )
    
    # Act
    frame = service.interpret(input_data)
    
    # Assert
    assert frame.action == IntentType.answer
    assert frame.confidence == 0.85


def test_empty_fragments_unknown_intent():
    """Test: empty fragments result in unknown intent with low confidence.
    
    Validates: Requirements 3.1, 3.2
    """
    # Arrange
    service = IntentService(llm=None)
    input_data = CommunicationInput(
        person_id="elena",
        fragments=[],
    )
    
    # Act
    frame = service.interpret(input_data)
    
    # Assert
    assert frame.action == IntentType.unknown
    assert frame.confidence == 0.1  # Very low confidence
    assert "no_input" in frame.unresolved


def test_multiple_fragments_fallback():
    """Test: multiple unknown fragments use deterministic fallback."""
    # Arrange
    service = IntentService(llm=None)  # No LLM, forces fallback
    input_data = CommunicationInput(
        person_id="elena",
        fragments=["tired", "tomorrow", "visit"],
    )
    
    # Act
    frame = service.interpret(input_data)
    
    # Assert
    assert isinstance(frame, IntentFrame)
    assert frame.confidence <= 0.5  # Moderate or low confidence for fallback
    assert "deterministic_fallback" in frame.evidence
