// IntentSelector — Four large intent buttons for the communication flow.
//
// Renders: Answer, Ask, Request, Explain
// Keyboard accessible with ARIA labels
// Calls dispatch({ type: 'SET_INTENT', intent }) on selection

import { type IntentType } from "../../lib/api";

interface IntentSelectorProps {
  selectedIntent: IntentType | null;
  onSelect: (intent: IntentType) => void;
}

const INTENT_OPTIONS: Array<{
  value: IntentType;
  label: string;
  description: string;
}> = [
  {
    value: "answer",
    label: "Answer",
    description: "Respond to a question",
  },
  {
    value: "question",
    label: "Ask",
    description: "Ask a question",
  },
  {
    value: "request",
    label: "Request",
    description: "Ask for something",
  },
  {
    value: "explain",
    label: "Explain",
    description: "Explain something",
  },
];

export function IntentSelector({ selectedIntent, onSelect }: IntentSelectorProps) {
  return (
    <div
      className="grid grid-cols-2 gap-4"
      role="group"
      aria-label="Select communication intent"
    >
      {INTENT_OPTIONS.map((option) => {
        const isSelected = selectedIntent === option.value;
        return (
          <button
            key={option.value}
            type="button"
            onClick={() => onSelect(option.value)}
            className={`
              flex flex-col items-center justify-center
              min-h-[120px] px-6 py-4
              text-lg font-medium
              rounded-xl
              transition-all duration-200
              focus:outline-none focus:ring-4 focus:ring-blue-400 focus:ring-offset-2
              ${
                isSelected
                  ? "bg-blue-600 text-white shadow-lg scale-105"
                  : "bg-white text-gray-800 border-2 border-gray-300 hover:border-blue-400 hover:bg-blue-50"
              }
            `}
            aria-pressed={isSelected}
            aria-label={`${option.label}: ${option.description}`}
          >
            <span className="text-2xl font-bold">{option.label}</span>
            <span className="text-sm mt-2 opacity-80">{option.description}</span>
          </button>
        );
      })}
    </div>
  );
}

export default IntentSelector;
