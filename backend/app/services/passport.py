"""PassportService — facade over GraphService, StyleService, and LearningService.

Provides a user-facing Communication Passport representation backed by the
existing infrastructure.
"""

from __future__ import annotations

from typing import Any

from app.domain.passport import CommunicationPassport, PersonProfile


class PassportService:
    """Facade over GraphService, StyleService, LearningService exposing the
    Communication Passport concept."""

    def __init__(
        self,
        graph: Any | None = None,
        style: Any | None = None,
        learning: Any | None = None,
    ) -> None:
        self.graph = graph
        self.style = style
        self.learning = learning

    def get_passport(self, person_id: str) -> CommunicationPassport:
        """Retrieve the Communication Passport for a person.

        Maps graph nodes to passport fields:
        - contact → people
        - phrase → vocabulary
        - avoid_phrase → avoided_expressions
        - expression_preference → preferred_expressions
        - communication_rule → communication_rules
        - routine → routines

        Graceful degradation: returns empty passport if graph is None.
        """
        if self.graph is None:
            return CommunicationPassport(person_id=person_id)

        try:
            nodes = self.graph.person_nodes(person_id)
            edges = self.graph.person_edges(person_id)
        except Exception:
            # Graph unavailable or error - return empty passport
            return CommunicationPassport(person_id=person_id)

        # Build node lookup
        node_by_id = {n["id"]: n for n in nodes}

        # Map contacts to PersonProfile
        people: list[PersonProfile] = []
        for node in nodes:
            if node["kind"] == "contact":
                # Find address term from addresses_as edges
                address_term = None
                relationship = None
                for edge in edges:
                    if edge["type"] == "addresses_as":
                        if edge["source"] == node["id"]:
                            # This contact addresses someone
                            address_term = edge.get("term") or None
                        elif edge["target"] == node["id"]:
                            # Someone addresses this contact
                            pass
                
                people.append(
                    PersonProfile(
                        id=node["id"],
                        name=node["label"],
                        relationship=relationship,
                        address_term=address_term,
                    )
                )

        # Map other node kinds
        vocabulary = [n["label"] for n in nodes if n["kind"] == "phrase"]
        avoided_expressions = [n["label"] for n in nodes if n["kind"] == "avoid_phrase"]
        preferred_expressions = [
            n["label"] for n in nodes if n["kind"] == "expression_preference"
        ]
        communication_rules = [
            n["label"] for n in nodes if n["kind"] == "communication_rule"
        ]
        routines = [n["label"] for n in nodes if n["kind"] == "routine"]

        # Emergency phrases - get from phrases tagged as emergency or use defaults
        emergency_phrases = [
            n["label"]
            for n in nodes
            if n["kind"] == "phrase" and "emergency" in str(n.get("label", "")).lower()
        ]
        if not emergency_phrases:
            emergency_phrases = [
                "I need help.",
                "I am in pain.",
                "Call my caregiver.",
            ]

        return CommunicationPassport(
            person_id=person_id,
            people=people,
            vocabulary=vocabulary,
            preferred_expressions=preferred_expressions,
            avoided_expressions=avoided_expressions,
            communication_rules=communication_rules,
            routines=routines,
            emergency_phrases=emergency_phrases,
            repair_preferences=[],
            accessibility_preferences={},
        )

    def add_preference(self, person_id: str, expression: str) -> None:
        """Add a preferred expression to the passport.

        Creates or updates a node with kind=expression_preference.
        """
        if self.graph is None:
            return

        # Create a node ID based on the expression
        import hashlib
        import re

        slug = re.sub(r"[^a-z0-9]+", "_", expression.lower()).strip("_")[:48]
        expr_hash = hashlib.sha1(expression.encode("utf-8")).hexdigest()[:10]
        node_id = f"{person_id}:expr_pref_{slug}_{expr_hash}"

        try:
            # Create embedding if embedding provider is available
            embedding = None
            if hasattr(self, "embedding") and self.embedding:
                try:
                    embedding = self.embedding.embed(expression)
                except Exception:
                    pass

            self.graph.upsert_node(
                kind="expression_preference",
                id=node_id,
                label=expression,
                salience=1.0,
                embedding=embedding,
            )
        except Exception:
            pass

    def add_avoided(self, person_id: str, expression: str) -> None:
        """Add an avoided expression to the passport.

        Creates or updates a node with kind=avoid_phrase.
        """
        if self.graph is None:
            return

        # Create a node ID based on the expression
        import hashlib
        import re

        slug = re.sub(r"[^a-z0-9]+", "_", expression.lower()).strip("_")[:48]
        expr_hash = hashlib.sha1(expression.encode("utf-8")).hexdigest()[:10]
        node_id = f"{person_id}:avoid_{slug}_{expr_hash}"

        try:
            # Create embedding if embedding provider is available
            embedding = None
            if hasattr(self, "embedding") and self.embedding:
                try:
                    embedding = self.embedding.embed(expression)
                except Exception:
                    pass

            self.graph.upsert_node(
                kind="avoid_phrase",
                id=node_id,
                label=expression,
                salience=1.0,
                embedding=embedding,
            )
        except Exception:
            pass

    def update_passport(self, person_id: str, updates: dict) -> None:
        """Update passport fields by dispatching to appropriate graph upserts.

        Supports updating:
        - preferred_expressions: list of expressions to add
        - avoided_expressions: list of expressions to add
        - emergency_phrases: list of phrases to add
        """
        if self.graph is None:
            return

        # Add preferred expressions
        for expr in updates.get("preferred_expressions", []):
            self.add_preference(person_id, expr)

        # Add avoided expressions
        for expr in updates.get("avoided_expressions", []):
            self.add_avoided(person_id, expr)

        # Add emergency phrases
        for phrase in updates.get("emergency_phrases", []):
            # Add as regular phrase node with emergency tag
            import hashlib
            import re

            slug = re.sub(r"[^a-z0-9]+", "_", phrase.lower()).strip("_")[:48]
            phrase_hash = hashlib.sha1(phrase.encode("utf-8")).hexdigest()[:10]
            node_id = f"{person_id}:emergency_{slug}_{phrase_hash}"

            try:
                embedding = None
                if hasattr(self, "embedding") and self.embedding:
                    try:
                        embedding = self.embedding.embed(phrase)
                    except Exception:
                        pass

                self.graph.upsert_node(
                    kind="phrase",
                    id=node_id,
                    label=f"EMERGENCY: {phrase}",
                    salience=2.0,  # Higher salience for emergency phrases
                    embedding=embedding,
                )
            except Exception:
                pass
