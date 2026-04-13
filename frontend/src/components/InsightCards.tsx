"use client";

import { Lightbulb, AlertTriangle, Target } from "lucide-react";
import type { Report } from "@/lib/types";
import clsx from "clsx";

interface InsightCardsProps {
  report: Report;
}

function Card({
  icon,
  title,
  items,
  accent,
}: {
  icon: React.ReactNode;
  title: string;
  items: string[];
  accent: string;
}) {
  if (!items.length) return null;
  return (
    <div
      className={clsx(
        "bg-slate-900 border rounded-2xl p-5 flex flex-col gap-4",
        accent
      )}
    >
      <div className="flex items-center gap-2">
        <div className="p-1.5 rounded-lg bg-slate-800">{icon}</div>
        <h3 className="font-semibold text-slate-200 text-sm">{title}</h3>
        <span className="ml-auto bg-slate-800 text-slate-400 text-xs px-2 py-0.5 rounded-full">
          {items.length}
        </span>
      </div>
      <ul className="space-y-2.5">
        {items.map((item, i) => (
          <li key={i} className="flex items-start gap-2.5">
            <span className="mt-1.5 w-1.5 h-1.5 rounded-full bg-current shrink-0 opacity-50" />
            <span className="text-sm text-slate-300 leading-relaxed">{item}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

export default function InsightCards({ report }: InsightCardsProps) {
  const { insights, anomalies, recommendations } = report;

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold text-white">AI Insights</h2>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card
          icon={<Lightbulb className="w-4 h-4 text-amber-400" />}
          title="Key Insights"
          items={insights}
          accent="border-amber-500/20 text-amber-400"
        />
        <Card
          icon={<AlertTriangle className="w-4 h-4 text-rose-400" />}
          title="Anomalies"
          items={anomalies}
          accent="border-rose-500/20 text-rose-400"
        />
        <Card
          icon={<Target className="w-4 h-4 text-emerald-400" />}
          title="Recommendations"
          items={recommendations}
          accent="border-emerald-500/20 text-emerald-400"
        />
      </div>
    </div>
  );
}
