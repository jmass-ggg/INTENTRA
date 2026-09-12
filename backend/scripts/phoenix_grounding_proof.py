#!/usr/bin/env python3
"""Phoenix PROOF that submodular context selection beats top-k (sponsor: Arize).

Sends real traces + evaluations to a LOCAL Phoenix so the win is visible in the
Phoenix UI, and writes a durable report file. For each fixed test case it runs
retrieval ONCE (so both selectors see the SAME candidate pool — a fair A/B),
then emits, per config, a `context_selection` span carrying:
    config = submodular | topk
    grounding.accuracy = fraction of gold facts placed in the selected context
    context.redundancy = mean intra-set cosine (lower = more diverse)
and attaches a Phoenix `grounding_accuracy` evaluation to each span.

Prereqs: a Phoenix server on :6006 (`phoenix serve`) + local LM Studio.
Run from the backend dir:  .venv/bin/python scripts/phoenix_grounding_proof.py
"""

from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
import time

sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

BACKEND = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))
SRC_DB = os.path.join(BACKEND, "data", "kuzu_db")
TMP_DB = tempfile.mkdtemp(prefix="lucid-proof-kuzu-") + "/kuzu_db"
shutil.copytree(SRC_DB, TMP_DB)
os.environ["KUZU_DB_PATH"] = TMP_DB
os.environ["REDIS_ENABLED"] = "false"

PERSON = "elena"
PHOENIX_ENDPOINT = "http://localhost:6006/v1/traces"
PHOENIX_BASE = "http://localhost:6006"
PROJECT = "grounding-eval"
REPORT_DIR = os.path.join(BACKEND, "reports")

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
            if str(nd["label"]).lower().strip() == w:
                hit = nid
                break
        if hit is None:
            for nid, nd in pnodes.items():
                if w in str(nd["label"]).lower():
                    hit = nid
                    break
        if hit:
            ids.append(hit)
    return ids


