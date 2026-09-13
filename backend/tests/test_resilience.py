"""Test failure resilience and degraded-mode behavior.

Verify that the system remains functional when individual AI components fail:
- LLM=None: structured AAC controls
- graph=None: empty passport, not 500
- TTS=None: empty audio
- Emergency phrases work when all services are None

Requirements: 19.1, 19.2, 19.3, 19.4, 19.5
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app, _singletons
from app.domain.communication import CommunicationInput, EffortMode
from app.domain.intent import IntentType
from app.services.effort import EffortService


@pytest.fixture
def client():
    """Create a test client."""
    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_singletons():
    """Reset singleton services before each test."""
    global _singletons
    original = _singletons.copy()
    yield
    _singletons = original


class TestDegradedModeLLM:
    """Test behavior when LLM is unavailable (Requirement 19.1)."""

    def test_communication_generate_without_llm(self, client):
        """When LLM=None, /communication/generate should return structured AAC controls.
        
        The IntentService uses deterministic fallback with moderate confidence,
        and the GenerationService builds simple expressions from fragments.
        System returns alternatives (structured controls) for user to choose from.
        
        Requirement 19.1: LLM unavailable → structured AAC controls (alternatives)
        """
        # Force LLM to None
        _singletons["llm"] = None
        # This also affects dependent services
        _singletons.pop("intent", None)
        _singletons.pop("generation", None)
        _singletons.pop("communication", None)

        response = client.post(
            "/communication/generate",
            json={
                "person_id": "test_user",
                "fragments": ["tired", "tomorrow"],
                "intent_type": None,
                "listener": "sofia",
                "emotion": None,
                "partial_speech": None,
                "selected_symbols": [],
                "conversation_context": "",
                "effort_mode": "full",
                "input_methods": ["word"],
            },
        )

        # Should return 200 with a valid response structure (not 503)
        assert response.status_code == 200
        data = response.json()
        
        # Should return structured controls (ready status with alternatives)
        # The deterministic fallback produces MEDIUM confidence, which triggers alternatives
        assert data["status"] == "ready"
        
        # Should provide alternatives (structured AAC controls) for user to choose
        assert "expression" in data
        assert "alternatives" in data["expression"] or "text" in data["expression"]
        
        # IntentService should indicate it used deterministic fallback
        assert "intent" in data
        intent = data["intent"]
        assert "llm_unavailable" in intent.get("unresolved", [])
        assert "deterministic_fallback" in intent.get("evidence", [])
        
        # Should still require confirmation (safety)
        assert data["requires_confirmation"] is True
        assert data["status"] in ["ready", "clarification_required"]

    def test_intent_interpret_without_llm(self, client):
        """When LLM=None, /intent/interpret should return deterministic fallback.
        
        IntentService should return a valid IntentFrame using deterministic
        classification. For "tired", it recognizes it as an emotion pattern.
        For multiple fragments, it uses fallback with moderate confidence.
        """
        # Force LLM to None
        _singletons["llm"] = None
        _singletons.pop("intent", None)

        response = client.post(
            "/intent/interpret",
            json={
                "person_id": "test_user",
                "fragments": ["tired", "tomorrow"],
                "intent_type": None,
                "listener": "sofia",
                "emotion": None,
                "partial_speech": None,
                "selected_symbols": [],
                "conversation_context": "",
                "effort_mode": "full",
                "input_methods": ["word"],
            },
        )

        assert response.status_code == 200
        data = response.json()
        
        # Should return valid IntentFrame
        # With "tired" in fragments, deterministic path may classify as emotion or unknown
        assert data["action"] in ["emotion", "unknown"]
        assert 0.0 <= data["confidence"] <= 1.0
        assert "tired" in data["concepts"] or "tomorrow" in data["concepts"]
        # Should indicate LLM was unavailable
        assert any("unavailable" in str(u).lower() or "uncertain" in str(u).lower() 
                   for u in data["unresolved"])


class TestDegradedModeGraph:
    """Test behavior when graph database is unavailable (Requirement 19.2)."""

    def test_passport_without_graph(self, client):
        """When graph=None, /passport/{id} should return empty passport, not 500.
        
        PassportService should gracefully degrade to a minimal non-personalized
        passport rather than crashing.
        """
        # Force graph to None
        _singletons["graph"] = None
        _singletons.pop("passport", None)
        _singletons.pop("retrieval", None)
        _singletons.pop("style", None)
        _singletons.pop("learning", None)

        response = client.get("/passport/test_user")

        # Should return 200 with empty passport, not 500
        assert response.status_code == 200
        data = response.json()
        
        assert data["person_id"] == "test_user"
        assert data["people"] == []
        assert data["vocabulary"] == []
        assert data["preferred_expressions"] == []
        assert data["avoided_expressions"] == []

    def test_graph_endpoint_without_graph(self, client):
        """When graph=None, /graph/{id} should return empty graph, not 500."""
        # Force graph to None
        _singletons["graph"] = None

        response = client.get("/graph/test_user")

        # Should return 200 with empty graph
        assert response.status_code == 200
        data = response.json()
        
        assert data["nodes"] == []
        assert data["edges"] == []

    def test_confirm_without_graph(self, client):
        """When graph=None, /confirm should return gracefully without crashing.
        
        Learning service depends on graph, so confirm should handle None gracefully.
        """
        # Force graph to None
        _singletons["graph"] = None
        _singletons.pop("learning", None)

        response = client.post(
            "/confirm",
            json={
                "person_id": "test_user",
                "text": "I'm tired, can we talk tomorrow?",
                "context": "",
                "partner": "sofia",
            },
        )

        # Should return 200 with empty result, not crash
        assert response.status_code == 200
        data = response.json()
        
        assert data["changed_node_ids"] == []
        assert data["changed_edge_ids"] == []


class TestDegradedModeTTS:
    """Test behavior when TTS is unavailable (Requirement 19.3)."""

    def test_speak_without_tts(self, client):
        """When TTS=None, /speak should return empty audio.
        
        Browser SpeechSynthesis handles the empty audio case,
        so the endpoint should not crash.
        """
        # Force TTS to None
        _singletons["tts"] = None

        response = client.post(
            "/speak",
            json={
                "person_id": "test_user",
                "text": "Hello world",
            },
        )

        # Should return 200 with empty or fallback audio
        assert response.status_code == 200
        data = response.json()
        
        # audio_base64 may be empty string when TTS unavailable
        assert "audio_base64" in data
        # cached should be False since no TTS was used
        assert data["cached"] is False


class TestEmergencyPhrasesResilience:
    """Test emergency phrases work without any AI services (Requirements 19.4, 19.5)."""

    def test_emergency_phrases_without_any_services(self, client):
        """Emergency phrases must work when LLM, graph, and embeddings are all None.
        
        This is critical for safety - emergency communication must always be available.
        """
        # Force all AI services to None
        _singletons["llm"] = None
        _singletons["graph"] = None
        _singletons["embedding"] = None
        _singletons.pop("effort", None)
        _singletons.pop("passport", None)
        _singletons.pop("retrieval", None)
        _singletons.pop("learning", None)
        _singletons.pop("style", None)

        response = client.get("/accessibility/test_user")

        # Emergency phrases MUST be returned even when all services are None
        assert response.status_code == 200
        data = response.json()
        
        assert "emergency_phrases" in data
        assert len(data["emergency_phrases"]) > 0
        
        # Check that default emergency phrases are present
        phrases = data["emergency_phrases"]
        assert "I need help." in phrases
        assert "I am in pain." in phrases

    def test_emergency_phrases_class_directly(self):
        """Test EffortService.get_emergency_phrases with all dependencies None.
        
        Direct unit test to ensure the service itself handles None dependencies.
        """
        # Create service with all dependencies None
        service = EffortService(graph=None, passport=None)
        
        phrases = service.get_emergency_phrases("test_user")
        
        # Should return default phrases
        assert len(phrases) > 0
        assert "I need help." in phrases
        assert "I am in pain." in phrases
        assert "Call my caregiver." in phrases
        assert "Call my family." in phrases
        assert "I cannot breathe." in phrases
        assert "I need medical help." in phrases

    def test_accessibility_endpoint_with_all_services_none(self, client):
        """Full integration test: accessibility endpoint with complete AI failure.
        
        Verifies that the endpoint returns defaults even when EffortService
        itself cannot be initialized.
        """
        # Force EffortService to None
        _singletons["effort"] = None
        _singletons["graph"] = None
        _singletons["passport"] = None

        response = client.get("/accessibility/test_user")

        assert response.status_code == 200
        data = response.json()
        
        # Should still return defaults
        assert data["effort_mode"] == "full"
        assert len(data["emergency_phrases"]) > 0
        assert "I need help." in data["emergency_phrases"]


class TestLowEffortModeResilience:
    """Test Low Effort mode works without AI (Requirement 19.5)."""

    def test_low_effort_buttons_without_ai(self, client):
        """Low Effort mode buttons should be available without AI services."""
        # Force all AI services to None
        _singletons["llm"] = None
        _singletons["graph"] = None
        _singletons["embedding"] = None

        response = client.get("/accessibility/test_user")

        assert response.status_code == 200
        data = response.json()
        
        # Low effort buttons should be present
        assert "low_effort_buttons" in data
        buttons = data["low_effort_buttons"]
        
        assert "YES" in buttons
        assert "NO" in buttons
        assert "HELP" in buttons
        assert "PAIN" in buttons
        assert "STOP" in buttons


class TestPersonIDValidation:
    """Test person_id validation prevents path traversal even in degraded mode."""

    def test_invalid_person_id_rejected_in_body(self, client):
        """Invalid person_id in request body should return 422 before any service is called."""
        # Force all services to None to ensure validation happens first
        _singletons["llm"] = None
        _singletons["graph"] = None

        # Try various malicious person_ids in POST body
        malicious_ids = [
            "../../../etc/passwd",
            "user/../admin",
            "user/../../secret",
            "user\x00admin",
            "",
            " ",
            "user with spaces",
        ]

        for person_id in malicious_ids:
            response = client.post(
                "/intent/interpret",
                json={
                    "person_id": person_id,
                    "fragments": ["test"],
                    "intent_type": None,
                    "listener": None,
                    "emotion": None,
                    "partial_speech": None,
                    "selected_symbols": [],
                    "conversation_context": "",
                    "effort_mode": "full",
                    "input_methods": ["word"],
                },
            )
            
            # Should return 422 validation error, not 500 or 200
            assert response.status_code == 422, f"Failed to reject: {person_id}"
            detail = str(response.json()["detail"]).lower()
            assert "person_id" in detail or "invalid" in detail

    def test_valid_person_id_accepted(self, client):
        """Valid person_id should pass validation."""
        valid_ids = ["user123", "test-user", "alice_bob", "a", "a" * 64]

        for person_id in valid_ids:
            # Even with no graph, should return 200 with empty passport
            _singletons["graph"] = None
            _singletons.pop("passport", None)
            
            response = client.get(f"/passport/{person_id}")
            
            # Should return 200, not 422
            assert response.status_code == 200, f"Failed to accept: {person_id}"
