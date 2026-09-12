// Shared motion language. Exponential ease-out (confident, no bounce) for
// enters/transitions; a low-bounce spring reserved for the one signature moment
// (the candidate bloom + the chosen-utterance rise). Durations stay in the
// 150–250ms product range except the deliberate bloom.

export const EASE_OUT = [0.16, 1, 0.3, 1] as const; // ease-out-expo
export const EASE_OUT_QUART = [0.25, 1, 0.5, 1] as const; // softer ease-out (UI states)

// Low-bounce spring for the speak moment only.
export const SPRING = {
  type: "spring",
  stiffness: 180,
  damping: 26,
  mass: 0.7,
} as const;

export const DUR = {
  fast: 0.16,
  base: 0.22,
  moment: 0.42,
} as const;
