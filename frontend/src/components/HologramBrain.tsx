// HologramBrain — a 3D holographic "brain" visualization of the Personal
// Knowledge Graph (WebGL / three.js). Drop-in replacement for <ForceGraph>:
// same props (data, width, height, highlight, growth).
//
// What it draws:
//   • a procedural brain-shaped point cloud (two hemispheres + median fissure +
//     gyri wrinkles) — generated in-code, NO external 3D asset, so it stays
//     offline/on-device and small.
//   • the PKG nodes as glowing neurons (Elena pinned at center), colored by kind
//     (KIND_COLORS), edges as faint synapses.
//   • when a /generate trace arrives, the retrieved subgraph "fires": grounded
//     nodes flare, and a coral pulse travels the retrieved edges (source→target).
//   • the "memory growth" slider fades non-core nodes/edges via a single uniform.
//
// Performance (the "no lag" budget):
//   • capped devicePixelRatio, half-res bloom, additive points (no shadows).
//   • zero per-frame allocations; only uniform scalars are written each frame.
//   • rAF pauses on tab-hidden and on unmount; everything is disposed on cleanup.

import { useEffect, useRef } from "react";
import * as THREE from "three";
import { EffectComposer } from "three/examples/jsm/postprocessing/EffectComposer.js";
import { RenderPass } from "three/examples/jsm/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/examples/jsm/postprocessing/UnrealBloomPass.js";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";
import {
  KIND_COLORS,
  type GraphData,
  type Highlight,
  type Growth,
  type FGNode,
  type FGLink,
} from "./ForceGraph";

interface Props {
  data: GraphData;
  width: number;
  height: number;
  highlight: Highlight;
  growth: Growth;
}

// Brain half-axes (the envelope the cloud + nodes live inside). Elongated
// front-back (z) and flatter top-bottom (y) than a sphere → a cerebrum profile.
const AX = 1.72; // half width  (left↔right)
const AY = 1.6; // half height (down↔up)
const AZ = 2.18; // half length (back↔front)
const BRAIN_POINTS = 7400; // dense enough that the folded surface reads clearly

// --- deterministic PRNG so node/cloud layout is stable across renders --------
function hashStr(s: string): number {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) h = Math.imul(h ^ s.charCodeAt(i), 16777619);
  return h >>> 0;
}
function rng(seed: number): () => number {
  let t = seed >>> 0;
  return () => {
    t += 0x6d2b79f5;
    let x = Math.imul(t ^ (t >>> 15), t | 1);
    x ^= x + Math.imul(x ^ (x >>> 7), x | 61);
    return ((x ^ (x >>> 14)) >>> 0) / 4294967296;
  };
}

// --- 3D value noise + ridged fBm: the gyri/sulci folding of the cortex -------
function hash3(x: number, y: number, z: number): number {
  let n = Math.imul(x | 0, 374761393) + Math.imul(y | 0, 668265263) + Math.imul(z | 0, 1442695040);
  n = Math.imul(n ^ (n >>> 13), 1274126177);
  return ((n ^ (n >>> 16)) >>> 0) / 4294967296;
}
function vnoise(x: number, y: number, z: number): number {
  const xi = Math.floor(x), yi = Math.floor(y), zi = Math.floor(z);
  const xf = x - xi, yf = y - yi, zf = z - zi;
  const u = xf * xf * (3 - 2 * xf), v = yf * yf * (3 - 2 * yf), w = zf * zf * (3 - 2 * zf);
  const L = (a: number, b: number, t: number) => a + (b - a) * t;
  const c = (dx: number, dy: number, dz: number) => hash3(xi + dx, yi + dy, zi + dz);
  const x00 = L(c(0, 0, 0), c(1, 0, 0), u), x10 = L(c(0, 1, 0), c(1, 1, 0), u);
  const x01 = L(c(0, 0, 1), c(1, 0, 1), u), x11 = L(c(0, 1, 1), c(1, 1, 1), u);
  return L(L(x00, x10, v), L(x01, x11, v), w);
}
// Ridged fBm in [0,1]: sharp ridges (gyri) separated by grooves (sulci).
function ridged(x: number, y: number, z: number): number {
  let amp = 0.5, f = 1, sum = 0, norm = 0;
  for (let o = 0; o < 4; o++) {
    const r = 1 - Math.abs(vnoise(x * f, y * f, z * f) * 2 - 1);
    sum += r * r * amp;
    norm += amp;
    amp *= 0.5;
    f *= 2.15;
  }
  return sum / norm;
}

