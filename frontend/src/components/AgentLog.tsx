"use client";

import { useEffect, useRef } from "react";
import { CheckCircle2, AlertCircle, AlertTriangle, Info, Loader2 } from "lucide-react";
import type { AgentLog } from "@/lib/types";
import clsx from "clsx";

interface AgentLogProps {
  logs: AgentLog[];
  isRunning: boolean;
}

const AGENT_COLORS: Record<string, string> = {
  DataAccessAgent: "text-sky-600 dark:text-sky-400",
  ScalingAgent:    "text-violet-600 dark:text-violet-400",
  SchemaAgent:     "text-emerald-600 dark:text-emerald-400",
  PlannerAgent:    "text-amber-600 dark:text-amber-400",
  ExecutionAgent:  "text-indigo-600 dark:text-indigo-400",
  InsightAgent:    "text-pink-600 dark:text-pink-400",
  ReportAgent:     "text-teal-600 dark:text-teal-400",
  QAAgent:         "text-orange-600 dark:text-orange-400",
};

const AGENT_ICONS: Record<string, string> = {
  DataAccessAgent: "📂",
  ScalingAgent:    "⚖️",
  SchemaAgent:     "🔍",
  PlannerAgent:    "🧠",
  ExecutionAgent:  "⚡",
  InsightAgent:    "💡",
  ReportAgent:     "📊",
  QAAgent:         "💬",
};

function LevelIcon({ level }: { level: AgentLog["level"] }) {
  const cls = "w-4 h-4 shrink-0";
  switch (level) {
    case "success": return <CheckCircle2 className={clsx(cls, "text-emerald-500 dark:text-emerald-400")} />;
    case "error":   return <AlertCircle  className={clsx(cls, "text-rose-500 dark:text-rose-400")} />;
    case "warning": return <AlertTriangle className={clsx(cls, "text-amber-500 dark:text-amber-400")} />;
    default:        return <Info className={clsx(cls, "text-slate-400 dark:text-slate-500")} />;
  }
}

export default function AgentLogPanel({ logs, isRunning }: AgentLogProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs.length]);

  return (
    <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl overflow-hidden shadow-sm">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-3.5 border-b border-slate-100 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/80">
        <div className="flex items-center gap-2">
          <span className="text-base font-semibold text-slate-800 dark:text-slate-200">Agent Activity</span>
          {isRunning && (
            <span className="flex items-center gap-1.5 text-sm text-indigo-600 dark:text-indigo-400">
              <Loader2 className="w-3.5 h-3.5 animate-spin" />
              Running…
            </span>
          )}
        </div>
        <span className="text-sm text-slate-400">{logs.length} events</span>
      </div>

      {/* Log entries */}
      <div className="h-96 overflow-y-auto p-4 space-y-1.5 font-mono text-base bg-white dark:bg-slate-900">
        {logs.length === 0 && (
          <div className="flex items-center justify-center h-full text-slate-400 dark:text-slate-600 text-base">
            Waiting for agents…
          </div>
        )}
        {logs.map((log, i) => (
          <div
            key={i}
            className={clsx(
              "flex items-start gap-3 py-1.5 px-3 rounded-lg transition-colors animate-fade-in",
              log.level === "error"   && "bg-rose-50 dark:bg-rose-500/5",
              log.level === "warning" && "bg-amber-50 dark:bg-amber-500/5",
            )}
          >
            <LevelIcon level={log.level} />
            <span className={clsx("shrink-0 font-semibold text-base", AGENT_COLORS[log.agent] ?? "text-slate-500")}>
              {AGENT_ICONS[log.agent] ?? "•"} {log.agent}
            </span>
            <span className={clsx(
              "flex-1 min-w-0 break-words text-base",
              log.level === "success" && "text-emerald-700 dark:text-emerald-300",
              log.level === "error"   && "text-rose-600 dark:text-rose-300",
              log.level === "warning" && "text-amber-700 dark:text-amber-300",
              log.level === "info"    && "text-slate-600 dark:text-slate-400",
            )}>
              {log.message}
            </span>
            <span className="text-slate-400 dark:text-slate-600 text-sm shrink-0 tabular-nums">
              {new Date(log.timestamp).toLocaleTimeString()}
            </span>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
