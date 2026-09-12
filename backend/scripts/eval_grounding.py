#!/usr/bin/env python3
"""Phoenix tracing + grounding eval (sponsor: Arize).

Launches a LOCAL Arize Phoenix instance, runs a small FIXED test set through the
real retrieval+generation pipeline (tracing BOTH LLM calls — anchor extraction
and candidate generation), then:

  1. EVAL — reports "grounding accuracy" = the fraction of the gold facts a
     config places into the selected context the model is allowed to use (facts
     not selected can't ground the answer). Compares the SUBMODULAR context
     selector vs plain TOP-K and prints the measurable improvement.

  2. TRACES — verifies Phoenix captured the two LLM span types, and prints the
     local Phoenix URL so a judge can open the traces live.

Requires: local LM Studio (LLM) + the seeded kuzu graph. Run from backend dir:
    .venv/bin/python scripts/eval_grounding.py
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile
import time

sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

# Use a lock-free copy of the graph so a running server isn't disturbed.
BACKEND = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
SRC_DB = os.path.join(BACKEND, "data", "kuzu_db")
TMP_DB = tempfile.mkdtemp(prefix="lucid-eval-kuzu-") + "/kuzu_db"
shutil.copytree(SRC_DB, TMP_DB)
os.environ["KUZU_DB_PATH"] = TMP_DB
os.environ["REDIS_ENABLED"] = "false"  # eval focuses on selection + tracing

PERSON = "elena"

# Fixed test set: (name, fragments, partner-context, gold fact labels). The gold
# labels are the partner + the topical fact(s) a faithful answer must be grounded
# in. Labels are resolved to node ids against the live graph.
TESTS = [
    ("sunday-call", ["sunday", "call"],
     "Sofia: Mom, will you call me on Sunday?",
     ["Sofia", "calls Sofia on Sundays"]),
    ("dinner-time", ["dinner", "six"],
     "Marco: what time do you want dinner?",
     ["Marco", "dinner around six"]),
    ("play-with-mateo", ["tired", "later"],
     "Mateo: Grandma, can we play now?",
     ["Mateo", "gentle with Mateo"]),
    ("morning-garden", ["garden", "morning"],
     "Sofia: what did you get up to today?",
     ["Sofia", "gardens in the morning"]),
    ("friday-plans", ["maybe", "not", "sure"],
     "Marco: can you commit to Friday plans now?",
     ["Marco", "doesn't commit to plans early"]),
    ("after-lunch-rest", ["nap", "rest"],
     "Sofia: how are you feeling after lunch?",
     ["Sofia", "naps after lunch"]),
]


def _resolve_gold(pnodes: dict, labels: list[str]) -> list[str]:
    ids = []
    for want in labels:
        w = want.lower().strip()
        hit = None
        for nid, nd in pnodes.items():
            lab = str(nd["label"]).lower().strip()
            if lab == w:
                hit = nid
                break
        if hit is None:  # fall back to substring match
            for nid, nd in pnodes.items():
                if w in str(nd["label"]).lower():
                    hit = nid
                    break
        if hit:
            ids.append(hit)
    return ids


def main() -> int:
    import phoenix as px
    import app.tracing as tracing
    from app.services.graph import GraphService
    from app.services.retrieval import RetrievalService
    from app.services.generation import GenerationService
    from app.providers import get_embedding_provider, get_llm_provider
    from app.config import settings

    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor, SpanExportResult
    from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource

    print("Launching local Phoenix ...")
    session = px.launch_app()
    endpoint = "http://localhost:6006/v1/traces"

    # Send spans to the local Phoenix collector (real capture, visible in the UI)
    # AND tee them to an in-memory exporter for reliable, version-independent
    # assertions. A thin wrapper counts spans Phoenix's collector ACCEPTED.
    class CountingOTLP(OTLPSpanExporter):
        accepted = 0

        def export(self, spans):
            res = super().export(spans)
            if res == SpanExportResult.SUCCESS:
                CountingOTLP.accepted += len(spans)
            return res

    provider = TracerProvider(
        resource=Resource.create({"openinference.project.name": "lucid-voice"})
    )
    otlp = CountingOTLP(endpoint=endpoint)
    mem = InMemorySpanExporter()
    provider.add_span_processor(SimpleSpanProcessor(otlp))
    provider.add_span_processor(SimpleSpanProcessor(mem))

    # Point the app's tracing helpers at this provider (what llm_span() uses).
    tracing._tracer = provider.get_tracer("lucid_voice")
    tracing._enabled = True

    print(f"  Phoenix UI: {session.url}")
    print(f"  tracing active: {tracing.is_active()} (-> Phoenix collector {endpoint})")

    graph = GraphService()
    graph.connect()
    embedding = get_embedding_provider()
    llm = get_llm_provider()
    retrieval = RetrievalService(graph, llm, embedding)
    generation = GenerationService(llm)

    pnodes = {n["id"]: n for n in graph.person_nodes(PERSON)}
    print(f"  graph: {len(pnodes)} nodes for {PERSON}\n")

    rows = []
    n_anchor_calls = 0
    n_gen_calls = 0
    for name, frags, ctx, gold_labels in TESTS:
        gold = set(_resolve_gold(pnodes, gold_labels))
        if not gold:
            print(f"  [skip] {name}: gold labels unresolved")
            continue
        r = retrieval.retrieve(PERSON, frags, ctx)
        n_anchor_calls += 1
        sel = r.get("selection") or {}
        sub_ids = set(sel.get("submodular", {}).get("ids", []))
        top_ids = set(sel.get("topk", {}).get("ids", []))
        sub_cov = len(gold & sub_ids) / len(gold)
        top_cov = len(gold & top_ids) / len(gold)
        sub_div = sel.get("submodular", {}).get("intra_sim")
        top_div = sel.get("topk", {}).get("intra_sim")

        # Run generation too, so the candidate_generation LLM call is traced.
        try:
            generation.generate_candidates(
                frags, ctx, r.get("context_block", ""),
                valid_node_ids=r.get("grounded_ids", []),
            )
            n_gen_calls += 1
        except Exception as exc:
            print(f"    (generation note for {name}: {exc})")

        rows.append((name, len(gold), sub_cov, top_cov, sub_div, top_div))
        print(f"  {name:18s} gold={len(gold)}  submodular={sub_cov:.0%}  topk={top_cov:.0%}")

    if not rows:
        print("No evaluable test cases.")
        return 1

    sub_mean = sum(r[2] for r in rows) / len(rows)
    top_mean = sum(r[3] for r in rows) / len(rows)
    sub_div_mean = sum((r[4] or 0) for r in rows) / len(rows)
    top_div_mean = sum((r[5] or 0) for r in rows) / len(rows)
    delta = sub_mean - top_mean

    print("\n" + "=" * 64)
    print("GROUNDING ACCURACY (gold facts present in the selected context)")
    print("=" * 64)
    print(f"  cases evaluated         : {len(rows)}")
    print(f"  SUBMODULAR  accuracy    : {sub_mean:.1%}   (avg redundancy {sub_div_mean:.3f})")
    print(f"  TOP-K       accuracy    : {top_mean:.1%}   (avg redundancy {top_div_mean:.3f})")
    print(f"  IMPROVEMENT (submodular): {delta:+.1%}")
    print("=" * 64)

    # --- Phoenix trace verification ---
    print("\nVerifying Phoenix captured the LLM traces ...")
    provider.force_flush()
    time.sleep(1.0)

    finished = mem.get_finished_spans()
    names = [s.name for s in finished]
    anchor_n = names.count("anchor_extraction")
    gen_n = names.count("candidate_generation")

    # Confirm the OpenInference LLM attributes are actually set on the spans.
    def _attr_ok(span_name: str) -> bool:
        for s in finished:
            if s.name == span_name:
                a = dict(s.attributes or {})
                if a.get("openinference.span.kind") == "LLM" and a.get("input.value"):
                    return True
        return False

    attrs_ok = _attr_ok("anchor_extraction") and _attr_ok("candidate_generation")

    print(f"  spans produced (in-mem) : {len(finished)}")
    print(f"  anchor_extraction spans : {anchor_n}")
    print(f"  candidate_generation    : {gen_n}")
    print(f"  OpenInference LLM attrs : {'present' if attrs_ok else 'MISSING'}")
    print(f"  spans accepted by Phoenix: {CountingOTLP.accepted}  (OTLP -> {endpoint})")
    print(f"  open traces at          : {session.url}")

    ok_eval = delta >= 0 and sub_mean >= top_mean and sub_mean > 0
    ok_traces = anchor_n >= 1 and gen_n >= 1 and attrs_ok and CountingOTLP.accepted >= (anchor_n + gen_n)
    print()
    if ok_eval and ok_traces:
        print(f"RESULT: PASS — Phoenix traced both LLM calls; submodular grounding "
              f"{'beats' if delta > 0 else 'matches'} top-k by {delta:+.1%}.")
        return 0
    print(f"RESULT: FAIL — eval_ok={ok_eval} traces_ok={ok_traces}")
    return 1


if __name__ == "__main__":
    code = 1
    try:
        code = main()
    finally:
        try:
            import phoenix as px

            px.close_app()
        except Exception:
            pass
        shutil.rmtree(os.path.dirname(TMP_DB), ignore_errors=True)
    sys.exit(code)
