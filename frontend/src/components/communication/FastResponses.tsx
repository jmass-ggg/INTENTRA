// FastResponses — Quick answer buttons for binary and choice questions
//
// Displays immediate response options without full AI pipeline
// for simple questions like "Do you want tea or coffee?"
//
// Requirements: 16.1, 16.2, 16.3

import { Lightning } from "@phosphor-icons/react";

interface FastResponsesProps {
  type: "binary" | "choice";
  options: string[];
  onSelect: (option: string) => void;
}

export function FastResponses({ type, options, onSelect }: FastResponsesProps) {
  const title = type === "binary" ? "Quick answer:" : "Choose one:";

  return (
    <section
      className="p-6 bg-emerald-50 rounded-xl border-2 border-emerald-300 shadow-md"
      aria-label="Fast response options"
    >
      <div className="flex items-center gap-3 mb-4">
        <Lightning size={32} weight="fill" className="text-emerald-700" />
        <div>
          <h3 className="text-xl font-bold text-gray-900">{title}</h3>
          <p className="text-sm text-gray-600">Tap to respond quickly</p>
        </div>
      </div>
      
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
        {options.map((option, index) => (
          <button
            key={index}
            type="button"
            onClick={() => onSelect(option)}
            className="px-6 py-4 bg-white text-gray-900 rounded-lg border-2 border-emerald-300 text-lg font-medium hover:bg-emerald-100 hover:border-emerald-400 focus:outline-none focus:ring-4 focus:ring-emerald-400 transition-all duration-200 hover:scale-105 active:scale-95"
          >
            {option}
          </button>
        ))}
      </div>
    </section>
  );
}

export default FastResponses;
