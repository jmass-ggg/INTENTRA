"""LLM tracing via Arize Phoenix / OpenInference (sponsor: Arize).

Phoenix is open-source and runs LOCALLY, so this adds NO cloud dependency. When
``settings.phoenix_enabled`` is False (the default), every helper here is a clean
no-op and the app runs fully offline. When enabled, ``init_tracing()`` registers
an OpenTelemetry tracer that exports to a local Phoenix collector, and
``llm_span(...)`` wraps an LLM call with OpenInference semantic attributes
(span kind = LLM, model, input, output) so the two model calls in the pipeline —
anchor extraction and candidate generation — show up as real traces.

All heavy imports (phoenix, opentelemetry, openinference) are lazy and guarded.
"""

from __future__ import annotations

import contextlib
import logging
from typing import Any, Iterator

logger = logging.getLogger("lucid_voice.tracing")

_enabled = False
_tracer: Any = None


def init_tracing(
    force: bool | None = None,
    project_name: str | None = None,
    endpoint: str | None = None,
) -> bool:
    """Register the Phoenix/OpenInference tracer. Idempotent.

    Returns True if tracing is active, False if it was a no-op (disabled or the
    libraries/collector are unavailable). ``force`` overrides the settings flag
    (used by the eval/verify script after launching an in-process Phoenix).
    """
    global _enabled, _tracer
    from app.config import settings

    enabled = bool(getattr(settings, "phoenix_enabled", False)) if force is None else force
    if not enabled:
        logger.info("Phoenix tracing disabled (offline-safe no-op).")
        _enabled = False
        return False

    try:
        from phoenix.otel import register
        from opentelemetry import trace as ot
    except Exception as exc:  # pragma: no cover - libs should be installed
        logger.warning("Phoenix/OTel unavailable (%s); tracing disabled.", exc)
        _enabled = False
        return False

    try:
        tracer_provider = register(
            project_name=project_name or getattr(settings, "phoenix_project_name", "lucid-voice"),
            endpoint=endpoint or getattr(settings, "phoenix_collector_endpoint", None),
            batch=False,                     # synchronous export -> traces visible immediately
            set_global_tracer_provider=True,
        )
        _tracer = tracer_provider.get_tracer("lucid_voice")
        _enabled = True
        logger.info("Phoenix tracing initialized.")
        return True
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Phoenix register() failed (%s); tracing disabled.", exc)
        _enabled = False
        return False


def is_active() -> bool:
    return _enabled and _tracer is not None


class _Span:
    """Thin wrapper exposing set_output()/set_attr() over an OTel span (or no-op)."""

    def __init__(self, span: Any = None) -> None:
        self._span = span

    def set_output(self, value: str) -> None:
        if self._span is None:
            return
        try:
            from openinference.semconv.trace import SpanAttributes

            self._span.set_attribute(SpanAttributes.OUTPUT_VALUE, str(value)[:4000])
        except Exception:
            pass

    def set_attr(self, key: str, value: Any) -> None:
        if self._span is None:
            return
        try:
            self._span.set_attribute(key, value)
        except Exception:
            pass


@contextlib.contextmanager
def llm_span(
    name: str, model: str = "", input_value: str = "", metadata: dict | None = None
) -> Iterator[_Span]:
    """Trace an LLM call as an OpenInference LLM span. No-op when tracing is off.

    Usage:
        with llm_span("candidate_generation", model="gemma", input_value=prompt) as s:
            out = llm.generate(prompt)
            s.set_output(out)
    """
    if not is_active():
        yield _Span(None)
        return

    try:
        from openinference.semconv.trace import SpanAttributes, OpenInferenceSpanKindValues

        with _tracer.start_as_current_span(name) as span:
            try:
                span.set_attribute(
                    SpanAttributes.OPENINFERENCE_SPAN_KIND,
                    OpenInferenceSpanKindValues.LLM.value,
                )
                if model:
                    span.set_attribute(SpanAttributes.LLM_MODEL_NAME, model)
                if input_value:
                    span.set_attribute(SpanAttributes.INPUT_VALUE, str(input_value)[:4000])
                for k, v in (metadata or {}).items():
                    span.set_attribute(f"metadata.{k}", v)
            except Exception:
                pass
            yield _Span(span)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("llm_span(%s) failed (%s); continuing untraced.", name, exc)
        yield _Span(None)


def flush() -> None:
    """Force-flush spans to the collector (used before reading them back)."""
    try:
        from opentelemetry import trace as ot

        provider = ot.get_tracer_provider()
        if hasattr(provider, "force_flush"):
            provider.force_flush()
    except Exception:
        pass
