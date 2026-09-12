"""RetrievalService — hybrid GraphRAG grounding (Phase 3).

Turns sparse fragments + situational context into a grounded RETRIEVED FACTS
block plus a ``RetrievalInfo``-shaped dict, by fusing:

  1. Anchor extraction — LLM NER over fragments + context, entity-linked to graph
     nodes by exact/fuzzy label match and embedding cosine; plus direct linking
     of any partner/contact name found in the context or situation.
  2. Graph expansion — multi-hop ``graph.neighborhood`` traversal from anchors.
  3. Vector retrieval — embed the full query, cosine over all of the person's
     node embeddings, union the nearest into the subgraph.
  4. Re-rank — score = a*graph_proximity + b*edge_weight_norm + c*recency +
     d*semantic, every component normalized to [0, 1]; keep top_k.
  5. Confidence gate — confidence = 0.5*(any anchor matched) + 0.5*(max semantic
     over top_k); below ``confidence_threshold`` ⇒ abstain ("ask for one word").
  6. Assemble a human-readable RETRIEVED FACTS block (with node ids) for the
     generation prompt.

Heavy deps are reached only through the injected providers/graph service.
"""

from __future__ import annotations

import difflib
import json
import math
import re
from datetime import datetime, timezone
from typing import Any

import numpy as np

from app.config import settings

# Recency time-constant (seconds). recency = exp(-(now - last_seen) / TAU).
RECENCY_TAU_SECONDS = 7 * 24 * 3600  # ~7 days

# Anchor entity-linking thresholds.
# Exact/word/fuzzy label matching is the primary, precise path. Embedding-only
# linking is a fallback: bge-small compresses cosines into ~0.5-0.77, so an
# embedding link must clear a high absolute bar AND beat the runner-up by a
# margin — this rejects ambiguous matches (e.g. "tired"→cold, which barely
# edges out routine_nap) while exact matches (cold, window, play, dinner) are
# unaffected because they never reach this fallback.
_FUZZY_THRESHOLD = 0.86          # difflib ratio for label match
_ANCHOR_SEMANTIC_THRESHOLD = 0.62  # min cosine for an embedding-only anchor link
_ANCHOR_SEMANTIC_MARGIN = 0.03     # best must beat 2nd-best by at least this


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _strip_reasoning(raw: str) -> str:
    """Remove <think>...</think> blocks and markdown fences from model output."""
    if not raw:
        return ""
    raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL | re.IGNORECASE)
    raw = re.sub(r"```(?:json)?", "", raw)
    return raw.strip()


def _parse_str_list(raw: str) -> list[str]:
    """Best-effort parse of a JSON array (or {key: array}) of strings."""
    text = _strip_reasoning(raw)
    start, end = text.find("["), text.rfind("]")
    candidate = text[start : end + 1] if (start != -1 and end > start) else text
    try:
        data = json.loads(candidate)
    except Exception:
        # Last resort: try the whole thing as an object and grab its first list.
        try:
            data = json.loads(text)
        except Exception:
            return []
    if isinstance(data, dict):
        for v in data.values():
            if isinstance(v, list):
                data = v
                break
        else:
            return []
    if not isinstance(data, list):
        return []
    return [str(x).strip() for x in data if str(x).strip()]


def _cos(a: np.ndarray, b: np.ndarray) -> float:
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    if denom == 0.0:
        return 0.0
    return float(np.dot(a, b) / denom)


