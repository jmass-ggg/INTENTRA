"""Tests for IdentityGuard.

Includes both unit tests and property-based tests using Hypothesis.
"""

import pytest
from hypothesis import given, strategies as st, settings

from app.domain.identity import IdentityResult
from app.domain.intent import IntentFrame, IntentType
from app.domain.passport import CommunicationPassport, PersonProfile
from app.services.identity_guard import IdentityGuard


# Hypothesis strategies for generating test data

@st.composite
def avoided_expression_with_containing_text(draw):
    """Generate an avoided phrase and a text that contains it."""
    # Generate a simple avoided phrase
    avoided_phrase = draw(
        st.text(
            alphabet=st.characters(whitelist_categories=('Lu', 'Ll'), min_codepoint=65, max_codepoint=122),
            min_size=3,
            max_size=20
        ).filter(lambda x: x.strip() != "")
    )
    
    # Generate text that contains the avoided phrase
    # Add prefix and suffix to make it look like a sentence
    prefix = draw(st.text(
        alphabet=st.characters(whitelist_categories=('Lu', 'Ll'), min_codepoint=65, max_codepoint=122),
        min_size=0,
        max_size=30
    ))
    suffix = draw(st.text(
        alphabet=st.characters(whitelist_categories=('Lu', 'Ll'), min_codepoint=65, max_codepoint=122),
        min_size=0,
        max_size=30
    ))
    
    # Construct expression containing the avoided phrase
    expression = f"{prefix} {avoided_phrase} {suffix}".strip()
    
    return avoided_phrase, expression


# Property-based tests

@given(avoided_expression_with_containing_text())
@settings(max_examples=100)
def test_avoided_expressions_rejected(data):
    """Property 3: Avoided expressions are rejected.
    
    Feature: intentra-refactor, Property 3: For any Communication Passport
    containing an avoided expression E, and any generated expression containing
    E as a substring (case-insensitive), the IdentityGuard shall set
    safe_to_present = false and include the violated rule in violated_rules.
    
    Validates: Requirements 6.1, 6.3, 14.2, 14.3
    """
    avoided_phrase, expression = data
    
    # Arrange
    guard = IdentityGuard(style_service=None)
    
    passport = CommunicationPassport(
        person_id="test_user",
        avoided_expressions=[avoided_phrase]
    )
    
    intent = IntentFrame(
        action=IntentType.request,
        concepts=["help"],
        confidence=0.9
    )
    
    # Act
    result = guard.verify(
        intent=intent,
        expression=expression,
        passport=passport,
        evidence_ids=[]
    )
    
    # Assert
    assert result.safe_to_present is False, (
        f"Expression '{expression}' containing avoided phrase '{avoided_phrase}' "
        "should not be safe to present"
    )
    assert any(avoided_phrase.lower() in rule.lower() for rule in result.violated_rules), (
        f"Avoided phrase '{avoided_phrase}' should appear in violated_rules: {result.violated_rules}"
    )


# Unit tests

def test_no_avoided_phrases_safe_to_present():
    """Test: no avoided phrases results in safe_to_present = True.
    
    Validates: Requirements 6.1, 6.2, 6.4
    """
    # Arrange
    guard = IdentityGuard(style_service=None)
    
    passport = CommunicationPassport(
        person_id="elena",
        avoided_expressions=[]  # No avoided expressions
    )
    
    intent = IntentFrame(
        action=IntentType.answer,
        concepts=["tired", "tomorrow"],
        confidence=0.9
    )
    
    expression = "I'm tired tonight. Could we talk tomorrow instead?"
    
    # Act
    result = guard.verify(
        intent=intent,
        expression=expression,
        passport=passport,
        evidence_ids=["node_123"]
    )
    
    # Assert
    assert result.safe_to_present is True
    assert len(result.violated_rules) == 0
    assert result.hallucination_risk < 0.5


