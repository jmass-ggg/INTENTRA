/**
 * EffortModeSelector
 * 
 * Provides four effort mode options: Full, Assist, Low Effort, Emergency
 * Updates CommunicateView layout when selection changes
 * 
 * Requirements: 11.1, 11.2, 11.3, 11.4
 */

export type EffortMode = "full" | "assist" | "low_effort" | "emergency";

interface EffortModeSelectorProps {
  currentMode: EffortMode;
  onModeChange: (mode: EffortMode) => void;
}

const EFFORT_MODES: Array<{
  value: EffortMode;
  label: string;
  description: string;
  icon: string;
}> = [
  {
    value: "full",
    label: "Full",
    description: "All controls and features available",
    icon: "⚡",
  },
  {
    value: "assist",
    label: "Assist",
    description: "Simplified controls with helpful suggestions",
    icon: "🤝",
  },
  {
    value: "low_effort",
    label: "Low Effort",
    description: "Large essential buttons only",
    icon: "✨",
  },
  {
    value: "emergency",
    label: "Emergency",
    description: "Critical phrases only",
    icon: "🚨",
  },
];

export function EffortModeSelector({
  currentMode,
  onModeChange,
}: EffortModeSelectorProps) {
  return (
    <div className="effort-mode-selector" role="radiogroup" aria-label="Effort mode">
      <div className="flex flex-col sm:flex-row gap-3">
        {EFFORT_MODES.map((mode) => {
          const isSelected = currentMode === mode.value;
          
          return (
            <button
              key={mode.value}
              type="button"
              role="radio"
              aria-checked={isSelected}
              onClick={() => onModeChange(mode.value)}
              className={`
                flex flex-col items-center justify-center
                p-4 rounded-lg border-2 transition-all
                min-h-[120px] flex-1
                ${
                  isSelected
                    ? "border-blue-500 bg-blue-50 shadow-md"
                    : "border-gray-300 bg-white hover:border-blue-300 hover:bg-blue-25"
                }
              `}
              aria-label={`${mode.label} mode: ${mode.description}`}
            >
              <span className="text-3xl mb-2" aria-hidden="true">
                {mode.icon}
              </span>
              <span className="font-semibold text-lg mb-1">{mode.label}</span>
              <span className="text-sm text-gray-600 text-center">
                {mode.description}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