def _sim_matrix(ids: list[str], embs: dict[str, np.ndarray]) -> np.ndarray:
    """Pairwise cosine-similarity matrix over the given node ids, clipped to [0,1]."""
    M = np.stack([embs[i] for i in ids]).astype(np.float32)
    norms = np.linalg.norm(M, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    Mn = M / norms
    W = Mn @ Mn.T
    np.clip(W, 0.0, 1.0, out=W)
    return W


def greedy_submodular(
    pool_ids: list[str], r_map: dict[str, float], embs: dict[str, np.ndarray],
    lam: float, budget: int, seed_ids: list[str] | None = None,
) -> list[str]:
    """Lin-Bilmes facility-location selection by greedy maximization.

    Maximizes the monotone submodular objective
        f(S) = lam * sum_{j in S} r_j  +  sum_{i in V} max_{j in S} w(i,j)
    over a cardinality budget, where r_j is the existing per-node relevance and
    w(i,j) is node-embedding cosine. Greedy gives the (1 - 1/e) guarantee and is
    O(B*|V|^2) — sub-millisecond here. No ILP/LP solver, no external calls.

    ``seed_ids`` (the query's anchors/partner) are pre-included so the facts
    always cover the query's entry points; greedy then fills the rest of the
    budget by marginal gain.
    """
    n = len(pool_ids)
    if n == 0:
        return []
    idx = {nid: k for k, nid in enumerate(pool_ids)}
    W = _sim_matrix(pool_ids, embs)            # |V| x |V| coverage similarities
    r = np.array([float(r_map.get(i, 0.0)) for i in pool_ids], dtype=np.float32)
    cover = np.zeros(n, dtype=np.float32)       # current max_{j in S} w(i, j) per i
    sel = np.zeros(n, dtype=bool)
    chosen: list[str] = []
    budget = min(int(budget), n)

    # Mandatory seeds first (anchors/partner), de-duped and in order.
    for s in (seed_ids or []):
        if len(chosen) >= budget:
            break
        k = idx.get(s)
        if k is None or sel[k]:
            continue
        sel[k] = True
        chosen.append(s)
        cover = np.maximum(cover, W[:, k])

    while len(chosen) < budget:
        # marginal gain of adding x: lam*r_x + sum_i max(0, w(i,x) - cover_i)
        coverage_gain = np.maximum(0.0, W - cover[:, None]).sum(axis=0)
        gains = lam * r + coverage_gain
        gains[sel] = -np.inf
        x = int(np.argmax(gains))
        if not np.isfinite(gains[x]) or gains[x] <= 0.0:
            break
        sel[x] = True
        chosen.append(pool_ids[x])
        cover = np.maximum(cover, W[:, x])
    return chosen


def _intra_set_similarity(ids: list[str], embs: dict[str, np.ndarray]) -> float:
    """Mean pairwise cosine within a set (redundancy; lower = more diverse)."""
    if len(ids) < 2:
        return 0.0
    W = _sim_matrix(ids, embs)
    iu = np.triu_indices(len(ids), k=1)
    return float(round(W[iu].mean(), 4))


class RetrievalService:
    """Assembles grounded context for generation from the graph + vectors."""

    def __init__(self, graph: Any, llm: Any, embedding: Any, redis_store: Any = None) -> None:
        self.graph = graph
        self.llm = llm
        self.embedding = embedding
        # Optional Redis vector backend. When available, the nearest-node lookup
        # is served by Redis KNN; otherwise it falls back to in-process cosine.
        self.redis_store = redis_store
        self.last_vector_backend: str = "in-process"

    # --- 1) anchor extraction ----------------------------------------------

    def _llm_mentions(self, fragments: list[str], context: str) -> list[str]:
        """Ask the LLM to list entity mentions. Degrades to [] on any failure."""
        system = "You extract entities. Return ONLY a JSON array of short strings, no prose."
        user = (
            "From the FRAGMENTS and CONTEXT below, list the distinct real-world things "
            "being referred to or implied: people, places, topics, activities, feelings, "
            "objects, and times. Return ONLY a JSON array of short lowercase strings.\n\n"
            f"FRAGMENTS: {fragments}\n"
            f"CONTEXT: {context or '(none)'}"
        )
        from app.tracing import llm_span

        try:
            with llm_span("anchor_extraction", model=self._llm_model(), input_value=user) as _s:
                raw = self.llm.generate(user, system=system)
                _s.set_output(raw)
        except Exception:
            return []
        return _parse_str_list(raw)

    def _llm_model(self) -> str:
        return getattr(self.llm, "model", "") or ""

    def _match_mention(
        self,
        mention: str,
        pnodes: dict[str, dict],
        embs: dict[str, np.ndarray],
        mention_emb: np.ndarray | None,
    ) -> str | None:
        """Link one mention string to its best node id, or None."""
        m = mention.strip().lower()
        if len(m) < 2:
            return None
        best_fuzzy_id, best_fuzzy = None, 0.0
        for nid, nd in pnodes.items():
            label = str(nd["label"]).lower()
            words = re.findall(r"[a-z0-9']+", label)
            if m == label or m in words:
                return nid  # strong exact/word match
            ratio = difflib.SequenceMatcher(None, m, label).ratio()
            if ratio > best_fuzzy:
                best_fuzzy, best_fuzzy_id = ratio, nid
        if best_fuzzy >= _FUZZY_THRESHOLD:
            return best_fuzzy_id
        if mention_emb is not None:
            sims = sorted((_cos(mention_emb, embs[nid]) for nid in pnodes), reverse=True)
            best_sem = sims[0] if sims else 0.0
            second = sims[1] if len(sims) > 1 else 0.0
            if best_sem >= _ANCHOR_SEMANTIC_THRESHOLD and (best_sem - second) >= _ANCHOR_SEMANTIC_MARGIN:
                # recompute the winning id (sorted() dropped it)
                for nid in pnodes:
                    if abs(_cos(mention_emb, embs[nid]) - best_sem) < 1e-9:
                        return nid
        return None

    def extract_anchors(
        self,
        person_id: str,
        fragments: list[str],
        context: str,
        situation: Any | None,
        pnodes: dict[str, dict],
        embs: dict[str, np.ndarray],
    ) -> list[str]:
        """Map fragments + context + situation to anchor node ids."""
        # Mentions = the user's own fragments + LLM-extracted entities.
        mentions: list[str] = [f for f in fragments if f and f.strip()]
        mentions += self._llm_mentions(fragments, context)
        # De-dup preserving order.
        seen_m: set[str] = set()
        mentions = [m for m in mentions if not (m.lower() in seen_m or seen_m.add(m.lower()))]

        mention_embs: dict[str, np.ndarray] = {}
        if mentions:
            try:
                vecs = self.embedding.embed_batch(mentions)
                mention_embs = {m: np.asarray(v, dtype=np.float32) for m, v in zip(mentions, vecs)}
            except Exception:
                mention_embs = {}

        anchors: list[str] = []
        for m in mentions:
            nid = self._match_mention(m, pnodes, embs, mention_embs.get(m))
            if nid and nid not in anchors:
                anchors.append(nid)

        # Direct partner/contact linking from context text + situation.
        haystack = (context or "").lower()
        present = []
        if situation is not None:
            present = list(getattr(situation, "present_people", None) or [])
        present_l = " ".join(str(p).lower() for p in present)
        for nid, nd in pnodes.items():
            if nd["kind"] != "contact":
                continue
            name = str(nd["label"]).lower()
            if re.search(rf"\b{re.escape(name)}\b", haystack) or (name and name in present_l):
                if nid not in anchors:
                    anchors.append(nid)
        return anchors

    def _detect_partner(
        self,
        context: str,
        situation: Any | None,
        pnodes: dict[str, dict],
        partner_by_term: dict[str, str],
    ) -> str | None:
        """Identify the conversation partner's contact id, if discernible.

        Order: (1) by how they address the speaker ("Mom" → Sofia, "Grandma" →
        Mateo), (2) by a present_people name, (3) by a contact name in context.
        """
        hay = (context or "").lower()
        for term, cid in partner_by_term.items():
            if term and re.search(rf"\b{re.escape(term)}\b", hay):
                return cid
        present = []
        if situation is not None:
            present = [str(p).lower() for p in (getattr(situation, "present_people", None) or [])]
        for nid, nd in pnodes.items():
            if nd["kind"] == "contact" and str(nd["label"]).lower() in present:
                return nid
        for nid, nd in pnodes.items():
            if nd["kind"] == "contact":
                name = str(nd["label"]).lower()
                if name and re.search(rf"\b{re.escape(name)}\b", hay):
                    return nid
        return None

    # --- 3) vector retrieval -----------------------------------------------

    def vector_retrieve(
        self, query_emb: np.ndarray, embs: dict[str, np.ndarray], top_n: int
    ) -> list[tuple[str, float]]:
        """Top-N (node_id, semantic) by cosine over all node embeddings (in-process)."""
        scored = [(nid, max(0.0, _cos(query_emb, v))) for nid, v in embs.items()]
        scored.sort(key=lambda t: t[1], reverse=True)
        return scored[:top_n]

    def vector_retrieve_backed(
        self,
        person_id: str,
        query_emb: np.ndarray,
        embs: dict[str, np.ndarray],
        top_n: int,
        pnode_list: list[dict] | None = None,
    ) -> list[tuple[str, float]]:
        """Top-N nearest nodes, served by Redis KNN when available.

        Redis uses a FLAT/COSINE index, so the returned nearest-node set is
        identical to the in-process cosine ranking. Falls back to in-process on
        any unavailability/error. Records which backend served the request in
        ``self.last_vector_backend`` for the trace.
        """
        rs = self.redis_store
        if rs is not None and getattr(rs, "available", False) and getattr(rs, "has_search", False):
            nodes = pnode_list or [{"id": nid, "embedding": v} for nid, v in embs.items()]
            if rs.sync_person(person_id, nodes):
                hits = rs.knn(person_id, query_emb, top_n)
                if hits is not None:
                    self.last_vector_backend = "redis-knn"
                    # Keep only ids we actually hold embeddings for (defensive).
                    return [(nid, sim) for nid, sim in hits if nid in embs]
        self.last_vector_backend = "in-process"
        return self.vector_retrieve(query_emb, embs, top_n)

    # --- 6) facts assembly --------------------------------------------------

    def _assemble_facts(
        self,
        topk_ids: list[str],
        pnodes: dict[str, dict],
        addr_term: dict[str, str],
        partner_id: str | None = None,
    ) -> str:
        """Human-readable RETRIEVED FACTS block, each line tagged with its id."""
        order = ["contact", "preference", "routine", "phrase", "need", "topic", "place", "event", "user"]

        def line(nid: str) -> str:
            nd = pnodes[nid]
            kind, label = nd["kind"], nd["label"]
            if kind == "contact":
                # The partner (the listener) is shown separately below with their
                # term of address. Other contacts are only *mentioned*, so we do
                # NOT surface their address term — that would compete with the
                # partner's (e.g. "sweetie" leaking in when talking to Mateo).
                return f"[{nid}] {label} is someone in your life."
            if kind == "preference":
                return f"[{nid}] Preference: {label}."
            if kind == "routine":
                return f"[{nid}] Routine: {label}."
            if kind == "phrase":
                return f'[{nid}] You often say: "{label}".'
            if kind == "need":
                return f"[{nid}] Possible need: {label}."
            if kind == "topic":
                return f"[{nid}] Topic that matters to you: {label}."
            if kind == "place":
                return f"[{nid}] Place: {label}."
            if kind == "user":
                return f"[{nid}] Speaker: {label}."
            return f"[{nid}] {label}."

        lines: list[str] = []
        # Lead with the identified partner so generation addresses them right.
        shown: set[str] = set()
        if partner_id and partner_id in pnodes:
            nd = pnodes[partner_id]
            term = addr_term.get(partner_id)
            p = f"[{partner_id}] PARTNER: You are speaking with {nd['label']}"
            if term:
                p += f', whom you call "{term}" — address them this way'
            lines.append(p + ".")
            shown.add(partner_id)

        by_kind: dict[str, list[str]] = {}
        for nid in topk_ids:
            if nid in shown:
                continue
            by_kind.setdefault(pnodes[nid]["kind"], []).append(nid)
        for kind in order:
            for nid in by_kind.get(kind, []):
                lines.append(line(nid))
        return "\n".join(lines) if lines else "(no specific facts retrieved)"

    # --- orchestration ------------------------------------------------------

    def retrieve(
        self,
        person_id: str,
        fragments: list[str],
        context: str = "",
        situation: Any | None = None,
    ) -> dict[str, Any]:
        """Run the full hybrid pipeline; return facts + RetrievalInfo + flags."""
        empty = {
            "context_block": "",
            "retrieval": {"anchor_ids": [], "subgraph_node_ids": [],
                          "subgraph_edge_ids": [], "confidence": 0.0},
            "confidence": 0.0,
            "abstain": True,
            "abstain_reason": "I don't have enough to go on yet — add one more word.",
            "grounded_ids": [],
            "topk": [],
        }
        if self.graph is None:
            return empty

        pnode_list = self.graph.person_nodes(person_id)
        if not pnode_list:
            return empty
        pnodes: dict[str, dict] = {n["id"]: n for n in pnode_list}
        embs: dict[str, np.ndarray] = {
            n["id"]: np.asarray(n["embedding"], dtype=np.float32) for n in pnode_list
        }
        pedges = self.graph.person_edges(person_id)
        # How the speaker addresses each contact (forward: user -> contact).
        addr_term = {
            e["target"]: e["term"]
            for e in pedges
            if e["type"] == "addresses_as" and e.get("term")
            and pnodes.get(e["target"], {}).get("kind") == "contact"
        }
        # How each contact addresses the speaker (reverse: contact -> user) —
        # used to identify the partner from how they open ("Mom..." -> Sofia).
        partner_by_term = {
            str(e["term"]).lower(): e["source"]
            for e in pedges
            if e["type"] == "addresses_as" and e.get("term")
            and pnodes.get(e["target"], {}).get("kind") == "user"
        }

        # query embedding (fragments + context)
        query_text = " ".join([*(fragments or []), context or ""]).strip()
        try:
            query_emb = np.asarray(self.embedding.embed(query_text), dtype=np.float32)
        except Exception:
            query_emb = np.zeros(next(iter(embs.values())).shape, dtype=np.float32)
        semantic = {nid: max(0.0, _cos(query_emb, v)) for nid, v in embs.items()}

        # 1) anchors (+ identify the conversation partner, who leads ranking)
        partner_id = self._detect_partner(context, situation, pnodes, partner_by_term)
        anchors = self.extract_anchors(person_id, fragments, context, situation, pnodes, embs)
        if partner_id:
            anchors = [partner_id] + [a for a in anchors if a != partner_id]

        # 2) graph expansion
        nb = self.graph.neighborhood(anchors, settings.retrieval_hops) if anchors else \
            {"node_ids": [], "edge_ids": [], "hops": {}}
        hops_map: dict[str, int] = dict(nb.get("hops", {}))

        # 3) vector retrieval (union into the subgraph) — Redis KNN when enabled,
        #    else in-process cosine. FLAT/COSINE makes the two identical.
        top_n = int(settings.retrieval_top_k)
        vec_top = self.vector_retrieve_backed(
            person_id, query_emb, embs, top_n, pnode_list=pnode_list
        )
        vec_ids = [nid for nid, _ in vec_top]

        candidate_ids = list(dict.fromkeys([*anchors, *nb.get("node_ids", []), *vec_ids]))

        # edge weight normalization (best incident weight / global max)
        best_incident: dict[str, float] = {}
        global_max_w = 1.0
        for e in pedges:
            w = float(e["weight"] or 0.0)
            global_max_w = max(global_max_w, w)
            for nid in (e["source"], e["target"]):
                best_incident[nid] = max(best_incident.get(nid, 0.0), w)

        # 4) re-rank
        a, b, c, d = (settings.rank_alpha, settings.rank_beta,
                      settings.rank_gamma, settings.rank_delta)
        now = _now()
        decay = float(settings.decay_factor)
        ranked: list[dict[str, Any]] = []
        for nid in candidate_ids:
            nd = pnodes.get(nid)
            if nd is None:
                continue
            hop = 0 if nid in anchors else hops_map.get(nid)
            graph_prox = (decay ** hop) if hop is not None else 0.0
            ew = best_incident.get(nid, 0.0) / global_max_w
            last_seen = nd["last_seen"]
            if isinstance(last_seen, datetime):
                dt = max(0.0, (now - last_seen).total_seconds())
                recency = math.exp(-dt / RECENCY_TAU_SECONDS)
            else:
                recency = 0.0
            sem = semantic.get(nid, 0.0)
            score = a * graph_prox + b * ew + c * recency + d * sem
            ranked.append({
                "id": nid, "label": nd["label"], "kind": nd["kind"],
                "score": round(score, 4), "graph_proximity": round(graph_prox, 4),
                "edge_weight_norm": round(ew, 4), "recency": round(recency, 4),
                "semantic": round(sem, 4), "hop": hop,
            })
        ranked.sort(key=lambda r: r["score"], reverse=True)

        # --- 5) context selection under a fact budget ---
        # Candidate pool V = the retrieved subgraph nodes that have scores.
        # Replace plain top-k with greedy submodular (facility-location) maximization
        # so the selected facts are relevant AND low-redundancy. Both selections are
        # computed for the trace's side-by-side A/B; selection_mode picks which is used.
        import time as _t
        budget = int(getattr(settings, "context_budget", 8))
        lam = float(getattr(settings, "context_lambda", 2.0))
        mode = getattr(settings, "selection_mode", "submodular")

        pool_ids = [r["id"] for r in ranked]               # V
        r_map = {r["id"]: r["score"] for r in ranked}

        topk_ids = [r["id"] for r in ranked[:budget]]      # baseline top-k by score
        # The query's entry points (anchors + partner) are mandatory in S so the
        # facts always ground the query; submodular fills the remaining budget.
        seed_ids = [a for a in anchors if a in r_map]
        if partner_id and partner_id in r_map and partner_id not in seed_ids:
            seed_ids.append(partner_id)
        _t0 = _t.time()
        submod_ids = greedy_submodular(pool_ids, r_map, embs, lam, budget, seed_ids=seed_ids)
        select_ms = round((_t.time() - _t0) * 1000, 3)

        selected_ids = submod_ids if mode == "submodular" else topk_ids

        def _kinds(ids: list[str]) -> list[str]:
            return sorted({pnodes[i]["kind"] for i in ids if i in pnodes})

        selection_debug = {
            "mode": mode, "budget": budget, "lambda": lam,
            "pool_size": len(pool_ids), "select_ms": select_ms, "solver": "greedy-submodular",
            "submodular": {
                "ids": submod_ids, "kinds": _kinds(submod_ids),
                "intra_sim": _intra_set_similarity(submod_ids, embs),
                "relevance_sum": round(sum(r_map[i] for i in submod_ids), 4),
            },
            "topk": {
                "ids": topk_ids, "kinds": _kinds(topk_ids),
                "intra_sim": _intra_set_similarity(topk_ids, embs),
                "relevance_sum": round(sum(r_map[i] for i in topk_ids), 4),
            },
        }

        # The selected set S IS the subgraph the GraphView highlights.
        subgraph_node_ids = selected_ids
        subgraph_edges = self.graph._fetch_edges_among(subgraph_node_ids)
        subgraph_edge_ids = [e["id"] for e in subgraph_edges]

        # 6) confidence gate (over the selected set)
        sel_set = set(selected_ids)
        any_anchor = 1.0 if anchors else 0.0
        max_sem_sel = max((r["semantic"] for r in ranked if r["id"] in sel_set), default=0.0)
        confidence = round(0.5 * any_anchor + 0.5 * max_sem_sel, 4)
        abstain = confidence < float(settings.confidence_threshold)

        # 7) facts block (partner leads); partner is always a valid grounding id
        context_block = self._assemble_facts(selected_ids, pnodes, addr_term, partner_id)
        grounded_ids = selected_ids + (
            [partner_id] if partner_id and partner_id not in selected_ids else []
        )

        return {
            "context_block": context_block,
            "retrieval": {
                "anchor_ids": anchors,
                "subgraph_node_ids": subgraph_node_ids,
                "subgraph_edge_ids": subgraph_edge_ids,
                "confidence": confidence,
            },
            "confidence": confidence,
            "abstain": abstain,
            "abstain_reason": (
                "I don't have enough to go on yet — add one more word." if abstain else None
            ),
            "grounded_ids": grounded_ids,
            "selection": selection_debug,
            "candidate_pool_ids": pool_ids,
            "topk": ranked[:budget],
            "vector_backend": self.last_vector_backend,
        }
