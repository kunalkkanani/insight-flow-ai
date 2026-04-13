"use client";

import dynamic from "next/dynamic";
import type { ChartItem } from "@/lib/types";
import { BarChart3 } from "lucide-react";

// Plotly must be dynamically imported (no SSR) due to browser-only APIs
const Plot = dynamic(() => import("react-plotly.js"), { ssr: false });

interface ChartGridProps {
  charts: ChartItem[];
}

function ChartCard({ chart }: { chart: ChartItem }) {
  if (!chart.chart_spec || !chart.chart_spec.data?.length) {
    return (
      <div className="bg-slate-900 border border-slate-800 rounded-2xl p-5 flex flex-col items-center justify-center min-h-[300px] text-slate-600">
        <BarChart3 className="w-8 h-8 mb-2 opacity-30" />
        <p className="text-sm">No data for this chart</p>
      </div>
    );
  }

  return (
    <div className="bg-slate-900 border border-slate-800 rounded-2xl p-4 overflow-hidden">
      <div className="mb-2">
        <h3 className="font-semibold text-slate-200 text-sm truncate">{chart.title}</h3>
        {chart.description && (
          <p className="text-xs text-slate-500 mt-0.5 truncate">{chart.description}</p>
        )}
      </div>
      <Plot
        data={chart.chart_spec.data as Plotly.Data[]}
        layout={{
          ...(chart.chart_spec.layout as Partial<Plotly.Layout>),
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
  if (!charts.length) {
    return (
      <div className="flex items-center justify-center h-40 text-slate-600">
        No charts available
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <h2 className="text-lg font-semibold text-white">
        Visualisations
        <span className="ml-2 text-sm font-normal text-slate-500">
          ({charts.length} charts)
        </span>
      </h2>
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-5">
        {charts.map((chart) => (
          <ChartCard key={chart.id} chart={chart} />
        ))}
      </div>
    </div>
  );
}