// Place a node deterministically inside the brain volume. The user (speaker)
// sits at the exact center; everyone else is scattered through the volume by a
// stable hash of their id, biased toward the surface so connections arc.
function nodePosition(node: FGNode): THREE.Vector3 {
  if (node.kind === "user") return new THREE.Vector3(0, 0, 0);
  const r = rng(hashStr(node.id));
  const phi = r() * Math.PI * 2;
  const u = r() * 2 - 1;
  const s = Math.sqrt(1 - u * u);
  const rad = 0.42 + r() * 0.5; // 0.42..0.92 of the envelope
  return new THREE.Vector3(s * Math.cos(phi) * AX * rad, u * AY * rad, s * Math.sin(phi) * AZ * rad);
}

// Build the brain point cloud: a folded cerebrum (with a midline fissure and
// flattened underside) plus a small, tightly-foliated cerebellum at the back.
// Returns positions, a per-point random (flicker) and the fold value 0..1
// (ridge intensity) so the shader can brighten gyri and dim sulci.
function buildBrainCloud(): { positions: Float32Array; rand: Float32Array; fold: Float32Array } {
  const positions = new Float32Array(BRAIN_POINTS * 3);
  const rand = new Float32Array(BRAIN_POINTS);
  const fold = new Float32Array(BRAIN_POINTS);
  const r = rng(0x9e3779b9);
  const nCereb = Math.floor(BRAIN_POINTS * 0.13);
  for (let i = 0; i < BRAIN_POINTS; i++) {
    // Uniform direction on the sphere.
    const u0 = r() * 2 - 1;
    const phi = r() * Math.PI * 2;
    const s0 = Math.sqrt(1 - u0 * u0);
    let nx = s0 * Math.cos(phi);
    let ny = u0;
    let nz = s0 * Math.sin(phi);

    if (i < nCereb) {
      // --- cerebellum: small flattened ball at posterior-inferior, tight folds.
      const tight = 1 + 0.07 * Math.sin(ny * 30); // fine parallel foliation
      const g = 0.55 + 0.45 * Math.abs(Math.sin(ny * 30));
      positions[i * 3] = nx * 0.62 * AX * 0.6 * tight;
      positions[i * 3 + 1] = -1.0 * AY * 0.52 + ny * 0.5 * AY * 0.46 * tight;
      positions[i * 3 + 2] = -0.92 * AZ * 0.62 + nz * 0.5 * AZ * 0.5 * tight;
      rand[i] = r();
      fold[i] = g;
      continue;
    }

    // --- cerebrum ---------------------------------------------------------
    if (ny < 0) ny *= 0.72; // flatten the underside
    nx *= 1 - 0.18 * Math.pow(Math.abs(nz), 3); // taper the frontal/occipital poles
    // Convolution: ridged fBm with a little domain warp → worm-like gyri.
    const warp = 0.3 * vnoise(nx * 2 + 11, ny * 2 + 3, nz * 2 + 7);
    const g = ridged(nx * 3.0 + warp, ny * 3.0 + warp, nz * 3.0 + warp);
    let rad = 1 + 0.22 * (g - 0.5) * 2; // ±0.22 folds (visible gyri)
    rad += -0.18 * Math.exp(-(nx * nx) / 0.006); // deep midline longitudinal fissure
    rad *= 1 - Math.pow(r(), 2) * 0.05; // thin shell, slight scatter
    if (Math.abs(nx) < 0.03) nx += (nx >= 0 ? 1 : -1) * 0.03; // keep the seam open
    positions[i * 3] = nx * AX * rad;
    positions[i * 3 + 1] = ny * AY * rad;
    positions[i * 3 + 2] = nz * AZ * rad;
    rand[i] = r();
    fold[i] = g;
  }
  return { positions, rand, fold };
}

function colorOf(kind: string): THREE.Color {
  return new THREE.Color(KIND_COLORS[kind] ?? "#6B7787");
}

const linkEnd = (e: string | FGNode): string => (typeof e === "string" ? e : e.id);

