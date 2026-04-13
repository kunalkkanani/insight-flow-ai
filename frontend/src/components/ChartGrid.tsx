"use client";

import dynamic from "next/dynamic";
import type { ChartItem } from "@/lib/types";
import { BarChart3 } from "lucide-react";
import { useTheme } from "@/lib/theme";

const Plot = dynamic(() => import("react-plotly.js"), { ssr: false });

// ---------------------------------------------------------------------------
// Plotly layout overrides per theme
// ---------------------------------------------------------------------------

const LIGHT_LAYOUT = {
  paper_bgcolor: "#ffffff",
  plot_bgcolor:  "#f8fafc",
  font:  { color: "#475569", family: "Inter, sans-serif" },
  xaxis: {
    gridcolor: "#e2e8f0", zerolinecolor: "#cbd5e1", linecolor: "#e2e8f0",
    tickfont: { color: "#64748b" }, titlefont: { color: "#475569" },
  },
  yaxis: {
    gridcolor: "#e2e8f0", zerolinecolor: "#cbd5e1", linecolor: "#e2e8f0",
    tickfont: { color: "#64748b" }, titlefont: { color: "#475569" },
  },
  title:      { font: { color: "#1e293b" } },
  hoverlabel: { bgcolor: "#ffffff", bordercolor: "#e2e8f0", font: { color: "#1e293b" } },
  legend:     { font: { color: "#475569" }, bgcolor: "rgba(0,0,0,0)" },
};

const DARK_LAYOUT = {
  paper_bgcolor: "#0f172a",
  plot_bgcolor:  "#1e293b",
  font:  { color: "#94a3b8", family: "Inter, sans-serif" },
  xaxis: {
    gridcolor: "#334155", zerolinecolor: "#475569", linecolor: "#334155",
    tickfont: { color: "#94a3b8" }, titlefont: { color: "#cbd5e1" },
  },
  yaxis: {
    gridcolor: "#334155", zerolinecolor: "#475569", linecolor: "#334155",
    tickfont: { color: "#94a3b8" }, titlefont: { color: "#cbd5e1" },
  },
  title:      { font: { color: "#e2e8f0" } },
  hoverlabel: { bgcolor: "#1e293b", bordercolor: "#475569", font: { color: "#f1f5f9" } },
  legend:     { font: { color: "#94a3b8" }, bgcolor: "rgba(0,0,0,0)" },
};

// ---------------------------------------------------------------------------

interface ChartGridProps {
  charts: ChartItem[];
}

function ChartCard({ chart, themeLayout }: { chart: ChartItem; themeLayout: object }) {
  if (!chart.chart_spec || !chart.chart_spec.data?.length) {
    return (
      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-5 flex flex-col items-center justify-center min-h-[300px] text-slate-400 dark:text-slate-600 shadow-sm">
        <BarChart3 className="w-8 h-8 mb-2 opacity-30" />
        <p className="text-sm">No data for this chart</p>
      </div>
    );
  }

  const mergedLayout = {
    ...(chart.chart_spec.layout as object),
    ...themeLayout,
    // Restore title text from the original spec
    title: {
      ...(themeLayout as Record<string, Record<string, unknown>>)["title"],
      text: (chart.chart_spec.layout as Record<string, Record<string, unknown>>)?.["title"]?.["text"] ?? chart.title,
    },
  };

  return (
    <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-4 overflow-hidden shadow-sm">
      <div className="mb-2">
        <h3 className="font-semibold text-slate-800 dark:text-slate-200 text-sm truncate">{chart.title}</h3>
        {chart.description && (
          <p className="text-xs text-slate-400 dark:text-slate-500 mt-0.5 truncate">{chart.description}</p>
        )}
      </div>
      <Plot
        data={chart.chart_spec.data as Plotly.Data[]}
        layout={{
          ...(mergedLayout as Partial<Plotly.Layout>),
          autosize: true,
          height: 280,
          margin: { t: 20, r: 20, b: 55, l: 65 },
        }}
        config={{
          displayModeBar: true,
          modeBarButtonsToRemove: ["lasso2d", "select2d", "autoScale2d"],
          displaylogo: false,
          responsive: true,
        }}
        style={{ width: "100%" }}
        useResizeHandler
      />
    </div>
  );
}

export default function ChartGrid({ charts }: ChartGridProps) {
  const { theme } = useTheme();
  const themeLayout = theme === "dark" ? DARK_LAYOUT : LIGHT_LAYOUT;

  if (!charts.length) {
    return (
      <div className="flex items-center justify-center h-40 text-slate-400 dark:text-slate-600">
        No charts available
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold text-slate-900 dark:text-white">
        Visualisations
        <span className="ml-2 text-sm font-normal text-slate-400 dark:text-slate-500">
          ({charts.length} charts)
        </span>
      </h2>
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-5">
        {charts.map((chart) => (
          <ChartCard key={chart.id} chart={chart} themeLayout={themeLayout} />
        ))}
      </div>
    </div>
  );
}
