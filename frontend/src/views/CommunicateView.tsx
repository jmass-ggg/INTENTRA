// CommunicateView — Primary screen for the Intentra communication flow.
//
// Assembles:
// - Listener display (who you're talking to + their last statement)
// - IntentSelector (Answer, Ask, Request, Explain buttons)
// - SignalComposer (word fragments + speech input)
// - ExpressionPreview (generated expression + Speak/Edit buttons)
// - CommunicationOutcome (post-speaking feedback)
//
// Shows clarification panel when state is needs_clarification
// Shows MEDIUM-confidence alternatives as choice buttons when applicable
// Clean layout: calm, high-contrast, large touch targets, no graph/brain elements
//
// Supports adaptive effort modes:
// - full: show all controls
// - assist: simplified controls (intent buttons + frequent phrases + speak)
// - low_effort: only large YES/NO/HELP/MORE/STOP/PAIN/HOME/DRINK/TOILET buttons
// - emergency: render EmergencyBoard exclusively
//
// Requirements: 17.1, 17.2, 17.3, 17.5, 17.6, 17.7, 11.2, 11.3, 11.4, 11.5

import { useState, useEffect } from "react";
import { User, ChatCircle, Question, ArrowsClockwise } from "@phosphor-icons/react";
import { IntentSelector } from "../components/communication/IntentSelector";
import { SignalComposer } from "../components/communication/SignalComposer";
import { ExpressionPreview } from "../components/communication/ExpressionPreview";
import { CommunicationOutcome } from "../components/communication/CommunicationOutcome";
import { FastResponses } from "../components/communication/FastResponses";
import { EffortModeSelector, type EffortMode } from "../components/accessibility/EffortModeSelector";
import { EmergencyBoard } from "../components/accessibility/EmergencyBoard";
import { useCommunication } from "../hooks/useCommunication";
import type { IntentType } from "../lib/api";
import { API_BASE } from "../lib/api";

// Default person ID (matches demo persona)
const PERSON_ID = "elena";

// Low effort buttons
const LOW_EFFORT_BUTTONS = [
  { label: "YES", value: "yes" },
  { label: "NO", value: "no" },
  { label: "HELP", value: "help" },
  { label: "MORE", value: "more" },
  { label: "STOP", value: "stop" },
  { label: "PAIN", value: "pain" },
  { label: "HOME", value: "home" },
  { label: "DRINK", value: "drink" },
  { label: "TOILET", value: "toilet" },
];