export default function HologramBrain({ data, width, height, highlight, growth }: Props) {
  const mountRef = useRef<HTMLDivElement>(null);

  // three.js objects that persist for the component's life.
  const rendererRef = useRef<THREE.WebGLRenderer | null>(null);
  const composerRef = useRef<EffectComposer | null>(null);
  const cameraRef = useRef<THREE.PerspectiveCamera | null>(null);
  const groupRef = useRef<THREE.Group | null>(null);

  // Rebuildable graph objects + the buffers we mutate on highlight changes.
  const nodeObjRef = useRef<THREE.Points | null>(null);
  const edgeObjRef = useRef<THREE.LineSegments | null>(null);
  const nodeIndexRef = useRef<Map<string, number>>(new Map());
  const nodeStateAttrRef = useRef<THREE.BufferAttribute | null>(null);
  const nodeHoverAttrRef = useRef<THREE.BufferAttribute | null>(null);
  const edgeFiringAttrRef = useRef<THREE.BufferAttribute | null>(null);
  const edgeIdsRef = useRef<string[]>([]);
  // Per-node metadata the interaction layer (raycast hover + HTML labels) reads.
  const nodeMetaRef = useRef<{
    ids: string[];
    labels: string[];
    kinds: string[];
    core: Float32Array;
    pos: Float32Array;
  } | null>(null);

  // Latest props read inside the rAF loop / imperative builders.
  const highlightRef = useRef(highlight);
  highlightRef.current = highlight;
  const growthRef = useRef(growth);
  growthRef.current = growth;

  const frameRef = useRef<number | null>(null);

  // --- one-time scene setup --------------------------------------------------
  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) return;
    const w = Math.max(1, width);
    const h = Math.max(1, height);

    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(1.5, window.devicePixelRatio || 1));
    renderer.setSize(w, h);
    renderer.setClearColor(0x05090e, 1);
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.05;
    mount.appendChild(renderer.domElement);
    renderer.domElement.style.display = "block";
    rendererRef.current = renderer;

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(50, w / h, 0.1, 100);
    camera.position.set(0, 0, 8.2);
    cameraRef.current = camera;

    const group = new THREE.Group();
    group.rotation.x = -0.12;
    scene.add(group);
    groupRef.current = group;

    // Brain point cloud (static, holographic cyan).
    const cloud = buildBrainCloud();
    const cloudGeo = new THREE.BufferGeometry();
    cloudGeo.setAttribute("position", new THREE.BufferAttribute(cloud.positions, 3));
    cloudGeo.setAttribute("aRand", new THREE.BufferAttribute(cloud.rand, 1));
    cloudGeo.setAttribute("aFold", new THREE.BufferAttribute(cloud.fold, 1));
    const cloudMat = new THREE.ShaderMaterial({
      uniforms: {
        uTime: { value: 0 },
        uSize: { value: 0.84 },
        uPixelRatio: { value: renderer.getPixelRatio() },
        uColor: { value: new THREE.Color(0x2fd6c8) }, // deep teal (sulci / grooves)
        uColor2: { value: new THREE.Color(0x9bfff2) }, // bright aqua (gyri / ridges)
        uOpacity: { value: 0.36 },
        // Near-camera dissolve: points closer than this (view depth) fade out,
        // so zooming in melts the front shell and reveals the folds inside.
        uNearFade: { value: 3.4 },
        // Hover spotlight: dim/fade the dust within uDullRadius (NDC) of the
        // cursor so the nodes + labels under the pointer become easy to read.
        uPointer: { value: new THREE.Vector2(0, 0) },
        uPointerOn: { value: 0 },
        uAspect: { value: w / h },
        uDullRadius: { value: 0.34 },
      },
      vertexShader: /* glsl */ `
        attribute float aRand, aFold;
        varying float vRand, vFold, vFade;
        varying vec2 vNdc;
        uniform float uTime, uSize, uPixelRatio, uNearFade;
        void main() {
          vRand = aRand;
          vFold = aFold;
          vec3 p = position * (1.0 + 0.01 * sin(uTime * 0.5 + aRand * 6.2831));
          vec4 mv = modelViewMatrix * vec4(p, 1.0);
          float depth = -mv.z;
          vFade = smoothstep(uNearFade * 0.45, uNearFade, depth); // 0 when very close
          gl_PointSize = uSize * uPixelRatio * (16.0 / depth);
          gl_Position = projectionMatrix * mv;
          vNdc = gl_Position.xy / gl_Position.w;
        }
      `,
      fragmentShader: /* glsl */ `
        varying float vRand, vFold, vFade;
        varying vec2 vNdc;
        uniform float uTime, uOpacity, uPointerOn, uAspect, uDullRadius;
        uniform vec2 uPointer;
        uniform vec3 uColor, uColor2;
        void main() {
          float d = length(gl_PointCoord - 0.5);
          if (d > 0.5) discard;
          float a = smoothstep(0.5, 0.0, d);
          // Gentler twinkle with a high floor → vibrant, never dull.
          float fl = 0.82 + 0.18 * sin(uTime * 2.0 + vRand * 40.0);
          // Ridges (gyri) glow bright aqua; grooves (sulci) stay teal but lit.
          float ridge = 0.7 + 0.7 * vFold;
          vec3 col = mix(uColor, uColor2, vFold);
          // Hover spotlight: fade dust near the cursor (circular in screen space).
          float dim = 1.0;
          if (uPointerOn > 0.5) {
            vec2 dd = vNdc - uPointer;
            dd.x *= uAspect;
            dim = mix(0.12, 1.0, smoothstep(0.0, uDullRadius, length(dd)));
          }
          gl_FragColor = vec4(col * fl * ridge, a * uOpacity * (0.7 + 0.3 * vRand) * vFade * dim);
        }
      `,
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    });
    const cloudPoints = new THREE.Points(cloudGeo, cloudMat);
    cloudPoints.frustumCulled = false;
    cloudPoints.userData.isCloud = true;
    group.add(cloudPoints);

    // Post-processing: half-res bloom for the holographic glow.
    const composer = new EffectComposer(renderer);
    composer.setPixelRatio(Math.min(1.5, window.devicePixelRatio || 1));
    composer.setSize(w, h);
    composer.addPass(new RenderPass(scene, camera));
    const bloom = new UnrealBloomPass(new THREE.Vector2(w / 2, h / 2), 1.05, 0.45, 0.42);
    composer.addPass(bloom);
    composerRef.current = composer;

    // --- camera controls: drag to orbit, scroll to zoom (graph navigation) --
    const controls = new OrbitControls(camera, renderer.domElement);
    controls.enableDamping = true;
    controls.dampingFactor = 0.08;
    controls.enablePan = false;
    controls.minDistance = 4.5;
    controls.maxDistance = 16;
    controls.autoRotate = true;
    controls.autoRotateSpeed = 0.55;
    controls.target.set(0, 0, 0);
    // Pause the ambient spin while the user is actively dragging; resume after.
    let resumeTimer: number | null = null;
    controls.addEventListener("start", () => {
      controls.autoRotate = false;
      if (resumeTimer != null) clearTimeout(resumeTimer);
    });
    controls.addEventListener("end", () => {
      if (resumeTimer != null) clearTimeout(resumeTimer);
      resumeTimer = window.setTimeout(() => (controls.autoRotate = true), 2500);
    });

    // --- hover picking: raycast the node points, light + label the hit -------
    const raycaster = new THREE.Raycaster();
    raycaster.params.Points = { threshold: 0.16 };
    const ndc = new THREE.Vector2();
    let hoverIndex = -1;
    let lastPick = 0;
    const setHover = (idx: number) => {
      if (idx === hoverIndex) return;
      hoverIndex = idx;
      const attr = nodeHoverAttrRef.current;
      if (attr) {
        const arr = attr.array as Float32Array;
        arr.fill(0);
        if (idx >= 0 && idx < arr.length) arr[idx] = 1;
        attr.needsUpdate = true;
      }
      renderer.domElement.style.cursor = idx >= 0 ? "pointer" : "grab";
    };
    const onPick = (e: PointerEvent) => {
      const now = performance.now();
      if (now - lastPick < 33) return; // cap raycasting at ~30fps
      lastPick = now;
      const node = nodeObjRef.current;
      if (!node) return setHover(-1);
      const r = renderer.domElement.getBoundingClientRect();
      ndc.x = ((e.clientX - r.left) / r.width) * 2 - 1;
      ndc.y = -(((e.clientY - r.top) / r.height) * 2 - 1);
      // Drive the cloud's hover spotlight (fade dust near the cursor).
      cloudMat.uniforms.uPointer.value.set(ndc.x, ndc.y);
      cloudMat.uniforms.uPointerOn.value = 1;
      raycaster.setFromCamera(ndc, camera);
      const hits = raycaster.intersectObject(node, false);
      setHover(hits.length ? hits[0].index ?? -1 : -1);
    };
    const onPickLeave = () => {
      setHover(-1);
      cloudMat.uniforms.uPointerOn.value = 0;
    };
    renderer.domElement.addEventListener("pointermove", onPick);
    renderer.domElement.addEventListener("pointerleave", onPickLeave);
    renderer.domElement.style.cursor = "grab";

    // --- HTML label layer (user node + lit nodes + hovered node) ------------
    const labelLayer = document.createElement("div");
    Object.assign(labelLayer.style, {
      position: "absolute",
      inset: "0",
      pointerEvents: "none",
      overflow: "hidden",
    });
    mount.appendChild(labelLayer);
    const labelEls = new Map<string, HTMLDivElement>();
    const proj = new THREE.Vector3();
    const updateLabels = () => {
      const meta = nodeMetaRef.current;
      if (!meta) return;
      const hl = highlightRef.current;
      const gt = growthRef.current.t;
      const W = renderer.domElement.clientWidth;
      const H = renderer.domElement.clientHeight;
      const want = new Set<string>();
      meta.ids.forEach((id, i) => {
        const lit = hl.active && (hl.groundedIds.has(id) || hl.anchorIds.has(id));
        const isUser = meta.kinds[i] === "user";
        const isHover = i === hoverIndex;
        if (!(isHover || lit || isUser)) return;
        if (!meta.core[i] && gt < 0.5 && !isHover) return; // hidden by growth
        want.add(id);
      });
      labelEls.forEach((el, id) => {
        if (!want.has(id)) {
          el.remove();
          labelEls.delete(id);
        }
      });
      meta.ids.forEach((id, i) => {
        if (!want.has(id)) return;
        proj.set(meta.pos[i * 3], meta.pos[i * 3 + 1], meta.pos[i * 3 + 2]);
        proj.applyMatrix4(group.matrixWorld).project(camera);
        let el = labelEls.get(id);
        if (!el) {
          el = document.createElement("div");
          Object.assign(el.style, {
            position: "absolute",
            transform: "translate(-50%, calc(-100% - 9px))",
            font: "600 11px ui-monospace, SFMono-Regular, Menlo, monospace",
            background: "rgba(6,14,20,0.72)",
            borderRadius: "7px",
            padding: "2px 7px",
            whiteSpace: "nowrap",
            backdropFilter: "blur(4px)",
            boxShadow: "0 2px 10px rgba(0,0,0,0.35)",
          });
          el.textContent = meta.labels[i];
          labelLayer.appendChild(el);
          labelEls.set(id, el);
        }
        if (proj.z > 1) {
          el.style.display = "none";
          return;
        }
        const lit = hl.active && hl.groundedIds.has(id);
        el.style.display = "block";
        el.style.left = ((proj.x * 0.5 + 0.5) * W).toFixed(1) + "px";
        el.style.top = ((-proj.y * 0.5 + 0.5) * H).toFixed(1) + "px";
        el.style.color = lit ? "#ffd9cc" : "#dff6f2";
        el.style.border = `1px solid ${lit ? "rgba(255,120,80,0.6)" : "rgba(80,220,205,0.35)"}`;
      });
    };

    const clock = new THREE.Clock();
    const animate = () => {
      frameRef.current = requestAnimationFrame(animate);
      const t = clock.getElapsedTime();
      const gt = growthRef.current.t;
      group.children.forEach((child) => {
        const m = (child as THREE.Points).material as THREE.ShaderMaterial | undefined;
        if (m && m.uniforms) {
          if (m.uniforms.uTime) m.uniforms.uTime.value = t;
          if (m.uniforms.uGrowthT) m.uniforms.uGrowthT.value = gt;
          if (m.uniforms.uAspect) m.uniforms.uAspect.value = camera.aspect; // keep spotlight circular
        }
      });
      controls.update();
      updateLabels();
      composer.render();
    };
    animate();

    // Pause the loop when the tab is hidden (saves battery + cache warmth).
    const onVisibility = () => {
      if (document.hidden) {
        if (frameRef.current != null) cancelAnimationFrame(frameRef.current);
        frameRef.current = null;
      } else if (frameRef.current == null) {
        animate();
      }
    };
    document.addEventListener("visibilitychange", onVisibility);

    return () => {
      document.removeEventListener("visibilitychange", onVisibility);
      renderer.domElement.removeEventListener("pointermove", onPick);
      renderer.domElement.removeEventListener("pointerleave", onPickLeave);
      if (resumeTimer != null) clearTimeout(resumeTimer);
      if (frameRef.current != null) cancelAnimationFrame(frameRef.current);
      frameRef.current = null;
      controls.dispose();
      labelEls.forEach((el) => el.remove());
      labelEls.clear();
      if (labelLayer.parentNode === mount) mount.removeChild(labelLayer);
      // Dispose everything WebGL.
      scene.traverse((o) => {
        const any = o as THREE.Mesh;
        if (any.geometry) any.geometry.dispose();
        const mat = (any as unknown as { material?: THREE.Material | THREE.Material[] }).material;
        if (Array.isArray(mat)) mat.forEach((m) => m.dispose());
        else if (mat) mat.dispose();
      });
      composer.dispose();
      renderer.dispose();
      if (renderer.domElement.parentNode === mount) mount.removeChild(renderer.domElement);
      rendererRef.current = null;
      composerRef.current = null;
      cameraRef.current = null;
      groupRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // --- (re)build node + edge geometry when the graph data changes -----------
  useEffect(() => {
    const group = groupRef.current;
    if (!group || !data) return;

    // Tear down any previous graph objects (keep the brain cloud).
    [nodeObjRef.current, edgeObjRef.current].forEach((obj) => {
      if (obj) {
        group.remove(obj);
        obj.geometry.dispose();
        (obj.material as THREE.Material).dispose();
      }
    });

    const nodes = data.nodes;
    const n = nodes.length;
    const posMap = new Map<string, THREE.Vector3>();
    const indexMap = new Map<string, number>();

    const nPos = new Float32Array(n * 3);
    const nColor = new Float32Array(n * 3);
    const nSize = new Float32Array(n);
    const nState = new Float32Array(n); // 0 normal · 1 subgraph · 2 anchor · 3 grounded
    const nCore = new Float32Array(n); // 1 = present at "session start"
    const nSeed = new Float32Array(n);
    const nHover = new Float32Array(n); // 1 = currently hovered (raycast)
    const ids: string[] = [];
    const labels: string[] = [];
    const kinds: string[] = [];

    nodes.forEach((node, i) => {
      const p = nodePosition(node);
      posMap.set(node.id, p);
      indexMap.set(node.id, i);
      ids.push(node.id);
      labels.push(node.label);
      kinds.push(node.kind);
      nPos[i * 3] = p.x;
      nPos[i * 3 + 1] = p.y;
      nPos[i * 3 + 2] = p.z;
      const c = colorOf(node.kind);
      nColor[i * 3] = c.r;
      nColor[i * 3 + 1] = c.g;
      nColor[i * 3 + 2] = c.b;
      const sal = Math.min(3, Math.max(0, node.salience || 0));
      nSize[i] = node.kind === "user" ? 15 : 5.5 + sal * 1.6;
      nState[i] = 0;
      nCore[i] = growthRef.current.coreNodeIds.has(node.id) ? 1 : 0;
      nSeed[i] = (hashStr(node.id) % 1000) / 1000;
    });
    nodeIndexRef.current = indexMap;
    nodeMetaRef.current = { ids, labels, kinds, core: nCore, pos: nPos };

    const nodeGeo = new THREE.BufferGeometry();
    nodeGeo.setAttribute("position", new THREE.BufferAttribute(nPos, 3));
    nodeGeo.setAttribute("aColor", new THREE.BufferAttribute(nColor, 3));
    nodeGeo.setAttribute("aBaseSize", new THREE.BufferAttribute(nSize, 1));
    const stateAttr = new THREE.BufferAttribute(nState, 1);
    stateAttr.setUsage(THREE.DynamicDrawUsage);
    nodeGeo.setAttribute("aState", stateAttr);
    nodeGeo.setAttribute("aCore", new THREE.BufferAttribute(nCore, 1));
    nodeGeo.setAttribute("aSeed", new THREE.BufferAttribute(nSeed, 1));
    const hoverAttr = new THREE.BufferAttribute(nHover, 1);
    hoverAttr.setUsage(THREE.DynamicDrawUsage);
    nodeGeo.setAttribute("aHover", hoverAttr);
    nodeStateAttrRef.current = stateAttr;
    nodeHoverAttrRef.current = hoverAttr;

    const nodeMat = new THREE.ShaderMaterial({
      uniforms: {
        uTime: { value: 0 },
        uGrowthT: { value: growthRef.current.t },
        uPixelRatio: { value: rendererRef.current?.getPixelRatio() ?? 1 },
      },
      vertexShader: /* glsl */ `
        attribute vec3 aColor;
        attribute float aBaseSize, aState, aCore, aSeed, aHover;
        uniform float uTime, uGrowthT, uPixelRatio;
        varying vec3 vColor;
        varying float vBright, vAlpha;
        void main() {
          vColor = aColor;
          float b = 0.72 + 0.12 * sin(uTime * 1.5 + aSeed * 6.2831);
          float size = aBaseSize;
          if (aState > 2.5) { b = 2.1 + 0.5 * sin(uTime * 5.0); size *= 1.35 + 0.18 * sin(uTime * 5.0); }
          else if (aState > 1.5) { b = 1.6 + 0.25 * sin(uTime * 3.0); size *= 1.22; }
          else if (aState > 0.5) { b = 1.25; size *= 1.12; }
          if (aHover > 0.5) { b += 0.9; size *= 1.6; }
          vBright = b;
          vAlpha = aCore > 0.5 ? 1.0 : smoothstep(0.0, 1.0, uGrowthT);
          vec4 mv = modelViewMatrix * vec4(position, 1.0);
          gl_PointSize = size * uPixelRatio * (16.0 / -mv.z);
          gl_Position = projectionMatrix * mv;
        }
      `,
      fragmentShader: /* glsl */ `
        varying vec3 vColor;
        varying float vBright, vAlpha;
        void main() {
          float d = length(gl_PointCoord - 0.5);
          if (d > 0.5) discard;
          float core = smoothstep(0.5, 0.16, d);
          float halo = smoothstep(0.5, 0.0, d) * 0.32;
          gl_FragColor = vec4(vColor * vBright, (core + halo) * vAlpha);
        }
      `,
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    });
    const nodePoints = new THREE.Points(nodeGeo, nodeMat);
    nodePoints.frustumCulled = false;
    group.add(nodePoints);
    nodeObjRef.current = nodePoints;

    // Edges (synapses): 2 verts per link.
    const links = data.links.filter((l) => posMap.has(linkEnd(l.source)) && posMap.has(linkEnd(l.target)));
    const m = links.length;
    const ePos = new Float32Array(m * 6);
    const eParam = new Float32Array(m * 2);
    const eFiring = new Float32Array(m * 2);
    const eCore = new Float32Array(m * 2);
    const eOffset = new Float32Array(m * 2);
    const edgeIds: string[] = [];
    links.forEach((l: FGLink, i) => {
      const a = posMap.get(linkEnd(l.source))!;
      const b = posMap.get(linkEnd(l.target))!;
      ePos[i * 6] = a.x; ePos[i * 6 + 1] = a.y; ePos[i * 6 + 2] = a.z;
      ePos[i * 6 + 3] = b.x; ePos[i * 6 + 4] = b.y; ePos[i * 6 + 5] = b.z;
      eParam[i * 2] = 0; eParam[i * 2 + 1] = 1;
      eFiring[i * 2] = 0; eFiring[i * 2 + 1] = 0;
      const core = growthRef.current.coreEdgeIds.has(l.id) ? 1 : 0;
      eCore[i * 2] = core; eCore[i * 2 + 1] = core;
      const off = (hashStr(l.id) % 1000) / 1000;
      eOffset[i * 2] = off; eOffset[i * 2 + 1] = off;
      edgeIds.push(l.id);
    });
    edgeIdsRef.current = edgeIds;

    const edgeGeo = new THREE.BufferGeometry();
    edgeGeo.setAttribute("position", new THREE.BufferAttribute(ePos, 3));
    edgeGeo.setAttribute("aParam", new THREE.BufferAttribute(eParam, 1));
    const firingAttr = new THREE.BufferAttribute(eFiring, 1);
    firingAttr.setUsage(THREE.DynamicDrawUsage);
    edgeGeo.setAttribute("aFiring", firingAttr);
    edgeGeo.setAttribute("aCoreEdge", new THREE.BufferAttribute(eCore, 1));
    edgeGeo.setAttribute("aOffset", new THREE.BufferAttribute(eOffset, 1));
    edgeFiringAttrRef.current = firingAttr;

    const edgeMat = new THREE.ShaderMaterial({
      uniforms: {
        uTime: { value: 0 },
        uGrowthT: { value: growthRef.current.t },
        uBase: { value: new THREE.Color(0x2bd6c6) },
        uFire: { value: new THREE.Color(0xff6a45) },
      },
      vertexShader: /* glsl */ `
        attribute float aParam, aFiring, aCoreEdge, aOffset;
        uniform float uGrowthT;
        varying float vParam, vFiring, vOffset, vVis;
        void main() {
          vParam = aParam; vFiring = aFiring; vOffset = aOffset;
          vVis = aCoreEdge > 0.5 ? 1.0 : smoothstep(0.0, 1.0, uGrowthT);
          gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
        }
      `,
      fragmentShader: /* glsl */ `
        uniform float uTime;
        uniform vec3 uBase, uFire;
        varying float vParam, vFiring, vOffset, vVis;
        void main() {
          float pulsePos = fract(uTime * 0.5 + vOffset);
          float dd = abs(vParam - pulsePos);
          dd = min(dd, 1.0 - dd);
          float pulse = smoothstep(0.10, 0.0, dd) * vFiring;
          vec3 col = mix(uBase, uFire, pulse);
          float a = (0.10 + pulse * 0.9 + vFiring * 0.14) * vVis;
          gl_FragColor = vec4(col, a);
        }
      `,
      transparent: true,
      depthWrite: false,
      blending: THREE.AdditiveBlending,
    });
    const edgeLines = new THREE.LineSegments(edgeGeo, edgeMat);
    edgeLines.frustumCulled = false;
    group.add(edgeLines);
    edgeObjRef.current = edgeLines;

    applyHighlight();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data]);

  // --- push the current highlight into the node/edge attribute buffers -------
  const applyHighlight = () => {
    const hl = highlightRef.current;
    const stateAttr = nodeStateAttrRef.current;
    const idx = nodeIndexRef.current;
    if (stateAttr && idx) {
      const arr = stateAttr.array as Float32Array;
      arr.fill(0);
      if (hl.active) {
        hl.subgraphNodeIds.forEach((id) => {
          const i = idx.get(id);
          if (i != null) arr[i] = Math.max(arr[i], 1);
        });
        hl.anchorIds.forEach((id) => {
          const i = idx.get(id);
          if (i != null) arr[i] = Math.max(arr[i], 2);
        });
        hl.groundedIds.forEach((id) => {
          const i = idx.get(id);
          if (i != null) arr[i] = 3;
        });
      }
      stateAttr.needsUpdate = true;
    }
    const firingAttr = edgeFiringAttrRef.current;
    const edgeIds = edgeIdsRef.current;
    if (firingAttr && edgeIds) {
      const arr = firingAttr.array as Float32Array;
      arr.fill(0);
      if (hl.active) {
        edgeIds.forEach((id, i) => {
          if (hl.subgraphEdgeIds.has(id)) {
            arr[i * 2] = 1;
            arr[i * 2 + 1] = 1;
          }
        });
      }
      firingAttr.needsUpdate = true;
    }
  };

  useEffect(() => {
    applyHighlight();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [highlight]);

  // --- resize ----------------------------------------------------------------
  useEffect(() => {
    const renderer = rendererRef.current;
    const composer = composerRef.current;
    const camera = cameraRef.current;
    if (!renderer || !composer || !camera) return;
    const w = Math.max(1, width);
    const h = Math.max(1, height);
    renderer.setSize(w, h);
    composer.setSize(w, h);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
  }, [width, height]);

  return <div ref={mountRef} style={{ position: "absolute", inset: 0 }} />;
}
