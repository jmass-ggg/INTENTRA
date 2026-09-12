// ForceGraph — canvas renderer over react-force-graph-2d (Phase 6, LIGHT theme).
//
// Metaphor: neural ACTIVATION expressed through behavior, not a brain shape and
// not neon glow. When a trace is active, warm coral particles fire along the
// retrieved edges (anchor -> grounded) - that is the neuron firing. The layout
// stays force-directed so proximity keeps meaning relatedness.
//
// Two visual states driven by `highlight.active`:
//   idle      - calm; clean filled nodes with a soft ring, labels for the user
//               node + on hover. Link weight drives width/opacity (reinforcement).
//   retrieved - non-subgraph nodes/links dimmed; the retrieved subgraph at full
//               strength with always-on labels; anchors get a dark ring; grounded
//               nodes are emphasized most (a warm coral ring). Coral particles
//               flow along the retrieved edges. Disabled under reduced motion.

import { useEffect, useRef, useState } from "react";
import { useReducedMotion } from "framer-motion";
import ForceGraph2D from "react-force-graph-2d";
// d3-force-3d is the same force lib react-force-graph-2d uses internally, so a
// collision force from it composes cleanly and keeps nodes/labels from crowding.
import { forceCollide } from "d3-force-3d";

// Kind palette tuned for a LIGHT canvas (#F5F7FA): saturated, mid-dark fills so
// every swatch reads with contrast against the off-white and carries a legible
// dark label below it. (No pastels-on-white, no neon.)
export const KIND_COLORS: Record<string, string> = {
  user: "#D98A00", // deep amber - the speaker, centered + primary
  contact: "#D6456B", // rose
  topic: "#0C8276", // teal (the machine's mind tone)
  routine: "#2F6BD8", // blue
  preference: "#7C4FE0", // violet
  need: "#D9591F", // warm orange
  place: "#3E9E5C", // green
  phrase: "#C2469E", // magenta-pink
  event: "#8A8A1E", // olive
};
const DEFAULT_COLOR = "#6B7787";

// Light-theme constants.
const BG = "#F5F7FA"; // app canvas (Tailwind `ink`)
const VOICE = "#E14826"; // THE HUMAN coral - the firing particle color
const LINK_IDLE = "#C2CCDA"; // calm neutral pathways
const LINK_RETRIEVED = "#0C8276"; // teal - the lit pathway under retrieval
const LABEL_TEXT = "#161A21"; // near-black, AA on the light canvas
const LABEL_PILL = "rgba(255,255,255,0.86)"; // light pill behind labels
const RING_SOFT = "rgba(22,26,33,0.14)"; // subtle ring on every node
const ANCHOR_RING = "#161A21"; // dark anchor ring (high contrast on light)

export interface FGNode {
  id: string;
  kind: string;
  label: string;
  salience: number;
  x?: number;
  y?: number;
  fx?: number;
  fy?: number;
}
export interface FGLink {
  id: string;
  source: string | FGNode;
  target: string | FGNode;
  type: string;
  weight: number;
  term?: string;
}
export interface GraphData {
  nodes: FGNode[];
  links: FGLink[];
}
export interface Highlight {
  active: boolean;
  anchorIds: Set<string>;
  subgraphNodeIds: Set<string>;
  subgraphEdgeIds: Set<string>;
  groundedIds: Set<string>;
}

// Memory growth (the learning loop). `coreNodeIds` / `coreEdgeIds` are the
// sparse "session start" subset that is fully present at t=0. Everything else
// is a "learned" node/edge that grows in as `t` goes 0 -> 1. Core edges also
// thicken from a hint of their weight toward their full weight-scaled width.
// `t` is interpolated by the parent (rAF / snapped under reduced motion).
export interface Growth {
  coreNodeIds: Set<string>;
  coreEdgeIds: Set<string>;
  t: number; // 0 = session start, 1 = after learning
}

function nodeRadius(n: FGNode): number {
  const base = n.kind === "user" ? 11 : 5.5;
  const s = Math.min(2, Math.max(0.4, n.salience ?? 1));
  return base * (0.82 + 0.3 * s);
}

// Gentle breathing used only on retrieved rings (subtle, not flashing).
const pulse = () => 0.5 + 0.5 * Math.sin(performance.now() / 520);

