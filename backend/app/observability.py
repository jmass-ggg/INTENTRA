"""Sentry error monitoring (sponsor: Sentry).

OFFLINE-SAFE: when ``settings.sentry_dsn`` (env SENTRY_DSN) is empty, every
function here is a clean no-op, so the app runs fully on-device with no cloud
dependency. When a DSN is set, unhandled exceptions and per-request performance
traces are captured automatically via the FastAPI/Starlette integrations, and
the helpers below add breadcrumbs/spans around the generation pipeline for real,
domain-specific signal.

``sentry_sdk`` is imported lazily and guarded so the module imports even if the
SDK is absent. The breadcrumb/span helpers are safe to call unconditionally:
sentry_sdk treats them as no-ops when no client is active.
"""

from __future__ import annotations

import contextlib
import logging
from typing import Any, Iterator

logger = logging.getLogger("lucid_voice.sentry")

_active = False


def init_sentry(dsn: str | None = None, **overrides: Any) -> bool:
    """Initialize Sentry from settings (or an explicit ``dsn``).

    Returns True if Sentry was activated, False if it was a no-op (no DSN or SDK
    unavailable). ``overrides`` are passed through to ``sentry_sdk.init`` (used by
    the verification script to inject a capturing ``before_send``).
    """
    global _active
    from app.config import settings

    dsn = dsn if dsn is not None else (getattr(settings, "sentry_dsn", "") or "")
    dsn = dsn.strip()
    if not dsn:
        logger.info("SENTRY_DSN not set; Sentry disabled (offline-safe no-op).")
        _active = False
        return False

    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.starlette import StarletteIntegration
    except Exception as exc:  # pragma: no cover - SDK should be installed
        logger.warning("sentry-sdk unavailable (%s); Sentry disabled.", exc)
        _active = False
        return False

    kwargs: dict[str, Any] = dict(
        dsn=dsn,
        integrations=[StarletteIntegration(), FastApiIntegration()],
        traces_sample_rate=float(getattr(settings, "sentry_traces_sample_rate", 1.0)),
        environment=getattr(settings, "sentry_environment", "development"),
        send_default_pii=False,  # AAC content is sensitive — never send PII/bodies.
        release="lucid-voice@dev",
    )
    kwargs.update(overrides)
    try:
        sentry_sdk.init(**kwargs)
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("sentry_sdk.init failed (%s); Sentry disabled.", exc)
        _active = False
        return False

    _active = True
    logger.info("Sentry initialized (environment=%s).", kwargs.get("environment"))
    return True


def is_active() -> bool:
    """Whether a Sentry client is currently active."""
    try:
        import sentry_sdk

        client = sentry_sdk.get_client()
        return bool(client and client.is_active())
    except Exception:
        return _active


def add_breadcrumb(category: str, message: str, level: str = "info", **data: Any) -> None:
    """Add a Sentry breadcrumb. No-op when Sentry is inactive/unavailable."""
    try:
        import sentry_sdk

        sentry_sdk.add_breadcrumb(category=category, message=message, level=level, data=data or None)
    except Exception:
        pass


def set_tag(key: str, value: Any) -> None:
    """Tag the current scope. No-op when Sentry is inactive/unavailable."""
    try:
        import sentry_sdk

        sentry_sdk.set_tag(key, value)
    except Exception:
        pass


@contextlib.contextmanager
def span(op: str, description: str | None = None) -> Iterator[Any]:
    """Open a Sentry span (child of the request transaction when one exists).

    No-op (yields None) when Sentry is inactive or the SDK is unavailable.
    """
    try:
        import sentry_sdk

        with sentry_sdk.start_span(op=op, description=description) as s:
            yield s
    except Exception:
        yield None
