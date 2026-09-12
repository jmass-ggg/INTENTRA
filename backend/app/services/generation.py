"""GenerationService — candidate utterance generation (Phase 3).

Given the user's fragments, conversational context, and the grounded RETRIEVED
FACTS from retrieval, asks the LLM to reconstruct the full intended message and
returns three ``Candidate``-shaped dicts.

Robust JSON handling: strip reasoning/markdown, extract the first ``[`` .. last
``]`` and ``json.loads``. On failure, do ONE repair retry. On a second failure,
fall back to a single candidate built directly from the fragments, so the
endpoint never hard-fails. Model-supplied ``grounded_node_ids`` are validated
against the actually-retrieved node ids; invented ids are dropped.

The LLM client is injected; no heavy deps are imported at module top-level.
"""

from __future__ import annotations

import json
import re
from typing import Any

# AAC reconstruction system role (the person confirms; we never auto-speak).
SYSTEM_PROMPT = """You assist a person who cannot easily speak. They know what \
they want to say but can only produce a few words or sounds. Reconstruct their \
intended message from their INPUT, the CONVERSATION CONTEXT, and the RETRIEVED \
FACTS about their life.

Rules:
1. Do NOT invent meaning the input and context do not imply. Stay faithful; if \
evidence is thin, prefer a shorter, safer utterance.
2. Output EXACTLY 3 candidates that vary in length and directness.
3. Use the RETRIEVED FACTS to match how they address people (use the exact term \
of address shown) and how they normally talk.
4. STRICT JSON ONLY — no prose, no markdown. Output a JSON ARRAY of exactly 3 \
objects, each:
{"text": "<full utterance, first person>", "register": "warm"|"neutral"|"direct", \
"length_label": "short"|"medium"|"full", "rationale": "<one short reason>", \
"grounded_node_ids": ["<ids from RETRIEVED FACTS this draws on>"]}"""

_REGISTERS = {"warm", "neutral", "direct"}
_LENGTHS = {"short", "medium", "full"}


class GenerationService:
    """Generates candidate utterances from fragments + grounded facts."""

    def __init__(self, llm: Any) -> None:
        self.llm = llm

    def _build_user_prompt(
        self, fragments: list[str], context: str, retrieved_facts: str, style_prompt: str = ""
    ) -> str:
        joined = " | ".join(f for f in fragments if f) or "(none)"
        style_block = f"{style_prompt.strip()}\n\n" if style_prompt and style_prompt.strip() else ""
        return (
            f"CONVERSATION CONTEXT (what the partner just said / situation):\n"
            f"{context.strip() or '(none)'}\n\n"
            f"RETRIEVED FACTS (ground your wording in these; cite ids in grounded_node_ids):\n"
            f"{retrieved_facts.strip() or '(none)'}\n\n"
            f"{style_block}"
            f"INPUT (the person's fragments):\n{joined}\n\n"
            f"Return the JSON array of 3 candidates now."
        )

    # --- JSON extraction ----------------------------------------------------

    @staticmethod
    def _extract_array(raw: str) -> list[Any] | None:
        if not raw:
            return None
        text = re.sub(r"<think>.*?</think>", "", raw, flags=re.DOTALL | re.IGNORECASE)
        text = re.sub(r"```(?:json)?", "", text)
        start, end = text.find("["), text.rfind("]")
        if start == -1 or end <= start:
            return None
        try:
            data = json.loads(text[start : end + 1])
        except Exception:
            return None
        return data if isinstance(data, list) else None

    def _coerce(self, items: list[Any], valid_ids: set[str]) -> list[dict[str, Any]]:
        """Validate/normalize raw candidate dicts to the Candidate contract."""
        out: list[dict[str, Any]] = []
        for it in items:
            if not isinstance(it, dict):
                continue
            text = str(it.get("text", "")).strip()
            if not text:
                continue
            register = str(it.get("register", "neutral")).lower()
            if register not in _REGISTERS:
                register = "neutral"
            length_label = str(it.get("length_label", "medium")).lower()
            if length_label not in _LENGTHS:
                length_label = "medium"
            rationale = str(it.get("rationale", "")).strip()
            raw_ids = it.get("grounded_node_ids") or []
            if not isinstance(raw_ids, list):
                raw_ids = []
            # Drop any ids the model invented (not actually retrieved).
            grounded = [str(i) for i in raw_ids if str(i) in valid_ids]
            out.append({
                "text": text,
                "register": register,
                "length_label": length_label,
                "rationale": rationale,
                "grounded_node_ids": grounded,
            })
        return out[:3]

    @staticmethod
    def _fallback(fragments: list[str]) -> list[dict[str, Any]]:
        words = [f.strip() for f in fragments if f and f.strip()]
        text = " ".join(words).strip() or "I need a moment."
        text = text[0].upper() + text[1:]
        if text[-1] not in ".?!":
            text += "."
        return [{
            "text": text,
            "register": "neutral",
            "length_label": "short",
            "rationale": "Built directly from your words (the language model was unavailable or unparseable).",
            "grounded_node_ids": [],
        }]

    def generate_candidates(
        self,
        fragments: list[str],
        context: str,
        retrieved_facts: str,
        valid_node_ids: list[str] | None = None,
        style_prompt: str = "",
    ) -> list[dict[str, Any]]:
        """Produce up to three Candidate-shaped dicts (never raises)."""
        from app.tracing import llm_span

        valid_ids = set(valid_node_ids or [])
        user_prompt = self._build_user_prompt(fragments, context, retrieved_facts, style_prompt)
        model = getattr(self.llm, "model", "") or ""

        # First attempt.
        try:
            with llm_span("candidate_generation", model=model, input_value=user_prompt) as _s:
                raw = self.llm.generate(user_prompt, system=SYSTEM_PROMPT)
                _s.set_output(raw)
        except Exception:
            return self._fallback(fragments)

        items = self._extract_array(raw)
        if items is not None:
            coerced = self._coerce(items, valid_ids)
            if coerced:
                return coerced

        # One repair retry.
        repair = (
            "Your previous reply was not valid JSON. Return ONLY a JSON array of exactly 3 "
            "objects with keys text, register, length_label, rationale, grounded_node_ids. "
            "No prose, no markdown.\n\n" + user_prompt
        )
        try:
            raw2 = self.llm.generate(repair, system=SYSTEM_PROMPT)
            items2 = self._extract_array(raw2)
            if items2 is not None:
                coerced2 = self._coerce(items2, valid_ids)
                if coerced2:
                    return coerced2
        except Exception:
            pass

        # Final fallback so /generate never hard-fails.
        return self._fallback(fragments)
