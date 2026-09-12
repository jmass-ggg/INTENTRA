"""Integration test for /intent/interpret endpoint."""

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.domain.intent import IntentType

client = TestClient(app)


def test_intent_interpret_endpoint_explicit_intent():
    """Test /intent/interpret with explicit intent_type."""
    response = client.post(
        "/intent/interpret",
        json={
            "person_id": "elena",
            "fragments": ["tired", "tomorrow"],
            "intent_type": "answer",
            "listener": "sofia",
        },
    )
    
    assert response.status_code == 200
    data = response.json()
    
    # Verify response structure
    assert "action" in data
    assert "concepts" in data
    assert "confidence" in data
    assert "evidence" in data
    
    # Verify content
    assert data["action"] == "answer"
    assert data["confidence"] >= 0.0
    assert data["confidence"] <= 1.0


def test_intent_interpret_endpoint_known_pattern():
    """Test /intent/interpret with known fragment pattern."""
    response = client.post(
        "/intent/interpret",
        json={
            "person_id": "test_user",
            "fragments": ["help"],
        },
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["action"] == "request"
    assert 0.0 <= data["confidence"] <= 1.0


def test_intent_interpret_endpoint_empty_fragments():
    """Test /intent/interpret with empty fragments."""
    response = client.post(
        "/intent/interpret",
        json={
            "person_id": "test_user",
            "fragments": [],
        },
    )
    
    assert response.status_code == 200
    data = response.json()
    
    assert data["action"] == "unknown"
    assert data["confidence"] <= 0.2  # Low confidence for empty input


def test_intent_interpret_endpoint_invalid_person_id():
    """Test /intent/interpret rejects invalid person_id."""
    # Path traversal attempt
    response = client.post(
        "/intent/interpret",
        json={
            "person_id": "../../../etc/passwd",
            "fragments": ["help"],
        },
    )
    
    assert response.status_code == 422
    assert "person_id" in response.text.lower()


def test_intent_interpret_endpoint_empty_person_id():
    """Test /intent/interpret rejects empty person_id."""
    response = client.post(
        "/intent/interpret",
        json={
            "person_id": "",
            "fragments": ["help"],
        },
    )
    
    assert response.status_code == 422


def test_intent_interpret_endpoint_valid_person_id_patterns():
    """Test /intent/interpret accepts valid person_id patterns."""
    valid_ids = [
        "alice",
        "bob123",
        "user_test",
        "test-user",
        "User_123-test",
    ]
    
    for person_id in valid_ids:
        response = client.post(
            "/intent/interpret",
            json={
                "person_id": person_id,
                "fragments": ["hello"],
            },
        )
        
        assert response.status_code == 200, f"Failed for person_id: {person_id}"
