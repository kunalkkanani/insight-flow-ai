"use client";

import { useState } from "react";
import { BarChart3, Lightbulb, Database, MessageSquare, ScrollText } from "lucide-react";
import type { AgentLog, Report } from "@/lib/types";
import AgentLogPanel from "./AgentLog";
import InsightCards from "./InsightCards";
import ChartGrid from "./ChartGrid";
import DataOverview from "./DataOverview";
import ChatBox from "./ChatBox";
import clsx from "clsx";

type Tab = "overview" | "charts" | "insights" | "chat" | "logs";

const TABS: { id: Tab; label: string; icon: React.ReactNode }[] = [
  { id: "overview",  label: "Overview",   icon: <Database className="w-4 h-4" /> },
  { id: "charts",    label: "Charts",     icon: <BarChart3 className="w-4 h-4" /> },
  { id: "insights",  label: "Insights",   icon: <Lightbulb className="w-4 h-4" /> },
  { id: "chat",      label: "Ask AI",     icon: <MessageSquare className="w-4 h-4" /> },
  { id: "logs",      label: "Agent Logs", icon: <ScrollText className="w-4 h-4" /> },
];

interface DashboardProps {
  report: Report;
  logs: AgentLog[];
  sessionId: string;
  onReset: () => void;
}

export default function Dashboard({ report, logs, sessionId, onReset }: DashboardProps) {
  const [activeTab, setActiveTab] = useState<Tab>("overview");

  return (
    <div className="w-full max-w-7xl mx-auto space-y-6 animate-slide-up">
      {/* Top bar */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-slate-900 dark:text-white">
            {report.dataset.filename}
          </h2>
          <p className="text-sm text-slate-500 dark:text-slate-500 mt-0.5">
            {report.dataset.row_count.toLocaleString()} rows ·{" "}
            {report.dataset.column_count} columns ·{" "}
            {report.dataset.size_mb.toFixed(1)} MB ·{" "}
            <span className="capitalize">{report.dataset.strategy} scan</span>
          </p>
        </div>
        <button
          onClick={onReset}
          className="text-sm text-slate-500 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white border border-slate-200 dark:border-slate-700 hover:border-slate-400 dark:hover:border-slate-500 px-4 py-2 rounded-xl transition-all"
        >
          ← New Analysis
        </button>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-1 overflow-x-auto shadow-sm">
        {TABS.map((tab) => (
          <button
            key={tab.id}
            onClick={() => setActiveTab(tab.id)}
            className={clsx(
              "flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium whitespace-nowrap transition-all",
              activeTab === tab.id
                ? "bg-indigo-600 text-white shadow-sm"
                : "text-slate-500 dark:text-slate-400 hover:text-slate-800 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800"
            )}
          >
            {tab.icon}
            {tab.label}
            {tab.id === "charts" && report.charts.length > 0 && (
              <span className={clsx(
                "text-xs px-1.5 py-0.5 rounded-full",
                activeTab === tab.id ? "bg-white/20" : "bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400"
              )}>
                {report.charts.length}
              </span>
            )}
            {tab.id === "insights" && report.insights.length > 0 && (
              <span className={clsx(
                "text-xs px-1.5 py-0.5 rounded-full",
                activeTab === tab.id ? "bg-white/20" : "bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400"
              )}>
                {report.insights.length}
              </span>
            )}
          </button>
        ))}
      </div>

      {/* Content */}
      <div className="animate-fade-in">
        {activeTab === "overview"  && <DataOverview report={report} />}
        {activeTab === "charts"    && <ChartGrid charts={report.charts} />}
        {activeTab === "insights"  && <InsightCards report={report} />}
        {activeTab === "chat"      && <ChatBox sessionId={sessionId} />}
        {activeTab === "logs"      && <AgentLogPanel logs={logs} isRunning={false} />}
      </div>

      {/* Non-fatal errors */}
      {report.errors.length > 0 && (
        <div className="bg-rose-50 dark:bg-rose-500/10 border border-rose-200 dark:border-rose-500/20 rounded-xl p-4">
          <p className="text-rose-600 dark:text-rose-400 font-medium text-sm mb-2">
            {report.errors.length} non-fatal error(s) during analysis:
          </p>
          <ul className="space-y-1">
            {report.errors.map((e, i) => (
              <li key={i} className="text-rose-500 dark:text-rose-300 text-xs font-mono">{e}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
