// Lucid Voice — API client + shared types.
// These TypeScript types mirror the SHARED API CONTRACT (the backend Pydantic
// models in aac/backend/app/models.py) EXACTLY: same field names, same
// optionality. Keep the two files in lock-step.

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface Situation {
  time?: string;
  place?: string;
  present_people?: string[];
}

export interface GenerateRequest {
  person_id: string;
  fragments: string[];
  context?: string; // default ""
  situation?: Situation;
}

export type Register = "warm" | "neutral" | "direct";
export type LengthLabel = "short" | "medium" | "full";

export interface Candidate {
  text: string;
  register: Register;
  length_label: LengthLabel;
  rationale: string;
  grounded_node_ids: string[];
}

export interface RetrievalInfo {
  anchor_ids: string[];
  subgraph_node_ids: string[];
  subgraph_edge_ids: string[];
  confidence: number;
}

export interface GenerateResponse {
  candidates: Candidate[];
  retrieval: RetrievalInfo;
  trace: Record<string, unknown>;
  abstain: boolean; // default false
  abstain_reason?: string;
}

export interface SpeakRequest {
  person_id: string;
  text: string;
}

export interface SpeakResponse {
  audio_base64: string;
  cached: boolean;
}

export interface ConfirmRequest {
  person_id: string;
  text: string;
  context?: string;
  partner?: string;
}

// Elements CREATED by a confirmation (for live incremental graph growth).
export interface NewNode {
  id: string;
  kind: string;
  label: string;
  salience: number;
}

export interface NewEdge {
  source: string;
  target: string;
  type: string;
  weight: number;
}

export interface ConfirmResponse {
  changed_node_ids: string[];
  changed_edge_ids: string[];
  // Additive (optional): elements created this turn so the graph can bloom them.
  new_nodes?: NewNode[];
  new_edges?: NewEdge[];
}

// --- /assistant_turn (Build Your Brain) ---

export interface AssistantTurnMessage {
  role: "assistant" | "user";
  text: string;
}

export interface AssistantTurnRequest {
  person_id: string;
  history: AssistantTurnMessage[];
}

export interface AssistantTurnResponse {
  text: string;
  // Short, question-specific answer words for the "Next" suggestions.
  suggestions?: string[];
}

export interface ConsolidateRequest {
  person_id: string;
}

export interface ConsolidateResponse {
  new_node_ids: string[];
  new_edge_ids: string[];
}

export interface STTRequest {
  audio_base64: string;
}

export interface STTResponse {
  text: string;
}

export interface EnrollRequest {
  person_id: string;
  audio_base64: string;
}

export interface EnrollResponse {
  ok: boolean;
  voice_ref: string;
}

export interface GraphNode {
  id: string;
  label: string;
  type: string;
  salience: number;
  last_seen: string;
  group?: string;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  type: string;
  weight: number;
  count: number;
  last_reinforced: string;
}

