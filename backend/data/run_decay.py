"""Manually apply time-based decay to the graph (Phase 6).

Salience (nodes) and weight (edges) are multiplied by
``decay_factor ** (elapsed_seconds / 86400)``, so unused memories fade. Intended
to be run on a schedule (e.g. a daily cron) rather than as an autonomous loop.

Usage (from the backend directory):

    python -m data.run_decay [elapsed_seconds]

Default elapsed is one day (86400s).
"""

from __future__ import annotations

import sys


def main(argv: list[str]) -> int:
    from app.config import settings
    from app.services.graph import GraphService

    elapsed = float(argv[1]) if len(argv) > 1 else 86400.0
    factor = float(settings.decay_factor) ** (elapsed / 86400.0)

    graph = GraphService()
    graph.connect()

    # Show the effect on a sample edge so the run is observable.
    before = graph._q(
        "MATCH ()-[e:Edge]->() RETURN e.weight ORDER BY e.weight DESC LIMIT 1"
    )
    graph.decay(elapsed)
    after = graph._q(
        "MATCH ()-[e:Edge]->() RETURN e.weight ORDER BY e.weight DESC LIMIT 1"
    )
    b = before[0][0] if before else None
    a = after[0][0] if after else None
    print(f"decay applied: elapsed={elapsed}s, factor={factor:.4f}")
    print(f"  max edge weight: {b} -> {a}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
