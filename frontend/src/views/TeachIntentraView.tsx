// TeachIntentraView — Guided flow to teach Intentra about communication preferences
//
// Questions covering: preferred help phrases, names for family, phrases to avoid,
// response length, tired communication style, hardest situations, important people,
// yes/no signals, emergency phrases
//
// Three input modes: Speak (POST /stt), Type (text input), Choose words (word chips)
// Skip option per question
// After each answer: show "Saved to your Communication Passport" confirmation

import { useState } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { 
  Microphone, 
  CheckCircle, 
  ArrowRight, 
  ArrowLeft,
  X,
  Plus,
  ChatCircle
} from "@phosphor-icons/react";
import { 
  stt, 
  addPassportPreference, 
  addPassportAvoid,
  type STTRequest 
} from "../lib/api";
import { DUR, EASE_OUT } from "../lib/motion";

const PERSON_ID = "elena";

type InputMode = "speak" | "type" | "chips";
type QuestionType = "preference" | "avoid" | "info";

interface Question {
  id: string;
  text: string;
  type: QuestionType;
  placeholder?: string;
  suggestedWords?: string[];
}

const QUESTIONS: Question[] = [
  {
    id: "help_phrases",
    text: "What are your preferred ways to ask for help?",
    type: "preference",
    placeholder: "e.g., 'I need assistance', 'Can you help me?'",
    suggestedWords: ["help", "assistance", "support", "please", "need"]
  },
  {
    id: "family_names",
    text: "What are the names of important people in your life?",
    type: "info",
    placeholder: "e.g., 'Sofia', 'Mom', 'Dr. Chen'",
    suggestedWords: []
  },
  {
    id: "avoided_phrases",
    text: "Are there any phrases you would never use?",
    type: "avoid",
    placeholder: "e.g., phrases that don't sound like you",
    suggestedWords: []
  },
  {
    id: "response_length",
    text: "Do you prefer short or detailed responses?",
    type: "preference",
    placeholder: "e.g., 'Keep it brief', 'Give me details'",
    suggestedWords: ["short", "brief", "detailed", "concise", "full"]
  },
  {
    id: "tired_style",
    text: "How do you communicate when you're tired?",
    type: "preference",
    placeholder: "e.g., 'One word answers', 'Very direct'",
    suggestedWords: ["tired", "simple", "direct", "minimal", "short"]
  },
  {
    id: "hard_situations",
    text: "What are the hardest situations for you to communicate in?",
    type: "info",
    placeholder: "e.g., 'When I'm in pain', 'In noisy places'",
    suggestedWords: ["pain", "noisy", "tired", "emergency", "stressed"]
  },
  {
    id: "yes_no_signals",
    text: "How do you signal yes and no?",
    type: "preference",
    placeholder: "e.g., 'Thumbs up/down', 'Nod/shake head'",
    suggestedWords: ["yes", "no", "nod", "thumbs", "blink"]
  },
  {
    id: "emergency_phrases",
    text: "What phrases do you need for emergencies?",
    type: "preference",
    placeholder: "e.g., 'I need help', 'Call my doctor'",
    suggestedWords: ["help", "emergency", "pain", "doctor", "caregiver", "family"]
  }
];

