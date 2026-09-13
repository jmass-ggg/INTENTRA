// useCommunication — state machine for the Intentra communication flow.
//
// State sequence:
// idle → capturing_input → understanding_intent → [needs_clarification | generating_expression]
// → ready_for_confirmation → speaking → awaiting_outcome → [idle | repair_mode]
//
// CRITICAL: TTS is ONLY triggered from speak() and NEVER called automatically.
// The user must explicitly confirm before any speech.

import { useCallback, useState } from "react";
import {
  communicationGenerate,
  communicationConfirm,
  conversationOutcome,
  communicationRepair,
  communicationFastResponse,
  speak as apiSpeak,
  type CommunicationInput,
  type IntentFrame,
  type IdentityResult,
  type ConfidenceBand,
  type RepairPlan,
  type IntentType,
  type EffortMode,
} from "../lib/api";

// --- State Machine Types ---

type CommState =
  | { status: "idle" }
  | { status: "capturing_input" }
  | { status: "understanding_intent" }
  | {
      status: "needs_clarification";
      question: string;
      options: string[];
    }
  | { status: "generating_expression" }
  | {
      status: "ready_for_confirmation";
      expression: string;
      confidence: ConfidenceBand;
      intent: IntentFrame;
      identity: IdentityResult;
      alternatives?: Array<{ text: string }>;
    }
  | { status: "speaking" }
  | { status: "awaiting_outcome" }
  | {
      status: "repair_mode";
      plan: RepairPlan;
      originalIntent: IntentFrame;
      originalExpression: string;
    }
  | {
      status: "fast_response_ready";
      responseType: "binary" | "choice";
      options: string[];
      partnerSpeech: string;
    };

// --- Action Types ---

type CommAction =
  | { type: "START_INPUT" }
  | { type: "SET_INTENT"; intent: IntentType }
  | { type: "ADD_FRAGMENT"; fragment: string }
  | { type: "REMOVE_FRAGMENT"; fragment: string }
  | { type: "SET_LISTENER"; listener: string }
  | { type: "SET_EMOTION"; emotion: string }
  | { type: "GENERATE" }
  | { type: "CLARIFY"; answer: string }
  | { type: "SELECT_ALTERNATIVE"; text: string }
  | { type: "EDIT_EXPRESSION"; text: string }
  | { type: "CONFIRM_SPEAK" }
  | { type: "OUTCOME_SUCCESS" }
  | { type: "OUTCOME_FAILURE" }
  | { type: "REPAIR_COMPLETE"; expression: string }
  | { type: "RESET" }
  | {
      type: "GENERATION_COMPLETE";
      response: {
        status: "ready" | "clarification_required";
        intent?: IntentFrame;
        expression?: { text: string };
        identity?: IdentityResult;
        confidence_band?: ConfidenceBand;
        question?: string;
        options?: string[];
        alternatives?: Array<{ text: string }>;
      };
    }
  | { type: "SPEAKING_COMPLETE" }
  | {
      type: "REPAIR_INITIATED";
      plan: RepairPlan;
      originalIntent: IntentFrame;
      originalExpression: string;
    }
  | {
      type: "FAST_RESPONSE_READY";
      responseType: "binary" | "choice";
      options: string[];
      partnerSpeech: string;
    }
  | { type: "FAST_RESPONSE_SELECTED"; option: string }
  | { type: "BYPASS_FAST_RESPONSE" };

// --- Hook Interface ---

export interface UseCommunication {
  state: CommState;
  input: {
    fragments: string[];
    intentType: IntentType | null;
    listener: string | null;
    emotion: string | null;
    effortMode: EffortMode;
  };
  dispatch: (action: CommAction) => void;
  speak: (text: string) => Promise<void>;
  generate: () => Promise<void>;
  recordOutcome: (success: boolean) => Promise<void>;
  initiateRepair: () => Promise<void>;
  checkFastResponse: (partnerSpeech: string) => Promise<void>;
}

// --- Main Hook ---

