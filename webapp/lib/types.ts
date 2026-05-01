// Wire types mirroring FastAPI schemas.py exactly.
// Keep in sync with api/schemas.py — field names and shapes must match.

export type RunStatus = "success" | "error" | "timeout" | "blocked";

export type StepType =
  | "user_message"
  | "llm_response"
  | "tool_call"
  | "tool_result";

export interface StateStep {
  index: number;
  step_type: StepType;
  name: string | null;
  content: string;
  duration_ms: number | null;
}

export interface TokenUsage {
  input_tokens: number;
  output_tokens: number;
  cached_tokens: number;
  total_tokens: number;
}

export interface CostBreakdown {
  input_cost_usd: number;
  output_cost_usd: number;
  cached_cost_usd: number;
  total_cost_usd: number;
}

export interface QueryResponse {
  request_id: string;
  user_id: string;
  query: string;
  timestamp: string;
  model: string;
  status: RunStatus;
  final_output: string | null;
  response_time_ms: number;
  usage: TokenUsage;
  cost: CostBreakdown;
  state_flow: StateStep[];
  error: string | null;
}

// SSE events
export interface StreamChunk {
  request_id: string;
  delta: string;
}

export interface StreamDone {
  request_id: string;
  result: QueryResponse;
}

export interface StreamError {
  request_id: string;
  error: string;
}

export type StreamEvent = StreamChunk | StreamDone | StreamError;

// History
export interface HistoryMessage {
  role: "user" | "assistant";
  content: string;
}

export interface HistoryResponse {
  user_id: string;
  session_id: string;
  messages: HistoryMessage[];
}

// Traces
export interface TraceSummary {
  request_id: string;
  user_id: string;
  query: string;
  timestamp: string;
  status: RunStatus;
  response_time_ms: number;
  total_tokens: number;
  total_cost_usd: number;
}

export interface TraceListResponse {
  date: string;
  total: number;
  traces: TraceSummary[];
}

// Documents
export interface DocumentMeta {
  filename: string;
  size_bytes: number;
  suffix: string;
}

export interface DocumentUploadResponse {
  filename: string;
  chunks_added: number;
  message: string;
}

// Health
export interface ServiceStatus {
  name: string;
  ok: boolean;
  latency_ms: number | null;
  error: string | null;
}

export interface HealthResponse {
  healthy: boolean;
  services: ServiceStatus[];
}
