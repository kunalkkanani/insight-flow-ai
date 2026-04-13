import axios from "axios";
import type { Report } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL
  ? `${process.env.NEXT_PUBLIC_API_URL}/api`
  : "/api";

// ---------------------------------------------------------------------------
// Start analysis
// ---------------------------------------------------------------------------

export async function analyzeFile(file: File): Promise<string> {
  const form = new FormData();
  form.append("file", file);
  const { data } = await axios.post<{ session_id: string }>(
    `${API_BASE}/analyze/file`,
    form,
    { headers: { "Content-Type": "multipart/form-data" } }
  );
  return data.session_id;
}

export async function analyzeUrl(url: string): Promise<string> {
  const { data } = await axios.post<{ session_id: string }>(
    `${API_BASE}/analyze/url`,
    { url }
  );
  return data.session_id;
}

// ---------------------------------------------------------------------------
// Poll for result (for environments where SSE is unavailable)
// ---------------------------------------------------------------------------

export async function getStatus(
  sessionId: string
): Promise<{ status: string; report: Report | null }> {
  const { data } = await axios.get(`${API_BASE}/status/${sessionId}`);
  return data;
}

// ---------------------------------------------------------------------------
// QA
// ---------------------------------------------------------------------------

export async function askQuestion(
  sessionId: string,
  question: string
): Promise<{ response: string; conversation_history: unknown[] }> {
  const { data } = await axios.post(`${API_BASE}/question/${sessionId}`, {
    question,
  });
  return data;
}

// ---------------------------------------------------------------------------
// Cleanup
// ---------------------------------------------------------------------------

export async function deleteSession(sessionId: string): Promise<void> {
  await axios.delete(`${API_BASE}/session/${sessionId}`);
}

// ---------------------------------------------------------------------------
// SSE helper
// ---------------------------------------------------------------------------

export function createEventSource(sessionId: string): EventSource {
  const url = `${API_BASE}/stream/${sessionId}`;
  return new EventSource(url);
}