export function useCommunication(personId: string): UseCommunication {
  const [state, setState] = useState<CommState>({ status: "idle" });
  const [fragments, setFragments] = useState<string[]>([]);
  const [intentType, setIntentType] = useState<IntentType | null>(null);
  const [listener, setListener] = useState<string | null>(null);
  const [emotion, setEmotion] = useState<string | null>(null);
  const [effortMode] = useState<EffortMode>("full");
  const [sessionId] = useState(() => `session_${Date.now()}_${Math.random().toString(36).slice(2)}`);

  // Reducer-like dispatch for state actions
  const dispatch = useCallback((action: CommAction) => {
    switch (action.type) {
      case "START_INPUT":
        setState({ status: "capturing_input" });
        break;

      case "SET_INTENT":
        setIntentType(action.intent);
        break;

      case "ADD_FRAGMENT":
        setFragments((prev) => [...prev, action.fragment]);
        break;

      case "REMOVE_FRAGMENT":
        setFragments((prev) => prev.filter((f) => f !== action.fragment));
        break;

      case "SET_LISTENER":
        setListener(action.listener);
        break;

      case "SET_EMOTION":
        setEmotion(action.emotion);
        break;

      case "GENERATE":
        setState({ status: "understanding_intent" });
        break;

      case "GENERATION_COMPLETE":
        if (action.response.status === "clarification_required") {
          setState({
            status: "needs_clarification",
            question: action.response.question || "What did you mean?",
            options: action.response.options || [],
          });
        } else if (action.response.status === "ready") {
          setState({
            status: "ready_for_confirmation",
            expression: action.response.expression?.text || "",
            confidence: action.response.confidence_band || "high",
            intent: action.response.intent!,
            identity: action.response.identity!,
            alternatives: action.response.alternatives,
          });
        }
        break;

      case "CLARIFY":
        // User answered clarification question - could trigger re-generation
        setState({ status: "generating_expression" });
        break;

      case "SELECT_ALTERNATIVE":
        setState((prev) => {
          if (prev.status === "ready_for_confirmation") {
            return {
              ...prev,
              expression: action.text,
            };
          }
          return prev;
        });
        break;

      case "EDIT_EXPRESSION":
        setState((prev) => {
          if (prev.status === "ready_for_confirmation") {
            return {
              ...prev,
              expression: action.text,
            };
          }
          return prev;
        });
        break;

      case "CONFIRM_SPEAK":
        setState({ status: "speaking" });
        break;

      case "SPEAKING_COMPLETE":
        setState({ status: "awaiting_outcome" });
        break;

      case "OUTCOME_SUCCESS":
        setState({ status: "idle" });
        // Reset input
        setFragments([]);
        setIntentType(null);
        setListener(null);
        setEmotion(null);
        break;

      case "OUTCOME_FAILURE":
        // Will transition to repair_mode via initiateRepair()
        break;

      case "REPAIR_INITIATED":
        setState({
          status: "repair_mode",
          plan: action.plan,
          originalIntent: action.originalIntent,
          originalExpression: action.originalExpression,
        });
        break;

      case "REPAIR_COMPLETE":
        setState({
          status: "ready_for_confirmation",
          expression: action.expression,
          confidence: "medium",
          intent:
            state.status === "repair_mode" ? state.originalIntent : ({} as IntentFrame),
          identity: {
            intent_match: 0,
            grounding_score: 0,
            identity_match: 0,
            hallucination_risk: 0,
            violated_rules: [],
            safe_to_present: true,
          },
        });
        break;

      case "RESET":
        setState({ status: "idle" });
        setFragments([]);
        setIntentType(null);
        setListener(null);
        setEmotion(null);
        break;

      case "FAST_RESPONSE_READY":
        setState({
          status: "fast_response_ready",
          responseType: action.responseType,
          options: action.options,
          partnerSpeech: action.partnerSpeech,
        });
        break;

      case "FAST_RESPONSE_SELECTED":
        // User selected a fast response option - add as fragment and generate
        setFragments([action.option]);
        setState({ status: "understanding_intent" });
        break;

      case "BYPASS_FAST_RESPONSE":
        // User chose to bypass fast response and use full pipeline
        setState({ status: "idle" });
        break;
    }
  }, [state]);

  // Generate expression via the communication pipeline
  const generate = useCallback(async () => {
    dispatch({ type: "GENERATE" });

    try {
      const input: CommunicationInput = {
        person_id: personId,
        fragments,
        intent_type: intentType || undefined,
        listener: listener || undefined,
        emotion: emotion || undefined,
        effort_mode: effortMode,
      };

      const response = await communicationGenerate(input);

      dispatch({ type: "GENERATION_COMPLETE", response });
    } catch (error) {
      console.error("Generation failed:", error);
      // Fallback to idle on error
      dispatch({ type: "RESET" });
    }
  }, [personId, fragments, intentType, listener, emotion, effortMode, dispatch]);

  // Speak function - ONLY way to trigger TTS
  const speak = useCallback(
    async (text: string) => {
      const trimmed = text.trim();
      if (!trimmed) return;

      try {
        // Get current state to access intent for confirmation
        if (state.status === "ready_for_confirmation") {
          // Record confirmation
          await communicationConfirm({
            person_id: personId,
            expression: trimmed,
            intent: state.intent,
          });
        }

        // Call TTS API
        const res = await apiSpeak({ person_id: personId, text: trimmed });
        
        // Play audio if available
        if (res.audio_base64) {
          const audio = new Audio(`data:audio/wav;base64,${res.audio_base64}`);
          await audio.play();
        } else {
          // Fallback to browser TTS
          if (typeof window !== "undefined" && window.speechSynthesis) {
            window.speechSynthesis.cancel();
            const utter = new SpeechSynthesisUtterance(trimmed);
            utter.lang = "en-US";
            window.speechSynthesis.speak(utter);
          }
        }

        // Transition to awaiting outcome
        dispatch({ type: "SPEAKING_COMPLETE" });
      } catch (error) {
        console.error("Speak failed:", error);
        // Still transition to outcome on error
        dispatch({ type: "SPEAKING_COMPLETE" });
      }
    },
    [personId, state, dispatch]
  );

  // Record conversation outcome
  const recordOutcome = useCallback(
    async (success: boolean) => {
      try {
        const intent = state.status === "awaiting_outcome" || state.status === "ready_for_confirmation"
          ? (state as any).intent
          : undefined;
        const expression = state.status === "awaiting_outcome" || state.status === "ready_for_confirmation"
          ? (state as any).expression
          : undefined;

        await conversationOutcome({
          session_id: sessionId,
          person_id: personId,
          success,
          intent_frame: intent,
          expression,
          repair_needed: !success,
        });

        if (success) {
          dispatch({ type: "OUTCOME_SUCCESS" });
        } else {
          dispatch({ type: "OUTCOME_FAILURE" });
        }
      } catch (error) {
        console.error("Failed to record outcome:", error);
      }
    },
    [personId, sessionId, state, dispatch]
  );

  // Initiate repair flow
  const initiateRepair = useCallback(async () => {
    try {
      if (
        state.status !== "awaiting_outcome" &&
        state.status !== "ready_for_confirmation"
      ) {
        return;
      }

      const intent = (state as any).intent as IntentFrame;
      const expression = (state as any).expression as string;

      const plan = await communicationRepair({
        person_id: personId,
        intent_frame: intent,
        original_expression: expression,
      });

      dispatch({
        type: "REPAIR_INITIATED",
        plan,
        originalIntent: intent,
        originalExpression: expression,
      });
    } catch (error) {
      console.error("Failed to initiate repair:", error);
    }
  }, [personId, state, dispatch]);

  // Check for fast response opportunity
  const checkFastResponse = useCallback(
    async (partnerSpeech: string) => {
      try {
        const result = await communicationFastResponse({
          partner_speech: partnerSpeech,
          person_id: personId,
        });

        if (result.type === "binary" || result.type === "choice") {
          // Show fast response UI
          dispatch({
            type: "FAST_RESPONSE_READY",
            responseType: result.type,
            options: result.options || [],
            partnerSpeech,
          });
        } else {
          // Proceed to full pipeline
          dispatch({ type: "BYPASS_FAST_RESPONSE" });
        }
      } catch (error) {
        console.error("Fast response check failed:", error);
        // Fall back to full pipeline on error
        dispatch({ type: "BYPASS_FAST_RESPONSE" });
      }
    },
    [personId, dispatch]
  );

  return {
    state,
    input: {
      fragments,
      intentType,
      listener,
      emotion,
      effortMode,
    },
    dispatch,
    speak,
    generate,
    recordOutcome,
    initiateRepair,
    checkFastResponse,
  };
}

export default useCommunication;