export interface GraphResponse {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface HealthResponse {
  status: string;
  demo_mode: boolean;
  providers: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// Fetch wrapper
// ---------------------------------------------------------------------------

// Base URL matches the Vite dev-server proxy ("/api" -> backend).
export const API_BASE = "/api";

class ApiError extends Error {
  status: number;
  body: string;
  constructor(status: number, body: string) {
    super(`API ${status}: ${body}`);
    this.name = "ApiError";
    this.status = status;
    this.body = body;
  }
}

async function request<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  if (!res.ok) {
    const body = await res.text().catch(() => "");
    throw new ApiError(res.status, body);
  }
  return (await res.json()) as T;
}

function post<TReq, TRes>(path: string, body: TReq): Promise<TRes> {
  return request<TRes>(path, {
    method: "POST",
    body: JSON.stringify(body),
  });
}

function get<TRes>(path: string): Promise<TRes> {
  return request<TRes>(path, { method: "GET" });
}

// ---------------------------------------------------------------------------
// Typed endpoint functions — ready to use even though the backend returns
// correctly-shaped placeholders during early phases.
// ---------------------------------------------------------------------------

export function generate(req: GenerateRequest): Promise<GenerateResponse> {
  return post<GenerateRequest, GenerateResponse>("/generate", req);
}

export function speak(req: SpeakRequest): Promise<SpeakResponse> {
  return post<SpeakRequest, SpeakResponse>("/speak", req);
}

export function confirm(req: ConfirmRequest): Promise<ConfirmResponse> {
  return post<ConfirmRequest, ConfirmResponse>("/confirm", req);
}

export function consolidate(
  req: ConsolidateRequest,
): Promise<ConsolidateResponse> {
  return post<ConsolidateRequest, ConsolidateResponse>("/consolidate", req);
}

export function assistantTurn(
  req: AssistantTurnRequest,
): Promise<AssistantTurnResponse> {
  return post<AssistantTurnRequest, AssistantTurnResponse>("/assistant_turn", req);
}

export function stt(req: STTRequest): Promise<STTResponse> {
  return post<STTRequest, STTResponse>("/stt", req);
}

export function enroll(req: EnrollRequest): Promise<EnrollResponse> {
  return post<EnrollRequest, EnrollResponse>("/enroll", req);
}

export function getGraph(personId: string): Promise<GraphResponse> {
  return get<GraphResponse>(`/graph/${encodeURIComponent(personId)}`);
}

export function getHealth(): Promise<HealthResponse> {
  return get<HealthResponse>("/health");
}

export function getLatestTrace(): Promise<Record<string, unknown>> {
  return get<Record<string, unknown>>("/trace/latest");
}

// --- Passport API ---

export interface PersonProfile {
  id: string;
  name: string;
  relationship?: string;
  address_term?: string;
}

export interface CommunicationPassport {
  person_id: string;
  people: PersonProfile[];
  vocabulary: string[];
  preferred_expressions: string[];
  avoided_expressions: string[];
  communication_rules: string[];
  routines: string[];
  emergency_phrases: string[];
  repair_preferences: string[];
  accessibility_preferences: Record<string, unknown>;
}

export function getPassport(personId: string): Promise<CommunicationPassport> {
  return get<CommunicationPassport>(`/passport/${encodeURIComponent(personId)}`);
}

export function addPassportPreference(req: { person_id: string; expression: string }): Promise<{ ok: boolean }> {
  return post<{ person_id: string; expression: string }, { ok: boolean }>("/passport/preference", req);
}

export function addPassportAvoid(req: { person_id: string; expression: string }): Promise<{ ok: boolean }> {
  return post<{ person_id: string; expression: string }, { ok: boolean }>("/passport/avoid", req);
}

// --- Communication Pipeline API (Intentra) ---

export type IntentType = "request" | "answer" | "question" | "explain" | "emotion" | "social" | "emergency" | "unknown";
export type EffortMode = "full" | "assist" | "low_effort" | "emergency";
export type ConfidenceBand = "high" | "medium" | "low";

export interface IntentFrame {
  action: IntentType;
  concepts: string[];
  listener_id?: string;
  listener_name?: string;
  emotional_state?: string;
  temporal_reference?: string;
  location_reference?: string;
  confidence: number;
  unresolved: string[];
  evidence: string[];
}

export interface IdentityResult {
  intent_match: number;
  grounding_score: number;
  identity_match: number;
  hallucination_risk: number;
  violated_rules: string[];
  safe_to_present: boolean;
}

export interface CommunicationInput {
  person_id: string;
  fragments: string[];
  intent_type?: IntentType;
  listener?: string;
  emotion?: string;
  partial_speech?: string;
  selected_symbols?: string[];
  conversation_context?: string;
  effort_mode?: EffortMode;
}

export interface CommunicationResponse {
  status: "ready" | "clarification_required";
  intent?: IntentFrame;
  expression?: { text: string; used_evidence: string[] };
  identity?: IdentityResult;
  confidence_band?: ConfidenceBand;
  requires_confirmation?: boolean;
  question?: string;
  options?: string[];
  alternatives?: Array<{ text: string }>;
}

export interface ConversationOutcome {
  session_id: string;
  person_id: string;
  success: boolean;
  intent_frame?: IntentFrame;
  expression?: string;
  repair_needed: boolean;
}

export interface RepairPlan {
  strategy: string;
  question?: string;
  options: Array<{ label: string; value: string }>;
  rebuilt_expression?: string;
}

export function communicationGenerate(req: CommunicationInput): Promise<CommunicationResponse> {
  return post<CommunicationInput, CommunicationResponse>("/communication/generate", req);
}

export function communicationConfirm(req: { person_id: string; expression: string; intent: IntentFrame }): Promise<{ ok: boolean }> {
  return post<{ person_id: string; expression: string; intent: IntentFrame }, { ok: boolean }>("/communication/confirm", req);
}

export function conversationOutcome(req: ConversationOutcome): Promise<{ ok: boolean }> {
  return post<ConversationOutcome, { ok: boolean }>("/conversation/outcome", req);
}

export function communicationRepair(req: { person_id: string; intent_frame: IntentFrame; original_expression: string }): Promise<RepairPlan> {
  return post<{ person_id: string; intent_frame: IntentFrame; original_expression: string }, RepairPlan>("/communication/repair", req);
}

// --- Fast Response API ---

export interface FastResponseRequest {
  partner_speech: string;
  person_id: string;
}

export type FastResponseType = "binary" | "choice" | "pipeline";

export interface FastResponseResult {
  type: FastResponseType;
  options?: string[];
}

export function communicationFastResponse(req: FastResponseRequest): Promise<FastResponseResult> {
  return post<FastResponseRequest, FastResponseResult>("/communication/fast-response", req);
}

export { ApiError };
