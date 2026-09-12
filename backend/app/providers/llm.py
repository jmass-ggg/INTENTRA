"""LLM providers.

Default is the local LM Studio OpenAI-compatible server. The Claude provider is
cloud, opt-in, and used for the consolidation pass (Phase 6).
"""

from __future__ import annotations

import json
from abc import ABC, abstractmethod

import httpx


class LLMProvider(ABC):
    """Abstract base for chat-completion style language models."""

    @abstractmethod
    def generate(self, prompt: str, system: str | None = None) -> str:
        """Generate a completion for ``prompt`` with an optional ``system`` message."""
        raise NotImplementedError

    def generate_json(self, prompt: str, system: str | None = None) -> dict:
        """Convenience helper: generate and parse a JSON object response.

        Subclasses may override to use a provider-native JSON mode. The default
        implementation parses the raw text returned by :meth:`generate`.
        """
        raw = self.generate(prompt, system=system)
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            # Best-effort recovery: extract the first {...} block.
            start = raw.find("{")
            end = raw.rfind("}")
            if start != -1 and end != -1 and end > start:
                return json.loads(raw[start : end + 1])
            raise


class LMStudioProvider(LLMProvider):
    """Local LM Studio provider (DEFAULT).

    Talks to the OpenAI-compatible ``/chat/completions`` endpoint exposed by
    LM Studio at ``settings.lm_studio_base_url``. Requires LM Studio running at
    request time.
    """

    def __init__(self) -> None:
        from app.config import settings

        self.base_url: str = settings.lm_studio_base_url.rstrip("/")
        self.model: str = getattr(settings, "lm_studio_model", "local-model")
        self.timeout: float = float(getattr(settings, "llm_timeout", 120.0))
        # Reasoning control (see config). "none" disables Gemma-4's chain-of-thought.
        self.reasoning_effort: str = str(
            getattr(settings, "lm_studio_reasoning_effort", "none") or ""
        ).strip()
        self.max_tokens: int = int(getattr(settings, "lm_studio_max_tokens", 0) or 0)

    def _messages(self, prompt: str, system: str | None) -> list[dict]:
        messages: list[dict] = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        return messages

    def _payload(self, prompt: str, system: str | None, **extra) -> dict:
        payload: dict = {
            "model": self.model,
            "messages": self._messages(prompt, system),
            "temperature": 0.7,
            "stream": False,
        }
        # reasoning_effort: "none" makes Gemma-4 skip thinking entirely (huge
        # latency win); omit when blank/"default" so non-reasoning models are
        # unaffected.
        if self.reasoning_effort and self.reasoning_effort.lower() != "default":
            payload["reasoning_effort"] = self.reasoning_effort
        if self.max_tokens > 0:
            payload["max_tokens"] = self.max_tokens
        payload.update(extra)
        return payload

    def generate(self, prompt: str, system: str | None = None) -> str:
        url = f"{self.base_url}/chat/completions"
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(url, json=self._payload(prompt, system))
            resp.raise_for_status()
            data = resp.json()
        return data["choices"][0]["message"]["content"]

    def generate_json(self, prompt: str, system: str | None = None) -> dict:
        url = f"{self.base_url}/chat/completions"
        payload = self._payload(prompt, system, response_format={"type": "json_object"})
        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
        raw = data["choices"][0]["message"]["content"]
        return json.loads(raw)


class ClaudeProvider(LLMProvider):
    """Cloud Claude provider (opt-in).

    Used for the consolidation pass. The ``anthropic`` SDK is imported lazily so
    the package imports cleanly without it installed.
    """

    def __init__(self) -> None:
        from app.config import settings

        self.api_key: str | None = getattr(settings, "anthropic_api_key", None)
        self.model: str = getattr(settings, "claude_model", "claude-sonnet-4-5")
        self.max_tokens: int = int(getattr(settings, "claude_max_tokens", 2048))

    def _client(self):
        # LAZY import: only require anthropic when actually invoked.
        import anthropic

        return anthropic.Anthropic(api_key=self.api_key)

    def generate(self, prompt: str, system: str | None = None) -> str:
        client = self._client()
        kwargs: dict = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            kwargs["system"] = system
        message = client.messages.create(**kwargs)
        # Concatenate text blocks from the response content.
        return "".join(
            block.text for block in message.content if getattr(block, "type", None) == "text"
        )
