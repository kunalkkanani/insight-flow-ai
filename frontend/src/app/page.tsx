"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { AgentLog, AppPhase, Report } from "@/lib/types";
import { createEventSource } from "@/lib/api";
import DataInput from "@/components/DataInput";
import AgentLogPanel from "@/components/AgentLog";
import Dashboard from "@/components/Dashboard";
import { AlertCircle, Loader2 } from "lucide-react";

export default function Home() {
  const [phase, setPhase] = useState<AppPhase>("idle");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [logs, setLogs] = useState<AgentLog[]>([]);
  const [report, setReport] = useState<Report | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const esRef = useRef<EventSource | null>(null);

  // ── SSE connection ────────────────────────────────────────────────────────
  const connectStream = useCallback((sid: string) => {
    if (esRef.current) {
      esRef.current.close();
    }

    const es = createEventSource(sid);
    esRef.current = es;

    es.addEventListener("log", (e: MessageEvent) => {
      try {
        const log: AgentLog = JSON.parse(e.data);
        setLogs((prev) => [...prev, log]);
      } catch {
        /* ignore */
      }
    });

    es.addEventListener("result", (e: MessageEvent) => {
      try {
        const r: Report = JSON.parse(e.data);
        setReport(r);
        setPhase("complete");
      } catch {
        setPhase("error");
        setErrorMessage("Failed to parse analysis result");
      }
    });

    es.addEventListener("error", (e: MessageEvent) => {
      try {
        const err = JSON.parse(e.data);
        setErrorMessage(err.message ?? "Unknown error");
      } catch {
        setErrorMessage("Stream error");
      }
      setPhase("error");
    });

    es.addEventListener("done", () => {
      es.close();
    });

    es.onerror = () => {
      // SSE connection error (network)
      if (phase !== "complete" && phase !== "error") {
        setPhase("error");
        setErrorMessage("Connection to analysis stream lost");
      }
      es.close();
    };
  }, [phase]);

  // ── Handlers ──────────────────────────────────────────────────────────────
  const handleSessionStart = (sid: string) => {
    setSessionId(sid);
    setPhase("analyzing");
    setLogs([]);
    setReport(null);
    setErrorMessage(null);
    connectStream(sid);
  };

  const handleError = (msg: string) => {
    setPhase("error");
    setErrorMessage(msg);
  };

  const handleReset = () => {
    esRef.current?.close();
    setPhase("idle");
    setSessionId(null);
    setLogs([]);
    setReport(null);
    setErrorMessage(null);
  };

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      esRef.current?.close();
    };
  }, []);

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <main className="min-h-screen bg-slate-950 px-4 py-12">
      {/* ── IDLE: show input ──────────────────────────────────────────────── */}
      {phase === "idle" && (
        <DataInput
          onSessionStart={handleSessionStart}
          onError={handleError}
          onUploading={() => setPhase("uploading")}
        />
      )}

      {/* ── UPLOADING: brief spinner ─────────────────────────────────────── */}
      {phase === "uploading" && (
        <div className="flex flex-col items-center justify-center min-h-[40vh] gap-4">
          <Loader2 className="w-10 h-10 text-indigo-400 animate-spin" />
          <p className="text-slate-400">Uploading dataset…</p>
        </div>
      )}

      {/* ── ANALYZING: live agent log ─────────────────────────────────────── */}
      {phase === "analyzing" && (
        <div className="max-w-3xl mx-auto space-y-6">
          {/* Progress header */}
          <div className="text-center">
            <div className="inline-flex items-center gap-2 bg-indigo-500/10 border border-indigo-500/20 rounded-full px-4 py-1.5 text-indigo-400 text-sm mb-4">
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
              Agents running…
            </div>
            <h2 className="text-2xl font-bold text-white">Analysing Dataset</h2>
            <p className="text-slate-400 mt-1 text-sm">
              8 specialised agents are working on your data
            </p>
          </div>

          {/* Agent pipeline visual */}
          <div className="flex items-center justify-center gap-1 text-xs text-slate-600 overflow-x-auto pb-2">
            {[
              "Data Access",
              "Scaling",
              "Schema",
              "Planner",
              "Execution",
              "Insight",
              "Report",
            ].map((name, i) => {
              const isActive = logs.some((l) =>
                l.agent.toLowerCase().includes(name.toLowerCase().replace(" ", ""))
              );
              return (
                <span key={name} className="flex items-center gap-1">
                  <span
                    className={`px-2 py-1 rounded-lg border ${
                      isActive
                        ? "border-indigo-500/50 text-indigo-300 bg-indigo-500/10"
                        : "border-slate-800 text-slate-600"
                    }`}
                  >
                    {name}
                  </span>
                  {i < 6 && <span className="text-slate-700">→</span>}
                </span>
              );
            })}
          </div>

          <AgentLogPanel logs={logs} isRunning />
        </div>
      )}

      {/* ── COMPLETE: full dashboard ─────────────────────────────────────── */}
      {phase === "complete" && report && sessionId && (
        <Dashboard
          report={report}
          logs={logs}
          sessionId={sessionId}
          onReset={handleReset}
        />
      )}

      {/* ── ERROR ─────────────────────────────────────────────────────────── */}
      {phase === "error" && (
        <div className="max-w-lg mx-auto text-center space-y-6 pt-16">
          <div className="inline-flex items-center justify-center w-16 h-16 bg-rose-500/10 border border-rose-500/20 rounded-2xl">
            <AlertCircle className="w-8 h-8 text-rose-400" />
          </div>
          <div>
            <h2 className="text-xl font-bold text-white mb-2">Analysis Failed</h2>
            <p className="text-slate-400 text-sm">{errorMessage}</p>
          </div>
          {logs.length > 0 && (
            <AgentLogPanel logs={logs} isRunning={false} />
          )}
          <button
            onClick={handleReset}
            className="bg-indigo-600 hover:bg-indigo-500 text-white font-medium px-6 py-3 rounded-xl transition-colors"
          >
            Try Again
          </button>
        </div>
      )}
    </main>
  );
}