def test_unknown_capitalized_name_increases_hallucination_risk():
    """Test: unknown capitalized name not in passport increases hallucination_risk.
    
    Validates: Requirements 6.1, 6.2, 6.4
    """
    # Arrange
    guard = IdentityGuard(style_service=None)
    
    passport = CommunicationPassport(
        person_id="elena",
        people=[
            PersonProfile(id="sofia", name="Sofia", relationship="daughter")
        ]
    )
    
    intent = IntentFrame(
        action=IntentType.answer,
        concepts=["visit"],
        confidence=0.9
    )
    
    # Expression mentions unknown person "Marcus"
    expression = "Could you ask Marcus to visit tomorrow?"
    
    # Act
    result = guard.verify(
        intent=intent,
        expression=expression,
        passport=passport,
        evidence_ids=[]  # Marcus is not in evidence either
    )
    
    # Assert
    assert result.hallucination_risk > 0.0, "Unknown entity should increase hallucination risk"
    assert any("Marcus" in rule for rule in result.violated_rules), (
        f"Marcus should be flagged as unknown entity in: {result.violated_rules}"
    )
    assert result.safe_to_present is False, "Unknown entity should make expression unsafe"


def test_all_concepts_missing_low_intent_match():
    """Test: all IntentFrame concepts missing from expression results in low intent_match.
    
    Validates: Requirements 6.1, 6.2, 6.4
    """
    # Arrange
    guard = IdentityGuard(style_service=None)
    
    passport = CommunicationPassport(
        person_id="elena",
        people=[]
    )
    
    intent = IntentFrame(
        action=IntentType.request,
        concepts=["water", "drink", "thirsty"],  # These concepts
        confidence=0.9
    )
    
    # Expression doesn't mention any of the concepts
    expression = "Please help me with the remote control."
    
    # Act
    result = guard.verify(
        intent=intent,
        expression=expression,
        passport=passport,
        evidence_ids=[]
    )
    
    # Assert
    assert result.intent_match == 0.0, (
        f"Intent match should be 0.0 when no concepts present, got {result.intent_match}"
    )


def test_partial_concepts_match():
    """Test: some concepts present results in partial intent_match."""
    # Arrange
    guard = IdentityGuard(style_service=None)
    
    passport = CommunicationPassport(
        person_id="elena",
        people=[]
    )
    
    intent = IntentFrame(
        action=IntentType.request,
        concepts=["water", "drink", "thirsty"],
        confidence=0.9
    )
    
    # Expression mentions 2 out of 3 concepts
    expression = "I'm thirsty. Could I have some water?"
    
    # Act
    result = guard.verify(
        intent=intent,
        expression=expression,
        passport=passport,
        evidence_ids=[]
    )
    
    # Assert
    # 2 out of 3 concepts = 0.6667
    assert 0.6 <= result.intent_match <= 0.7, (
        f"Intent match should be ~0.67 for 2/3 concepts, got {result.intent_match}"
    )


def test_avoided_expression_case_insensitive():
    """Test: avoided expression detection is case-insensitive."""
    # Arrange
    guard = IdentityGuard(style_service=None)
    
    passport = CommunicationPassport(
        person_id="elena",
        avoided_expressions=["sweetie", "honey"]
    )
    
    intent = IntentFrame(
        action=IntentType.answer,
        concepts=["yes"],
        confidence=0.9
    )
    
    # Expression contains "SWEETIE" in different case
    expression = "Yes, SWEETIE, I would love that."
    
    # Act
    result = guard.verify(
        intent=intent,
        expression=expression,
        passport=passport,
        evidence_ids=[]
    )
    
    # Assert
    assert result.safe_to_present is False
    assert any("sweetie" in rule.lower() for rule in result.violated_rules)


def test_known_person_not_flagged():
    """Test: known people from passport are not flagged as hallucinations."""
    # Arrange
    guard = IdentityGuard(style_service=None)
    
    passport = CommunicationPassport(
        person_id="elena",
        people=[
            PersonProfile(id="sofia", name="Sofia", relationship="daughter"),
            PersonProfile(id="marco", name="Marco", relationship="son")
        ]
    )
    
    intent = IntentFrame(
        action=IntentType.request,
        concepts=["visit"],
        confidence=0.9
    )
    
    # Expression mentions known people
    expression = "Could Sofia and Marco visit this weekend?"
    
    # Act
    result = guard.verify(
        intent=intent,
        expression=expression,
        passport=passport,
        evidence_ids=[]
    )
    
    # Assert
    assert result.hallucination_risk == 0.0, "Known people should not increase hallucination risk"
    assert result.safe_to_present is True


