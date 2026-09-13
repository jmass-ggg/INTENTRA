// CommunicationOutcome — Post-speaking feedback interface.
//
// Shown after speaking: "Did that work?"
// Two buttons: "Yes, they understood" and "No, help me clarify"
// Calls POST /conversation/outcome
// "No" transitions to repair_mode state

import { CheckCircle, WarningCircle } from "@phosphor-icons/react";

interface CommunicationOutcomeProps {
  onSuccess: () => void;
  onFailure: () => void;
}

export function CommunicationOutcome({
  onSuccess,
  onFailure,
}: CommunicationOutcomeProps) {
  return (
    <div className="space-y-4 p-6 bg-white rounded-xl border-2 border-gray-200 shadow-sm">
      {/* Question */}
      <div className="text-center">
        <h3 className="text-2xl font-bold text-gray-900 mb-2">Did that work?</h3>
        <p className="text-gray-600">Did your listener understand you?</p>
      </div>

      {/* Outcome buttons */}
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 pt-2">
        <button
          type="button"
          onClick={onSuccess}
          className="flex items-center justify-center gap-3 px-8 py-6 bg-green-600 text-white rounded-xl text-lg font-bold hover:bg-green-700 focus:outline-none focus:ring-4 focus:ring-green-400 focus:ring-offset-2 transition-all duration-200 shadow-md hover:shadow-lg"
          aria-label="Communication was successful"
        >
          <CheckCircle size={32} weight="bold" />
          <span>Yes, they understood</span>
        </button>

        <button
          type="button"
          onClick={onFailure}
          className="flex items-center justify-center gap-3 px-8 py-6 bg-amber-600 text-white rounded-xl text-lg font-bold hover:bg-amber-700 focus:outline-none focus:ring-4 focus:ring-amber-400 focus:ring-offset-2 transition-all duration-200 shadow-md hover:shadow-lg"
          aria-label="Communication failed, need help"
        >
          <WarningCircle size={32} weight="bold" />
          <span>No, help me clarify</span>
        </button>
      </div>
    </div>
  );
}

export default CommunicationOutcome;
