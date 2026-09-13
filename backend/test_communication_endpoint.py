#!/usr/bin/env python3
"""Test script to verify /communication/generate endpoint."""

import json
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_communication_generate_low_confidence():
    """Test LOW confidence path (clarification required)."""
    print("\n=== Testing LOW confidence (empty fragments) ===")
    
    response = client.post(
        "/communication/generate",
        json={
            "person_id": "test_user",
            "fragments": [],
            "intent_type": None,
            "listener": None,
            "emotion": None,
            "partial_speech": None,
            "selected_symbols": [],
            "conversation_context": None,
            "effort_mode": "full",
            "input_methods": [],
        },
    )
    
    print(f"Status: {response.status_code}")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    
    data = response.json()
    print(f"Response: {json.dumps(data, indent=2)}")
    
    # Verify response shape for LOW confidence
    assert "status" in data
    assert data["status"] == "clarification_required"
    assert "intent" in data
    assert "confidence_band" in data
    assert data["confidence_band"] == "low"
    assert "requires_confirmation" in data
    assert data["requires_confirmation"] is True
    assert "question" in data
    assert "options" in data
    assert isinstance(data["options"], list)
    
    # LOW confidence should NOT have an expression
    assert "expression" not in data or data.get("expression") is None
    
    print("✓ LOW confidence test passed")


def test_communication_generate_high_confidence():
    """Test HIGH confidence path (explicit intent)."""
    print("\n=== Testing HIGH confidence (explicit intent) ===")
    
    response = client.post(
        "/communication/generate",
        json={
            "person_id": "test_user",
            "fragments": ["tired", "tomorrow"],
            "intent_type": "answer",
            "listener": "Sofia",
            "emotion": "tired",
            "partial_speech": None,
            "selected_symbols": [],
            "conversation_context": "Sofia asked if I want to meet tonight",
            "effort_mode": "full",
            "input_methods": ["word"],
        },
    )
    
    print(f"Status: {response.status_code}")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    
    data = response.json()
    print(f"Response: {json.dumps(data, indent=2)}")
    
    # Verify response shape for HIGH confidence
    assert "status" in data
    assert data["status"] == "ready"
    assert "intent" in data
    assert "confidence_band" in data
    assert data["confidence_band"] == "high"
    assert "requires_confirmation" in data
    assert data["requires_confirmation"] is True
    assert "expression" in data
    assert data["expression"] is not None
    
    # HIGH confidence should have expression text
    if data["expression"]:
        assert "text" in data["expression"]
        assert isinstance(data["expression"]["text"], str)
        assert len(data["expression"]["text"]) > 0
    
    # Should have identity check results
    assert "identity" in data
    if data["identity"]:
        assert "safe_to_present" in data["identity"]
        assert "violated_rules" in data["identity"]
    
    print("✓ HIGH confidence test passed")


def test_communication_generate_invalid_person_id():
    """Test person_id validation."""
    print("\n=== Testing person_id validation ===")
    
    # Test with path traversal attempt
    response = client.post(
        "/communication/generate",
        json={
            "person_id": "../../../etc/passwd",
            "fragments": ["hello"],
            "intent_type": None,
            "listener": None,
            "emotion": None,
            "partial_speech": None,
            "selected_symbols": [],
            "conversation_context": None,
            "effort_mode": "full",
            "input_methods": [],
        },
    )
    
    print(f"Status: {response.status_code}")
    assert response.status_code == 422, f"Expected 422, got {response.status_code}"
    
    data = response.json()
    print(f"Response: {json.dumps(data, indent=2)}")
    
    assert "detail" in data
    print("✓ Invalid person_id rejected correctly")


def test_communication_confirm():
    """Test /communication/confirm endpoint."""
    print("\n=== Testing /communication/confirm ===")
    
    response = client.post(
        "/communication/confirm",
        json={
            "person_id": "test_user",
            "text": "I'm feeling tired.",
            "context": "Conversation with Sofia",
            "partner": "Sofia",
        },
    )
    
    print(f"Status: {response.status_code}")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    
    data = response.json()
    print(f"Response: {json.dumps(data, indent=2)}")
    
    assert "ok" in data
    assert data["ok"] is True
    
    print("✓ Confirm endpoint test passed")


def test_communication_repair():
    """Test /communication/repair stub endpoint."""
    print("\n=== Testing /communication/repair (stub) ===")
    
    response = client.post(
        "/communication/repair",
        json={
            "person_id": "test_user",
            "original_intent": {
                "action": "answer",
                "concepts": ["tired"],
                "confidence": 0.8,
            },
            "original_expression": "I'm tired.",
        },
    )
    
    print(f"Status: {response.status_code}")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    
    data = response.json()
    print(f"Response: {json.dumps(data, indent=2)}")
    
    # Stub should return a status
    assert "status" in data
    assert data["status"] == "stub"
    
    print("✓ Repair stub endpoint test passed")


def test_conversation_outcome():
    """Test /conversation/outcome endpoint."""
    print("\n=== Testing /conversation/outcome ===")
    
    response = client.post(
        "/conversation/outcome",
        json={
            "person_id": "test_user",
            "session_id": "test_session_123",
            "success": True,
            "expression": "I'm feeling tired.",
        },
    )
    
    print(f"Status: {response.status_code}")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}"
    
    data = response.json()
    print(f"Response: {json.dumps(data, indent=2)}")
    
    assert "ok" in data
    assert data["ok"] is True
    assert "recorded" in data
    
    print("✓ Conversation outcome endpoint test passed")


if __name__ == "__main__":
    print("Testing Communication API Endpoints")
    print("=" * 60)
    
    try:
        test_communication_generate_low_confidence()
        test_communication_generate_high_confidence()
        test_communication_generate_invalid_person_id()
        test_communication_confirm()
        test_communication_repair()
        test_conversation_outcome()
        
        print("\n" + "=" * 60)
        print("✓ All communication endpoint tests passed!")
        print("=" * 60)
    except AssertionError as e:
        print(f"\n✗ Test failed: {e}")
        exit(1)
    except Exception as e:
        print(f"\n✗ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        exit(1)