export default function CommunicateView() {
  const {
    state,
    input,
    dispatch,
    speak,
    generate,
    recordOutcome,
    initiateRepair,
    checkFastResponse,
  } = useCommunication(PERSON_ID);

  // Effort mode state
  const [effortMode, setEffortMode] = useState<EffortMode>("full");
  const [showEffortModeSelector, setShowEffortModeSelector] = useState(false);

  // Load effort mode from API on mount
  useEffect(() => {
    const loadEffortMode = async () => {
      try {
        const response = await fetch(
          `${API_BASE}/accessibility/${encodeURIComponent(PERSON_ID)}`
        );
        if (response.ok) {
          const data = await response.json();
          if (data.effort_mode) {
            setEffortMode(data.effort_mode as EffortMode);
          }
        }
      } catch (err) {
        console.error("Failed to load effort mode:", err);
        // Keep default "full" mode
      }
    };

    loadEffortMode();
  }, []);

  // Save effort mode to API when changed
  const handleEffortModeChange = async (mode: EffortMode) => {
    setEffortMode(mode);
    setShowEffortModeSelector(false);

    try {
      await fetch(`${API_BASE}/accessibility/${encodeURIComponent(PERSON_ID)}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ effort_mode: mode }),
      });
    } catch (err) {
      console.error("Failed to save effort mode:", err);
    }
  };

  // UI-only state for listener display (static for now, will be dynamic in future tasks)
  const listenerName = "Sofia";
  const partnerStatement = "Would you like me to come tonight?";
  const [showPartnerInput, setShowPartnerInput] = useState(false);
  const [partnerInputValue, setPartnerInputValue] = useState("");

  // Handle intent selection
  const handleIntentSelect = (intent: IntentType) => {
    dispatch({ type: "SET_INTENT", intent });
    // Auto-start input capture when intent is selected
    if (state.status === "idle") {
      dispatch({ type: "START_INPUT" });
    }
  };

  // Handle fragment management
  const handleAddFragment = (fragment: string) => {
    dispatch({ type: "ADD_FRAGMENT", fragment });
  };

  const handleRemoveFragment = (fragment: string) => {
    dispatch({ type: "REMOVE_FRAGMENT", fragment });
  };

  // Handle expression actions
  const handleSpeak = async (text: string) => {
    dispatch({ type: "CONFIRM_SPEAK" });
    await speak(text);
  };

  const handleEdit = (text: string) => {
    dispatch({ type: "EDIT_EXPRESSION", text });
  };

  // Handle outcome
  const handleSuccess = async () => {
    await recordOutcome(true);
  };

  const handleFailure = async () => {
    await recordOutcome(false);
    await initiateRepair();
  };

  // Handle clarification
  const handleClarificationAnswer = (answer: string) => {
    dispatch({ type: "CLARIFY", answer });
    // In real implementation, would re-trigger generation with the answer
    // For now, just transition state
  };

  // Handle alternative selection
  const handleSelectAlternative = (text: string) => {
    dispatch({ type: "SELECT_ALTERNATIVE", text });
  };

  // Handle partner speech (for fast response)
  const handlePartnerSpeech = async (speech: string) => {
    await checkFastResponse(speech);
  };

  // Handle fast response selection
  const handleFastResponseSelect = async (option: string) => {
    dispatch({ type: "FAST_RESPONSE_SELECTED", option });
    // Auto-generate after fast response selection
    await generate();
  };

  // Handle bypassing fast response
  const handleBypassFastResponse = () => {
    dispatch({ type: "BYPASS_FAST_RESPONSE" });
  };

  // Handle partner speech input submission
  const handlePartnerInputSubmit = async () => {
    if (partnerInputValue.trim()) {
      await handlePartnerSpeech(partnerInputValue.trim());
      setPartnerInputValue("");
      setShowPartnerInput(false);
    }
  };

  // Handle generate
  const handleGenerate = async () => {
    if (input.fragments.length > 0) {
      await generate();
    }
  };

  // Handle low effort button press
  const handleLowEffortButton = (value: string) => {
    dispatch({ type: "ADD_FRAGMENT", fragment: value });
    // Auto-generate for low effort mode
    dispatch({ type: "START_INPUT" });
    setTimeout(() => {
      generate();
    }, 100);
  };

  // Handle emergency phrase selection
  const handleEmergencyPhrase = (phrase: string) => {
    // Add as fragment and mark as emergency so it generates immediately
    dispatch({ type: "ADD_FRAGMENT", fragment: phrase });
    dispatch({ type: "EDIT_EXPRESSION", text: phrase });
  };

  // Determine if we're ready to generate
  const canGenerate =
    input.fragments.length > 0 &&
    state.status !== "understanding_intent" &&
    state.status !== "generating_expression" &&
    state.status !== "speaking";

  // Determine if expression preview should be shown
  const showExpressionPreview =
    state.status === "ready_for_confirmation" ||
    state.status === "awaiting_outcome";

  // Emergency mode: render only emergency board
  if (effortMode === "emergency") {
    return (
      <div className="flex min-h-full flex-col gap-6 p-4 lg:p-6 max-w-5xl mx-auto">
        <header className="flex items-center justify-between">
          <h1 className="text-3xl font-bold text-red-600">Emergency Communication</h1>
          <button
            type="button"
            onClick={() => setShowEffortModeSelector(!showEffortModeSelector)}
            className="px-4 py-2 bg-gray-200 hover:bg-gray-300 rounded-lg text-sm font-medium transition-colors"
            aria-label="Change effort mode"
          >
            Change Mode
          </button>
        </header>

        {showEffortModeSelector && (
          <section className="p-4 bg-white rounded-xl border-2 border-gray-300 shadow-lg">
            <EffortModeSelector
              currentMode={effortMode}
              onModeChange={handleEffortModeChange}
            />
          </section>
        )}

        {showExpressionPreview && state.status === "ready_for_confirmation" ? (
          <section aria-label="Review your expression">
            <ExpressionPreview
              expression={state.expression}
              confidence={state.confidence}
              isReady={state.status === "ready_for_confirmation"}
              onSpeak={handleSpeak}
              onEdit={handleEdit}
            />
          </section>
        ) : state.status === "awaiting_outcome" ? (
          <section aria-label="Communication outcome">
            <CommunicationOutcome
              onSuccess={handleSuccess}
              onFailure={handleFailure}
            />
          </section>
        ) : (
          <EmergencyBoard personId={PERSON_ID} onPhraseSelect={handleEmergencyPhrase} />
        )}
      </div>
    );
  }

  // Low effort mode: render only large essential buttons
  if (effortMode === "low_effort") {
    return (
      <div className="flex min-h-full flex-col gap-6 p-4 lg:p-6 max-w-5xl mx-auto">
        <header className="flex items-center justify-between">
          <h1 className="text-3xl font-bold text-gray-900">Communicate</h1>
          <button
            type="button"
            onClick={() => setShowEffortModeSelector(!showEffortModeSelector)}
            className="px-4 py-2 bg-gray-200 hover:bg-gray-300 rounded-lg text-sm font-medium transition-colors"
            aria-label="Change effort mode"
          >
            Change Mode
          </button>
        </header>

        {showEffortModeSelector && (
          <section className="p-4 bg-white rounded-xl border-2 border-gray-300 shadow-lg">
            <EffortModeSelector
              currentMode={effortMode}
              onModeChange={handleEffortModeChange}
            />
          </section>
        )}

        {showExpressionPreview && state.status === "ready_for_confirmation" ? (
          <section aria-label="Review your expression">
            <ExpressionPreview
              expression={state.expression}
              confidence={state.confidence}
              isReady={state.status === "ready_for_confirmation"}
              onSpeak={handleSpeak}
              onEdit={handleEdit}
            />
          </section>
        ) : state.status === "awaiting_outcome" ? (
          <section aria-label="Communication outcome">
            <CommunicationOutcome
              onSuccess={handleSuccess}
              onFailure={handleFailure}
            />
          </section>
        ) : (
          <section aria-label="Essential communication buttons">
            <h2 className="text-2xl font-bold text-gray-900 mb-4 text-center">
              Tap to communicate
            </h2>
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-4">
              {LOW_EFFORT_BUTTONS.map((button) => (
                <button
                  key={button.value}
                  type="button"
                  onClick={() => handleLowEffortButton(button.value)}
                  className="
                    p-8 rounded-xl
                    bg-blue-600 text-white
                    hover:bg-blue-700 active:bg-blue-800
                    text-2xl font-bold
                    min-h-[120px]
                    transition-all duration-200
                    hover:scale-105 active:scale-95
                    shadow-lg hover:shadow-xl
                    focus:outline-none focus:ring-4 focus:ring-blue-400
                  "
                  aria-label={button.label}
                >
                  {button.label}
                </button>
              ))}
            </div>
          </section>
        )}
      </div>
    );
  }

  return (
    <div className="flex min-h-full flex-col gap-6 p-4 lg:p-6 max-w-5xl mx-auto">
      {/* Header */}
      <header className="flex items-center justify-between gap-4">
        <div>
          <h1 className="text-3xl font-bold text-gray-900">Communicate</h1>
          <p className="text-gray-600">
            {effortMode === "assist"
              ? "Simplified controls to help you communicate easily."
              : "Build your message with words and signals. Intentra will help you express it."}
          </p>
        </div>
        <button
          type="button"
          onClick={() => setShowEffortModeSelector(!showEffortModeSelector)}
          className="px-4 py-2 bg-gray-200 hover:bg-gray-300 rounded-lg text-sm font-medium transition-colors shrink-0"
          aria-label="Change effort mode"
        >
          {effortMode === "full" ? "⚡ Full" : effortMode === "assist" ? "🤝 Assist" : "Mode"}
        </button>
      </header>

      {/* Effort mode selector (collapsible) */}
      {showEffortModeSelector && (
        <section className="p-4 bg-white rounded-xl border-2 border-gray-300 shadow-lg">
          <EffortModeSelector
            currentMode={effortMode}
            onModeChange={handleEffortModeChange}
          />
        </section>
      )}

      {/* Listener display */}
      <section
        className="p-5 bg-blue-50 rounded-xl border-2 border-blue-200"
        aria-label="Current conversation context"
      >
        <div className="flex items-center gap-3 mb-3">
          <div className="flex items-center justify-center w-12 h-12 bg-blue-200 rounded-full">
            <User size={28} weight="bold" className="text-blue-700" />
          </div>
          <div>
            <h2 className="text-lg font-bold text-gray-900">Talking with {listenerName}</h2>
          </div>
        </div>
        {partnerStatement && (
          <div className="flex items-start gap-3 mt-3 p-4 bg-white rounded-lg border border-blue-200">
            <ChatCircle
              size={24}
              weight="fill"
              className="text-blue-600 shrink-0 mt-1"
            />
            <div className="flex-1">
              <p className="text-sm font-semibold text-gray-700 mb-1">
                {listenerName} said:
              </p>
              <p className="text-lg text-gray-900">"{partnerStatement}"</p>
            </div>
            {state.status === "idle" && (
              <button
                type="button"
                onClick={() => handlePartnerSpeech(partnerStatement)}
                className="px-4 py-2 bg-emerald-600 text-white text-sm font-medium rounded-lg hover:bg-emerald-700 focus:outline-none focus:ring-2 focus:ring-emerald-400 transition-colors shrink-0"
              >
                Quick Response
              </button>
            )}
          </div>
        )}
        
        {/* Partner speech input (for testing) */}
        {showPartnerInput && (
          <div className="mt-3 flex gap-2">
            <input
              type="text"
              value={partnerInputValue}
              onChange={(e) => setPartnerInputValue(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  handlePartnerInputSubmit();
                } else if (e.key === "Escape") {
                  setShowPartnerInput(false);
                  setPartnerInputValue("");
                }
              }}
              placeholder="What did they say?"
              className="flex-1 px-4 py-2 text-base border-2 border-blue-400 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-400"
              autoFocus
            />
            <button
              type="button"
              onClick={handlePartnerInputSubmit}
              className="px-4 py-2 bg-emerald-600 text-white text-sm font-medium rounded-lg hover:bg-emerald-700 focus:outline-none focus:ring-2 focus:ring-emerald-400"
            >
              Check
            </button>
            <button
              type="button"
              onClick={() => {
                setShowPartnerInput(false);
                setPartnerInputValue("");
              }}
              className="px-4 py-2 bg-gray-300 text-gray-700 text-sm font-medium rounded-lg hover:bg-gray-400"
            >
              Cancel
            </button>
          </div>
        )}
        
        {!showPartnerInput && state.status === "idle" && (
          <button
            type="button"
            onClick={() => setShowPartnerInput(true)}
            className="mt-3 w-full px-4 py-2 bg-white text-blue-700 text-sm font-medium rounded-lg border-2 border-blue-300 hover:bg-blue-50 focus:outline-none focus:ring-2 focus:ring-blue-400"
          >
            + Add partner speech to check for quick response
          </button>
        )}
      </section>

      {/* Main content area */}
      <div className="flex flex-col gap-6">
        {/* Fast response panel (shown when fast_response_ready) */}
        {state.status === "fast_response_ready" && (
          <>
            <FastResponses
              type={state.responseType}
              options={state.options}
              onSelect={handleFastResponseSelect}
            />
            <div className="text-center">
              <button
                type="button"
                onClick={handleBypassFastResponse}
                className="px-6 py-3 bg-gray-200 hover:bg-gray-300 rounded-lg text-sm font-medium transition-colors"
              >
                Or, build a custom message
              </button>
            </div>
          </>
        )}

        {/* Clarification panel (shown when needs_clarification) */}
        {state.status === "needs_clarification" && (
          <section
            className="p-6 bg-amber-50 rounded-xl border-2 border-amber-300 shadow-md"
            aria-label="Clarification needed"
          >
            <div className="flex items-start gap-3 mb-4">
              <Question size={32} weight="bold" className="text-amber-700 shrink-0" />
              <div>
                <h3 className="text-xl font-bold text-gray-900 mb-2">
                  I need to understand better
                </h3>
                <p className="text-lg text-gray-800">{state.question}</p>
              </div>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {state.options.map((option, index) => (
                <button
                  key={index}
                  type="button"
                  onClick={() => handleClarificationAnswer(option)}
                  className="px-6 py-4 bg-white text-gray-900 rounded-lg border-2 border-amber-300 text-lg font-medium hover:bg-amber-100 hover:border-amber-400 focus:outline-none focus:ring-4 focus:ring-amber-400 transition-colors"
                >
                  {option}
                </button>
              ))}
            </div>
          </section>
        )}

        {/* Intent selector (hidden in assist mode to simplify) */}
        {effortMode === "full" &&
          state.status !== "awaiting_outcome" &&
          state.status !== "speaking" &&
          state.status !== "needs_clarification" &&
          state.status !== "fast_response_ready" && (
            <section aria-label="Select your intent">
              <h3 className="text-xl font-bold text-gray-900 mb-4">
                What are you trying to do?
              </h3>
              <IntentSelector
                selectedIntent={input.intentType}
                onSelect={handleIntentSelect}
              />
            </section>
          )}

        {/* Signal composer */}
        {state.status !== "awaiting_outcome" &&
          state.status !== "speaking" &&
          state.status !== "needs_clarification" &&
          state.status !== "fast_response_ready" && (
            <section aria-label="Add your clues">
              <h3 className="text-xl font-bold text-gray-900 mb-4">
                {effortMode === "assist" ? "What do you want to say?" : "Your clues"}
              </h3>
              <SignalComposer
                fragments={input.fragments}
                onAddFragment={handleAddFragment}
                onRemoveFragment={handleRemoveFragment}
              />
            </section>
          )}

        {/* Generate button */}
        {state.status !== "awaiting_outcome" &&
          state.status !== "speaking" &&
          state.status !== "needs_clarification" &&
          state.status !== "fast_response_ready" &&
          !showExpressionPreview && (
            <section className="flex justify-center">
              <button
                type="button"
                onClick={handleGenerate}
                disabled={!canGenerate}
                className={`flex items-center gap-3 px-10 py-5 rounded-xl text-xl font-bold transition-all duration-200 focus:outline-none focus:ring-4 focus:ring-offset-2 shadow-lg ${
                  canGenerate
                    ? "bg-green-600 text-white hover:bg-green-700 focus:ring-green-400 hover:shadow-xl hover:scale-105"
                    : "bg-gray-300 text-gray-500 cursor-not-allowed"
                }`}
                aria-label="Generate expression from your clues"
              >
                {state.status === "understanding_intent" ||
                state.status === "generating_expression" ? (
                  <>
                    <ArrowsClockwise
                      size={28}
                      weight="bold"
                      className="animate-spin"
                    />
                    <span>Thinking...</span>
                  </>
                ) : (
                  <>
                    <ChatCircle size={28} weight="bold" />
                    <span>Generate Expression</span>
                  </>
                )}
              </button>
            </section>
          )}

        {/* MEDIUM confidence alternatives */}
        {showExpressionPreview &&
          state.status === "ready_for_confirmation" &&
          state.confidence === "medium" &&
          state.alternatives &&
          state.alternatives.length > 0 && (
            <section
              className="p-6 bg-yellow-50 rounded-xl border-2 border-yellow-300"
              aria-label="Choose the meaning you want"
            >
              <h3 className="text-xl font-bold text-gray-900 mb-4">
                Which meaning is closest?
              </h3>
              <div className="grid grid-cols-1 gap-3">
                {state.alternatives.map((alt, index) => (
                  <button
                    key={index}
                    type="button"
                    onClick={() => handleSelectAlternative(alt.text)}
                    className={`px-6 py-4 text-left rounded-lg border-2 text-lg transition-all duration-200 focus:outline-none focus:ring-4 focus:ring-yellow-400 ${
                      state.expression === alt.text
                        ? "bg-yellow-200 border-yellow-500 font-semibold"
                        : "bg-white border-yellow-300 hover:bg-yellow-100 hover:border-yellow-400"
                    }`}
                  >
                    {alt.text}
                  </button>
                ))}
              </div>
            </section>
          )}

        {/* Expression preview */}
        {showExpressionPreview && state.status === "ready_for_confirmation" && (
          <section aria-label="Review your expression">
            <h3 className="text-xl font-bold text-gray-900 mb-4">
              Intentra understood
            </h3>
            <ExpressionPreview
              expression={state.expression}
              confidence={state.confidence}
              isReady={state.status === "ready_for_confirmation"}
              onSpeak={handleSpeak}
              onEdit={handleEdit}
            />
          </section>
        )}

        {/* Communication outcome (shown after speaking) */}
        {state.status === "awaiting_outcome" && (
          <section aria-label="Communication outcome">
            <CommunicationOutcome
              onSuccess={handleSuccess}
              onFailure={handleFailure}
            />
          </section>
        )}

        {/* Repair mode placeholder */}
        {state.status === "repair_mode" && (
          <section
            className="p-6 bg-orange-50 rounded-xl border-2 border-orange-300"
            aria-label="Repair mode"
          >
            <h3 className="text-xl font-bold text-gray-900 mb-3">
              Let's try a different way
            </h3>
            <p className="text-lg text-gray-700 mb-4">
              Strategy: {state.plan.strategy}
            </p>
            {state.plan.question && (
              <p className="text-lg text-gray-800 mb-4">{state.plan.question}</p>
            )}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
              {state.plan.options.map((option, index) => (
                <button
                  key={index}
                  type="button"
                  onClick={() => {
                    // Repair complete logic would go here
                    dispatch({
                      type: "REPAIR_COMPLETE",
                      expression: option.label,
                    });
                  }}
                  className="px-6 py-4 bg-white text-gray-900 rounded-lg border-2 border-orange-300 text-lg font-medium hover:bg-orange-100 hover:border-orange-400 focus:outline-none focus:ring-4 focus:ring-orange-400 transition-colors"
                >
                  {option.label}
                </button>
              ))}
            </div>
          </section>
        )}
      </div>

      {/* Status indicator */}
      <footer className="mt-auto pt-6 border-t border-gray-200">
        <div className="flex items-center justify-between text-sm text-gray-600">
          <span>
            Status:{" "}
            <span className="font-medium">
              {state.status === "idle" && "Ready to start"}
              {state.status === "capturing_input" && "Adding clues"}
              {state.status === "understanding_intent" && "Understanding intent"}
              {state.status === "generating_expression" && "Generating expression"}
              {state.status === "ready_for_confirmation" && "Ready to speak"}
              {state.status === "speaking" && "Speaking"}
              {state.status === "awaiting_outcome" && "Waiting for feedback"}
              {state.status === "needs_clarification" && "Needs clarification"}
              {state.status === "repair_mode" && "Repair mode"}
              {state.status === "fast_response_ready" && "Quick response available"}
            </span>
          </span>
          <span className="font-mono text-xs bg-gray-100 px-2 py-1 rounded">
            {input.fragments.length} clue{input.fragments.length !== 1 ? "s" : ""}
          </span>
        </div>
      </footer>
    </div>
  );
}
