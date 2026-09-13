/**
 * YesNoRepair — Shows question with Yes/No large buttons
 */

import { RepairPlan } from './types';

interface YesNoRepairProps {
  plan: RepairPlan;
  onSelection: (selections: Record<string, string>) => void;
  onCancel?: () => void;
}

export function YesNoRepair({ plan, onSelection, onCancel }: YesNoRepairProps) {
  const question = plan.question || 'Did you mean this?';
  const expression = plan.rebuilt_expression;

  return (
    <div className="flex flex-col gap-6 p-6 bg-white border border-gray-200 rounded-lg shadow-sm">
      {/* Question */}
      <div className="text-center">
        <h3 className="text-xl font-medium text-gray-900 mb-2">
          {question}
        </h3>
        {expression && (
          <p className="text-2xl font-semibold text-blue-600 mt-4 p-4 bg-blue-50 rounded-lg">
            "{expression}"
          </p>
        )}
      </div>

      {/* Large Yes/No Buttons */}
      <div className="grid grid-cols-2 gap-4">
        <button
          onClick={() => onSelection({ answer: 'yes' })}
          className="
            px-8 py-6 
            text-2xl font-semibold 
            bg-green-600 text-white 
            rounded-xl 
            hover:bg-green-700 
            active:bg-green-800 
            transition-colors
            focus:outline-none focus:ring-4 focus:ring-green-300
          "
          aria-label="Yes"
        >
          Yes
        </button>

        <button
          onClick={() => onSelection({ answer: 'no' })}
          className="
            px-8 py-6 
            text-2xl font-semibold 
            bg-red-600 text-white 
            rounded-xl 
            hover:bg-red-700 
            active:bg-red-800 
            transition-colors
            focus:outline-none focus:ring-4 focus:ring-red-300
          "
          aria-label="No"
        >
          No
        </button>
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
