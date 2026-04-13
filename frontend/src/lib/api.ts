import axios from "axios";
import type { Report } from "./types";

// ---------------------------------------------------------------------------
// Base URLs
//
// PROXY_BASE  — light JSON calls routed through the Next.js rewrite proxy.
//               Avoids CORS in the browser; fine for small payloads.
//
// DIRECT_BASE — file uploads and SSE streams go DIRECTLY to the backend,
//               bypassing the proxy.  Reasons:
//                 • File uploads can be hundreds of MB — the Next.js proxy
//                   buffers the whole body and has a hard 10 MB cap.
//                 • SSE connections are long-lived; proxies add unnecessary
//                   buffering and timeout risk.
//               NEXT_PUBLIC_API_URL must be set in production so the browser
//               can reach the backend directly.  In local dev it defaults to
//               the standard FastAPI port.
// ---------------------------------------------------------------------------

const DIRECT_BASE =
  (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000") + "/api";

const PROXY_BASE = "/api";

// ---------------------------------------------------------------------------
// Analysis — file upload (direct, no proxy)
// ---------------------------------------------------------------------------

export async function analyzeFile(file: File): Promise<string> {
  const form = new FormData();
  form.append("file", file);
  const { data } = await axios.post<{ session_id: string }>(
    `${DIRECT_BASE}/analyze/file`,
    form,
    // Let axios set Content-Type with the correct boundary automatically
    { headers: { "Content-Type": "multipart/form-data" } }
  );
  return data.session_id;
}

// ---------------------------------------------------------------------------
// Analysis — URL (small JSON body, proxy is fine)
// ---------------------------------------------------------------------------

export async function analyzeUrl(url: string): Promise<string> {
  const { data } = await axios.post<{ session_id: string }>(
    `${PROXY_BASE}/analyze/url`,
    { url }
  );
  return data.session_id;
}

// ---------------------------------------------------------------------------
// Poll for result (non-SSE fallback)
// ---------------------------------------------------------------------------

export async function getStatus(
  sessionId: string
): Promise<{ status: string; report: Report | null }> {
  const { data } = await axios.get(`${PROXY_BASE}/status/${sessionId}`);
  return data;
}

// ---------------------------------------------------------------------------
// QA
// ---------------------------------------------------------------------------

export async function askQuestion(
  sessionId: string,
  question: string
): Promise<{ response: string; conversation_history: unknown[] }> {
  const { data } = await axios.post(`${PROXY_BASE}/question/${sessionId}`, {
    question,
  });
  return data;
}

// ---------------------------------------------------------------------------
// Session cleanup
// ---------------------------------------------------------------------------

export async function deleteSession(sessionId: string): Promise<void> {
  await axios.delete(`${PROXY_BASE}/session/${sessionId}`);
}

// ---------------------------------------------------------------------------
// SSE stream (direct, no proxy — long-lived connection)
// ---------------------------------------------------------------------------

export function createEventSource(sessionId: string): EventSource {
  return new EventSource(`${DIRECT_BASE}/stream/${sessionId}`);
}
