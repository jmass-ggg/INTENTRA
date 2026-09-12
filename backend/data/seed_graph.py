"""Seed the Lucid Voice knowledge graph (Phase 2).

Builds the demo personas as GENERIC Nodes and Edges (single Node/Edge tables;
see :mod:`app.services.graph`), embeds each node's ``label + descriptor`` with
the local sentence-transformers model, stores the 384-dim vector on the node,
and seeds the weighted ``co_occurs`` pairings retrieval relies on.

Run from the backend directory::

    python -m data.seed_graph        # or: ./.venv/bin/python data/seed_graph.py

----------------------------------------------------------------------------
PRIMARY PERSONA — Elena
----------------------------------------------------------------------------
Elena, 67, retired high-school Spanish teacher; expressive aphasia after a
stroke; bilingual (English + Spanish), code-switches endearments with family.
Contacts: Marco (husband, "Marco"), Sofia (daughter, "sweetie"),
Mateo (grandson, 4, "mijo"; related_to Sofia). Routines: gardens in the
morning, naps after lunch, dinner ~6pm, calls Sofia on Sundays. Topics: garden,
grandchildren, telenovelas. Preferences: doesn't commit to plans early, gentle
with Mateo. Phrases: "I love you", "can I have some water". Seed co_occurs:
cold↔window, Mateo↔play, Mateo↔story (plus connectors so the dinner/Sunday and
play demos retrieve well).

----------------------------------------------------------------------------
SECONDARY PERSONA — Ben (lighter, ALS)
----------------------------------------------------------------------------
Ben, ALS — a second persona to exercise voice-banking and multi-condition
support. ALS is motor- (not language-) affecting, so this persona stresses the
voice-clone path and confirms more than one condition profile is supported.
"""

from __future__ import annotations

import os
import shutil
from typing import Any

# Node tuples: (local_id, kind, label, descriptor)
# Edge tuples: (type, src_local, dst_local, weight, count, term)

ELENA_NODES: list[tuple[str, str, str, str]] = [
    ("elena", "user", "Elena", "Elena, 67, retired Spanish teacher; expressive aphasia after a stroke; bilingual English and Spanish"),
    ("marco", "contact", "Marco", "Marco, Elena's husband"),
    ("sofia", "contact", "Sofia", "Sofia, Elena's adult daughter"),
    ("mateo", "contact", "Mateo", "Mateo, Elena's grandson, four years old"),
    ("garden", "topic", "garden", "the garden, gardening, the plants and flowers Elena tends"),
    ("grandchildren", "topic", "grandchildren", "Elena's grandchildren"),
    ("telenovelas", "topic", "telenovelas", "telenovelas, the Spanish-language television dramas Elena enjoys"),
    ("routine_garden_am", "routine", "gardens in the morning", "Elena works in her garden every morning"),
    ("routine_nap", "routine", "naps after lunch", "Elena takes a nap after lunch each afternoon"),
    ("routine_dinner", "routine", "dinner around six", "Elena has dinner around six in the evening"),
    ("routine_call_sofia", "routine", "calls Sofia on Sundays", "Elena phones her daughter Sofia every Sunday"),
    ("pref_no_early_plans", "preference", "doesn't commit to plans early", "Elena prefers not to commit to plans in advance; she likes to decide closer to the time"),
    ("pref_gentle_mateo", "preference", "gentle with Mateo", "Elena is gentle and uses simple, playful language with her grandson Mateo"),
    ("phrase_love", "phrase", "I love you", "a phrase Elena often says: I love you"),
    ("phrase_water", "phrase", "can I have some water", "a phrase Elena often says: can I have some water"),
    ("cold", "need", "feeling cold", "Elena feels cold and would like to be warmer"),
    ("window", "need", "the window", "the window in the room; opening or closing it changes how warm it is"),
    ("play", "topic", "play", "playing and games, especially with the grandchildren"),
    ("story", "topic", "story", "telling a story, storytime with Mateo"),
    ("home", "place", "home", "Elena's home, where she lives"),
]

ELENA_EDGES: list[tuple[str, str, str, float, int, str]] = [
    ("talks_to", "elena", "marco", 5, 5, ""),
    ("talks_to", "elena", "sofia", 8, 8, ""),
    ("talks_to", "elena", "mateo", 6, 6, ""),
    ("addresses_as", "elena", "marco", 5, 5, "Marco"),
    ("addresses_as", "elena", "sofia", 8, 8, "sweetie"),
    ("addresses_as", "elena", "mateo", 6, 6, "mijo"),
    # Reverse: how each contact addresses Elena — lets the engine identify the
    # partner from how they open ("Mom..." -> Sofia, "Grandma..." -> Mateo).
    ("addresses_as", "sofia", "elena", 8, 8, "Mom"),
    ("addresses_as", "mateo", "elena", 6, 6, "Grandma"),
    ("addresses_as", "marco", "elena", 5, 5, "mi amor"),
    ("related_to", "mateo", "sofia", 5, 5, ""),
    ("interested_in", "elena", "garden", 6, 6, ""),
    ("interested_in", "elena", "grandchildren", 6, 6, ""),
    ("interested_in", "elena", "telenovelas", 4, 4, ""),
    ("prefers", "elena", "pref_no_early_plans", 4, 4, ""),
    ("prefers", "elena", "pref_gentle_mateo", 4, 4, ""),
    ("uses_phrase", "elena", "phrase_love", 6, 6, ""),
    ("uses_phrase", "elena", "phrase_water", 7, 7, ""),
    ("at_place", "elena", "home", 5, 5, ""),
    # --- seed co_occurs pairings (the demo-critical ones) ---
    ("co_occurs", "cold", "window", 6, 6, ""),
    ("co_occurs", "mateo", "play", 5, 5, ""),
    ("co_occurs", "mateo", "story", 4, 4, ""),
    # --- connectors so dinner/Sunday + play demos retrieve well ---
    ("co_occurs", "grandchildren", "mateo", 5, 5, ""),
    ("co_occurs", "garden", "routine_garden_am", 5, 5, ""),
    ("co_occurs", "routine_dinner", "sofia", 4, 4, ""),
    ("co_occurs", "routine_call_sofia", "sofia", 6, 6, ""),
    ("co_occurs", "routine_dinner", "pref_no_early_plans", 3, 3, ""),
    ("co_occurs", "sofia", "pref_no_early_plans", 4, 4, ""),
    ("co_occurs", "mateo", "pref_gentle_mateo", 4, 4, ""),
    ("co_occurs", "routine_nap", "telenovelas", 3, 3, ""),
]

