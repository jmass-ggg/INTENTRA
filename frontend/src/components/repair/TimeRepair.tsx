/**
 * TimeRepair — Shows time selection options
 */

import { RepairPlan } from './types';

interface TimeRepairProps {
  plan: RepairPlan;
  onSelection: (selections: Record<string, string>) => void;
  onCancel?: () => void;
}

export function TimeRepair({ plan, onSelection, onCancel }: TimeRepairProps) {
  const question = plan.question || 'When did you mean?';

  return (
    <div className="flex flex-col gap-6 p-6 bg-white border border-gray-200 rounded-lg shadow-sm">
      {/* Question */}
      <div className="text-center">
        <h3 className="text-xl font-medium text-gray-900">
          {question}
        </h3>
      </div>

      {/* Time Selection Buttons */}
      <div className="grid grid-cols-2 gap-4">
        {plan.options.map((option, index) => (
          <button
            key={index}
            onClick={() => onSelection({ time: option.value, label: option.label })}
            className="
              px-6 py-5 
              text-xl font-medium 
              bg-purple-600 text-white 
              rounded-xl 
              hover:bg-purple-700 
              active:bg-purple-800 
              transition-colors
              focus:outline-none focus:ring-4 focus:ring-purple-300
            "
            aria-label={option.label}
          >
            {option.label}
          </button>
        ))}
      </div>

      {/* Cancel option */}
      {onCancel && (
        <button
          onClick={onCancel}
          className="
            mt-2 px-4 py-2 
            text-sm text-gray-600 
            hover:text-gray-900 
            transition-colors
          "
        >
          Cancel
        </button>
      )}
    </div>
  );
}
