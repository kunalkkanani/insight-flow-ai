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
  DataAccessAgent: "text-sky-400",
  ScalingAgent: "text-violet-400",
  SchemaAgent: "text-emerald-400",
  PlannerAgent: "text-amber-400",
  ExecutionAgent: "text-indigo-400",
  InsightAgent: "text-pink-400",
  ReportAgent: "text-teal-400",
  QAAgent: "text-orange-400",
};

const AGENT_ICONS: Record<string, string> = {
  DataAccessAgent: "📂",
  ScalingAgent: "⚖️",
  SchemaAgent: "🔍",
  PlannerAgent: "🧠",
  ExecutionAgent: "⚡",
  InsightAgent: "💡",
  ReportAgent: "📊",
  QAAgent: "💬",
};

function LevelIcon({ level }: { level: AgentLog["level"] }) {
  const cls = "w-3.5 h-3.5 shrink-0";
  switch (level) {
    case "success":
      return <CheckCircle2 className={clsx(cls, "text-emerald-400")} />;
    case "error":
      return <AlertCircle className={clsx(cls, "text-rose-400")} />;
    case "warning":
      return <AlertTriangle className={clsx(cls, "text-amber-400")} />;
    default:
      return <Info className={clsx(cls, "text-slate-500")} />;
  }
}

export default function AgentLogPanel({ logs, isRunning }: AgentLogProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [logs.length]);

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-2xl overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-3.5 border-b border-slate-800 bg-slate-900/80">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-slate-200">Agent Activity</span>
          {isRunning && (
            <span className="flex items-center gap-1.5 text-xs text-indigo-400">
              <Loader2 className="w-3 h-3 animate-spin" />
              Running…
            </span>
          )}
        </div>
        <span className="text-xs text-slate-500">{logs.length} events</span>
      </div>

      {/* Log entries */}
      <div className="h-80 overflow-y-auto p-4 space-y-1 font-mono text-xs">
        {logs.length === 0 && (
          <div className="flex items-center justify-center h-full text-slate-600">
            Waiting for agents…
          </div>
        )}
        {logs.map((log, i) => (
          <div
            key={i}
            className={clsx(
              "flex items-start gap-2.5 py-1 px-2 rounded-lg transition-colors",
              log.level === "error" && "bg-rose-500/5",
              log.level === "warning" && "bg-amber-500/5",
              "animate-fade-in"
            )}
          >
            <LevelIcon level={log.level} />
            <span
              className={clsx(
                "shrink-0 font-medium",
                AGENT_COLORS[log.agent] ?? "text-slate-400"
              )}
            >
              {AGENT_ICONS[log.agent] ?? "•"} {log.agent}
            </span>
            <span
              className={clsx(
                "flex-1 min-w-0 break-words",
                log.level === "success" && "text-emerald-300",
                log.level === "error" && "text-rose-300",
                log.level === "warning" && "text-amber-300",
                log.level === "info" && "text-slate-400"
              )}
            >
              {log.message}
            </span>
            <span className="text-slate-700 text-[10px] shrink-0 tabular-nums">
              {new Date(log.timestamp).toLocaleTimeString()}
            </span>
          </div>
        ))}
        <div ref={bottomRef} />
      </div>
    </div>
  );
}
