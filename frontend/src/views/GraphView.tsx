// GraphView — live knowledge-graph visualization with retrieval highlighting
// (Phase 5). Loads GET /graph/{person} once, then polls /trace/latest every
// 600ms; when a new /generate trace arrives it lights up the retrieved
// subgraph (anchor rings on the partner, glow on retrieved nodes, grounded
// nodes emphasized most) and shows the candidates with their grounded labels.

import { useCallback, useEffect, useMemo, useRef, useState, type CSSProperties } from "react";
import { useReducedMotion } from "framer-motion";
import {
  KIND_COLORS,
  type FGNode,
  type FGLink,
  type GraphData,
  type Highlight,
  type Growth,
} from "../components/ForceGraph";
import HologramBrain from "../components/HologramBrain";
import BuildBrainPanel from "../components/BuildBrainPanel";
import { getGraph, generate } from "../lib/api";
import type { ConfirmResponse, Candidate } from "../lib/api";
import { DUR, EASE_OUT } from "../lib/motion";

const PERSON_ID = "elena";
const POLL_MS = 600;

// LIGHT theme tokens (mirror tailwind.config.js so the inline styles re-theme
// by value, keeping AA contrast on the soft off-white canvas).
const INK = "#F5F7FA";
const INK_RAISED = "#FFFFFF";
const INK_LINE = "#D6DEE8";
const TEXT = "#161A21";
const TEXT_MUTED = "#566273";
const TEXT_FAINT = "#8089A3";
const VOICE = "#E14826"; // THE HUMAN coral
const VOICE_DEEP = "#C23A1B";
const VOICE_SOFT = "#FCE9E3";
const MIND = "#0C8276"; // THE MACHINE teal
const MIND_SOFT = "#DBF1ED";

// Shared frosted-card style for the brain-canvas overlays (light on the dark
// viewport), so the memory-growth and reconstruction cards align and match.
const CARD_STYLE: CSSProperties = {
  padding: "10px 13px",
  borderRadius: 12,
  background: "rgba(255,255,255,0.86)",
  backdropFilter: "blur(8px)",
  border: `1px solid ${INK_LINE}`,
  boxShadow: "0 1px 2px 0 rgba(22,26,33,0.04), 0 10px 24px -14px rgba(22,26,33,0.12)",
};

// Shared size for the bottom corner cards (reconstruction + legend) so they
// match. 320 matches the memory-growth card width; 210 is ~50% shorter than
// the reconstruction card's previous height, keeping the brain centered.
const PANEL_W = 320;
const PANEL_H = 240; // shared height for the matching bottom cards (legend + reconstruction)

interface TraceCandidate {
  text: string;
  register: string;
  length_label: string;
  rationale: string;
  grounded_node_ids: string[];
}
interface Trace {
  anchors?: string[];
  subgraph_node_ids?: string[];
  subgraph_edge_ids?: string[];
  confidence?: number;
  latency_ms?: number;
  abstain?: boolean;
  candidates?: TraceCandidate[];
}

const EMPTY_HL: Highlight = {
  active: false,
  anchorIds: new Set(),
  subgraphNodeIds: new Set(),
  subgraphEdgeIds: new Set(),
  groundedIds: new Set(),
};

const TRY_IT: { label: string; fragments: string[]; context: string }[] = [
  { label: "“cold”, “window”", fragments: ["cold", "window"], context: "" },
  {
    label: "“tired”, “maybe” · dinner",
    fragments: ["tired", "maybe"],
    context: "Mom, do you want to come for dinner Sunday?",
  },
  {
    label: "“tired”, “maybe” · play",
    fragments: ["tired", "maybe"],
    context: "Grandma, will you play with me?",
  },
];

