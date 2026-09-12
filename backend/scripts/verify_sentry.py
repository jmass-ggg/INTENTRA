#!/usr/bin/env python3
"""Verify the Sentry error-monitoring integration (sponsor: Sentry).

Run from the backend dir:  .venv/bin/python scripts/verify_sentry.py

Checks:
  1. No DSN  -> init is a clean no-op, Sentry inactive, app serves normally.
  2. With DSN -> Sentry activates; a deliberately-triggered route error is
     captured by the FastAPI integration (incl. our breadcrumb), AND a normal
     request produces a performance transaction (request traces). Events are
     intercepted via before_send / before_send_transaction so NOTHING is sent
     over the network — this proves capture without needing a live Sentry org.

Exit code is non-zero if any check fails.
"""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

from fastapi.testclient import TestClient  # noqa: E402

PASS, FAIL = "PASS", "FAIL"
_failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  [{PASS if ok else FAIL}] {name}{(' — ' + detail) if detail else ''}")
    if not ok:
        _failures.append(name)


# ---------------------------------------------------------------------------
# 1) No DSN -> no-op, app runs normally
# ---------------------------------------------------------------------------
print("1) No DSN (offline-safe no-op)")
from app import observability  # noqa: E402

active = observability.init_sentry(dsn="")
check("init_sentry('') returns False", active is False)
check("is_active() is False", observability.is_active() is False)

from app.main import app  # noqa: E402

client = TestClient(app, raise_server_exceptions=False)
r = client.get("/health")
check("GET /health works with Sentry off", r.status_code == 200, f"status={r.status_code}")
r = client.get("/debug/sentry-error")
check("error route 500s normally (nothing sent) with Sentry off", r.status_code == 500,
      f"status={r.status_code}")


# ---------------------------------------------------------------------------
# 2) With DSN -> activates + captures (events intercepted, no network)
# ---------------------------------------------------------------------------
print("2) With DSN (capture verified via before_send, no network)")

FAKE_DSN = "https://examplepublickey@o0.ingest.sentry.io/0"
errors: list[dict] = []
transactions: list[dict] = []


def _capture_error(event, hint):
    errors.append(event)
    return None  # drop -> never transmitted


def _capture_txn(event, hint):
    transactions.append(event)
    return None  # drop -> never transmitted


active = observability.init_sentry(
    dsn=FAKE_DSN,
    before_send=_capture_error,
    before_send_transaction=_capture_txn,
    traces_sample_rate=1.0,
)
check("init_sentry(<dsn>) returns True", active is True)
check("is_active() is True", observability.is_active() is True)

import sentry_sdk  # noqa: E402

# 2a. Direct SDK capture works (event queued/processed).
try:
    raise ValueError("direct-capture-probe")
except ValueError:
    sentry_sdk.capture_exception()
sentry_sdk.flush(timeout=2.0)


def _exc_type(event: dict) -> str:
    try:
        return event["exception"]["values"][-1]["type"]
    except Exception:
        return ""


direct = [e for e in errors if _exc_type(e) == "ValueError"]
check("direct capture_exception() produces an event", len(direct) >= 1,
      f"{len(direct)} event(s)")

# 2b. Route exception captured by the FastAPI integration, with our breadcrumb.
errors.clear()
transactions.clear()
client2 = TestClient(app, raise_server_exceptions=False)
resp = client2.get("/debug/sentry-error")
sentry_sdk.flush(timeout=2.0)

route_errs = [e for e in errors if _exc_type(e) == "RuntimeError"]
check("route 500 still returned to client", resp.status_code == 500, f"status={resp.status_code}")
check("FastAPI integration captured the route exception", len(route_errs) >= 1,
      f"{len(route_errs)} RuntimeError event(s)")

if route_errs:
    crumbs = route_errs[-1].get("breadcrumbs") or {}
    crumb_list = crumbs.get("values", crumbs) if isinstance(crumbs, dict) else crumbs
    msgs = [c.get("message", "") for c in (crumb_list or [])]
    check("captured event includes our pipeline breadcrumb",
          any("about to raise a test error" in m for m in msgs),
          f"{len(msgs)} breadcrumb(s)")

# 2c. A normal request produces a performance transaction (request trace).
errors.clear()
transactions.clear()
client2.get("/health")
sentry_sdk.flush(timeout=2.0)
health_txns = [t for t in transactions if "/health" in (t.get("transaction") or "")]
check("normal request produced a performance transaction (request trace)",
      len(health_txns) >= 1, f"{len(transactions)} transaction(s)")

print()
if _failures:
    print(f"RESULT: FAIL ({len(_failures)} check(s) failed: {', '.join(_failures)})")
    sys.exit(1)
print("RESULT: PASS — Sentry no-op offline; captures errors + traces when a DSN is set.")
