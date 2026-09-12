"""GraphService — Kuzu-backed personal knowledge graph (Phase 2).

The graph stores a person's world model: people, places, topics, routines,
preferences, needs and phrases, with weighted relationships between them.
Salience (on nodes) and weight/count (on edges) drive retrieval ranking and
decay over time.

STRUCTURAL DECISION: a single generic ``Node`` table and a single generic
``Edge`` table (rather than typed-per-entity tables). The entity kind lives in
``Node.kind`` and the relationship kind in ``Edge.type``. This keeps schema
evolution and multi-hop traversal simple.

Kuzu DDL (verified against kuzu 0.7.1)::

    CREATE NODE TABLE IF NOT EXISTS Node(
        id STRING, kind STRING, label STRING, salience DOUBLE,
        last_seen TIMESTAMP, embedding DOUBLE[384], PRIMARY KEY(id))
    CREATE REL TABLE IF NOT EXISTS Edge(
        FROM Node TO Node, type STRING, weight DOUBLE, count INT64,
        last_reinforced TIMESTAMP, term STRING)

``kind``  ∈ {user, contact, place, topic, event, routine, preference, need, phrase}
``type``  ∈ {talks_to, addresses_as, related_to, interested_in, at_place,
            mentions, prefers, uses_phrase, co_occurs}
The ``term`` edge property carries the term of address for ``addresses_as``.

Per-person scoping: node ids are namespaced ``"{person_id}:{local}"``. There are
no cross-person edges, so ``neighborhood`` traversal never leaks between people,
and :meth:`get_graph` / :meth:`person_nodes` filter by the id prefix.

``kuzu`` is LAZY-imported inside :meth:`connect` so importing this module — and
``python -m py_compile`` — works even when kuzu is not installed.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from app.config import settings

# Embedding dimensionality — must match the DOUBLE[N] column and the embedding
# model (BAAI/bge-small-en-v1.5 → 384).
EMB_DIM = 384

# Kuzu variable-length bounds (``*1..N``) must be integer literals, not query
# parameters, so the hop count is formatted into the query string. Only ever an
# ``int`` reaches the string, so this is injection-safe.
_DDL_NODE = (
    "CREATE NODE TABLE IF NOT EXISTS Node("
    "id STRING, kind STRING, label STRING, salience DOUBLE, "
    "last_seen TIMESTAMP, embedding DOUBLE[%d], PRIMARY KEY(id))" % EMB_DIM
)
_DDL_EDGE = (
    "CREATE REL TABLE IF NOT EXISTS Edge("
    "FROM Node TO Node, type STRING, weight DOUBLE, count INT64, "
    "last_reinforced TIMESTAMP, term STRING)"
)


def _now() -> datetime:
    """Naive UTC now (Kuzu TIMESTAMP comparisons use naive datetimes)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _ts_str(dt: datetime | None = None) -> str:
    """Format a datetime as an ISO string Kuzu's ``timestamp()`` accepts."""
    return (dt or _now()).strftime("%Y-%m-%dT%H:%M:%S")


def _iso(value: Any) -> str:
    """Render a value (datetime or other) as an ISO string for the API."""
    if isinstance(value, datetime):
        return value.isoformat()
    return "" if value is None else str(value)