export default function ForceGraph({
  data,
  width,
  height,
  highlight,
  growth,
}: {
  data: GraphData;
  width: number;
  height: number;
  highlight: Highlight;
  growth?: Growth;
}) {
  const fgRef = useRef<any>(null);
  const [hovered, setHovered] = useState<string | null>(null);
  const fitted = useRef(false);
  const reduceMotion = useReducedMotion();

  // Configure forces once for a stable, readable, well-spread layout.
  useEffect(() => {
    const fg = fgRef.current;
    if (!fg) return;
    fg.d3Force("charge")?.strength(-320).distanceMax(420);
    fg.d3Force("link")?.distance(78).strength(0.32);
    if (fg.d3Force("center")) fg.d3Force("center").strength(0.04);
    // Keep nodes (and therefore their labels) from overlapping.
    fg.d3Force("collide", forceCollide((n: FGNode) => nodeRadius(n) + 18).iterations(2));
    fitted.current = false;
    fg.d3ReheatSimulation?.();
  }, [data]);

  const hi = highlight.active;
  // Particles fire only while a trace is active and motion is allowed.
  const particlesOn = hi && !reduceMotion;

  // Growth membership. When no growth prop is supplied every node/edge is
  // treated as "core" so behavior is identical to before this feature.
  const tg = growth ? growth.t : 1;
  const isCoreNode = (id: string) => (growth ? growth.coreNodeIds.has(id) : true);
  const isCoreEdge = (id: string) => (growth ? growth.coreEdgeIds.has(id) : true);
  // Per-element growth factor (0..1): core elements are always 1; learned ones
  // ramp with t. smoothstep keeps the fade/scale calm rather than linear.
  const grow = (core: boolean) => (core ? 1 : smoothstep(tg));

  const nodeCanvas = (node: any, ctx: CanvasRenderingContext2D, scale: number) => {
    const n = node as FGNode;
    const color = KIND_COLORS[n.kind] ?? DEFAULT_COLOR;
    // Growth: learned nodes fade + scale in (0.4 -> full radius) as t rises.
    const g = grow(isCoreNode(n.id));
    if (g <= 0.001) return; // not yet learned: skip entirely at session start
    const r = nodeRadius(n) * (0.4 + 0.6 * g);
    const isUser = n.kind === "user";
    const inSub = highlight.subgraphNodeIds.has(n.id);
    const isAnchor = highlight.anchorIds.has(n.id);
    const isGrounded = highlight.groundedIds.has(n.id);
    const lit = inSub || isAnchor || isGrounded;
    const p = reduceMotion ? 0.5 : pulse();

    // Opacity: full when idle or lit; clearly dimmed (but still visible) when a
    // retrieval is active and this node is outside the subgraph.
    let alpha: number;
    if (!hi) alpha = 1;
    else if (lit) alpha = 1;
    else alpha = 0.22;
    alpha *= g; // learned nodes fade in with growth

    // Clean filled circle.
    ctx.save();
    ctx.globalAlpha = alpha;
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(n.x!, n.y!, r, 0, 2 * Math.PI);
    ctx.fill();

    // Subtle ring on every node (separates from the light canvas + neighbors).
    ctx.globalAlpha = alpha * (isUser ? 0.5 : 0.35);
    ctx.lineWidth = isUser ? 2 : 1;
    ctx.strokeStyle = isUser ? "rgba(255,255,255,0.9)" : RING_SOFT;
    ctx.beginPath();
    ctx.arc(n.x!, n.y!, r + (isUser ? 1.5 : 1), 0, 2 * Math.PI);
    ctx.stroke();
    ctx.restore();

    // Anchor: distinct dark ring (high contrast on the light canvas).
    if (hi && isAnchor) {
      ctx.save();
      ctx.globalAlpha = 0.9;
      ctx.lineWidth = 1.6 + 0.8 * p;
      ctx.strokeStyle = ANCHOR_RING;
      ctx.beginPath();
      ctx.arc(n.x!, n.y!, r + 3.5, 0, 2 * Math.PI);
      ctx.stroke();
      ctx.restore();
    }
    // Grounded: strongest emphasis - a warm coral breathing ring.
    if (hi && isGrounded) {
      ctx.save();
      ctx.globalAlpha = 0.55 + 0.4 * p;
      ctx.lineWidth = 2.6;
      ctx.strokeStyle = VOICE;
      ctx.beginPath();
      ctx.arc(n.x!, n.y!, r + 6, 0, 2 * Math.PI);
      ctx.stroke();
      ctx.restore();
    }

    // Labels: always for highlighted/hovered; the user node when idle; hover-only
    // for everyone else (keeps the idle view uncluttered). Dark text on a light
    // pill - legible on the light canvas.
    const showLabel = hovered === n.id || (hi && lit) || (!hi && isUser);
    if (showLabel) {
      const fontSize = (isUser ? 13 : 12) / scale;
      ctx.font = `600 ${fontSize}px ui-sans-serif, system-ui, -apple-system, sans-serif`;
      ctx.textAlign = "center";
      ctx.textBaseline = "top";
      const tw = ctx.measureText(n.label).width;
      const ty = n.y! + r + 3 / scale;
      const padX = 4 / scale;
      const padY = 2 / scale;
      const labelAlpha = (!hi || lit || hovered === n.id ? 1 : 0.4) * g;

      ctx.save();
      ctx.globalAlpha = labelAlpha;
      // Light pill behind the label for legibility over nodes/edges.
      ctx.fillStyle = LABEL_PILL;
      const pillR = 4 / scale;
      roundRect(
        ctx,
        n.x! - tw / 2 - padX,
        ty - padY,
        tw + padX * 2,
        fontSize + padY * 2,
        pillR,
      );
      ctx.fill();
      ctx.strokeStyle = "rgba(22,26,33,0.08)";
      ctx.lineWidth = 1 / scale;
      ctx.stroke();
      ctx.fillStyle = LABEL_TEXT;
      ctx.fillText(n.label, n.x!, ty);
      ctx.restore();
    }
  };

  const nodePointerArea = (node: any, color: string, ctx: CanvasRenderingContext2D) => {
    const n = node as FGNode;
    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(n.x!, n.y!, nodeRadius(n) + 4, 0, 2 * Math.PI);
    ctx.fill();
  };

  const linkCanvas = (link: any, ctx: CanvasRenderingContext2D) => {
    const s = link.source;
    const t = link.target;
    if (!s || !t || typeof s !== "object" || typeof t !== "object") return;
    const inSub = highlight.subgraphEdgeIds.has(link.id);
    const w = Number(link.weight ?? 1);
    // Reinforcement: stronger memories = stronger connections (width + opacity).
    const ww = Math.min(4, Math.max(0.4, w));
    const fullWidth = 0.5 + ww * 0.45;

    // Growth: learned edges fade in; core edges thicken from a thin hint toward
    // their full weight-scaled width as t rises (memory consolidation). At
    // session start (t=0) learned edges are absent and core edges are thin.
    const core = isCoreEdge(link.id);
    const g = grow(core);
    if (g <= 0.001) return; // learned edge not yet present at session start
    // Reinforcement of the persistent core edges: width animates with t.
    const tw = core ? 0.35 + 0.65 * smoothstep(tg) : 1;
    const baseWidth = fullWidth * tw;
    const weightAlpha = (0.3 + (ww / 4) * 0.4) * (core ? 1 : g); // 0.3 .. 0.7

    let alpha: number;
    let width = baseWidth;
    let color = LINK_IDLE;
    ctx.save();
    if (!hi) {
      alpha = weightAlpha;
    } else if (inSub) {
      width = baseWidth * 2.1;
      color = LINK_RETRIEVED;
      alpha = 0.9 * (core ? 1 : g);
    } else {
      alpha = 0.08 * (core ? 1 : g);
    }
    ctx.globalAlpha = alpha;
    ctx.strokeStyle = color;
    ctx.lineWidth = width;
    ctx.lineCap = "round";
    ctx.beginPath();
    ctx.moveTo(s.x, s.y);
    ctx.lineTo(t.x, t.y);
    ctx.stroke();
    ctx.restore();
  };

  // Particle config: only the retrieved edges fire, with warm coral particles.
  const linkParticles = (link: any): number => {
    if (!particlesOn) return 0;
    return highlight.subgraphEdgeIds.has(link.id) ? 4 : 0;
  };
  const linkParticleWidth = (link: any): number => {
    if (!particlesOn) return 0;
    const w = Number(link.weight ?? 1);
    return highlight.subgraphEdgeIds.has(link.id) ? 2.2 + Math.min(2, w) * 0.6 : 0;
  };

  return (
    <ForceGraph2D
      ref={fgRef}
      graphData={data}
      width={width}
      height={height}
      backgroundColor={BG}
      nodeId="id"
      // Keep redraw running while a retrieval is highlighted (rings breathe and
      // particles fly) or while the growth transition is mid-flight; pause when
      // fully idle and growth is settled (t at 0 or 1) for performance.
      autoPauseRedraw={!hi && (tg <= 0.001 || tg >= 0.999)}
      cooldownTicks={220}
      warmupTicks={60}
      onEngineStop={() => {
        if (!fitted.current) {
          fitted.current = true;
          const fg = fgRef.current;
          fg?.zoomToFit(600, 38);
          // A second fit after the layout fully settles avoids a premature frame.
          setTimeout(() => fg?.zoomToFit(500, 38), 700);
        }
      }}
      onNodeHover={(n: any) => setHovered(n ? n.id : null)}
      nodeCanvasObjectMode={() => "replace"}
      nodeCanvasObject={nodeCanvas}
      nodePointerAreaPaint={nodePointerArea}
      linkCanvasObjectMode={() => "replace"}
      linkCanvasObject={linkCanvas}
      // Built-in directional particles = the neuron firing along retrieved edges.
      linkDirectionalParticles={linkParticles}
      linkDirectionalParticleSpeed={0.012}
      linkDirectionalParticleWidth={linkParticleWidth}
      linkDirectionalParticleColor={() => VOICE}
    />
  );
}

// Smooth 0..1 ramp (Hermite) so growth fade/scale eases in/out, not linear.
function smoothstep(x: number): number {
  const c = Math.min(1, Math.max(0, x));
  return c * c * (3 - 2 * c);
}

// Small rounded-rect helper for label pills (scale-aware radius passed in).
function roundRect(
  ctx: CanvasRenderingContext2D,
  x: number,
  y: number,
  w: number,
  h: number,
  r: number,
) {
  const rr = Math.min(r, h / 2, w / 2);
  ctx.beginPath();
  ctx.moveTo(x + rr, y);
  ctx.arcTo(x + w, y, x + w, y + h, rr);
  ctx.arcTo(x + w, y + h, x, y + h, rr);
  ctx.arcTo(x, y + h, x, y, rr);
  ctx.arcTo(x, y, x + w, y, rr);
  ctx.closePath();
}
