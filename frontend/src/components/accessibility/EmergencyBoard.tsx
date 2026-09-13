import { useEffect, useState } from "react";
import { API_BASE } from "../../lib/api";

/**
 * EmergencyBoard
 * 
 * Large buttons for each emergency phrase.
 * Fetches phrases from GET /accessibility/{person_id}.
 * Still requires user tap before speaking (no auto-speak).
 * Falls back to hardcoded phrases if API fails.
 * 
 * Requirements: 12.3, 12.4, 12.5
 */

interface EmergencyBoardProps {
  personId: string;
  onPhraseSelect: (phrase: string) => void;
}

// Fallback emergency phrases (hardcoded)
const FALLBACK_EMERGENCY_PHRASES = [
  "I need help.",
  "I am in pain.",
  "Call my caregiver.",
  "Call my family.",
  "I cannot breathe.",
  "I need medical help.",
];

export function EmergencyBoard({ personId, onPhraseSelect }: EmergencyBoardProps) {
  const [phrases, setPhrases] = useState<string[]>(FALLBACK_EMERGENCY_PHRASES);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    // Fetch emergency phrases from the API
    const fetchEmergencyPhrases = async () => {
      try {
        setLoading(true);
        setError(null);
        
        const response = await fetch(
          `${API_BASE}/accessibility/${encodeURIComponent(personId)}`
        );
        
        if (!response.ok) {
          throw new Error(`Failed to fetch emergency phrases: ${response.status}`);
        }
        
        const data = await response.json();
        
        if (data.emergency_phrases && Array.isArray(data.emergency_phrases)) {
          setPhrases(data.emergency_phrases);
        } else {
          // Fallback if API doesn't return expected format
          setPhrases(FALLBACK_EMERGENCY_PHRASES);
        }
      } catch (err) {
        console.error("Failed to fetch emergency phrases:", err);
        setError("Using default emergency phrases");
        // Always fall back to hardcoded phrases if API fails
        setPhrases(FALLBACK_EMERGENCY_PHRASES);
      } finally {
        setLoading(false);
      }
    };

    fetchEmergencyPhrases();
  }, [personId]);

  return (
    <div className="emergency-board p-6">
      <div className="mb-6">
        <h2 className="text-2xl font-bold text-red-600 mb-2 flex items-center gap-2">
          <span aria-hidden="true">🚨</span>
          <span>Emergency Communication</span>
        </h2>
        <p className="text-gray-700">
          Select a phrase to communicate urgently. These work even without internet.
        </p>
        {error && (
          <p className="text-sm text-orange-600 mt-2" role="status">
            {error}
          </p>
        )}
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        {loading ? (
          <div className="col-span-full text-center py-8">
            <p className="text-gray-600">Loading emergency phrases...</p>
          </div>
        ) : (
          phrases.map((phrase, index) => (
            <button
              key={index}
              type="button"
              onClick={() => onPhraseSelect(phrase)}
              className="
                emergency-button
                p-6 rounded-lg
                bg-red-50 border-4 border-red-500
                hover:bg-red-100 hover:border-red-600
                active:bg-red-200 active:scale-95
                transition-all
                text-left
                min-h-[100px]
                flex items-center justify-center
                shadow-lg hover:shadow-xl
              "
              aria-label={`Emergency: ${phrase}`}
            >
              <span className="text-xl sm:text-2xl font-bold text-red-900">
                {phrase}
              </span>
            </button>
          ))
        )}
      </div>

      <div className="mt-6 p-4 bg-yellow-50 border-2 border-yellow-400 rounded-lg">
        <p className="text-sm text-yellow-900">
          <strong>Note:</strong> After selecting a phrase, you still need to confirm
          before it is spoken. This ensures you always have control.
        </p>
      </div>
    </div>
  );
}
