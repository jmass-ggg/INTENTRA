"""Unit tests for RepairService."""

import pytest

from app.domain.intent import IntentFrame, IntentType
from app.domain.repair import RepairRequest, RepairStrategy
from app.services.repair import RepairService


def test_create_yes_no_plan():
    """Test YES_NO repair plan creation."""
    repair_service = RepairService()
    
    intent = IntentFrame(
        action=IntentType.request,
        concepts=["water", "drink"],
        confidence=0.8
    )
    
    request = RepairRequest(
        person_id="test_user",
        original_intent=intent,
        original_expression="Could you please get me some water to drink?"
    )
    
    plan = repair_service.create_plan(request)
    
    assert plan.strategy == RepairStrategy.YES_NO
    assert plan.question is not None
    assert "water" in plan.question.lower() or "drink" in plan.question.lower()
    assert len(plan.options) == 2
    assert plan.options[0].label == "Yes"
    assert plan.options[1].label == "No"


def test_create_show_choices_plan():
    """Test SHOW_CHOICES repair plan when YES_NO already failed."""
    repair_service = RepairService()
    
    intent = IntentFrame(
        action=IntentType.question,
        concepts=["sofia", "visit", "tonight"],
        confidence=0.7
    )
    
    request = RepairRequest(
        person_id="test_user",
        original_intent=intent,
        original_expression="Is Sofia visiting tonight?",
        failed_strategy=RepairStrategy.YES_NO
    )
    
    plan = repair_service.create_plan(request)
    
    assert plan.strategy == RepairStrategy.SHOW_CHOICES
    assert plan.question is not None
    assert len(plan.options) >= 2  # At least the concepts + "Something else"
    # Check that concepts are in the options
    option_values = [opt.value for opt in plan.options]
    assert "sofia" in option_values or "visit" in option_values


def test_create_time_selection_plan():
    """Test TIME_SELECTION repair plan for temporal references."""
    repair_service = RepairService()
    
    intent = IntentFrame(
        action=IntentType.answer,
        concepts=["tomorrow"],
        temporal_reference="tomorrow",
        confidence=0.6
    )
    
    request = RepairRequest(
        person_id="test_user",
        original_intent=intent,
        original_expression="Tomorrow would be better",
        failed_strategy=RepairStrategy.YES_NO
    )
    
    plan = repair_service.create_plan(request)
    
    # Should select TIME_SELECTION due to temporal_reference
    assert plan.strategy == RepairStrategy.TIME_SELECTION
    assert plan.question is not None
    assert len(plan.options) == 4  # Today, Yesterday, This week, Earlier
    option_labels = [opt.label for opt in plan.options]
    assert "Today" in option_labels
    assert "Yesterday" in option_labels


def test_create_body_location_plan():
    """Test BODY_LOCATION repair plan for pain-related intents."""
    repair_service = RepairService()
    
    intent = IntentFrame(
        action=IntentType.emergency,
        concepts=["pain", "hurt"],
        confidence=0.9
    )
    
    request = RepairRequest(
        person_id="test_user",
        original_intent=intent,
        original_expression="I'm in pain",
        failed_strategy=RepairStrategy.YES_NO
    )
    
    plan = repair_service.create_plan(request)
    
    # Should select BODY_LOCATION due to pain concept
    assert plan.strategy == RepairStrategy.BODY_LOCATION
    assert plan.question is not None
    assert len(plan.options) == 5  # Head, Shoulder, Chest, Stomach, Other
    option_labels = [opt.label for opt in plan.options]
    assert "Head" in option_labels
    assert "Stomach" in option_labels
    assert "Other" in option_labels


def test_create_simplify_plan():
    """Test SIMPLIFY repair plan is used when appropriate."""
    repair_service = RepairService()
    
    intent = IntentFrame(
        action=IntentType.answer,
        concepts=[],  # No concepts will cause SHOW_CHOICES to fallback to SIMPLIFY
        confidence=0.5
    )
    
    # Mark YES_NO as failed
    request = RepairRequest(
        person_id="test_user",
        original_intent=intent,
        original_expression="Could you possibly help me with something?",
        failed_strategy=RepairStrategy.YES_NO
    )
    
    plan = repair_service.create_plan(request)
    
    # With no concepts and YES_NO failed, should go to SIMPLIFY
    # (SHOW_CHOICES would be skipped since len(concepts) < 2)
    assert plan.strategy == RepairStrategy.SIMPLIFY
    assert plan.rebuilt_expression is not None
    assert len(plan.rebuilt_expression) > 0


def test_simplify_expression():
    """Test expression simplification."""
    repair_service = RepairService()
    
    original = "Could you possibly help me with something please?"
    simplified = repair_service._simplify_expression(original)
    
    # Should be shorter and remove filler words
    assert len(simplified) < len(original)
    assert "possibly" not in simplified.lower()
    assert "please" not in simplified.lower()


def test_extract_keywords():
    """Test keyword extraction from text."""
    repair_service = RepairService()
    
    text = "I would like to have some water please"
    keywords = repair_service._extract_keywords(text)
    
    # Should extract meaningful words, filter stopwords
    assert "water" in keywords
    assert "like" in keywords or "have" not in keywords  # 'have' is stopword
    assert "the" not in keywords
    assert "would" not in keywords


def test_rebuild_expression_time_selection():
    """Test rebuilding expression from time selection."""
    repair_service = RepairService()
    
    plan = repair_service._create_time_selection_plan(
        RepairRequest(
            person_id="test",
            original_intent=IntentFrame(action=IntentType.answer, concepts=["visit"]),
            original_expression="Visit me"
        )
    )
    
    selections = {"time": "tomorrow", "base_concept": "visit"}
    rebuilt = repair_service.rebuild_expression(plan, selections)
    
    assert "visit" in rebuilt.lower()
    assert "tomorrow" in rebuilt.lower()


def test_rebuild_expression_body_location():
    """Test rebuilding expression from body location selection."""
    repair_service = RepairService()
    
    plan = repair_service._create_body_location_plan(
        RepairRequest(
            person_id="test",
            original_intent=IntentFrame(action=IntentType.emergency, concepts=["pain"]),
            original_expression="I hurt"
        )
    )
    
    selections = {"location": "head", "action": "pain"}
    rebuilt = repair_service.rebuild_expression(plan, selections)
    
    assert "head" in rebuilt.lower()
    assert "pain" in rebuilt.lower()


def test_strategy_priority():
    """Test that YES_NO is always tried first."""
    repair_service = RepairService()
    
    intent = IntentFrame(
        action=IntentType.request,
        concepts=["help"],
        confidence=0.8
    )
    
    # Without any failed strategy, should default to YES_NO
    request = RepairRequest(
        person_id="test_user",
        original_intent=intent,
        original_expression="Can you help me?"
    )
    
    plan = repair_service.create_plan(request)
    assert plan.strategy == RepairStrategy.YES_NO


def test_record_outcome():
    """Test recording repair outcome (should not raise errors)."""
    repair_service = RepairService()
    
    request = RepairRequest(
        person_id="test_user",
        original_intent=IntentFrame(action=IntentType.request, concepts=["help"]),
        original_expression="Help"
    )
    
    # Should not raise any exceptions
    repair_service.record_outcome(request, success=True)
    repair_service.record_outcome(request, success=False)
