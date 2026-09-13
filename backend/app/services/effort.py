"""EffortService — manages adaptive effort modes and emergency phrases.

Provides emergency phrases and effort mode configuration that must work
even when graph, LLM, and embeddings are unavailable.
"""

from __future__ import annotations

from typing import Any

from app.domain.communication import EffortMode


class EffortService:
    """Manages adaptive effort modes and emergency communication.

    Emergency phrases must work even when all AI services are None.
    """

    DEFAULT_EMERGENCY_PHRASES = [
        "I need help.",
        "I am in pain.",
        "Call my caregiver.",
        "Call my family.",
        "I cannot breathe.",
        "I need medical help.",
    ]

    def __init__(
        self,
        graph: Any | None = None,
        passport: Any | None = None,
    ) -> None:
        """Initialize EffortService.

        Args:
            graph: Optional GraphService for reading/writing preferences
            passport: Optional PassportService for reading emergency phrases
        """
        self.graph = graph
        self.passport = passport

    def get_emergency_phrases(self, person_id: str) -> list[str]:
        """Get emergency phrases for a person.

        Reads from passport if available, otherwise returns defaults.
        Must work even when graph, LLM, and embeddings are None.

        Args:
            person_id: Person identifier

        Returns:
            List of emergency phrases
        """
        # Try to get from passport first
        if self.passport is not None:
            try:
                passport_data = self.passport.get_passport(person_id)
                if passport_data.emergency_phrases:
                    return passport_data.emergency_phrases
            except Exception:
                # Fall through to defaults
                pass

        # Always return defaults if passport unavailable or empty
        return self.DEFAULT_EMERGENCY_PHRASES.copy()

    def get_effort_config(self, person_id: str) -> dict:
        """Get effort mode configuration for a person.

        Returns saved effort mode preference from graph if available,
        otherwise returns default configuration.

        Args:
            person_id: Person identifier

        Returns:
            Dictionary with effort_mode and related preferences
        """
        config = {
            "effort_mode": EffortMode.full.value,
            "emergency_phrases": self.get_emergency_phrases(person_id),
            "low_effort_buttons": [
                "YES",
                "NO",
                "HELP",
                "MORE",
                "STOP",
                "PAIN",
                "HOME",
                "DRINK",
                "TOILET",
            ],
        }

        # Try to read saved effort mode from graph
        if self.graph is not None:
            try:
                # Look for a preference node with effort_mode setting
                nodes = self.graph.person_nodes(person_id)
                for node in nodes:
                    if node.get("kind") == "preference" and "effort_mode" in node:
                        config["effort_mode"] = node["effort_mode"]
                        break
            except Exception:
                # Fall back to defaults
                pass

        return config

    def save_effort_config(self, person_id: str, config: dict) -> None:
        """Save effort mode configuration for a person.

        Stores effort mode preference in graph if available.

        Args:
            person_id: Person identifier
            config: Configuration dictionary with effort_mode key
        """
        if self.graph is None:
            return

        effort_mode = config.get("effort_mode", EffortMode.full.value)

        # Validate effort_mode
        try:
            EffortMode(effort_mode)
        except ValueError:
            # Invalid effort mode, skip saving
            return

        try:
            # Create or update preference node
            node_id = f"{person_id}:effort_mode_pref"
            self.graph.upsert_node(
                kind="preference",
                id=node_id,
                label=f"Effort mode: {effort_mode}",
                salience=1.0,
                effort_mode=effort_mode,
            )
        except Exception:
            # Unable to save - fail silently
            pass
