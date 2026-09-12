"""LearningService — online learning + memory consolidation (Phase 6).

Closes the loop:
  * on_confirm — when the user confirms an utterance, extract its entities,
    bump their salience, reinforce co_occurs edges among co-mentioned entities
    and between the partner and the chosen phrasing, mine the phrasing into a
    Phrase node, and record an Event node for the utterance.
  * consolidate — a scheduled/offline pass that reads recent Events and uses an
    LLM (Claude when ANTHROPIC_API_KEY is set, else the local LLM) to infer
    higher-order Preferences, writing Preference nodes + prefers edges.
  * run_decay — delegates to GraphService.decay so stale weights fade.

Entity extraction reuses RetrievalService's LLM NER + entity-linking. Heavy
deps are reached only through the injected providers/graph service.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
from datetime import datetime, timezone
from typing import Any

import numpy as np

from app.config import settings

SALIENCE_BUMP = 0.5
RECENT_EVENTS = 12  # how many recent events consolidate reads

# System role for the Build-Your-Brain interviewer (assistant_turn).
_ASSISTANT_SYSTEM = (
    "You are a warm, patient assistant getting to know a person so you can later "
    "help them communicate in their own voice. You are gently interviewing them "
    "about their life. Ask ONE short, friendly question at a time, building "
    "naturally on what they have already told you. Focus on things worth "
    "remembering: the important people in their life and what they call them, "
    "their daily routines, the places they go, and the things they like and care "
    "about. Prefer the topics the notes say are missing. Never ask more than one "
    "question at once, keep it warm and short (one or two sentences), and reply in "
    "exactly the response format the user asks for."
)

# Mentions only link to these "real" entity kinds (not events/phrases).
ENTITY_KINDS = {"user", "contact", "place", "topic", "routine", "preference", "need"}

# Words too generic to be entities (used when matching raw tokens to nodes).
_STOPWORDS = {
    "the", "and", "you", "your", "for", "can", "could", "please", "with", "have",
    "some", "i'm", "im", "are", "its", "it", "to", "do", "want", "will", "would",
    "me", "my", "of", "is", "so", "but", "not", "that", "this", "a", "an", "we",
    "she", "he", "they", "them", "his", "her", "our", "us", "be", "am", "was",
    "were", "in", "on", "at", "as", "if", "or", "let", "get", "got", "come",
}

# Lightweight, offline kind classification for entities CREATED during a
# confirmation, so Build-Your-Brain answers populate the RIGHT node kinds
# (people as contacts, days/times as routines, places as places) instead of
# everything defaulting to "topic". Keeps the interviewer's gap analysis honest.
_DAY_TIME_WORDS = {
    "monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday",
    "weekday", "weekdays", "weekend", "weekends", "daily", "weekly", "morning",
    "mornings", "afternoon", "afternoons", "evening", "evenings", "night",
    "nights", "noon", "midday", "breakfast", "lunch", "dinner", "bedtime",
}
_PLACE_WORDS = {
    "park", "church", "temple", "mosque", "garden", "store", "shop", "market",
    "mall", "hospital", "clinic", "kitchen", "beach", "school", "library", "cafe",
    "restaurant", "home", "house", "office", "gym", "studio", "farm", "porch",
}
_REL_WORDS = {
    "mom", "mum", "mommy", "dad", "daddy", "mother", "father", "sister", "brother",
    "daughter", "son", "wife", "husband", "friend", "aunt", "uncle", "grandson",
    "granddaughter", "grandmother", "grandfather", "grandma", "grandpa", "cousin",
    "neighbor", "neighbour", "nurse", "doctor", "partner", "caregiver",
}


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _slug(s: str, n: int = 48) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")
    return s[:n] or "x"


def _short_hash(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()[:10]


class LearningService:
    """Reinforces, mines, consolidates and decays the person's world model."""

    def __init__(self, graph: Any, llm: Any, embedding: Any) -> None:
        self.graph = graph
        self.llm = llm
        self.embedding = embedding
        self._retr = None

    # --- helpers ------------------------------------------------------------

    def _retrieval(self):
        """Reuse RetrievalService's entity extraction + linking."""
        if self._retr is None:
            from app.services.retrieval import RetrievalService

            self._retr = RetrievalService(self.graph, self.llm, self.embedding)
        return self._retr

    def _person_state(self, person_id: str):
        pnode_list = self.graph.person_nodes(person_id)
        pnodes = {n["id"]: n for n in pnode_list}
        embs = {nid: np.asarray(n["embedding"], dtype=np.float32) for nid, n in pnodes.items()}
        user_id = next(
            (nid for nid, n in pnodes.items() if n["kind"] == "user"),
            f"{person_id}:{person_id}",
        )
        pedges = self.graph.person_edges(person_id)
        return pnodes, embs, user_id, pedges

    def _embed(self, text: str) -> list[float]:
        try:
            return self.embedding.embed(text)
        except Exception:
            return [0.0] * 384

    def _salient_phrase(self, text: str) -> str:
        """The phrasing to remember — the trimmed, whitespace-collapsed sentence."""
        return re.sub(r"\s+", " ", (text or "").strip())

    @staticmethod
    def _named_people(text: str) -> set[str]:
        """Proper names that follow a relationship word, e.g. 'sister Maria' -> {maria}."""
        rels = "|".join(sorted(_REL_WORDS, key=len, reverse=True))
        out: set[str] = set()
        for mobj in re.finditer(rf"\b(?:{rels})\s+([A-Z][a-zA-Z]+)", text or ""):
            out.add(mobj.group(1).lower())
        return out

    @staticmethod
    def _classify_kind(mention: str, named_people: set[str]) -> str:
        """Best-effort node kind for a newly-created entity (default: topic)."""
        m = mention.strip().lower()
        if m in _DAY_TIME_WORDS:
            return "routine"
        if m in _PLACE_WORDS:
            return "place"
        if m in _REL_WORDS or m in named_people:
            return "contact"
        return "topic"

    # --- /confirm -----------------------------------------------------------

    def on_confirm(
        self,
        person_id: str,
        text: str,
        context: str = "",
        partner: str | None = None,
        situation: Any | None = None,
    ) -> dict[str, list[str]]:
        retr = self._retrieval()
        pnodes, embs, user_id, pedges = self._person_state(person_id)
        # Snapshot BEFORE any mutation so we can split created vs reinforced below.
        before_node_ids = set(pnodes.keys())
        before_edge_ids = {e["id"] for e in pedges}
        # Candidate set for entity-linking excludes events/phrases.
        link_nodes = {nid: nd for nid, nd in pnodes.items() if nd["kind"] in ENTITY_KINDS}
        link_embs = {nid: embs[nid] for nid in link_nodes}

        now = _now()
        changed_nodes: set[str] = set()
        changed_edges: set[str] = set()

        # --- 1) entity extraction (LLM NER, can create new nodes) ---
        # The partner is handled separately (linked to its contact node, never
        # created as a topic). Drop too-short / stopword mentions so we don't mint
        # junk nodes like "i"/"you".
        def _ok_mention(m: str) -> bool:
            s = m.strip().lower()
            return len(s) >= 3 and s not in _STOPWORDS

        llm_mentions = [m for m in retr._llm_mentions([text], context or "") if m and _ok_mention(m)]
        llm_mentions = list(dict.fromkeys(llm_mentions))

        mention_embs: dict[str, np.ndarray] = {}
        if llm_mentions:
            try:
                vecs = self.embedding.embed_batch(llm_mentions)
                mention_embs = {m: np.asarray(v, dtype=np.float32) for m, v in zip(llm_mentions, vecs)}
            except Exception:
                mention_embs = {}

        entity_ids: list[str] = []
        # Proper names that follow a relationship word (e.g. "sister Maria") so a
        # freshly-mentioned person is created as a contact, not a topic.
        named_people = self._named_people(text)

        def add_entity(nid: str) -> None:
            if nid not in entity_ids:
                entity_ids.append(nid)
            changed_nodes.add(nid)

        for m in llm_mentions:
            m_emb = mention_embs.get(m)
            nid = retr._match_mention(m, link_nodes, link_embs, m_emb)
            if nid is None:
                # Create a new entity node, classifying its kind from the mention.
                kind = self._classify_kind(m, named_people)
                nid = f"{person_id}:c_{_slug(m)}"
                emb_list = m_emb.tolist() if m_emb is not None else self._embed(m)
                self.graph.upsert_node(kind=kind, id=nid, label=m, salience=1.0,
                                       embedding=emb_list, last_seen=now)
                nd = {"id": nid, "kind": kind, "label": m, "salience": 1.0,
                      "last_seen": now, "embedding": emb_list}
                pnodes[nid] = nd
                link_nodes[nid] = nd
                link_embs[nid] = np.asarray(emb_list, dtype=np.float32)
            else:
                nd = pnodes[nid]
                self.graph.upsert_node(kind=nd["kind"], id=nid, label=nd["label"],
                                       salience=float(nd.get("salience") or 1.0) + SALIENCE_BUMP,
                                       embedding=nd["embedding"], last_seen=now)
            add_entity(nid)

        # --- also link bare content words to EXISTING entities (no creation) ---
        # Robustness: ensures e.g. "cold"/"window" link even if the LLM misses them.
        for w in re.findall(r"[a-zA-Z']+", (text or "").lower()):
            if len(w) < 3 or w in _STOPWORDS:
                continue
            nid = retr._match_mention(w, link_nodes, link_embs, None)  # no embedding fallback
            if nid is not None:
                add_entity(nid)

        # --- resolve the partner to a contact node (for partner<->phrase edge) ---
        partner_id = None
        if partner:
            pl = partner.strip().lower()
            for nid, nd in pnodes.items():
                if nd["kind"] == "contact" and str(nd["label"]).lower() == pl:
                    partner_id = nid
                    break
            if partner_id is None:
                # e.g. partner given as how they address the user ("Mom" -> Sofia)
                partner_by_term = {
                    str(e["term"]).lower(): e["source"]
                    for e in pedges
                    if e["type"] == "addresses_as" and e.get("term")
                    and pnodes.get(e["target"], {}).get("kind") == "user"
                }
                partner_id = partner_by_term.get(pl)
        if partner_id:
            nd = pnodes[partner_id]
            self.graph.upsert_node(kind=nd["kind"], id=partner_id, label=nd["label"],
                                   salience=float(nd.get("salience") or 1.0) + SALIENCE_BUMP,
                                   embedding=nd["embedding"], last_seen=now)
            add_entity(partner_id)

        # --- 2) reinforce co_occurs among co-mentioned entities (pairwise) ---
        for i in range(len(entity_ids)):
            for j in range(i + 1, len(entity_ids)):
                eid = self.graph.reinforce_edge_any_dir("co_occurs", entity_ids[i], entity_ids[j])
                changed_edges.add(eid)

        # --- 3) phrase mining: Phrase node + uses_phrase from the user ---
        phrase_text = self._salient_phrase(text)
        phrase_id = None
        if phrase_text:
            phrase_id = f"{person_id}:phrase_{_short_hash(phrase_text)}"
            self.graph.upsert_node(kind="phrase", id=phrase_id, label=phrase_text,
                                   salience=1.0, embedding=self._embed(phrase_text), last_seen=now)
            changed_nodes.add(phrase_id)
            changed_nodes.add(user_id)
            changed_edges.add(self.graph.reinforce_edge("uses_phrase", user_id, phrase_id))
            # between the partner/situation and the chosen phrasing
            if partner_id:
                changed_edges.add(
                    self.graph.reinforce_edge_any_dir("co_occurs", partner_id, phrase_id)
                )

        # --- 4) record an Event node (consolidate reads these) ---
        event_id = f"{person_id}:event_{int(time.time() * 1000)}"
        self.graph.upsert_node(kind="event", id=event_id, label=phrase_text[:160] or text[:160],
                               salience=1.0, embedding=self._embed(text), last_seen=now)
        changed_nodes.add(event_id)
        for ent in entity_ids:
            changed_edges.add(self.graph.reinforce_edge("mentions", event_id, ent))
        if phrase_id:
            changed_edges.add(self.graph.reinforce_edge("mentions", event_id, phrase_id))

        # --- 5) split created vs reinforced by diffing against the snapshot ---
        # Re-read the person's graph and report nodes/edges whose ids are new this
        # turn (with full metadata for the frontend to insert + bloom), leaving
        # changed_* to mean "pre-existing element that was reinforced" (pulse).
        after_nodes = self.graph.person_nodes(person_id)
        after_edges = self.graph.person_edges(person_id)
        new_nodes = [
            {
                "id": n["id"],
                "kind": n["kind"],
                "label": n["label"],
                "salience": float(n["salience"]) if n.get("salience") is not None else 1.0,
            }
            for n in after_nodes
            if n["id"] not in before_node_ids
        ]
        new_edges = [
            {
                "source": e["source"],
                "target": e["target"],
                "type": e["type"],
                "weight": float(e["weight"]) if e.get("weight") is not None else 1.0,
            }
            for e in after_edges
            if e["id"] not in before_edge_ids
        ]
        new_node_id_set = {n["id"] for n in new_nodes}
        new_edge_id_set = {e["id"] for e in after_edges if e["id"] not in before_edge_ids}

        return {
            "changed_node_ids": sorted(changed_nodes - new_node_id_set),
            "changed_edge_ids": sorted(changed_edges - new_edge_id_set),
            "new_nodes": new_nodes,
            "new_edges": new_edges,
        }

    # --- /assistant_turn (Build Your Brain interviewer) ---------------------

    # Kinds the interview tries to populate (excludes user/event/phrase).
    _INTERVIEW_KINDS = ("contact", "routine", "place", "topic", "preference", "need")
    _KIND_LABEL = {
        "contact": "people",
        "routine": "routines",
        "place": "places",
        "topic": "interests",
        "preference": "preferences",
        "need": "needs",
    }
    _FALLBACK_QUESTIONS = (
        "Who are the most important people in your life?",
        "What does a normal day look like for you?",
        "Where do you spend most of your time?",
        "What do you most enjoy doing?",
        "Is there anything you often need help with?",
    )

    def _graph_summary(self, person_id: str) -> str:
        """A brief plain-language summary of what the graph holds + where it's thin,
        so the interviewer asks about gaps ('it asks what it doesn't know')."""
        nodes = self.graph.person_nodes(person_id)
        edges = self.graph.person_edges(person_id)
        by_kind: dict[str, list[str]] = {}
        for n in nodes:
            by_kind.setdefault(n["kind"], []).append(str(n["label"]))
        node_by_id = {n["id"]: n for n in nodes}

        # Which contacts have a recorded term of address (addresses_as edge).
        contacts_with_term: set[str] = set()
        for e in edges:
            if e["type"] == "addresses_as" and (e.get("term") or "").strip():
                for endpoint in (e["source"], e["target"]):
                    nd = node_by_id.get(endpoint)
                    if nd and nd["kind"] == "contact":
                        contacts_with_term.add(endpoint)

        lines: list[str] = []
        for kind in self._INTERVIEW_KINDS:
            labels = by_kind.get(kind, [])
            shown = ", ".join(labels[:8]) if labels else "none yet"
            lines.append(f"- {self._KIND_LABEL[kind]} ({len(labels)}): {shown}")

        missing_term = [
            str(n["label"])
            for n in nodes
            if n["kind"] == "contact" and n["id"] not in contacts_with_term
        ]
        if missing_term:
            lines.append("- I don't know how they address: " + ", ".join(missing_term[:8]))

        gaps = [self._KIND_LABEL[k] for k in self._INTERVIEW_KINDS if not by_kind.get(k)]
        if gaps:
            lines.append("- Biggest gaps (ask about these first): " + ", ".join(gaps))
        return "\n".join(lines)

    @staticmethod
    def _clean_question(raw: str) -> str:
        """Reduce a model reply to a single clean question line."""
        if not raw:
            return ""
        text = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL | re.IGNORECASE)
        text = text.strip().strip("`").strip()
        # Drop a leading "Assistant:"/"Question:" label if present.
        text = re.sub(r"^\s*(assistant|question)\s*:\s*", "", text, flags=re.IGNORECASE)
        # First non-empty line is the question.
        for line in text.splitlines():
            line = line.strip().strip('"').strip()
            if line:
                return line
        return ""

    @staticmethod
    def _parse_interview(raw: str) -> tuple[str, list[str]]:
        """Parse the interviewer JSON {question, suggestions}. Falls back to
        treating the whole reply as the question (suggestions empty)."""
        if not raw:
            return "", []
        text = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL | re.IGNORECASE).strip()
        start, end = text.find("{"), text.rfind("}")
        if start != -1 and end != -1 and end > start:
            try:
                obj = json.loads(text[start : end + 1])
                q = str(obj.get("question") or "").strip()
                raw_sugg = obj.get("suggestions") or []
                clean: list[str] = []
                seen: set[str] = set()
                for s in raw_sugg:
                    s = str(s).strip().strip(".,!?\"'")
                    # short answer words only; drop placeholders like "[Name]"
                    if not s or len(s.split()) > 3 or "[" in s or "]" in s:
                        continue
                    k = s.lower()
                    if k in seen:
                        continue
                    seen.add(k)
                    clean.append(s)
                    if len(clean) >= 8:
                        break
                if q:
                    return q, clean
            except (json.JSONDecodeError, TypeError, ValueError):
                pass
        return LearningService._clean_question(raw), []

    def interview_question(self, person_id: str, history: list[dict[str, str]]) -> dict[str, Any]:
        """Return the next graph-aware interview question AND a few tailored answer
        words specific to it (so the UI's "Next" suggestions fit the question).

        The model sees a summary of what's known + the gaps and returns JSON
        {question, suggestions}. Degrades to a rotating fallback question (and no
        suggestions, so the UI falls back to its keyword categories) if the LLM is
        unavailable or the reply doesn't parse.
        """
        summary = self._graph_summary(person_id)
        convo_lines = [
            f"{'You' if m.get('role') == 'assistant' else 'Them'}: {m.get('text', '')}"
            for m in (history or [])[-12:]
            if m.get("text")
        ]
        convo = "\n".join(convo_lines)
        user = (
            "What I already know about this person:\n"
            f"{summary}\n\n"
            + (f"Conversation so far:\n{convo}\n\n" if convo else "This is the very first question.\n\n")
            + "Produce the single next question to learn something I don't already know "
            "(prefer the gaps above; build on what they just said), AND a few words the "
            "person could tap to answer it.\n"
            "Respond with ONLY a JSON object of exactly this shape:\n"
            '{"question": "<one warm question, 1-2 sentences>", '
            '"suggestions": ["<6-8 SHORT answer options specific to THIS question — single '
            "words or 1-2 word phrases the person might pick (names, places, terms of "
            'endearment, activities, times); concrete, not full sentences>"]}'
        )
        try:
            raw = self.llm.generate(user, system=_ASSISTANT_SYSTEM)
        except Exception:
            raw = ""
        q, suggestions = self._parse_interview(raw)
        if not q:
            q = self._FALLBACK_QUESTIONS[len(history or []) % len(self._FALLBACK_QUESTIONS)]
        return {"question": q, "suggestions": suggestions}

    # --- phrase mining (corpus helper) -------------------------------------

    def mine_phrases(self, person_id: str, confirmed_texts: list[str] | None = None) -> list[dict[str, Any]]:
        """Surface the person's existing Phrase nodes with their usage counts."""
        edges = self.graph.person_edges(person_id)
        counts = {e["target"]: e.get("count", 0) for e in edges if e["type"] == "uses_phrase"}
        phrases = [
            {"id": n["id"], "text": n["label"], "count": counts.get(n["id"], 0)}
            for n in self.graph.person_nodes(person_id)
            if n["kind"] == "phrase"
        ]
        phrases.sort(key=lambda p: p["count"], reverse=True)
        return phrases

    # --- /consolidate -------------------------------------------------------

    def _consolidation_llm(self):
        """Claude when a key is set, otherwise the injected local LLM."""
        if settings.anthropic_api_key:
            try:
                from app.providers.llm import ClaudeProvider

                return ClaudeProvider()
            except Exception:
                pass
        return self.llm

    def _infer_preferences(self, llm, person_id: str, utterances: list[str]) -> list[str]:
        from app.services.retrieval import _parse_str_list

        system = (
            "You infer a person's stable, higher-order preferences from things they "
            "recently chose to say. Return ONLY a JSON array of short preference "
            'statements (e.g. ["likes to keep replies short and warm with family"]). '
            "Only include patterns with clear support. Return 1-3 items."
        )
        bullets = "\n".join(f"- {u}" for u in utterances)
        user = f"Recent utterances:\n{bullets}\n\nReturn a JSON array of up to 3 inferred preferences."
        try:
            raw = llm.generate(user, system=system)
        except Exception:
            return []
        return _parse_str_list(raw)[:3]

    def consolidate(self, person_id: str) -> dict[str, list[str]]:
        pnodes, embs, user_id, _pedges = self._person_state(person_id)

        events = [n for n in pnodes.values() if n["kind"] == "event"]
        events.sort(key=lambda n: n.get("last_seen") or datetime.min, reverse=True)
        recent = events[:RECENT_EVENTS]
        # Fall back to phrases if no events have been recorded yet.
        if not recent:
            recent = [n for n in pnodes.values() if n["kind"] == "phrase"][:RECENT_EVENTS]
        utterances = [str(n["label"]) for n in recent if n.get("label")]
        if not utterances:
            return {"new_node_ids": [], "new_edge_ids": []}

        llm = self._consolidation_llm()
        prefs = self._infer_preferences(llm, person_id, utterances)

        existing = {str(n["label"]).lower() for n in pnodes.values() if n["kind"] == "preference"}
        now = _now()
        new_nodes: list[str] = []
        new_edges: list[str] = []
        for p in prefs:
            p = p.strip()
            if not p or p.lower() in existing:
                continue
            pid = f"{person_id}:pref_{_slug(p)}"
            if pid in pnodes:
                continue
            self.graph.upsert_node(kind="preference", id=pid, label=p, salience=1.0,
                                   embedding=self._embed(p), last_seen=now)
            new_nodes.append(pid)
            new_edges.append(self.graph.reinforce_edge("prefers", user_id, pid))
            existing.add(p.lower())
        return {"new_node_ids": new_nodes, "new_edge_ids": new_edges}

    # --- decay --------------------------------------------------------------

    def run_decay(self, elapsed: float = 86400.0) -> None:
        """Apply time-based decay (default: one day's worth)."""
        self.graph.decay(elapsed)