def main() -> int:
    import phoenix as px
    from phoenix.trace import SpanEvaluations
    import pandas as pd
    import app.tracing as tracing
    from app.services.graph import GraphService
    from app.services.retrieval import RetrievalService
    from app.services.generation import GenerationService
    from app.providers import get_embedding_provider, get_llm_provider
    from app.config import settings

    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.resources import Resource

    provider = TracerProvider(resource=Resource.create({"openinference.project.name": PROJECT}))
    provider.add_span_processor(SimpleSpanProcessor(OTLPSpanExporter(endpoint=PHOENIX_ENDPOINT)))
    tracer = provider.get_tracer("grounding-proof")
    tracing._tracer = tracer
    tracing._enabled = True

    graph = GraphService()
    graph.connect()
    embedding = get_embedding_provider()
    llm = get_llm_provider()
    retrieval = RetrievalService(graph, llm, embedding)
    generation = GenerationService(llm)
    pnodes = {n["id"]: n for n in graph.person_nodes(PERSON)}
    print(f"Phoenix project '{PROJECT}'  |  {len(pnodes)} nodes for {PERSON}\n")

    eval_rows = []     # (span_id_hex, score, label, case)
    report_rows = []   # durable artifact
    sub_scores, top_scores = [], []

    for name, frags, ctx, gold_labels in TESTS:
        gold = set(_resolve_gold(pnodes, gold_labels))
        if not gold:
            print(f"  [skip] {name}: gold unresolved")
            continue

        # ONE retrieval -> both selections from the SAME pool (fair A/B).
        with tracer.start_as_current_span("grounding_case") as case_span:
            case_span.set_attribute("openinference.span.kind", "CHAIN")
            case_span.set_attribute("case", name)
            case_span.set_attribute("input.value", f"{ctx} || fragments={frags}")
            case_span.set_attribute("gold.count", len(gold))

            r = retrieval.retrieve(PERSON, frags, ctx)  # anchor_extraction traced inside
            sel = r.get("selection") or {}
            configs = {
                "submodular": sel.get("submodular", {}),
                "topk": sel.get("topk", {}),
            }

            case_scores = {}
            for cfg, info in configs.items():
                ids = set(info.get("ids", []))
                score = len(gold & ids) / len(gold)
                redundancy = info.get("intra_sim")
                case_scores[cfg] = score
                with tracer.start_as_current_span("context_selection") as s:
                    s.set_attribute("openinference.span.kind", "RETRIEVER")
                    s.set_attribute("config", cfg)
                    s.set_attribute("case", name)
                    s.set_attribute("grounding.accuracy", score)
                    if redundancy is not None:
                        s.set_attribute("context.redundancy", float(redundancy))
                    s.set_attribute("selected.count", len(ids))
                    s.set_attribute("gold.hit", len(gold & ids))
                    s.set_attribute("gold.count", len(gold))
                    sid = format(s.get_span_context().span_id, "016x")
                eval_rows.append((sid, score, cfg, name))

            case_span.set_attribute("grounding.submodular", case_scores["submodular"])
            case_span.set_attribute("grounding.topk", case_scores["topk"])
            case_span.set_attribute("grounding.delta", case_scores["submodular"] - case_scores["topk"])

            # One real generation under the production (submodular) context.
            try:
                settings.selection_mode = "submodular"
                generation.generate_candidates(
                    frags, ctx, r.get("context_block", ""),
                    valid_node_ids=r.get("grounded_ids", []),
                )
            except Exception as exc:
                print(f"    (gen note {name}: {exc})")

        sub_scores.append(case_scores["submodular"])
        top_scores.append(case_scores["topk"])
        report_rows.append({
            "case": name, "gold": len(gold),
            "submodular": case_scores["submodular"], "topk": case_scores["topk"],
            "delta": case_scores["submodular"] - case_scores["topk"],
        })
        print(f"  {name:18s} submodular={case_scores['submodular']:.0%}  topk={case_scores['topk']:.0%}")

    if not report_rows:
        print("No evaluable cases.")
        return 1

    sub_mean = sum(sub_scores) / len(sub_scores)
    top_mean = sum(top_scores) / len(top_scores)
    delta = sub_mean - top_mean

    # Summary span (visible at a glance in Phoenix).
    with tracer.start_as_current_span("grounding_eval_summary") as summ:
        summ.set_attribute("openinference.span.kind", "CHAIN")
        summ.set_attribute("cases", len(report_rows))
        summ.set_attribute("grounding.submodular_mean", sub_mean)
        summ.set_attribute("grounding.topk_mean", top_mean)
        summ.set_attribute("grounding.improvement", delta)
        summ.set_attribute("output.value",
                           f"submodular {sub_mean:.1%} vs topk {top_mean:.1%} (+{delta:.1%})")

    provider.force_flush()
    time.sleep(2.0)

    # Attach first-class Phoenix evaluations to the per-config selection spans.
    evals_logged = False
    try:
        df = pd.DataFrame(
            {"score": [r[1] for r in eval_rows], "label": [r[2] for r in eval_rows]},
            index=[r[0] for r in eval_rows],
        )
        df.index.name = "context.span_id"
        px.Client(endpoint=PHOENIX_BASE).log_evaluations(
            SpanEvaluations(eval_name="grounding_accuracy", dataframe=df)
        )
        evals_logged = True
    except Exception as exc:
        print(f"  (log_evaluations note: {exc})")

    # Durable report artifact.
    os.makedirs(REPORT_DIR, exist_ok=True)
    md = os.path.join(REPORT_DIR, "grounding_eval.md")
    jl = os.path.join(REPORT_DIR, "grounding_eval.jsonl")
    with open(jl, "w") as f:
        for row in report_rows:
            f.write(json.dumps(row) + "\n")
    with open(md, "w") as f:
        f.write("# Grounding accuracy: submodular vs top-k context selection\n\n")
        f.write(f"Source: real retrieval over {len(pnodes)} nodes for `{PERSON}`, "
                f"traced in Phoenix project `{PROJECT}`. Metric = fraction of gold "
                f"facts placed into the selected context (a faithful answer can only "
                f"ground in facts that were selected).\n\n")
        f.write("| case | gold | submodular | top-k | Δ |\n|---|---|---|---|---|\n")
        for row in report_rows:
            f.write(f"| {row['case']} | {row['gold']} | {row['submodular']:.0%} | "
                    f"{row['topk']:.0%} | {row['delta']:+.0%} |\n")
        f.write(f"| **MEAN** | | **{sub_mean:.1%}** | **{top_mean:.1%}** | "
                f"**{delta:+.1%}** |\n")

    print("\n" + "=" * 60)
    print(f"  SUBMODULAR mean grounding : {sub_mean:.1%}")
    print(f"  TOP-K      mean grounding : {top_mean:.1%}")
    print(f"  IMPROVEMENT               : {delta:+.1%}")
    print("=" * 60)
    print(f"  Phoenix evaluations logged: {evals_logged}")
    print(f"  Phoenix UI                : {PHOENIX_BASE}  (project: {PROJECT})")
    print(f"  Durable report            : {md}")
    return 0 if delta > 0 else 1


if __name__ == "__main__":
    code = 1
    try:
        code = main()
    finally:
        shutil.rmtree(os.path.dirname(TMP_DB), ignore_errors=True)
    sys.exit(code)
