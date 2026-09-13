/**
 * RepairPanel — Container that renders the appropriate repair sub-component
 * based on the repair strategy.
 */

import { RepairPlan } from './types';
import { YesNoRepair } from './YesNoRepair';
import { ChoiceRepair } from './ChoiceRepair';
import { TimeRepair } from './TimeRepair';
import { BodyLocationRepair } from './BodyLocationRepair';

interface RepairPanelProps {
  plan: RepairPlan;
  onSelection: (selections: Record<string, string>) => void;
  onCancel?: () => void;
}

export function RepairPanel({ plan, onSelection, onCancel }: RepairPanelProps) {
  // Render the appropriate repair component based on strategy
  switch (plan.strategy) {
    case 'YES_NO':
      return (
        <YesNoRepair
          plan={plan}
          onSelection={onSelection}
          onCancel={onCancel}
        />
      );

    case 'SHOW_CHOICES':
      return (
        <ChoiceRepair
          plan={plan}
          onSelection={onSelection}
          onCancel={onCancel}
        />
      );

    case 'TIME_SELECTION':
      return (
        <TimeRepair
          plan={plan}
          onSelection={onSelection}
          onCancel={onCancel}
        />
      );

    case 'BODY_LOCATION':
      return (
        <BodyLocationRepair
          plan={plan}
          onSelection={onSelection}
          onCancel={onCancel}
        />
      );

    case 'SIMPLIFY':
    case 'KEYWORD_ONLY':
    case 'REPHRASE':
    case 'EXPAND':
      // These strategies use the rebuilt_expression from the plan
      // and can use a simple Yes/No confirmation
      return (
        <YesNoRepair
          plan={plan}
          onSelection={onSelection}
          onCancel={onCancel}
        />
      );

    default:
      return (
        <div className="p-6 bg-red-50 border border-red-200 rounded-lg">
          <p className="text-red-800">Unknown repair strategy: {plan.strategy}</p>
          {onCancel && (
            <button
              onClick={onCancel}
              className="mt-4 px-4 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700"
            >
              Cancel
            </button>
          )}
        </div>
      );
  }
}