export default function TeachIntentraView() {
  const [currentIndex, setCurrentIndex] = useState(0);
  const [inputMode, setInputMode] = useState<InputMode>("type");
  const [textInput, setTextInput] = useState("");
  const [chips, setChips] = useState<string[]>([]);
  const [isRecording, setIsRecording] = useState(false);
  const [saving, setSaving] = useState(false);
  const [showSaved, setShowSaved] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const currentQuestion = QUESTIONS[currentIndex];
  const isFirst = currentIndex === 0;
  const isLast = currentIndex === QUESTIONS.length - 1;

  const handleMicClick = async () => {
    if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      setError("Microphone access not supported in this browser");
      return;
    }

    if (isRecording) {
      setIsRecording(false);
      return;
    }

    try {
      setIsRecording(true);
      setError(null);
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
              setTextInput(response.text);
              setInputMode("type");
            }
          } catch (err) {
            setError("Speech recognition failed. Please try again.");
            console.error("STT failed:", err);
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
    } catch (err) {
      setError("Microphone access denied. Please enable microphone permissions.");
      setIsRecording(false);
      console.error("Microphone access failed:", err);
    }
  };

  const handleAddChip = (word: string) => {
    if (word.trim() && !chips.includes(word.trim())) {
      setChips([...chips, word.trim()]);
    }
  };

  const handleRemoveChip = (word: string) => {
    setChips(chips.filter((c) => c !== word));
  };

  const handleSave = async () => {
    setError(null);
    
    // Get answer text from current input mode
    let answerText = "";
    if (inputMode === "type") {
      answerText = textInput.trim();
    } else if (inputMode === "chips") {
      answerText = chips.join(", ");
    }

    if (!answerText) {
      return; // Empty answer, don't save
    }

    setSaving(true);

    try {
      // Save to passport based on question type
      if (currentQuestion.type === "preference") {
        await addPassportPreference({
          person_id: PERSON_ID,
          expression: answerText
        });
      } else if (currentQuestion.type === "avoid") {
        await addPassportAvoid({
          person_id: PERSON_ID,
          expression: answerText
        });
      } else {
        // For "info" type, save as preference for now
        await addPassportPreference({
          person_id: PERSON_ID,
          expression: answerText
        });
      }

      // Show success feedback
      setShowSaved(true);
      setTimeout(() => {
        setShowSaved(false);
        handleNext();
      }, 1500);
    } catch (err) {
      setError("Failed to save answer. Please try again.");
      console.error("Save failed:", err);
    } finally {
      setSaving(false);
    }
  };

  const handleSkip = () => {
    handleNext();
  };

  const handleNext = () => {
    if (isLast) {
      // Could redirect to passport or show completion
      window.location.href = "/passport";
    } else {
      setCurrentIndex(currentIndex + 1);
      resetInputs();
    }
  };

  const handlePrevious = () => {
    if (!isFirst) {
      setCurrentIndex(currentIndex - 1);
      resetInputs();
    }
  };

  const resetInputs = () => {
    setTextInput("");
    setChips([]);
    setInputMode("type");
    setError(null);
    setShowSaved(false);
  };

  return (
    <div className="h-full overflow-y-auto bg-ink">
      <div className="mx-auto max-w-3xl p-4 sm:p-6 lg:p-8">
        <motion.header
          initial={{ opacity: 0, y: -12 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: DUR.base, ease: EASE_OUT }}
          className="mb-8"
        >
          <h1 className="m-0 mb-2 font-ui text-[1.75rem] font-bold text-text sm:text-[2rem]">
            Teach Intentra
          </h1>
          <p className="m-0 font-ui text-aac-base text-text-muted">
            Help Intentra learn how you communicate. Answer as many questions as you like — you can always come back later.
          </p>
        </motion.header>

        {/* Progress indicator */}
        <div className="mb-8">
          <div className="flex items-center justify-between mb-2">
            <span className="font-mono text-[0.85rem] text-text-muted">
              Question {currentIndex + 1} of {QUESTIONS.length}
            </span>
            <span className="font-mono text-[0.85rem] text-text-muted">
              {Math.round(((currentIndex + 1) / QUESTIONS.length) * 100)}%
            </span>
          </div>
          <div className="h-2 w-full rounded-full bg-ink-line overflow-hidden">
            <motion.div
              className="h-full bg-voice"
              initial={{ width: 0 }}
              animate={{ width: `${((currentIndex + 1) / QUESTIONS.length) * 100}%` }}
              transition={{ duration: 0.3, ease: EASE_OUT }}
            />
          </div>
        </div>

        <AnimatePresence mode="wait">
          <motion.div
            key={currentQuestion.id}
            initial={{ opacity: 0, x: 20 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -20 }}
            transition={{ duration: DUR.base, ease: EASE_OUT }}
            className="rounded-xl border border-ink-line bg-ink-raised p-6 shadow-card sm:p-8"
          >
            {/* Question */}
            <div className="mb-6">
              <div className="mb-4 flex items-start gap-3">
                <div
                  aria-hidden
                  className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-voice-soft text-voice"
                >
                  <ChatCircle size={24} weight="duotone" />
                </div>
                <h2 className="m-0 font-ui text-[1.3rem] font-semibold text-text leading-tight">
                  {currentQuestion.text}
                </h2>
              </div>
            </div>

            {/* Input mode selector */}
            <div className="mb-6 flex gap-2">
              <button
                type="button"
                onClick={() => setInputMode("type")}
                className={`flex-1 rounded-lg px-4 py-2.5 font-ui text-[0.9rem] font-medium transition-colors ${
                  inputMode === "type"
                    ? "bg-voice text-on-voice shadow-sm"
                    : "bg-ink-sunken text-text-muted hover:bg-ink-line"
                }`}
              >
                Type
              </button>
              <button
                type="button"
                onClick={() => setInputMode("speak")}
                className={`flex-1 rounded-lg px-4 py-2.5 font-ui text-[0.9rem] font-medium transition-colors ${
                  inputMode === "speak"
                    ? "bg-voice text-on-voice shadow-sm"
                    : "bg-ink-sunken text-text-muted hover:bg-ink-line"
                }`}
              >
                Speak
              </button>
              {currentQuestion.suggestedWords && currentQuestion.suggestedWords.length > 0 && (
                <button
                  type="button"
                  onClick={() => setInputMode("chips")}
                  className={`flex-1 rounded-lg px-4 py-2.5 font-ui text-[0.9rem] font-medium transition-colors ${
                    inputMode === "chips"
                      ? "bg-voice text-on-voice shadow-sm"
                      : "bg-ink-sunken text-text-muted hover:bg-ink-line"
                  }`}
                >
                  Choose Words
                </button>
              )}
            </div>

            {/* Input area */}
            <div className="mb-6">
              {inputMode === "type" && (
                <textarea
                  value={textInput}
                  onChange={(e) => setTextInput(e.target.value)}
                  placeholder={currentQuestion.placeholder}
                  className="w-full min-h-[120px] rounded-lg border-2 border-ink-line bg-ink px-4 py-3 font-ui text-aac-base text-text placeholder:text-text-faint focus:border-voice focus:outline-none focus:ring-2 focus:ring-voice/30 resize-none"
                  autoFocus
                />
              )}

              {inputMode === "speak" && (
                <div className="flex flex-col items-center gap-4 py-8">
                  <button
                    type="button"
                    onClick={handleMicClick}
                    className={`flex h-24 w-24 items-center justify-center rounded-full font-medium transition-all shadow-lg ${
                      isRecording
                        ? "bg-red-500 text-white animate-pulse scale-110"
                        : "bg-voice text-on-voice hover:scale-105"
                    }`}
                    aria-label={isRecording ? "Recording... Click to stop" : "Start recording"}
                  >
                    <Microphone size={40} weight={isRecording ? "fill" : "bold"} />
                  </button>
                  <p className="font-ui text-aac-base text-text-muted">
                    {isRecording ? "Recording... (auto-stops after 5s)" : "Tap to start recording"}
                  </p>
                  {textInput && (
                    <div className="w-full rounded-lg border border-ink-line bg-ink-sunken p-4">
                      <p className="m-0 font-ui text-aac-base text-text">{textInput}</p>
                    </div>
                  )}
                </div>
              )}

              {inputMode === "chips" && (
                <div>
                  {/* Selected chips */}
                  <div className="mb-4 min-h-[80px] rounded-lg border-2 border-ink-line bg-ink p-3">
                    {chips.length === 0 ? (
                      <p className="m-0 text-center font-ui text-[0.9rem] text-text-faint italic">
                        Choose words below to build your answer
                      </p>
                    ) : (
                      <div className="flex flex-wrap gap-2">
                        {chips.map((chip, i) => (
                          <div
                            key={`${chip}-${i}`}
                            className="flex items-center gap-2 rounded-full bg-voice-soft px-4 py-2 font-ui text-[0.95rem] font-medium text-voice-deep"
                          >
                            <span>{chip}</span>
                            <button
                              type="button"
                              onClick={() => handleRemoveChip(chip)}
                              className="flex h-5 w-5 items-center justify-center rounded-full hover:bg-voice/20 transition-colors"
                              aria-label={`Remove ${chip}`}
                            >
                              <X size={14} weight="bold" />
                            </button>
                          </div>
                        ))}
                      </div>
                    )}
                  </div>

                  {/* Suggested words */}
                  {currentQuestion.suggestedWords && currentQuestion.suggestedWords.length > 0 && (
                    <div>
                      <p className="mb-2 font-ui text-[0.85rem] font-medium text-text-muted uppercase tracking-wide">
                        Suggested Words
                      </p>
                      <div className="flex flex-wrap gap-2">
                        {currentQuestion.suggestedWords.map((word) => (
                          <button
                            key={word}
                            type="button"
                            onClick={() => handleAddChip(word)}
                            disabled={chips.includes(word)}
                            className={`flex items-center gap-1.5 rounded-full px-4 py-2 font-ui text-[0.95rem] font-medium transition-colors ${
                              chips.includes(word)
                                ? "bg-ink-line text-text-faint cursor-not-allowed"
                                : "bg-ink-sunken text-text hover:bg-ink-line"
                            }`}
                          >
                            {!chips.includes(word) && <Plus size={16} weight="bold" />}
                            {word}
                          </button>
                        ))}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Error message */}
            {error && (
              <motion.div
                initial={{ opacity: 0, y: -10 }}
                animate={{ opacity: 1, y: 0 }}
                className="mb-6 rounded-lg border border-red-300 bg-red-50 p-4"
              >
                <p className="m-0 font-ui text-[0.9rem] text-red-800">{error}</p>
              </motion.div>
            )}

            {/* Saved confirmation */}
            <AnimatePresence>
              {showSaved && (
                <motion.div
                  initial={{ opacity: 0, scale: 0.9 }}
                  animate={{ opacity: 1, scale: 1 }}
                  exit={{ opacity: 0, scale: 0.9 }}
                  className="mb-6 flex items-center justify-center gap-3 rounded-lg border border-green-300 bg-green-50 p-4"
                >
                  <CheckCircle size={24} weight="fill" className="text-green-600" />
                  <p className="m-0 font-ui text-aac-base font-medium text-green-800">
                    Saved to your Communication Passport
                  </p>
                </motion.div>
              )}
            </AnimatePresence>

            {/* Action buttons */}
            <div className="flex flex-col gap-3 sm:flex-row">
              {!isFirst && (
                <button
                  type="button"
                  onClick={handlePrevious}
                  disabled={saving || showSaved}
                  className="flex items-center justify-center gap-2 rounded-lg border border-ink-line bg-ink-sunken px-6 py-3.5 font-ui text-aac-base font-medium text-text transition-colors hover:bg-ink-line disabled:opacity-50 disabled:cursor-not-allowed"
                >
                  <ArrowLeft size={20} weight="bold" />
                  Previous
                </button>
              )}
              
              <button
                type="button"
                onClick={handleSkip}
                disabled={saving || showSaved}
                className="flex-1 rounded-lg border border-ink-line bg-ink px-6 py-3.5 font-ui text-aac-base font-medium text-text-muted transition-colors hover:bg-ink-sunken disabled:opacity-50 disabled:cursor-not-allowed"
              >
                Skip
              </button>

              <button
                type="button"
                onClick={handleSave}
                disabled={
                  saving || 
                  showSaved || 
                  (inputMode === "type" && !textInput.trim()) ||
                  (inputMode === "chips" && chips.length === 0)
                }
                className="flex-1 flex items-center justify-center gap-2 rounded-lg bg-voice px-6 py-3.5 font-ui text-aac-base font-semibold text-on-voice shadow-card transition-all hover:bg-voice-deep disabled:opacity-50 disabled:cursor-not-allowed disabled:shadow-none"
              >
                {saving ? "Saving..." : isLast ? "Finish" : "Save & Continue"}
                {!saving && <ArrowRight size={20} weight="bold" />}
              </button>
            </div>
          </motion.div>
        </AnimatePresence>

        {/* Footer note */}
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: 0.3 }}
          className="mt-6 text-center"
        >
          <p className="m-0 font-ui text-[0.9rem] text-text-muted">
            Your answers are saved to your Communication Passport. You can update them anytime.
          </p>
        </motion.div>
      </div>
    </div>
  );
}
