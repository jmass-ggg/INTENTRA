// Waveform — the shared "sound bar": a center-weighted equalizer in `voice`
// (the human/speak color). Animates while `playing`; respects reduced motion
// (renders a designed STATIC silhouette, never a dead flat row). Decorative
// only — aria-hidden. Size is a coherent set (height + bar width + gap); never
// override the height via className (it would fight the size preset).

import { useMemo } from "react";
import { motion, useReducedMotion } from "framer-motion";

export type WaveSize = "sm" | "md" | "lg";

export interface WaveformProps {
  playing: boolean;
  size?: WaveSize;
  className?: string;
}

const SIZE: Record<WaveSize, { h: string; bars: number; bar: string; gap: string }> = {
  sm: { h: "h-6", bars: 7, bar: "w-1", gap: "gap-1" },
  md: { h: "h-10", bars: 9, bar: "w-1", gap: "gap-1.5" },
  lg: { h: "h-16", bars: 11, bar: "w-1.5", gap: "gap-1.5" },
};

const QUART = [0.25, 1, 0.5, 1] as const;

// Symmetric center-weighted envelope peak per bar (1.0 center → 0.45 edges) so
// the middle bars crest highest, like a real voiced sound, not a flat block.
function envelope(n: number): number[] {
  const mid = (n - 1) / 2;
  return Array.from({ length: n }, (_, i) => {
    const d = mid === 0 ? 0 : Math.abs(i - mid) / mid;
    return 0.45 + (1 - d) * 0.55;
  });
}

export default function Waveform({ playing, size = "sm", className = "" }: WaveformProps) {
  const reduce = useReducedMotion();
  const s = SIZE[size];

  // Per-bar peak + a de-synced phase so the wave reads organic, not a sweep.
  const cfg = useMemo(() => {
    return envelope(s.bars).map((peak, i) => ({
      peak,
      opacity: Math.min(1, 0.55 + (peak - 0.45)),
      duration: 0.6 + ((i * 7) % 5) * 0.12,
      delay: ((i * 5) % s.bars) * 0.07,
    }));
  }, [s.bars]);

  return (
    <div aria-hidden className={`inline-flex items-center ${s.gap} ${s.h} ${className}`}>
      {cfg.map((c, i) => (
        <motion.span
          key={i}
          className={`${s.bar} rounded-full ${playing ? "bg-voice" : "bg-ink-line"}`}
          style={{ opacity: playing ? c.opacity : 1 }}
          initial={false}
          animate={
            playing && !reduce
              ? { height: ["28%", `${c.peak * 100}%`, "42%", `${c.peak * 76}%`, "28%"] }
              : { height: `${c.peak * (playing ? 90 : 62)}%` }
          }
          transition={
            playing && !reduce
              ? { duration: c.duration, delay: c.delay, repeat: Infinity, ease: "easeInOut" }
              : { duration: 0.22, ease: QUART }
          }
        />
      ))}
    </div>
  );
}
