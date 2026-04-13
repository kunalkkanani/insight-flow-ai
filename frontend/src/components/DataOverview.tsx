"use client";

import { useState } from "react";
import {
  Database,
  Hash,
  Calendar,
  Type,
  ToggleLeft,
  FileText,
  AlertCircle,
} from "lucide-react";
import type { ColumnInfo, Report } from "@/lib/types";
import clsx from "clsx";

interface DataOverviewProps {
  report: Report;
}

const CATEGORY_ICON: Record<string, React.ReactNode> = {
  numeric: <Hash className="w-3.5 h-3.5" />,
  datetime: <Calendar className="w-3.5 h-3.5" />,
  categorical: <Type className="w-3.5 h-3.5" />,
  boolean: <ToggleLeft className="w-3.5 h-3.5" />,
  text: <FileText className="w-3.5 h-3.5" />,
};

const CATEGORY_COLOR: Record<string, string> = {
  numeric: "text-indigo-400 bg-indigo-500/10 border-indigo-500/20",
  datetime: "text-cyan-400 bg-cyan-500/10 border-cyan-500/20",
  categorical: "text-amber-400 bg-amber-500/10 border-amber-500/20",
  boolean: "text-emerald-400 bg-emerald-500/10 border-emerald-500/20",
  text: "text-violet-400 bg-violet-500/10 border-violet-500/20",
};

function StatBadge({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="bg-slate-800 border border-slate-700 rounded-xl p-4">
      <p className="text-xs text-slate-500 mb-1">{label}</p>
      <p className="text-xl font-bold text-white">{value}</p>
    </div>
  );
}

function ColumnRow({ col }: { col: ColumnInfo }) {
  const colorCls = CATEGORY_COLOR[col.category] ?? "text-slate-400 bg-slate-700 border-slate-600";
  const missingBad = col.missing_pct > 30;

  return (
    <tr className="border-b border-slate-800 hover:bg-slate-800/40 transition-colors">
      <td className="px-4 py-3 font-medium text-slate-200 text-sm">{col.name}</td>
      <td className="px-4 py-3">
        <span className={clsx("inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border", colorCls)}>
          {CATEGORY_ICON[col.category]}
          {col.category}
        </span>
      </td>
      <td className="px-4 py-3 text-xs text-slate-500 font-mono">{col.dtype}</td>
      <td className="px-4 py-3">
        <div className="flex items-center gap-1.5">
          {missingBad && <AlertCircle className="w-3.5 h-3.5 text-rose-400 shrink-0" />}
          <span className={clsx("text-sm", missingBad ? "text-rose-400" : "text-slate-400")}>
            {col.missing_pct.toFixed(1)}%
          </span>
        </div>
      </td>
      <td className="px-4 py-3 text-sm text-slate-400 tabular-nums">
        {col.unique_count.toLocaleString()}
      </td>
      <td className="px-4 py-3 text-xs text-slate-500 max-w-[200px] truncate">
        {col.category === "numeric" && col.mean_val != null
          ? `μ=${col.mean_val?.toFixed(2)} σ=${col.std_val?.toFixed(2)}`
          : col.sample_values?.slice(0, 3).join(", ")}
      </td>
    </tr>
  );
}

export default function DataOverview({ report }: DataOverviewProps) {
  const { dataset, schema, preview_rows } = report;
  const [previewOpen, setPreviewOpen] = useState(false);

  const previewCols =
    preview_rows.length > 0 ? Object.keys(preview_rows[0]).slice(0, 12) : [];

  return (
    <div className="space-y-6">
      {/* Dataset stats */}
      <div>
        <h2 className="text-lg font-semibold text-white mb-4">Dataset Overview</h2>
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
          <StatBadge label="Rows" value={dataset.row_count.toLocaleString()} />
          <StatBadge label="Columns" value={dataset.column_count} />
          <StatBadge label="Size" value={`${dataset.size_mb.toFixed(1)} MB`} />
          <StatBadge label="Format" value={dataset.format.toUpperCase()} />
          <StatBadge label="Strategy" value={dataset.strategy} />
          {dataset.sample_size && (
            <StatBadge
              label="Sample"
              value={dataset.sample_size.toLocaleString()}
            />
          )}
        </div>
      </div>

      {/* Column schema */}
      <div>
        <h3 className="text-base font-semibold text-white mb-3">Column Schema</h3>
        <div className="bg-slate-900 border border-slate-800 rounded-2xl overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-slate-800 bg-slate-800/60">
                  {["Column", "Type", "dtype", "Missing %", "Unique", "Stats / Samples"].map(
                    (h) => (
                      <th
                        key={h}
                        className="px-4 py-3 text-left text-xs font-semibold text-slate-400 uppercase tracking-wider"
                      >
                        {h}
                      </th>
                    )
                  )}
                </tr>
              </thead>
              <tbody>
                {schema.columns.map((col) => (
                  <ColumnRow key={col.name} col={col} />
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </div>

      {/* Data preview */}
      {preview_rows.length > 0 && (
        <div>
          <button
            onClick={() => setPreviewOpen(!previewOpen)}
            className="flex items-center gap-2 text-base font-semibold text-white mb-3 hover:text-slate-300 transition-colors"
          >
            <Database className="w-4 h-4" />
            Data Preview (5 rows)
            <span className="text-slate-500 text-sm font-normal">
              {previewOpen ? "▲ Hide" : "▼ Show"}
            </span>
          </button>
          {previewOpen && (
            <div className="bg-slate-900 border border-slate-800 rounded-2xl overflow-hidden">
              <div className="overflow-x-auto">
                <table className="data-table">
                  <thead>
                    <tr>
                      {previewCols.map((c) => (
                        <th key={c}>{c}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {preview_rows.map((row, i) => (
                      <tr key={i}>
                        {previewCols.map((c) => (
                          <td key={c} title={String(row[c] ?? "")}>
                            {String(row[c] ?? "—")}
                          </td>
                        ))}
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
