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
  borderClass,
  dotClass,
}: {
  icon: React.ReactNode;
  title: string;
  items: string[];
  borderClass: string;
  dotClass: string;
}) {
  if (!items.length) return null;
  return (
    <div className={clsx(
      "bg-white dark:bg-slate-900 border rounded-2xl p-6 flex flex-col gap-4 shadow-sm",
      borderClass
    )}>
      <div className="flex items-center gap-2.5">
        <div className="p-2 rounded-lg bg-slate-100 dark:bg-slate-800">{icon}</div>
        <h3 className="font-semibold text-slate-800 dark:text-slate-200 text-base">{title}</h3>
        <span className="ml-auto bg-slate-100 dark:bg-slate-800 text-slate-500 dark:text-slate-400 text-sm px-2.5 py-0.5 rounded-full font-medium">
          {items.length}
        </span>
      </div>
      <ul className="space-y-3">
        {items.map((item, i) => (
          <li key={i} className="flex items-start gap-3">
            <span className={clsx("mt-2 w-2 h-2 rounded-full shrink-0", dotClass)} />
            <span className="text-base text-slate-600 dark:text-slate-300 leading-relaxed">{item}</span>
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
      <h2 className="text-xl font-semibold text-slate-900 dark:text-white">AI Insights</h2>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Card
          icon={<Lightbulb className="w-5 h-5 text-amber-500 dark:text-amber-400" />}
          title="Key Insights"
          items={insights}
          borderClass="border-amber-200 dark:border-amber-500/20"
          dotClass="bg-amber-400"
        />
        <Card
          icon={<AlertTriangle className="w-5 h-5 text-rose-500 dark:text-rose-400" />}
          title="Anomalies"
          items={anomalies}
          borderClass="border-rose-200 dark:border-rose-500/20"
          dotClass="bg-rose-400"
        />
        <Card
          icon={<Target className="w-5 h-5 text-emerald-600 dark:text-emerald-400" />}
          title="Recommendations"
          items={recommendations}
          borderClass="border-emerald-200 dark:border-emerald-500/20"
          dotClass="bg-emerald-500"
        />
      </div>
    </div>
  );
}