class GraphService:
    """Wrapper around a Kuzu graph database for a person's world model."""

    def __init__(self, db_path: str | None = None) -> None:
        self.db_path = db_path or settings.kuzu_db_path
        self._db: Any | None = None
        self._conn: Any | None = None

    # --- connection / schema ------------------------------------------------

    def connect(self) -> None:
        """Open (or create) the Kuzu database, connection, and schema."""
        import kuzu  # LAZY: only needed when the graph is actually used.

        parent = os.path.dirname(os.path.abspath(self.db_path))
        os.makedirs(parent, exist_ok=True)
        self._db = kuzu.Database(self.db_path)
        self._conn = kuzu.Connection(self._db)
        self.init_schema()

    def _ensure(self) -> None:
        if self._conn is None:
            self.connect()

    def close(self) -> None:
        self._conn = None
        self._db = None

    def init_schema(self) -> None:
        """Create the generic Node and Edge tables if they do not exist."""
        self._conn.execute(_DDL_NODE)
        self._conn.execute(_DDL_EDGE)

    # --- low-level query helper --------------------------------------------

    def _q(self, query: str, params: dict | None = None) -> list[list[Any]]:
        """Execute a query and return all rows as lists."""
        self._ensure()
        res = self._conn.execute(query, parameters=params or {})
        rows: list[list[Any]] = []
        while res.has_next():
            rows.append(res.get_next())
        return rows

    @staticmethod
    def _edge_id(src_id: str, type_: str, dst_id: str) -> str:
        """Stable synthetic edge id (Edge has no PK column)."""
        return f"{src_id}|{type_}|{dst_id}"

    # --- writes -------------------------------------------------------------

    def upsert_node(
        self,
        kind: str,
        id: str,
        label: str,
        salience: float = 1.0,
        embedding: list[float] | None = None,
        last_seen: datetime | None = None,
    ) -> str:
        """Insert a node or update it if it already exists (MERGE by id)."""
        emb = embedding if embedding is not None else [0.0] * EMB_DIM
        if len(emb) != EMB_DIM:
            raise ValueError(
                f"embedding for node {id!r} has length {len(emb)}, expected {EMB_DIM}"
            )
        self._q(
            "MERGE (n:Node {id:$id}) "
            "SET n.kind=$kind, n.label=$label, n.salience=$sal, "
            "n.last_seen=timestamp($ts), n.embedding=$emb",
            {
                "id": id,
                "kind": kind,
                "label": label,
                "sal": float(salience),
                "ts": _ts_str(last_seen),
                "emb": [float(x) for x in emb],
            },
        )
        return id

    def upsert_edge(
        self,
        type: str,
        src_id: str,
        dst_id: str,
        weight: float = 1.0,
        count: int = 1,
        term: str = "",
        last_reinforced: datetime | None = None,
    ) -> str:
        """Insert a relationship or update it if it exists (MERGE by type)."""
        self._q(
            "MATCH (a:Node {id:$s}), (b:Node {id:$d}) "
            "MERGE (a)-[e:Edge {type:$t}]->(b) "
            "SET e.weight=$w, e.count=$c, e.term=$term, "
            "e.last_reinforced=timestamp($ts)",
            {
                "s": src_id,
                "d": dst_id,
                "t": type,
                "w": float(weight),
                "c": int(count),
                "term": term or "",
                "ts": _ts_str(last_reinforced),
            },
        )
        return self._edge_id(src_id, type, dst_id)

    def reinforce_edge(self, type: str, src_id: str, dst_id: str) -> str:
        """Strengthen an edge: ``weight += 1``, ``count += 1``, bump timestamp.

        Creates the edge (weight=1, count=1) if it does not yet exist.
        """
        rows = self._q(
            "MATCH (a:Node {id:$s})-[e:Edge {type:$t}]->(b:Node {id:$d}) "
            "RETURN e.weight, e.count",
            {"s": src_id, "t": type, "d": dst_id},
        )
        if rows:
            weight = (rows[0][0] or 0.0) + 1.0
            count = (rows[0][1] or 0) + 1
            self._q(
                "MATCH (a:Node {id:$s})-[e:Edge {type:$t}]->(b:Node {id:$d}) "
                "SET e.weight=$w, e.count=$c, e.last_reinforced=timestamp($ts)",
                {"s": src_id, "t": type, "d": dst_id, "w": weight, "c": count,
                 "ts": _ts_str()},
            )
            return self._edge_id(src_id, type, dst_id)
        return self.upsert_edge(type, src_id, dst_id, weight=1.0, count=1)

    def reinforce_edge_any_dir(self, type: str, a: str, b: str) -> str:
        """Reinforce an undirected-semantics edge (e.g. co_occurs) regardless of
        the stored direction. Reinforces an existing a->b or b->a edge if present,
        otherwise creates a->b. Avoids creating a duplicate reverse edge when the
        two endpoints are extracted in the opposite order from how they're stored.
        """
        fwd = self._q(
            "MATCH (:Node {id:$a})-[e:Edge {type:$t}]->(:Node {id:$b}) RETURN e.weight LIMIT 1",
            {"a": a, "t": type, "b": b},
        )
        if fwd:
            return self.reinforce_edge(type, a, b)
        rev = self._q(
            "MATCH (:Node {id:$b})-[e:Edge {type:$t}]->(:Node {id:$a}) RETURN e.weight LIMIT 1",
            {"a": a, "t": type, "b": b},
        )
        if rev:
            return self.reinforce_edge(type, b, a)
        return self.reinforce_edge(type, a, b)

    def decay(self, elapsed: float) -> None:
        """Time-based decay over the whole graph.

        ``salience`` and ``weight`` are multiplied by
        ``decay_factor ** (elapsed_seconds / 86400)`` so a day of disuse applies
        one ``decay_factor`` step.
        """
        factor = float(settings.decay_factor) ** (float(elapsed) / 86400.0)
        self._q("MATCH (n:Node) SET n.salience = n.salience * $f", {"f": factor})
        self._q("MATCH ()-[e:Edge]->() SET e.weight = e.weight * $f", {"f": factor})

    # --- reads --------------------------------------------------------------

    def _row_to_node(self, row: list[Any]) -> dict[str, Any]:
        # row = [id, kind, label, salience, last_seen, embedding]
        return {
            "id": row[0],
            "kind": row[1],
            "label": row[2],
            "salience": row[3],
            "last_seen": row[4],  # datetime (kept raw for recency math)
            "embedding": row[5],
        }

    def _fetch_nodes(self, ids: list[str]) -> list[dict[str, Any]]:
        if not ids:
            return []
        rows = self._q(
            "MATCH (n:Node) WHERE n.id IN $ids "
            "RETURN n.id, n.kind, n.label, n.salience, n.last_seen, n.embedding",
            {"ids": ids},
        )
        return [self._row_to_node(r) for r in rows]

    def _fetch_edges_among(self, ids: list[str]) -> list[dict[str, Any]]:
        """All edges whose endpoints are both within ``ids``."""
        if not ids:
            return []
        rows = self._q(
            "MATCH (a:Node)-[e:Edge]->(b:Node) "
            "WHERE a.id IN $ids AND b.id IN $ids "
            "RETURN a.id, b.id, e.type, e.weight, e.count, e.last_reinforced, e.term",
            {"ids": ids},
        )
        edges = []
        for r in rows:
            src, dst, type_ = r[0], r[1], r[2]
            edges.append(
                {
                    "id": self._edge_id(src, type_, dst),
                    "source": src,
                    "target": dst,
                    "type": type_,
                    "weight": r[3],
                    "count": r[4],
                    "last_reinforced": r[5],
                    "term": r[6],
                }
            )
        return edges

    def neighborhood(self, node_ids: list[str], hops: int = 1) -> dict[str, Any]:
        """Multi-hop neighborhood around the anchors.

        Runs a Kuzu variable-length undirected traversal ``-[*1..hops]-`` to find
        reachable nodes and their minimum hop distance from any anchor, then a
        second query to collect the edges among the resulting node set (this is
        more robust than unpacking recursive-rel structures and yields clean
        string ids).

        Returns::

            {
                "nodes": [<node dict + "hop">...],   # incl. embedding
                "edges": [<edge dict>...],
                "node_ids": [...],
                "edge_ids": [...],
                "hops": {node_id: min_hop_distance},  # anchors = 0
            }
        """
        anchors = [nid for nid in (node_ids or [])]
        if not anchors:
            return {"nodes": [], "edges": [], "node_ids": [], "edge_ids": [], "hops": {}}

        k = max(1, int(hops))
        hop_map: dict[str, int] = {}
        rows = self._q(
            f"MATCH (a:Node)-[e:Edge*1..{k}]-(b:Node) WHERE a.id IN $ids "
            "RETURN b.id AS bid, min(length(e)) AS hop",
            {"ids": anchors},
        )
        for bid, hop in rows:
            hop_map[bid] = int(hop)
        # Anchors are distance 0 (overrides any cycle-derived value).
        for aid in anchors:
            hop_map[aid] = 0

        node_ids = list(hop_map.keys())
        nodes = self._fetch_nodes(node_ids)
        for n in nodes:
            n["hop"] = hop_map.get(n["id"])
        edges = self._fetch_edges_among(node_ids)
        return {
            "nodes": nodes,
            "edges": edges,
            "node_ids": [n["id"] for n in nodes],
            "edge_ids": [e["id"] for e in edges],
            "hops": hop_map,
        }

    # --- per-person views ---------------------------------------------------

    def person_nodes(self, person_id: str) -> list[dict[str, Any]]:
        """All nodes belonging to ``person_id`` (by id prefix), with embeddings."""
        prefix = f"{person_id}:"
        rows = self._q(
            "MATCH (n:Node) "
            "RETURN n.id, n.kind, n.label, n.salience, n.last_seen, n.embedding"
        )
        return [self._row_to_node(r) for r in rows if str(r[0]).startswith(prefix)]

    def person_edges(self, person_id: str) -> list[dict[str, Any]]:
        """All edges whose endpoints both belong to ``person_id``."""
        ids = [n["id"] for n in self.person_nodes(person_id)]
        return self._fetch_edges_among(ids)

    def get_graph(self, person_id: str) -> dict[str, list[dict[str, Any]]]:
        """Person's full graph as GraphNode / GraphEdge shaped dicts."""
        nodes = self.person_nodes(person_id)
        ids = [n["id"] for n in nodes]
        edges = self._fetch_edges_among(ids)
        api_nodes = [
            {
                "id": n["id"],
                "label": n["label"],
                "type": n["kind"],
                "salience": float(n["salience"]) if n["salience"] is not None else 0.0,
                "last_seen": _iso(n["last_seen"]),
                "group": n["kind"],
            }
            for n in nodes
        ]
        api_edges = [
            {
                "id": e["id"],
                "source": e["source"],
                "target": e["target"],
                "type": e["type"],
                "weight": float(e["weight"]) if e["weight"] is not None else 0.0,
                "count": int(e["count"]) if e["count"] is not None else 0,
                "last_reinforced": _iso(e["last_reinforced"]),
            }
            for e in edges
        ]
        return {"nodes": api_nodes, "edges": api_edges}

    # --- counts (verification helpers) -------------------------------------

    def count_nodes(self) -> int:
        rows = self._q("MATCH (n:Node) RETURN count(n)")
        return int(rows[0][0]) if rows else 0

    def count_edges(self) -> int:
        rows = self._q("MATCH ()-[e:Edge]->() RETURN count(e)")
        return int(rows[0][0]) if rows else 0