BEN_NODES: list[tuple[str, str, str, str]] = [
    ("ben", "user", "Ben", "Ben, living with ALS; uses voice banking; his comprehension is fully intact"),
    ("clara", "contact", "Clara", "Clara, Ben's wife and main caregiver"),
    ("need_suction", "need", "suction", "Ben needs suctioning to clear his airway"),
    ("need_reposition", "need", "reposition me", "Ben needs to be repositioned for comfort"),
    ("need_water", "need", "a sip of water", "Ben would like a sip of water"),
    ("phrase_thanks", "phrase", "thank you", "a phrase Ben often says: thank you"),
    ("topic_baseball", "topic", "baseball", "baseball, a sport Ben follows closely"),
]

BEN_EDGES: list[tuple[str, str, str, float, int, str]] = [
    ("talks_to", "ben", "clara", 6, 6, ""),
    ("addresses_as", "ben", "clara", 6, 6, "Clara"),
    ("addresses_as", "clara", "ben", 6, 6, "honey"),
    ("uses_phrase", "ben", "phrase_thanks", 5, 5, ""),
    ("interested_in", "ben", "topic_baseball", 4, 4, ""),
    ("co_occurs", "clara", "topic_baseball", 3, 3, ""),
    ("co_occurs", "need_suction", "need_reposition", 3, 3, ""),
]

PERSONAS: list[dict[str, Any]] = [
    {"person_id": "elena", "nodes": ELENA_NODES, "edges": ELENA_EDGES},
    {"person_id": "ben", "nodes": BEN_NODES, "edges": BEN_EDGES},
]


def _nid(person_id: str, local: str) -> str:
    return f"{person_id}:{local}"


def build(graph: Any = None, embedder: Any = None, reset: bool = True) -> dict[str, int]:
    """Seed the graph for all personas. Returns inserted counts.

    Args:
        graph: a connected GraphService (created + connected if None).
        embedder: an EmbeddingProvider (LocalEmbeddingProvider if None).
        reset: if True, delete any existing Kuzu DB first for a clean, count-
            deterministic seed.
    """
    from app.config import settings
    from app.services.graph import GraphService
    from app.providers.embedding import LocalEmbeddingProvider

    if reset and graph is None:
        # Fresh DB so node/edge counts are deterministic.
        db_path = settings.kuzu_db_path
        for p in (db_path, db_path + ".wal"):
            if os.path.isdir(p):
                shutil.rmtree(p, ignore_errors=True)
            elif os.path.exists(p):
                os.remove(p)

    graph = graph or GraphService()
    graph.connect()
    embedder = embedder or LocalEmbeddingProvider()

    total_nodes = 0
    total_edges = 0
    for persona in PERSONAS:
        pid = persona["person_id"]
        nodes = persona["nodes"]
        # Batch-embed "label. descriptor" for all of this persona's nodes.
        texts = [f"{label}. {desc}" for (_l, _k, label, desc) in nodes]
        vectors = embedder.embed_batch(texts)
        for (local, kind, label, _desc), vec in zip(nodes, vectors):
            graph.upsert_node(kind=kind, id=_nid(pid, local), label=label, embedding=vec)
            total_nodes += 1
        for (etype, src, dst, weight, count, term) in persona["edges"]:
            graph.upsert_edge(
                type=etype,
                src_id=_nid(pid, src),
                dst_id=_nid(pid, dst),
                weight=float(weight),
                count=int(count),
                term=term,
            )
            total_edges += 1

    # Seed each persona's learned communication-style profile (warm-start, so
    # the demo isn't cold-start). Reset to the seed on every reseed.
    from app.services.style import StyleService

    style = StyleService()
    for persona in PERSONAS:
        style.seed_persona(persona["person_id"], force=True)

    return {"nodes": total_nodes, "edges": total_edges}


def main() -> None:
    from app.services.graph import GraphService

    counts = build(reset=True)
    graph = GraphService()
    graph.connect()
    print(f"seed_graph: inserted {counts['nodes']} nodes, {counts['edges']} edges")
    print(f"seed_graph: db now has {graph.count_nodes()} nodes, {graph.count_edges()} edges")
    for persona in PERSONAS:
        pid = persona["person_id"]
        g = graph.get_graph(pid)
        print(f"  - {pid}: {len(g['nodes'])} nodes, {len(g['edges'])} edges")


if __name__ == "__main__":
    main()
