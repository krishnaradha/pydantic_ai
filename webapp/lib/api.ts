import axios from "axios";
import type {
  DocumentMeta,
  DocumentUploadResponse,
  HealthResponse,
  HistoryResponse,
  QueryResponse,
  StreamDone,
  StreamChunk,
  StreamError,
  TraceListResponse,
} from "./types";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export const api = axios.create({
  baseURL: BASE_URL,
  headers: { "Content-Type": "application/json" },
});

// ---------------------------------------------------------------------------
// Query
// ---------------------------------------------------------------------------

export async function runQuery(
  query: string,
  userId: string,
  sessionId = "default"
): Promise<QueryResponse> {
  const { data } = await api.post<QueryResponse>("/query", {
    query,
    user_id: userId,
    session_id: sessionId,
  });
  return data;
}

/**
 * Open an SSE stream for a query. Calls onChunk for each token delta,
 * onDone with the final QueryResponse, and onError on failure.
 * Returns a cleanup function that aborts the stream.
 */
export function streamQuery(
  query: string,
  userId: string,
  sessionId = "default",
  callbacks: {
    onChunk: (delta: string) => void;
    onDone: (result: QueryResponse) => void;
    onError: (error: string) => void;
  }
): () => void {
  const controller = new AbortController();

  (async () => {
    try {
      const response = await fetch(`${BASE_URL}/query/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ query, user_id: userId, session_id: sessionId }),
        signal: controller.signal,
      });

      if (!response.ok) {
        const text = await response.text();
        callbacks.onError(`HTTP ${response.status}: ${text}`);
        return;
      }

      const reader = response.body?.getReader();
      if (!reader) { callbacks.onError("No response body"); return; }

      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\n\n");
        buffer = lines.pop() ?? "";

        for (const line of lines) {
          const data = line.replace(/^data: /, "").trim();
          if (!data) continue;

          const event = JSON.parse(data) as StreamChunk | StreamDone | StreamError;

          if ("error" in event) {
            callbacks.onError(event.error);
          } else if ("result" in event) {
            callbacks.onDone(event.result);
          } else {
            callbacks.onChunk(event.delta);
          }
        }
      }
    } catch (err) {
      if ((err as Error).name !== "AbortError") {
        callbacks.onError((err as Error).message);
      }
    }
  })();

  return () => controller.abort();
}

// ---------------------------------------------------------------------------
// History
// ---------------------------------------------------------------------------

export async function getHistory(
  userId: string,
  sessionId = "default"
): Promise<HistoryResponse> {
  const { data } = await api.get<HistoryResponse>(`/history/${userId}`, {
    params: { session_id: sessionId },
  });
  return data;
}

export async function clearHistory(
  userId: string,
  sessionId = "default"
): Promise<void> {
  await api.delete(`/history/${userId}`, { params: { session_id: sessionId } });
}

// ---------------------------------------------------------------------------
// Traces
// ---------------------------------------------------------------------------

export async function listTraces(params?: {
  date?: string;
  page?: number;
  page_size?: number;
  status?: string;
  user_id?: string;
}): Promise<TraceListResponse> {
  const { data } = await api.get<TraceListResponse>("/traces", { params });
  return data;
}

export async function getTrace(
  requestId: string,
  date = "today"
): Promise<QueryResponse> {
  const { data } = await api.get<QueryResponse>(`/traces/${requestId}`, {
    params: { date },
  });
  return data;
}

// ---------------------------------------------------------------------------
// Documents
// ---------------------------------------------------------------------------

export async function listDocuments(): Promise<DocumentMeta[]> {
  const { data } = await api.get<DocumentMeta[]>("/documents");
  return data;
}

export async function uploadDocument(
  file: File
): Promise<DocumentUploadResponse> {
  const form = new FormData();
  form.append("file", file);
  const { data } = await api.post<DocumentUploadResponse>("/documents", form, {
    headers: { "Content-Type": "multipart/form-data" },
  });
  return data;
}

// ---------------------------------------------------------------------------
// Health
// ---------------------------------------------------------------------------

export async function getHealth(): Promise<HealthResponse> {
  const { data } = await api.get<HealthResponse>("/health");
  return data;
}
