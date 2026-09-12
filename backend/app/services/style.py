"""StyleService — the Personal Communication-Style Model (per user).

A small, persistent per-person profile that captures *how* someone talks and
feeds it back into generation (prompt + style exemplars) and ranking (a
style-fit term). It learns online from /confirm as implicit feedback: the chosen
candidate's features are contrasted against the rejected alternatives and the
profile is nudged toward the choice (a small logistic-style weight update).

Learned features (continuous centers in [0,1], with categorical labels derived):
  - length      0 short ............... 1 long
  - directness  0 polite-elaborate .... 1 direct
  - endearment  0 low ................. 1 high
  - spanish     0 english-only ........ 1 spanish-with-family

Idiolect markers (the person's characteristic phrasings) and style exemplars
(their actual recent confirmed utterances) are read live from the graph's
``phrase`` / ``event`` nodes, so they stay fresh without being stored.

Persistence: a tiny JSON file per person under ``settings.styles_dir`` (runtime
data; no Kuzu schema change).
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

DIMS = ("length", "directness", "endearment", "spanish")

# Online-update rates: a confirmation moves the profile noticeably (so a handful
# of consistent choices visibly shift it) without being jumpy.
_LR = 0.34       # contrast term (chosen vs rejected alternatives)
_ANCHOR = 0.16   # pull toward the chosen absolute value (convergence)

# Style-fit dimension importance (length + directness dominate the felt style).
_FIT_W = {"length": 1.0, "directness": 1.0, "endearment": 0.6, "spanish": 0.4}

_ENDEARMENTS = {
    "sweetie", "honey", "dear", "love", "sweetheart", "darling",
    "mijo", "mija", "mi amor", "mi vida", "cariño", "carino", "corazón", "corazon",
}
_SPANISH = {
    "mijo", "mija", "mi amor", "mi vida", "cariño", "carino", "corazón", "corazon",
    "gracias", "sí", "si", "te amo", "abuela", "hola", "por favor", "agua",
}
_POLITE_MARKERS = [
    "could you", "would you", "please", "a bit", "a little", "maybe", "perhaps",
    "if you", "when you get", "sorry", "i'm feeling", "i am feeling", "do you mind",
    "would you mind", "i think", "i was wondering",
]

# Plausible seeded "learned" profiles so the demo isn't cold-start.
_SEED_PROFILES: dict[str, dict[str, Any]] = {
    # Elena: warm Spanish-speaking grandmother; medium length, somewhat polite,
    # high endearment, slips into Spanish with family. (Leaves room for the demo
    # to shift her toward short + direct.)
    "elena": {"weights": {"length": 0.55, "directness": 0.38, "endearment": 0.80,
                          "spanish": 0.60}, "updates": 3},
    # Ben (ALS): terse and direct, English-only, low endearment.
    "ben": {"weights": {"length": 0.20, "directness": 0.82, "endearment": 0.20,
                        "spanish": 0.0}, "updates": 2},
}

_DEFAULT_WEIGHTS = {"length": 0.5, "directness": 0.5, "endearment": 0.3, "spanish": 0.0}


def _clip(x: float) -> float:
    return 0.0 if x < 0 else 1.0 if x > 1 else x


def _norm_text(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]", "", (s or "").lower()).strip()


class StyleService:
    """Learns, persists, exposes and applies a per-person style profile."""

    def __init__(self, graph: Any = None) -> None:
        self.graph = graph
        from app.config import settings

        self.dir = Path(settings.styles_dir)
        self.dir.mkdir(parents=True, exist_ok=True)

    # --- persistence --------------------------------------------------------

    def _path(self, person_id: str) -> Path:
        return self.dir / f"{person_id}.json"

    def _load(self, person_id: str) -> dict[str, Any]:
        path = self._path(person_id)
        if path.exists():
            try:
                d = json.loads(path.read_text(encoding="utf-8"))
                w = {k: float(d.get("weights", {}).get(k, _DEFAULT_WEIGHTS[k])) for k in DIMS}
                return {"weights": w, "updates": int(d.get("updates", 0))}
            except Exception:
                pass
        # First access: seed known personas, else default.
        if person_id in _SEED_PROFILES:
            self.seed_persona(person_id, force=True)
            seed = _SEED_PROFILES[person_id]
            return {"weights": dict(seed["weights"]), "updates": int(seed["updates"])}
        state = {"weights": dict(_DEFAULT_WEIGHTS), "updates": 0}
        self._save(person_id, state)
        return state

    def _save(self, person_id: str, state: dict[str, Any]) -> None:
        self._path(person_id).write_text(
            json.dumps({"weights": state["weights"], "updates": state["updates"]}, indent=2),
            encoding="utf-8",
        )

    def seed_persona(self, person_id: str, force: bool = False) -> None:
        """Write the seeded learned profile for a known persona (demo warm-start)."""
        if person_id not in _SEED_PROFILES:
            return
        if force or not self._path(person_id).exists():
            seed = _SEED_PROFILES[person_id]
            self._save(person_id, {"weights": dict(seed["weights"]), "updates": int(seed["updates"])})

    # --- feature extraction -------------------------------------------------

    def candidate_features(
        self, text: str, register: str | None = None, length_label: str | None = None
    ) -> dict[str, float]:
        """Map a candidate to style-feature values in [0,1]. Uses the model's
        self-labels (register/length_label) when present, else text heuristics."""
        t = (text or "").lower()
        words = re.findall(r"[a-z']+", t)
        n = len(words)

        if length_label in ("short", "medium", "full"):
            length = {"short": 0.15, "medium": 0.5, "full": 0.9}[length_label]
        else:
            length = _clip((n - 2) / 12.0)

        if register in ("direct", "neutral", "warm"):
            directness = {"direct": 0.9, "neutral": 0.5, "warm": 0.2}[register]
        else:
            polite = sum(1 for m in _POLITE_MARKERS if m in t)
            directness = _clip(1.0 - 0.28 * polite - (0.2 if n > 8 else 0.0))

        endearment = 1.0 if any(e in t for e in _ENDEARMENTS) else 0.0
        spanish = 1.0 if any(s in re.findall(r"[a-zñáéíóú']+", t) or s in t for s in _SPANISH) else 0.0
        return {"length": length, "directness": directness, "endearment": endearment, "spanish": spanish}

    def style_fit(self, features: dict[str, float], weights: dict[str, float]) -> float:
        """How well a candidate's features match the learned profile, in [0,1]."""
        num = sum(_FIT_W[d] * abs(features[d] - weights[d]) for d in DIMS)
        den = sum(_FIT_W.values())
        return round(1.0 - num / den, 4)

    # --- online learning (implicit feedback from /confirm) ------------------

    def observe_confirm(
        self, person_id: str, chosen_text: str, candidates: list[dict] | None, partner: str | None = None
    ) -> dict[str, Any]:
        """Nudge the profile toward the chosen candidate vs the rejected ones."""
        state = self._load(person_id)
        weights = state["weights"]
        candidates = candidates or []

        chosen_feat: dict[str, float] | None = None
        rejected: list[dict[str, float]] = []
        target = _norm_text(chosen_text)
        for c in candidates:
            cf = self.candidate_features(c.get("text", ""), c.get("register"), c.get("length_label"))
            if chosen_feat is None and _norm_text(c.get("text", "")) == target:
                chosen_feat = cf
            else:
                rejected.append(cf)
        if chosen_feat is None:
            # User text didn't match a generated candidate (e.g. edited): learn
            # from the text alone, with no rejected contrast.
            chosen_feat = self.candidate_features(chosen_text)
            rejected = []

        for d in DIMS:
            if rejected:
                rmean = sum(r[d] for r in rejected) / len(rejected)
                weights[d] = _clip(
                    weights[d] + _LR * (chosen_feat[d] - rmean) + _ANCHOR * (chosen_feat[d] - weights[d])
                )
            else:
                weights[d] = _clip(weights[d] + (_LR + _ANCHOR) * (chosen_feat[d] - weights[d]))

        state["updates"] += 1
        self._save(person_id, state)
        return self.get_profile(person_id)

    # --- derived profile / exposure ----------------------------------------

    def _derive(self, w: dict[str, float]) -> dict[str, str]:
        length_pref = "short" if w["length"] < 0.40 else "long" if w["length"] > 0.70 else "medium"
        directness_pref = "direct" if w["directness"] >= 0.5 else "polite-elaborate"
        endearment_use = "high" if w["endearment"] >= 0.5 else "low"
        language_mix = "spanish-with-family" if w["spanish"] >= 0.40 else "english-only"
        return {
            "length_pref": length_pref,
            "directness_pref": directness_pref,
            "endearment_use": endearment_use,
            "language_mix": language_mix,
        }

    def _idiolect(self, person_id: str, k: int = 6) -> list[str]:
        """Characteristic phrasings: phrase-node labels + frequent n-grams."""
        markers: list[str] = []
        if self.graph is None:
            return markers
        try:
            nodes = self.graph.person_nodes(person_id)
        except Exception:
            return markers
        phrases = [n["label"] for n in nodes if n["kind"] == "phrase"]
        markers.extend(phrases)
        # Frequent 2/3-grams across the person's utterances (phrase + event).
        corpus = [n["label"] for n in nodes if n["kind"] in ("phrase", "event")]
        grams: Counter[str] = Counter()
        for utt in corpus:
            toks = re.findall(r"[a-z']+", utt.lower())
            for size in (3, 2):
                for i in range(len(toks) - size + 1):
                    grams[" ".join(toks[i:i + size])] += 1
        for gram, cnt in grams.most_common():
            if cnt >= 2 and gram not in (m.lower() for m in markers):
                markers.append(gram)
            if len(markers) >= k:
                break
        return markers[:k]

    def _exemplars(self, person_id: str, k: int = 3) -> list[str]:
        """The person's actual recent confirmed utterances (else known phrases)."""
        if self.graph is None:
            return []
        try:
            nodes = self.graph.person_nodes(person_id)
        except Exception:
            return []
        events = [n for n in nodes if n["kind"] == "event"]
        events.sort(key=lambda n: str(n.get("last_seen") or ""), reverse=True)
        out = [n["label"] for n in events[:k]]
        if len(out) < k:
            out += [n["label"] for n in nodes if n["kind"] == "phrase"][: k - len(out)]
        # de-dup, preserve order
        seen: set[str] = set()
        return [x for x in out if not (x in seen or seen.add(x))][:k]

    def get_profile(self, person_id: str) -> dict[str, Any]:
        """Full StyleProfile-shaped dict (for GET /style and /confirm)."""
        state = self._load(person_id)
        w = {k: round(state["weights"][k], 4) for k in DIMS}
        cat = self._derive(state["weights"])
        return {
            "person_id": person_id,
            **cat,
            "weights": w,
            "idiolect_markers": self._idiolect(person_id),
            "exemplars": self._exemplars(person_id),
            "updates": state["updates"],
        }

    # --- application to generation + ranking --------------------------------

    def style_prompt(self, person_id: str) -> str:
        """A prompt block instructing the model to match this person's voice."""
        p = self.get_profile(person_id)
        lines = [
            "SPEAKER STYLE — write in this person's learned voice:",
            f"- Length: prefers {p['length_pref']} utterances.",
            f"- Directness: {p['directness_pref']}.",
            f"- Endearment: {p['endearment_use']} use of terms of endearment.",
            f"- Language: {p['language_mix']}"
            + (" (use a Spanish term of endearment with family when natural)."
               if p["language_mix"] == "spanish-with-family" else "."),
        ]
        if p["idiolect_markers"]:
            lines.append("- Characteristic phrasings: " + ", ".join(f'"{m}"' for m in p["idiolect_markers"][:5]))
        if p["exemplars"]:
            lines.append("Examples of how they actually talk:")
            lines.extend(f'  - "{e}"' for e in p["exemplars"])
        lines.append("Make at least one candidate strongly match this style.")
        return "\n".join(lines)

    def rank_candidates(self, person_id: str, candidates: list[dict]) -> tuple[list[dict], list[dict]]:
        """Reorder candidates by style-fit (best first). Returns (sorted, fit_info)."""
        state = self._load(person_id)
        weights = state["weights"]
        scored = []
        for c in candidates:
            feat = self.candidate_features(c.get("text", ""), c.get("register"), c.get("length_label"))
            scored.append((c, self.style_fit(feat, weights)))
        scored.sort(key=lambda x: x[1], reverse=True)
        fit_info = [{"text": c.get("text", "")[:60], "style_fit": f,
                     "register": c.get("register"), "length_label": c.get("length_label")}
                    for c, f in scored]
        return [c for c, _ in scored], fit_info
