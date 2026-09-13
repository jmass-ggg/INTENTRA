// ExpressionPreview — Shows generated expression with confidence and action buttons.
//
// Features:
// - Display generated expression text
// - Show confidence band indicator (High / Medium / Low)
// - "Speak this" button (primary, large) — only enabled when state is ready_for_confirmation
// - "Edit" button — opens inline text editor
// - "Speak this" calls speak(text) from useCommunication; never auto-fires
//
// CRITICAL: TTS is NEVER triggered automatically. Only explicit user action.

import { useState } from "react";
import { SpeakerHigh, PencilSimple } from "@phosphor-icons/react";
import { type ConfidenceBand } from "../../lib/api";

interface ExpressionPreviewProps {
  expression: string;
  confidence: ConfidenceBand;
  isReady: boolean;
  onSpeak: (text: string) => void;
  onEdit: (text: string) => void;
}

const CONFIDENCE_LABELS: Record<ConfidenceBand, { label: string; color: string }> = {
  high: { label: "High", color: "text-green-700 bg-green-100" },
  medium: { label: "Medium", color: "text-yellow-700 bg-yellow-100" },
  low: { label: "Low", color: "text-red-700 bg-red-100" },
};

export function ExpressionPreview({
  expression,
  confidence,
  isReady,
  onSpeak,
  onEdit,
}: ExpressionPreviewProps) {
  const [isEditing, setIsEditing] = useState(false);
  const [editedText, setEditedText] = useState(expression);

  const handleEditSave = () => {
    onEdit(editedText);
    setIsEditing(false);
  };

  const handleEditCancel = () => {
    setEditedText(expression);
    setIsEditing(false);
  };

  const confidenceStyle = CONFIDENCE_LABELS[confidence] || CONFIDENCE_LABELS.high;

  return (
    <div className="space-y-4 p-6 bg-white rounded-xl border-2 border-gray-200 shadow-sm">
      {/* Confidence indicator */}
      <div className="flex items-center gap-2">
        <span className="text-sm font-medium text-gray-600">Confidence:</span>
        <span
          className={`px-3 py-1 rounded-full text-sm font-semibold ${confidenceStyle.color}`}
        >
          {confidenceStyle.label}
        </span>
      </div>

      {/* Expression text or editor */}
      {isEditing ? (
        <div className="space-y-3">
          <textarea
            value={editedText}
            onChange={(e) => setEditedText(e.target.value)}
            className="w-full min-h-[120px] px-4 py-3 text-lg border-2 border-blue-400 rounded-lg focus:outline-none focus:ring-4 focus:ring-blue-400 resize-none"
            aria-label="Edit expression"
            autoFocus
          />
          <div className="flex gap-3">
            <button
              type="button"
              onClick={handleEditSave}
              className="flex-1 px-6 py-3 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 focus:outline-none focus:ring-4 focus:ring-blue-400 transition-colors"
            >
              Save
            </button>
            <button
              type="button"
              onClick={handleEditCancel}
              className="px-6 py-3 bg-gray-300 text-gray-700 rounded-lg font-medium hover:bg-gray-400 focus:outline-none focus:ring-4 focus:ring-gray-400 transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <>
          <div
            className="text-xl font-medium text-gray-900 leading-relaxed min-h-[80px] p-4 bg-gray-50 rounded-lg"
            role="article"
            aria-label="Generated expression"
          >
            {expression || "No expression generated yet."}
          </div>

          {/* Action buttons */}
          <div className="flex gap-3 pt-2">
            <button
              type="button"
              onClick={() => onSpeak(expression)}
              disabled={!isReady || !expression}
              className={`flex-1 flex items-center justify-center gap-3 px-8 py-5 rounded-xl text-xl font-bold transition-all duration-200 focus:outline-none focus:ring-4 focus:ring-offset-2 ${
                isReady && expression
                  ? "bg-blue-600 text-white hover:bg-blue-700 focus:ring-blue-400 shadow-lg hover:shadow-xl hover:scale-105"
                  : "bg-gray-300 text-gray-500 cursor-not-allowed"
              }`}
              aria-label="Speak this expression"
              aria-disabled={!isReady || !expression}
            >
              <SpeakerHigh size={32} weight="bold" />
              <span>Speak this</span>
            </button>

            <button
              type="button"
              onClick={() => setIsEditing(true)}
              disabled={!expression}
              className={`flex items-center justify-center gap-2 px-6 py-5 rounded-xl font-medium transition-colors focus:outline-none focus:ring-4 focus:ring-offset-2 ${
                expression
                  ? "bg-gray-200 text-gray-800 hover:bg-gray-300 focus:ring-gray-400"
                  : "bg-gray-100 text-gray-400 cursor-not-allowed"
              }`}
              aria-label="Edit expression"
              aria-disabled={!expression}
            >
              <PencilSimple size={24} weight="bold" />
              <span className="hidden sm:inline">Edit</span>
            </button>
          </div>
        </>
      )}
    </div>
  );
}

export default ExpressionPreview;
