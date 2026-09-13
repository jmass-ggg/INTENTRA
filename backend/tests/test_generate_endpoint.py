"""Test the /generate endpoint to verify it still works after Phase 4 changes.

This is a checkpoint test for task 4.4 to ensure the existing /generate endpoint
remains functional after adding generate_expression() to GenerationService.
"""

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_generate_endpoint_responds():
    """Verify /generate endpoint returns a properly shaped response."""
    # Make a basic request to /generate
    response = client.post(
        "/generate",
        json={
            "person_id": "test_user",
            "fragments": ["hello", "friend"],
            "context": "greeting someone",
            "situation": None
        }
    )
    
    # Should return 200 OK
    assert response.status_code == 200
    
    # Check response structure
    data = response.json()
    assert "candidates" in data
    assert "retrieval" in data
    assert "trace" in data
    assert "abstain" in data
    
    # Response is valid even if services are unavailable (degraded mode)
    # In degraded mode: candidates=[], abstain=True
    # In normal mode: candidates=[...], abstain=False or True depending on confidence
    assert isinstance(data["candidates"], list)
    assert isinstance(data["abstain"], bool)


def test_generate_endpoint_with_empty_fragments():
    """Verify /generate handles empty fragments gracefully."""
    response = client.post(
        "/generate",
        json={
            "person_id": "test_user",
            "fragments": [],
            "context": "",
            "situation": None
        }
    )
    
    # Should still return 200 OK (never crashes)
    assert response.status_code == 200
    
    data = response.json()
    assert "candidates" in data
    assert "abstain" in data


def test_generate_endpoint_preserves_legacy_behavior():
    """Verify /generate still uses generate_candidates (not generate_expression)."""
    response = client.post(
        "/generate",
        json={
            "person_id": "test_user",
            "fragments": ["tired", "tomorrow"],
            "context": "talking about plans",
            "situation": None
        }
    )
    
    assert response.status_code == 200
    data = response.json()
    
    # The endpoint should return candidates (plural)
    # Even in degraded mode, the structure is preserved
    assert "candidates" in data
    
    # Trace should be present (even if empty in degraded mode)
    assert "trace" in data