export default function GraphView() {
  const [data, setData] = useState<GraphData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [highlight, setHighlight] = useState<Highlight>(EMPTY_HL);
  const [candidates, setCandidates] = useState<TraceCandidate[]>([]);
  const [meta, setMeta] = useState<{ confidence: number; latency: number; abstain: boolean } | null>(
    null,
  );
  const [dims, setDims] = useState({ w: 0, h: 0 });
  const [triggering, setTriggering] = useState<string | null>(null);

  // Build Your Brain mode: an interview that grows the graph live. While active,
  // the trace poller is paused so confirmation "blooms" own the highlight.
  const [byb, setByb] = useState(false);
  const bybRef = useRef(false);
  bybRef.current = byb;
  const bloomTimer = useRef<number | null>(null);

  // Build-Your-Brain session telemetry for the reconstruction overlay.
  const [recon, setRecon] = useState<
    { candidates: Candidate[]; confidence: number; latency: number } | null
  >(null);
  const [statements, setStatements] = useState<string[]>([]);
  const [grown, setGrown] = useState({ nodes: 0, edges: 0 });
  const [genStats, setGenStats] = useState({ sum: 0, count: 0 });

  // Memory growth: "after" = full current graph; "start" = sparse first-degree
  // subset. `t` (0 -> 1) is animated by rAF and interpolates the rendered data.
  const [mode, setMode] = useState<"start" | "after">("after");
  const [t, setT] = useState(1);
  const reduceMotion = useReducedMotion();

  const containerRef = useRef<HTMLDivElement>(null);
  const traceSig = useRef<string>("");
  const rafRef = useRef<number | null>(null);
  const tRef = useRef(t);
  tRef.current = t;

  // --- load the graph once ---
  useEffect(() => {
    let alive = true;
    getGraph(PERSON_ID)
      .then((g) => {
        if (!alive) return;
        const nodes: FGNode[] = g.nodes.map((n) => {
          const node: FGNode = {
            id: n.id,
            kind: n.type,
            label: n.label,
            salience: n.salience,
          };
          if (n.type === "user") {
            node.fx = 0; // pin the speaker at the center for a stable layout
            node.fy = 0;
          }
          return node;
        });
        const links: FGLink[] = g.edges.map((e) => ({
          id: e.id,
          source: e.source,
          target: e.target,
          type: e.type,
          weight: e.weight,
          term: (e as { term?: string }).term ?? "",
        }));
        setData({ nodes, links });
      })
      .catch((e) => alive && setError(String(e)));
    return () => {
      alive = false;
    };
  }, []);

  // --- size the canvas to its container ---
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const measure = () => setDims({ w: el.clientWidth, h: el.clientHeight });
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, [data]);

  // --- poll the latest trace; update highlight when it changes ---
  useEffect(() => {
    let alive = true;
    const tick = async () => {
      // Paused during Build Your Brain so confirmation blooms own the highlight.
      if (bybRef.current) return;
      try {
        const res = await fetch("/api/trace/latest");
        const trace = (await res.json()) as Trace;
        if (!alive) return;
        const sig = JSON.stringify([
          trace.anchors ?? [],
          trace.subgraph_node_ids ?? [],
          trace.latency_ms ?? 0,
          trace.confidence ?? 0,
          (trace.candidates ?? []).map((c) => c.text),
        ]);
        if (sig === traceSig.current) return;
        traceSig.current = sig;

        const grounded = new Set<string>();
        (trace.candidates ?? []).forEach((c) =>
          (c.grounded_node_ids ?? []).forEach((id) => grounded.add(id)),
        );
        const anchorIds = new Set(trace.anchors ?? []);
        const subgraphNodeIds = new Set(trace.subgraph_node_ids ?? []);
        setHighlight({
          active: subgraphNodeIds.size > 0 || anchorIds.size > 0,
          anchorIds,
          subgraphNodeIds,
          subgraphEdgeIds: new Set(trace.subgraph_edge_ids ?? []),
          groundedIds: grounded,
        });
        setCandidates(trace.candidates ?? []);
        setMeta({
          confidence: trace.confidence ?? 0,
          latency: trace.latency_ms ?? 0,
          abstain: !!trace.abstain,
        });
      } catch {
        /* keep polling */
      }
    };
    const id = setInterval(tick, POLL_MS);
    tick();
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, []);

  const labelById = useMemo(() => {
    const m = new Map<string, string>();
    data?.nodes.forEach((n) => m.set(n.id, n.label));
    return m;
  }, [data]);

  const runDemo = useCallback(
    async (t: (typeof TRY_IT)[number]) => {
      setTriggering(t.label);
      try {
        await generate({ person_id: PERSON_ID, fragments: t.fragments, context: t.context });
      } catch {
        /* the poller surfaces nothing; ignore */
      } finally {
        setTriggering(null);
      }
    },
    [],
  );

  // --- Build Your Brain: grow the graph from a confirmed answer ---
  // Insert created nodes/edges at their deterministic positions (no relayout, no
  // refetch — existing nodes keep their exact spots) and drive a transient bloom
  // via the existing highlight machinery: new nodes flare (grounded), new +
  // reinforced edges fire, reinforced nodes glow. Clears after a few seconds.
  const handleConfirmed = useCallback((result: ConfirmResponse, answer?: string) => {
    setGrown((g) => ({
      nodes: g.nodes + (result.new_nodes?.length ?? 0),
      edges: g.edges + (result.new_edges?.length ?? 0),
    }));
    if (answer && answer.trim()) setStatements((s) => [...s, answer.trim()]);
    const newNodeIds = (result.new_nodes ?? []).map((n) => n.id);
    const newEdgeIds = (result.new_edges ?? []).map(
      (e) => `${e.source}|${e.type}|${e.target}`,
    );

    setData((prev) => {
      if (!prev) return prev;
      const haveN = new Set(prev.nodes.map((n) => n.id));
      const haveL = new Set(prev.links.map((l) => l.id));
      const addNodes: FGNode[] = (result.new_nodes ?? [])
        .filter((n) => !haveN.has(n.id))
        .map((n) => ({ id: n.id, kind: n.kind, label: n.label, salience: n.salience }));
      const willHave = new Set<string>([...haveN, ...addNodes.map((n) => n.id)]);
      const addLinks: FGLink[] = (result.new_edges ?? [])
        .map((e) => ({
          id: `${e.source}|${e.type}|${e.target}`,
          source: e.source,
          target: e.target,
          type: e.type,
          weight: e.weight,
          term: "",
        }))
        .filter(
          (l) =>
            !haveL.has(l.id) &&
            willHave.has(l.source as string) &&
            willHave.has(l.target as string),
        );
      if (!addNodes.length && !addLinks.length) return prev;
      return { nodes: [...prev.nodes, ...addNodes], links: [...prev.links, ...addLinks] };
    });

    setHighlight({
      active: true,
      anchorIds: new Set(),
      subgraphNodeIds: new Set<string>([...newNodeIds, ...(result.changed_node_ids ?? [])]),
      subgraphEdgeIds: new Set<string>([...newEdgeIds, ...(result.changed_edge_ids ?? [])]),
      groundedIds: new Set<string>(newNodeIds),
    });
    if (bloomTimer.current != null) window.clearTimeout(bloomTimer.current);
    bloomTimer.current = window.setTimeout(() => setHighlight(EMPTY_HL), 4200);
  }, []);

  const handleGenerated = useCallback(
    (info: { candidates: Candidate[]; confidence: number; latency: number }) => {
      setRecon(info);
      setGenStats((g) => ({ sum: g.sum + (info.confidence || 0), count: g.count + 1 }));
    },
    [],
  );

  const enterByb = useCallback(() => {
    setByb(true);
    setMode("after"); // ensure newly-grown (non-core) nodes are visible
    setHighlight(EMPTY_HL); // calm canvas before the first bloom
    setRecon(null);
    setStatements([]);
    setGrown({ nodes: 0, edges: 0 });
    setGenStats({ sum: 0, count: 0 });
  }, []);

  const exitByb = useCallback(() => {
    setByb(false);
    if (bloomTimer.current != null) window.clearTimeout(bloomTimer.current);
    setHighlight(EMPTY_HL);
  }, []);

  useEffect(
    () => () => {
      if (bloomTimer.current != null) window.clearTimeout(bloomTimer.current);
    },
    [],
  );

  const usedKinds = useMemo(
    () => Array.from(new Set(data?.nodes.map((n) => n.kind) ?? [])).sort(),
    [data],
  );

  // Shared row style for the legend's "how to read" lines.
  const legendRow: CSSProperties = {
    display: "flex",
    alignItems: "center",
    gap: 8,
    fontSize: 12,
    color: TEXT_MUTED,
    lineHeight: 1.3,
  };

  // Reconstruction-overlay stats.
  const nodeCount = data?.nodes.length ?? 0;
  const edgeCount = data?.links.length ?? 0;
  const avgConf = genStats.count ? genStats.sum / genStats.count : null;
  const kindCounts = useMemo(() => {
    const m: Record<string, number> = {};
    data?.nodes.forEach((n) => {
      m[n.kind] = (m[n.kind] || 0) + 1;
    });
    return m;
  }, [data]);

  // --- "session start" subset: deterministic first-degree neighborhood of the
  // user (Elena) - the user node plus every node directly linked to them, and
  // every edge incident to the user. That is the sparse "what we knew at the
  // start of the session" graph; the rest is what got "learned". ---
  const core = useMemo(() => {
    const coreNodeIds = new Set<string>();
    const coreEdgeIds = new Set<string>();
    if (!data) return { coreNodeIds, coreEdgeIds };
    const userIds = new Set(data.nodes.filter((n) => n.kind === "user").map((n) => n.id));
    userIds.forEach((id) => coreNodeIds.add(id));
    const ref = (e: string | FGNode) => (typeof e === "string" ? e : e.id);
    for (const l of data.links) {
      const s = ref(l.source);
      const tg = ref(l.target);
      if (userIds.has(s) || userIds.has(tg)) {
        coreEdgeIds.add(l.id);
        coreNodeIds.add(s);
        coreNodeIds.add(tg);
      }
    }
    return { coreNodeIds, coreEdgeIds };
  }, [data]);

  // --- animate `t` toward the target mode (1 = after, 0 = start). Snap under
  // reduced motion; otherwise an eased rAF ramp drives the grow/recede. ---
  useEffect(() => {
    const target = mode === "after" ? 1 : 0;
    if (rafRef.current != null) cancelAnimationFrame(rafRef.current);
    if (reduceMotion) {
      setT(target);
      return;
    }
    const from = tRef.current;
    if (Math.abs(from - target) < 0.001) return;
    const dur = DUR.moment * 2.4 * 1000; // a deliberate, legible consolidation
    const start = performance.now();
    const step = (now: number) => {
      const p = Math.min(1, (now - start) / dur);
      const e = ease(p);
      setT(from + (target - from) * e);
      if (p < 1) rafRef.current = requestAnimationFrame(step);
      else rafRef.current = null;
    };
    rafRef.current = requestAnimationFrame(step);
    return () => {
      if (rafRef.current != null) cancelAnimationFrame(rafRef.current);
    };
  }, [mode, reduceMotion]);

  const growth = useMemo<Growth>(
    () => ({ coreNodeIds: core.coreNodeIds, coreEdgeIds: core.coreEdgeIds, t }),
    [core, t],
  );

  // Caption counts: full graph vs the sparse session-start subset.
  const startCount = core.coreNodeIds.size;
  const fullCount = data?.nodes.length ?? 0;
  const caption =
    mode === "after"
      ? `After learning: ${fullCount} memories, stronger links.`
      : `Session start: ${startCount} memories.`;

  return (
    <div style={{ display: "flex", height: "100%", background: INK, color: TEXT }}>
      {/* Graph canvas — dark viewport so the hologram brain glows (bloom). */}
      <div
        ref={containerRef}
        style={{
          position: "relative",
          flex: 1,
          minWidth: 0,
          background: "radial-gradient(120% 120% at 50% 38%, #0a1724 0%, #05090e 72%)",
        }}
      >
        {data && dims.w > 0 && dims.h > 0 ? (
          <HologramBrain
            data={data}
            width={dims.w}
            height={dims.h}
            highlight={highlight}
            growth={growth}
          />
        ) : (
          <div
            style={{
              display: "grid",
              placeItems: "center",
              height: "100%",
              color: "#8aa0b5",
              fontSize: 14,
            }}
          >
            {error ? `Could not load graph: ${error}` : "Loading memory graph…"}
          </div>
        )}

        {/* Status (top-left) */}
        <div style={overlay("top")}>
          <div style={{ fontSize: 16, fontWeight: 700, color: TEXT }}>Elena · memory graph</div>
          <div style={{ fontSize: 12, color: TEXT_MUTED, marginTop: 2 }}>
            {data ? `${data.nodes.length} nodes · ${data.links.length} edges` : "—"}
            {" · "}
            <span
              style={{
                color: highlight.active ? MIND : TEXT_FAINT,
                fontWeight: 600,
              }}
            >
              {highlight.active ? "firing" : "idle"}
            </span>
          </div>
        </div>

        {/* Memory growth (top-right). */}
        <div
          style={{
            ...CARD_STYLE,
            position: "absolute",
            top: 14,
            right: 14,
            width: 320,
            display: "flex",
            flexDirection: "column",
            gap: 8,
          }}
        >
          <div
            style={{
              fontSize: 10.5,
              letterSpacing: "0.1em",
              textTransform: "uppercase",
              color: TEXT_MUTED,
              fontWeight: 600,
            }}
          >
            Memory growth
          </div>
          <div
            role="radiogroup"
            aria-label="Memory growth stage"
            style={{
              display: "inline-flex",
              padding: 3,
              gap: 3,
              borderRadius: 10,
              background: INK,
              border: `1px solid ${INK_LINE}`,
            }}
          >
            {(
              [
                { key: "start", label: "Session start" },
                { key: "after", label: "After learning" },
              ] as const
            ).map((opt) => {
              const on = mode === opt.key;
              return (
                <button
                  key={opt.key}
                  type="button"
                  role="radio"
                  aria-checked={on}
                  onClick={() => setMode(opt.key)}
                  style={{
                    fontFamily:
                      "ui-monospace, SFMono-Regular, Menlo, monospace",
                    fontSize: 12,
                    padding: "6px 11px",
                    borderRadius: 8,
                    border: `1px solid ${on ? MIND : "transparent"}`,
                    background: on ? MIND_SOFT : "transparent",
                    color: on ? "#075E55" : TEXT_MUTED,
                    fontWeight: on ? 600 : 500,
                    cursor: "pointer",
                    transition: `background ${DUR.fast}s, color ${DUR.fast}s`,
                  }}
                >
                  {opt.label}
                </button>
              );
            })}
          </div>
          <div
            aria-live="polite"
            style={{
              fontSize: 12,
              color: TEXT_MUTED,
              lineHeight: 1.45,
            }}
          >
            {caption}
          </div>
        </div>

        {/* Reconstruction overlay (Build Your Brain) — compact, locked to the
            bottom-right so the brain stays centered; scrollable so it all fits. */}
        {byb && (
          <div
            className="scroll-ink"
            style={{
              ...CARD_STYLE,
              position: "absolute",
              bottom: 14,
              right: 14,
              width: PANEL_W,
              height: PANEL_H,
              padding: "9px 11px",
              display: "flex",
              flexDirection: "column",
              gap: 8,
              overflowY: "auto",
            }}
          >
            <div>
              <div style={{ fontSize: 13, fontWeight: 700, color: TEXT }}>Reconstruction</div>
              <div style={{ fontSize: 11, color: TEXT_MUTED, marginTop: 1 }}>
                Live as you build your brain.
              </div>
            </div>

            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {recon && <Pill label="confidence" value={recon.confidence.toFixed(2)} />}
              {recon && <Pill label="latency" value={`${recon.latency} ms`} />}
              <Pill label="answers" value={String(statements.length)} />
              {avgConf != null && <Pill label="avg conf" value={avgConf.toFixed(2)} />}
            </div>

            <div
              style={{
                display: "grid",
                gridTemplateColumns: "1fr 1fr",
                gap: "6px 12px",
                fontSize: 11.5,
              }}
            >
              <Stat label="memories" value={nodeCount} />
              <Stat label="links" value={edgeCount} />
              <Stat label="grown" value={`+${grown.nodes}`} accent />
              <Stat label="new links" value={`+${grown.edges}`} accent />
            </div>

            {usedKinds.length > 0 && (
              <div
                style={{
                  display: "flex",
                  flexWrap: "wrap",
                  gap: "5px 12px",
                  fontSize: 11,
                  color: TEXT_MUTED,
                  paddingTop: 8,
                  borderTop: `1px solid ${INK_LINE}`,
                }}
              >
                {["contact", "routine", "place", "topic", "preference"]
                  .filter((k) => kindCounts[k])
                  .map((k) => (
                    <span key={k} style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
                      <span
                        style={{
                          width: 8,
                          height: 8,
                          borderRadius: "50%",
                          background: KIND_COLORS[k] ?? "#6B7787",
                        }}
                      />
                      {k} <strong style={{ color: TEXT }}>{kindCounts[k]}</strong>
                    </span>
                  ))}
              </div>
            )}

            {recon && recon.candidates.length > 0 && (
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                <div
                  style={{
                    fontSize: 10.5,
                    letterSpacing: "0.1em",
                    textTransform: "uppercase",
                    color: TEXT_MUTED,
                    fontWeight: 600,
                  }}
                >
                  Latest options
                </div>
                {recon.candidates.map((c, i) => (
                  <div
                    key={i}
                    style={{
                      border: `1px solid ${INK_LINE}`,
                      background: INK,
                      borderRadius: 10,
                      padding: "8px 10px",
                    }}
                  >
                    <div style={{ fontSize: 13.5, lineHeight: 1.4, color: TEXT }}>{c.text}</div>
                    <div style={{ fontSize: 10.5, color: TEXT_MUTED, margin: "4px 0 6px" }}>
                      {c.register} · {c.length_label}
                    </div>
                    {(c.grounded_node_ids ?? []).length > 0 && (
                      <div style={{ display: "flex", flexWrap: "wrap", gap: 5 }}>
                        {(c.grounded_node_ids ?? []).map((id) => (
                          <span
                            key={id}
                            title={id}
                            style={{
                              fontSize: 10.5,
                              padding: "2px 7px",
                              borderRadius: 999,
                              background: VOICE_SOFT,
                              color: VOICE_DEEP,
                              border: `1px solid ${VOICE}`,
                            }}
                          >
                            {labelById.get(id) ?? id}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}

            {statements.length > 0 && (
              <div
                style={{
                  display: "flex",
                  flexDirection: "column",
                  gap: 6,
                  paddingTop: 8,
                  borderTop: `1px solid ${INK_LINE}`,
                }}
              >
                <div
                  style={{
                    fontSize: 10.5,
                    letterSpacing: "0.1em",
                    textTransform: "uppercase",
                    color: TEXT_MUTED,
                    fontWeight: 600,
                  }}
                >
                  Statements you’ve made
                </div>
                {statements
                  .slice()
                  .reverse()
                  .map((s, i) => (
                    <div
                      key={i}
                      style={{ fontSize: 12.5, color: TEXT, lineHeight: 1.4, display: "flex", gap: 6 }}
                    >
                      <span style={{ color: MIND, fontWeight: 700 }}>›</span>
                      <span>{s}</span>
                    </div>
                  ))}
              </div>
            )}

            {!recon && statements.length === 0 && (
              <div style={{ fontSize: 12, color: TEXT_MUTED, lineHeight: 1.45 }}>
                Answer a question to see your reconstruction and watch the graph grow.
              </div>
            )}
          </div>
        )}

        {/* Legend (bottom-left) — same size as the reconstruction card. */}
        <div
          style={{
            ...overlay("bottom"),
            display: "flex",
            flexDirection: "column",
            gap: 8,
            width: PANEL_W,
            minHeight: PANEL_H,
          }}
        >
          <div
            style={{
              fontSize: 10.5,
              letterSpacing: "0.1em",
              textTransform: "uppercase",
              color: TEXT_MUTED,
              fontWeight: 600,
            }}
          >
            Legend
          </div>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "6px 12px" }}>
            {usedKinds.map((k) => (
              <span
                key={k}
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 7,
                  fontSize: 12.5,
                  color: TEXT,
                }}
              >
                <span
                  style={{
                    width: 12,
                    height: 12,
                    borderRadius: "50%",
                    background: KIND_COLORS[k] ?? "#6B7787",
                    border: "1px solid rgba(22,26,33,0.14)",
                  }}
                />
                {k}
              </span>
            ))}
          </div>

          {/* How to read the brain — fills the matched height with useful info. */}
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              gap: 7,
              paddingTop: 8,
              marginTop: "auto",
              borderTop: `1px solid ${INK_LINE}`,
            }}
          >
            <span style={legendRow}>
              <span
                style={{
                  width: 11,
                  height: 11,
                  borderRadius: "50%",
                  background: MIND,
                  boxShadow: `0 0 0 3px ${MIND_SOFT}`,
                  flexShrink: 0,
                }}
              />
              Each dot is a memory — bigger means more important.
            </span>
            <span style={legendRow}>
              <span
                style={{ width: 16, height: 0, borderTop: "2px solid #2bd6c6", flexShrink: 0 }}
              />
              Lines connect related memories.
            </span>
            <span style={legendRow}>
              <span
                style={{ width: 16, height: 0, borderTop: `2px solid ${VOICE}`, flexShrink: 0 }}
              />
              Firing pulse: a retrieved memory path.
            </span>
            <span style={legendRow}>
              <span
                style={{
                  width: 11,
                  height: 11,
                  borderRadius: "50%",
                  background: VOICE,
                  boxShadow: `0 0 8px ${VOICE}`,
                  flexShrink: 0,
                }}
              />
              Bloom: a new memory forms as you answer.
            </span>
          </div>
        </div>
      </div>

      {/* Right side: Build Your Brain panel (graph stays the canvas on the left),
          or the Reconstruction panel otherwise. */}
      {byb ? (
        <div
          style={{
            width: "clamp(420px, 40vw, 560px)",
            flexShrink: 0,
            height: "100%",
            borderLeft: `1px solid ${INK_LINE}`,
          }}
        >
          <BuildBrainPanel
            personId={PERSON_ID}
            onConfirmed={handleConfirmed}
            onGenerated={handleGenerated}
            onExit={exitByb}
          />
        </div>
      ) : (
      <aside
        style={{
          width: 340,
          flexShrink: 0,
          borderLeft: `1px solid ${INK_LINE}`,
          background: INK_RAISED,
          padding: "18px 16px",
          overflowY: "auto",
        }}
      >
        <button
          type="button"
          onClick={enterByb}
          disabled={byb}
          style={{
            width: "100%",
            display: "inline-flex",
            alignItems: "center",
            justifyContent: "center",
            gap: 8,
            padding: "11px 14px",
            marginBottom: 16,
            borderRadius: 10,
            border: `1px solid ${byb ? MIND : "rgba(12,130,118,0.45)"}`,
            background: byb ? MIND_SOFT : MIND,
            color: byb ? "#075E55" : "#FFFFFF",
            fontSize: 14,
            fontWeight: 600,
            cursor: byb ? "default" : "pointer",
          }}
        >
          ✦ {byb ? "Building your brain…" : "Build your brain"}
        </button>

        <h2 style={{ margin: "0 0 4px", fontSize: 18, color: TEXT }}>Reconstruction</h2>
        <p style={{ margin: "0 0 14px", fontSize: 12.5, color: TEXT_MUTED, lineHeight: 1.5 }}>
          The candidates from the latest <code>/generate</code>, grounded in the lit-up nodes.
        </p>

        {meta && (
          <div style={{ display: "flex", gap: 8, marginBottom: 14, flexWrap: "wrap" }}>
            <Pill label="confidence" value={meta.confidence.toFixed(2)} />
            <Pill label="latency" value={`${meta.latency} ms`} />
            {meta.abstain && <Pill label="abstain" value="ask for a word" warn />}
          </div>
        )}

        {!meta && (
          <div style={{ fontSize: 13, color: TEXT_MUTED, marginBottom: 16 }}>
            No reconstruction yet. Trigger one below (or from the Conversation view).
          </div>
        )}

        {candidates.map((c, i) => (
          <div
            key={i}
            style={{
              border: `1px solid ${INK_LINE}`,
              background: INK,
              borderRadius: 12,
              padding: "10px 12px",
              marginBottom: 10,
            }}
          >
            <div style={{ fontSize: 15, lineHeight: 1.4, color: TEXT }}>{c.text}</div>
            <div style={{ fontSize: 11, color: TEXT_MUTED, margin: "6px 0 8px" }}>
              {c.register} · {c.length_label}
            </div>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 6 }}>
              {(c.grounded_node_ids ?? []).map((id) => (
                <span
                  key={id}
                  title={id}
                  style={{
                    fontSize: 11,
                    padding: "2px 8px",
                    borderRadius: 999,
                    background: VOICE_SOFT,
                    color: VOICE_DEEP,
                    border: `1px solid ${VOICE}`,
                  }}
                >
                  {labelById.get(id) ?? id}
                </span>
              ))}
            </div>
          </div>
        ))}

        <h3
          style={{
            fontSize: 11,
            letterSpacing: "0.1em",
            textTransform: "uppercase",
            color: TEXT_MUTED,
            fontWeight: 600,
            margin: "18px 0 8px",
          }}
        >
          Try it
        </h3>
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          {TRY_IT.map((t) => (
            <button
              key={t.label}
              type="button"
              disabled={triggering !== null}
              onClick={() => runDemo(t)}
              style={{
                textAlign: "left",
                padding: "9px 12px",
                borderRadius: 10,
                border: `1px solid ${triggering === t.label ? MIND : INK_LINE}`,
                background: triggering === t.label ? MIND_SOFT : INK_RAISED,
                color: TEXT,
                fontSize: 13,
                cursor: triggering ? "wait" : "pointer",
              }}
            >
              {triggering === t.label ? "thinking…" : t.label}
            </button>
          ))}
        </div>
      </aside>
      )}
    </div>
  );
}

// Evaluate the shared EASE_OUT cubic-bezier (0.16, 1, 0.3, 1) at progress p.
// Newton-step solve for the curve parameter, then read its y. Keeps the growth
// ramp on the same easing language as the rest of the app (lib/motion).
function ease(p: number): number {
  const [x1, y1, x2, y2] = EASE_OUT;
  if (p <= 0) return 0;
  if (p >= 1) return 1;
  const cx = (u: number) =>
    ((1 - u) ** 2 * 3 * u * x1) + ((1 - u) * 3 * u * u * x2) + u ** 3;
  const cy = (u: number) =>
    ((1 - u) ** 2 * 3 * u * y1) + ((1 - u) * 3 * u * u * y2) + u ** 3;
  let u = p;
  for (let i = 0; i < 6; i++) {
    const x = cx(u) - p;
    const dx =
      3 * (1 - u) ** 2 * x1 +
      6 * (1 - u) * u * (x2 - x1) +
      3 * u * u * (1 - x2);
    if (Math.abs(dx) < 1e-5) break;
    u -= x / dx;
    u = Math.min(1, Math.max(0, u));
  }
  return cy(u);
}

function overlay(pos: "top" | "bottom"): CSSProperties {
  return {
    position: "absolute",
    left: 14,
    [pos]: 14,
    padding: "10px 13px",
    borderRadius: 12,
    background: "rgba(255,255,255,0.82)",
    backdropFilter: "blur(8px)",
    border: `1px solid ${INK_LINE}`,
    boxShadow: "0 1px 2px 0 rgba(22,26,33,0.04), 0 10px 24px -14px rgba(22,26,33,0.12)",
  };
}

function Stat({
  label,
  value,
  accent,
}: {
  label: string;
  value: string | number;
  accent?: boolean;
}) {
  return (
    <span style={{ display: "inline-flex", alignItems: "baseline", gap: 5 }}>
      <span style={{ color: TEXT_MUTED }}>{label}</span>
      <strong style={{ color: accent ? "#075E55" : TEXT, fontVariantNumeric: "tabular-nums" }}>
        {value}
      </strong>
    </span>
  );
}

function Pill({ label, value, warn }: { label: string; value: string; warn?: boolean }) {
  return (
    <span
      style={{
        fontSize: 11,
        padding: "3px 9px",
        borderRadius: 999,
        background: warn ? "#FCE9E3" : MIND_SOFT,
        color: warn ? VOICE_DEEP : MIND,
        border: `1px solid ${warn ? VOICE : "rgba(12,130,118,0.35)"}`,
      }}
    >
      {label}: <strong style={{ color: warn ? VOICE_DEEP : "#075E55" }}>{value}</strong>
    </span>
  );
}
