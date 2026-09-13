// SignalComposer — Word fragment chips with add/remove + microphone for speech input.
//
// Features:
// - Display fragment chips with × remove button
// - + Add button to add new fragments
// - Microphone button for speech input (POST /stt)
// - Large touch targets, keyboard accessible

import { useState } from "react";
import { Microphone, Plus, X } from "@phosphor-icons/react";
import { stt, type STTRequest } from "../../lib/api";

interface SignalComposerProps {
  fragments: string[];
  onAddFragment: (fragment: string) => void;
  onRemoveFragment: (fragment: string) => void;
}

export function SignalComposer({
  fragments,
  onAddFragment,
  onRemoveFragment,
}: SignalComposerProps) {
  const [isRecording, setIsRecording] = useState(false);
  const [inputValue, setInputValue] = useState("");
  const [showInput, setShowInput] = useState(false);

  // Handle text input submission
  const handleAddClick = () => {
    if (inputValue.trim()) {
      onAddFragment(inputValue.trim());
      setInputValue("");
      setShowInput(false);
    } else {
      setShowInput(true);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && inputValue.trim()) {
      onAddFragment(inputValue.trim());
      setInputValue("");
      setShowInput(false);
    } else if (e.key === "Escape") {
      setInputValue("");
      setShowInput(false);
    }
  };

  // Handle microphone recording
  const handleMicClick = async () => {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      alert("Microphone access not supported in this browser");
      return;
    }

    if (isRecording) {
      // Stop recording (simplified - full implementation would need MediaRecorder)
      setIsRecording(false);
      return;
    }

    try {
      setIsRecording(true);
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      const mediaRecorder = new MediaRecorder(stream);
      const chunks: Blob[] = [];

      mediaRecorder.ondataavailable = (e) => {
        chunks.push(e.data);
      };

      mediaRecorder.onstop = async () => {
        const blob = new Blob(chunks, { type: "audio/webm" });
        const reader = new FileReader();
        
        reader.onloadend = async () => {
          const base64Audio = (reader.result as string).split(",")[1];
          
          try {
            const response = await stt({ audio_base64: base64Audio } as STTRequest);
            if (response.text) {
              // Split by spaces and add each word as a fragment
              const words = response.text.trim().split(/\s+/);
              words.forEach((word) => onAddFragment(word));
            }
          } catch (error) {
            console.error("STT failed:", error);
          }
        };
        
        reader.readAsDataURL(blob);
        stream.getTracks().forEach((track) => track.stop());
        setIsRecording(false);
      };

      mediaRecorder.start();
      
      // Auto-stop after 5 seconds
      setTimeout(() => {
        if (mediaRecorder.state === "recording") {
          mediaRecorder.stop();
        }
      }, 5000);
    } catch (error) {
      console.error("Microphone access failed:", error);
      setIsRecording(false);
    }
  };

  return (
    <div className="space-y-4">
      {/* Fragment chips */}
      <div
        className="flex flex-wrap gap-2 min-h-[60px] p-4 bg-gray-50 rounded-lg border-2 border-gray-200"
        role="list"
        aria-label="Your word clues"
      >
        {fragments.length === 0 && (
          <span className="text-gray-400 text-sm">No clues yet. Add words to help Intentra understand.</span>
        )}
        {fragments.map((fragment, index) => (
          <div
            key={`${fragment}-${index}`}
            className="flex items-center gap-2 px-4 py-2 bg-blue-100 text-blue-900 rounded-full text-lg font-medium"
            role="listitem"
          >
            <span>{fragment}</span>
            <button
              type="button"
              onClick={() => onRemoveFragment(fragment)}
              className="flex items-center justify-center w-6 h-6 rounded-full hover:bg-blue-200 focus:outline-none focus:ring-2 focus:ring-blue-400 transition-colors"
              aria-label={`Remove ${fragment}`}
            >
              <X size={16} weight="bold" />
            </button>
          </div>
        ))}
      </div>

      {/* Input row with conditional text input */}
      {showInput && (
        <div className="flex gap-3">
          <input
            type="text"
            value={inputValue}
            onChange={(e) => setInputValue(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Type a word..."
            className="flex-1 px-4 py-3 text-lg border-2 border-blue-400 rounded-lg focus:outline-none focus:ring-4 focus:ring-blue-400"
            autoFocus
            aria-label="Add word clue"
          />
          <button
            type="button"
            onClick={() => {
              setInputValue("");
              setShowInput(false);
            }}
            className="px-6 py-3 bg-gray-300 text-gray-700 rounded-lg font-medium hover:bg-gray-400 focus:outline-none focus:ring-4 focus:ring-gray-400 transition-colors"
          >
            Cancel
          </button>
        </div>
      )}

      {/* Action buttons */}
      {!showInput && (
        <div className="flex gap-3">
          <button
            type="button"
            onClick={handleAddClick}
            className="flex-1 flex items-center justify-center gap-2 px-6 py-4 bg-blue-600 text-white rounded-lg text-lg font-medium hover:bg-blue-700 focus:outline-none focus:ring-4 focus:ring-blue-400 focus:ring-offset-2 transition-colors"
            aria-label="Add word clue"
          >
            <Plus size={24} weight="bold" />
            <span>Add Word</span>
          </button>

          <button
            type="button"
            onClick={handleMicClick}
            className={`flex items-center justify-center gap-2 px-6 py-4 rounded-lg text-lg font-medium focus:outline-none focus:ring-4 focus:ring-offset-2 transition-colors ${
              isRecording
                ? "bg-red-600 text-white hover:bg-red-700 focus:ring-red-400 animate-pulse"
                : "bg-gray-700 text-white hover:bg-gray-800 focus:ring-gray-400"
            }`}
            aria-label={isRecording ? "Recording... Click to stop" : "Record speech"}
            aria-pressed={isRecording}
          >
            <Microphone size={24} weight={isRecording ? "fill" : "bold"} />
            <span className="hidden sm:inline">
              {isRecording ? "Recording..." : "Speak"}
            </span>
          </button>
        </div>
      )}
    </div>
  );
}

export default SignalComposer;
