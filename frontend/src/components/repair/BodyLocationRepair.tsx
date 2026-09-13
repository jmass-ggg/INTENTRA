/**
 * BodyLocationRepair — Shows body location selection options
 */

import { RepairPlan } from './types';

interface BodyLocationRepairProps {
  plan: RepairPlan;
  onSelection: (selections: Record<string, string>) => void;
  onCancel?: () => void;
}

export function BodyLocationRepair({ plan, onSelection, onCancel }: BodyLocationRepairProps) {
  const question = plan.question || 'Where does it hurt?';

  return (
    <div className="flex flex-col gap-6 p-6 bg-white border border-gray-200 rounded-lg shadow-sm">
      {/* Question */}
      <div className="text-center">
        <h3 className="text-xl font-medium text-gray-900">
          {question}
        </h3>
      </div>

      {/* Body Location Buttons */}
      <div className="grid grid-cols-2 gap-4">
        {plan.options.map((option, index) => (
          <button
            key={index}
            onClick={() => onSelection({ location: option.value, label: option.label })}
            className={`
              px-6 py-5 
              text-xl font-medium 
              rounded-xl 
              transition-colors
              focus:outline-none focus:ring-4
              ${
                option.value === 'other'
                  ? 'bg-gray-200 text-gray-800 hover:bg-gray-300 focus:ring-gray-300'
                  : 'bg-red-600 text-white hover:bg-red-700 active:bg-red-800 focus:ring-red-300'
              }
            `}
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