def test_evidence_ids_prevent_hallucination_flag():
    """Test: capitalized names in evidence_ids are not flagged."""
    # Arrange
    guard = IdentityGuard(style_service=None)
    
    passport = CommunicationPassport(
        person_id="elena",
        people=[]
    )
    
    intent = IntentFrame(
        action=IntentType.answer,
        concepts=["visit"],
        confidence=0.9
    )
    
    # Expression mentions a name that's in evidence
    expression = "Yes, tell Victoria I would love to see her."
    
    # Act
    result = guard.verify(
        intent=intent,
        expression=expression,
        passport=passport,
        evidence_ids=["Victoria", "node_victoria_123"]
    )
    
    # Assert
    assert result.hallucination_risk == 0.0, (
        "Names in evidence_ids should not be flagged as hallucinations"
    )


def test_no_concepts_perfect_match():
    """Test: IntentFrame with no concepts results in perfect intent_match."""
    # Arrange
    guard = IdentityGuard(style_service=None)
    
    passport = CommunicationPassport(
        person_id="elena",
        people=[]
    )
    
    intent = IntentFrame(
        action=IntentType.social,
        concepts=[],  # No specific concepts
        confidence=0.9
    )
    
    expression = "Hello, how are you today?"
    
    # Act
    result = guard.verify(
        intent=intent,
        expression=expression,
        passport=passport,
        evidence_ids=[]
    )
    
    # Assert
    assert result.intent_match == 1.0, (
        "Intent match should be 1.0 when there are no concepts to match"
    )


def test_temporal_reference_increases_grounding():
    """Test: temporal reference from intent appearing in expression increases grounding."""
    # Arrange
    guard = IdentityGuard(style_service=None)
    
    passport = CommunicationPassport(
        person_id="elena",
        people=[]
    )
    
    intent = IntentFrame(
        action=IntentType.answer,
        concepts=["visit"],
        temporal_reference="tomorrow",
        confidence=0.9
    )
    
    # Expression with temporal reference
    expression_with_temporal = "Yes, please come tomorrow."
    expression_without_temporal = "Yes, please come visit."
    
    # Act
    result_with = guard.verify(
        intent=intent,
        expression=expression_with_temporal,
        passport=passport,
        evidence_ids=["node_123"]
    )
    
    result_without = guard.verify(
        intent=intent,
        expression=expression_without_temporal,
        passport=passport,
        evidence_ids=["node_123"]
    )
    
    # Assert
    assert result_with.grounding_score > result_without.grounding_score, (
        "Expression with temporal reference should have higher grounding score"
    )


def test_common_capitalized_words_not_flagged():
    """Test: common capitalized words (I, Could, etc.) are not flagged as entities."""
    # Arrange
    guard = IdentityGuard(style_service=None)
    
    passport = CommunicationPassport(
        person_id="elena",
        people=[]
    )
    
    intent = IntentFrame(
        action=IntentType.request,
        concepts=["help"],
        confidence=0.9
    )
    
    # Expression with common capitalized words
    expression = "Could you please help me? I really need assistance. Thank you."
    
    # Act
    result = guard.verify(
        intent=intent,
        expression=expression,
        passport=passport,
        evidence_ids=[]
    )
    
    # Assert
    assert result.hallucination_risk == 0.0, (
        "Common capitalized words should not be flagged as hallucinations"
    )
    assert result.safe_to_present is True


def test_high_hallucination_risk_unsafe():
    """Test: hallucination_risk >= 0.5 makes expression unsafe to present."""
    # Arrange
    guard = IdentityGuard(style_service=None)
    
    passport = CommunicationPassport(
        person_id="elena",
        people=[]
    )
    
    intent = IntentFrame(
        action=IntentType.answer,
        concepts=["visit"],
        confidence=0.9
    )
    
    # Expression with multiple unknown entities (high hallucination risk)
    expression = "Tell Marcus, Jennifer, and Robert to come visit."
    
    # Act
    result = guard.verify(
        intent=intent,
        expression=expression,
        passport=passport,
        evidence_ids=[]
    )
    
    # Assert
    assert result.hallucination_risk >= 0.5, (
        f"Multiple unknown entities should result in high hallucination risk, got {result.hallucination_risk}"
    )
    assert result.safe_to_present is False, (
        "High hallucination risk should make expression unsafe to present"
    )
