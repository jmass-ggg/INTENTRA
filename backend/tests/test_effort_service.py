"""Tests for EffortService — emergency phrases and effort modes.

Requirements: 11.6, 12.1, 12.2
"""

import pytest
from app.services.effort import EffortService
from app.domain.communication import EffortMode


def test_emergency_phrases_without_dependencies():
    """
    Test that emergency phrases are returned even when all dependencies are None.
    
    Property 6: Emergency mode is AI-independent
    Validates: Requirements 11.6, 12.1, 12.2
    """
    # Create service with all dependencies as None
    service = EffortService(graph=None, passport=None)
    
    phrases = service.get_emergency_phrases("test_person")
    
    # Should return default phrases
    assert isinstance(phrases, list)
    assert len(phrases) > 0
    assert "I need help." in phrases
    assert "I am in pain." in phrases
    assert "Call my caregiver." in phrases


def test_effort_config_without_dependencies():
    """Test effort config returns defaults when dependencies are None."""
    service = EffortService(graph=None, passport=None)
    
    config = service.get_effort_config("test_person")
    
    assert isinstance(config, dict)
    assert "effort_mode" in config
    assert "emergency_phrases" in config
    assert "low_effort_buttons" in config
    assert len(config["emergency_phrases"]) > 0


def test_default_emergency_phrases_constant():
    """Test that DEFAULT_EMERGENCY_PHRASES is properly defined."""
    phrases = EffortService.DEFAULT_EMERGENCY_PHRASES
    
    assert isinstance(phrases, list)
    assert len(phrases) >= 6
    assert "I need help." in phrases
    assert "I am in pain." in phrases
    assert "Call my caregiver." in phrases
    assert "Call my family." in phrases
    assert "I cannot breathe." in phrases
    assert "I need medical help." in phrases


def test_effort_mode_validation():
    """Test that effort mode values are valid."""
    service = EffortService()
    
    # Valid effort modes
    for mode in [EffortMode.full, EffortMode.assist, EffortMode.low_effort, EffortMode.emergency]:
        config = {"effort_mode": mode.value}
        # Should not raise
        service.save_effort_config("test_person", config)


def test_get_effort_config_returns_full_by_default():
    """Test that default effort mode is 'full'."""
    service = EffortService(graph=None)
    
    config = service.get_effort_config("test_person")
    
    assert config["effort_mode"] == "full"


def test_emergency_phrases_immutable():
    """Test that getting emergency phrases doesn't mutate the defaults."""
    service = EffortService()
    
    phrases1 = service.get_emergency_phrases("person1")
    phrases2 = service.get_emergency_phrases("person2")
    
    # Should be equal but not the same object
    assert phrases1 == phrases2
    assert phrases1 is not phrases2
    
    # Modifying one shouldn't affect the other or the defaults
    phrases1.append("Custom phrase")
    assert len(phrases2) < len(phrases1)
    assert len(EffortService.DEFAULT_EMERGENCY_PHRASES) < len(phrases1)
