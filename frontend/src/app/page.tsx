"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { AgentLog, AppPhase, Report } from "@/lib/types";
import { createEventSource } from "@/lib/api";
import DataInput from "@/components/DataInput";
import AgentLogPanel from "@/components/AgentLog";
import Dashboard from "@/components/Dashboard";
import ThemeToggle from "@/components/ThemeToggle";
import { AlertCircle, Loader2, Zap } from "lucide-react";

export default function Home() {
  const [phase, setPhase] = useState<AppPhase>("idle");
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [logs, setLogs] = useState<AgentLog[]>([]);
  const [report, setReport] = useState<Report | null>(null);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const esRef = useRef<EventSource | null>(null);

  const connectStream = useCallback((sid: string) => {
    esRef.current?.close();
    const es = createEventSource(sid);
    esRef.current = es;

    es.addEventListener("log", (e: MessageEvent) => {
      try {
        const log: AgentLog = JSON.parse(e.data);
        setLogs((prev) => [...prev, log]);
      } catch { /* ignore */ }
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

    es.addEventListener("done", () => { es.close(); });
    es.onerror = () => {
      if (phase !== "complete" && phase !== "error") {
        setPhase("error");
        setErrorMessage("Connection to analysis stream lost");
      }
      es.close();
    };
  }, [phase]);

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

  useEffect(() => { return () => { esRef.current?.close(); }; }, []);

  return (
    <main className="min-h-screen bg-slate-50 dark:bg-slate-950 transition-colors duration-200">
      {/* Global top bar */}
      <header className="sticky top-0 z-50 border-b border-slate-200 dark:border-slate-800 bg-white/80 dark:bg-slate-950/80 backdrop-blur-sm">
        <div className="max-w-7xl mx-auto px-4 h-14 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 bg-indigo-600 rounded-lg flex items-center justify-center">
              <Zap className="w-4 h-4 text-white" />
            </div>
            <span className="font-semibold text-slate-900 dark:text-white text-sm">
              Insight Flow AI
            </span>
          </div>
          <ThemeToggle />
        </div>
      </header>

      <div className="px-4 py-10">
        {/* ── IDLE ──────────────────────────────────────────────────────────── */}
        {phase === "idle" && (
          <DataInput
            onSessionStart={handleSessionStart}
            onError={handleError}
            onUploading={() => setPhase("uploading")}
          />
        )}

        {/* ── UPLOADING ─────────────────────────────────────────────────────── */}
        {phase === "uploading" && (
          <div className="flex flex-col items-center justify-center min-h-[40vh] gap-4">
            <Loader2 className="w-10 h-10 text-indigo-500 animate-spin" />
            <p className="text-slate-500 dark:text-slate-400">Uploading dataset…</p>
          </div>
        )}

        {/* ── ANALYZING ─────────────────────────────────────────────────────── */}
        {phase === "analyzing" && (
          <div className="max-w-3xl mx-auto space-y-6">
            <div className="text-center">
              <div className="inline-flex items-center gap-2 bg-indigo-50 dark:bg-indigo-500/10 border border-indigo-200 dark:border-indigo-500/20 rounded-full px-4 py-1.5 text-indigo-600 dark:text-indigo-400 text-sm mb-4">
                <Loader2 className="w-3.5 h-3.5 animate-spin" />
                Agents running…
              </div>
              <h2 className="text-2xl font-bold text-slate-900 dark:text-white">Analysing Dataset</h2>
              <p className="text-slate-500 dark:text-slate-400 mt-1 text-sm">
                8 specialised agents are working on your data
              </p>
            </div>

            {/* Agent pipeline steps */}
            <div className="flex items-center justify-center flex-wrap gap-1.5 overflow-x-auto pb-2">
              {["Data Access","Scaling","Schema","Planner","Execution","Insight","Report"].map((name, i) => {
                const isActive = logs.some((l) =>
                  l.agent.toLowerCase().includes(name.toLowerCase().replace(" ", ""))
                );
                return (
                  <span key={name} className="flex items-center gap-1.5">
                    <span className={`px-3 py-1.5 rounded-xl border font-medium text-sm transition-all ${
                      isActive
                        ? "border-indigo-400 dark:border-indigo-500/60 text-indigo-700 dark:text-indigo-300 bg-indigo-50 dark:bg-indigo-500/10 shadow-sm"
                        : "border-slate-200 dark:border-slate-800 text-slate-400 dark:text-slate-600 bg-white dark:bg-slate-900"
                    }`}>
                      {name}
                    </span>
                    {i < 6 && <span className="text-slate-300 dark:text-slate-700 text-sm font-bold">→</span>}
                  </span>
                );
              })}
            </div>

            <AgentLogPanel logs={logs} isRunning />
          </div>
        )}

        {/* ── COMPLETE ──────────────────────────────────────────────────────── */}
        {phase === "complete" && report && sessionId && (
          <Dashboard report={report} logs={logs} sessionId={sessionId} onReset={handleReset} />
        )}

        {/* ── ERROR ─────────────────────────────────────────────────────────── */}
        {phase === "error" && (
          <div className="max-w-lg mx-auto text-center space-y-6 pt-16">
            <div className="inline-flex items-center justify-center w-16 h-16 bg-rose-50 dark:bg-rose-500/10 border border-rose-200 dark:border-rose-500/20 rounded-2xl">
              <AlertCircle className="w-8 h-8 text-rose-500 dark:text-rose-400" />
            </div>
            <div>
              <h2 className="text-xl font-bold text-slate-900 dark:text-white mb-2">Analysis Failed</h2>
              <p className="text-slate-500 dark:text-slate-400 text-sm">{errorMessage}</p>
            </div>
            {logs.length > 0 && <AgentLogPanel logs={logs} isRunning={false} />}
            <button
              onClick={handleReset}
              className="bg-indigo-600 hover:bg-indigo-500 text-white font-medium px-6 py-3 rounded-xl transition-colors"
            >
              Try Again
            </button>
          </div>
        )}
      </div>
    </main>
  );
}
