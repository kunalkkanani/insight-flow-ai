"use client";

import { useRef, useState } from "react";
import { Upload, Link2, Loader2, ChevronRight } from "lucide-react";
import { analyzeFile, analyzeUrl } from "@/lib/api";

interface DataInputProps {
  onSessionStart: (sessionId: string) => void;
  onError: (msg: string) => void;
  onUploading: () => void;
}

const DEMO_URLS = [
  {
    label: "NYC Taxi Trips",
    url: "https://d37ci6vzurychx.cloudfront.net/trip-data/yellow_tripdata_2023-01.parquet",
  },
  {
    label: "Sample Sales CSV",
    url: "https://raw.githubusercontent.com/plotly/datasets/master/sales_success.csv",
  },
  {
    label: "Titanic Dataset",
    url: "https://raw.githubusercontent.com/datasciencedojo/datasets/master/titanic.csv",
  },
];

export default function DataInput({
  onSessionStart,
  onError,
  onUploading,
}: DataInputProps) {
  const [tab, setTab] = useState<"file" | "url">("file");
  const [url, setUrl] = useState("");
  const [dragActive, setDragActive] = useState(false);
  const [loading, setLoading] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFile = async (file: File) => {
    setLoading(true);
    onUploading();
    try {
      const sessionId = await analyzeFile(file);
      onSessionStart(sessionId);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Upload failed";
      onError(msg);
      setLoading(false);
    }
  };

  const handleUrl = async () => {
    if (!url.trim()) return;
    setLoading(true);
    onUploading();
    try {
      const sessionId = await analyzeUrl(url.trim());
      onSessionStart(sessionId);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "URL analysis failed";
      onError(msg);
      setLoading(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragActive(false);
    const file = e.dataTransfer.files?.[0];
    if (file) handleFile(file);
  };

  return (
    <div className="w-full max-w-2xl mx-auto">
      {/* Hero */}
      <div className="text-center mb-10">
        <div className="inline-flex items-center gap-2 bg-indigo-500/10 border border-indigo-500/20 rounded-full px-4 py-1.5 text-indigo-400 text-sm font-medium mb-6">
          <span className="w-1.5 h-1.5 rounded-full bg-indigo-400 animate-pulse" />
          Multi-Agent AI Analyst
        </div>
        <h1 className="text-4xl md:text-5xl font-bold text-white tracking-tight mb-4">
          Insight Flow AI
        </h1>
        <p className="text-slate-400 text-lg max-w-lg mx-auto">
          Upload any dataset and get instant EDA, visualisations, and AI-powered
          insights — powered by 8 specialised agents.
        </p>
      </div>

      {/* Input card */}
      <div className="bg-slate-900 border border-slate-800 rounded-2xl p-6 shadow-2xl">
        {/* Tabs */}
        <div className="flex gap-1 bg-slate-800/50 rounded-xl p-1 mb-6">
          {(["file", "url"] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTab(t)}
              className={`flex-1 flex items-center justify-center gap-2 py-2 px-4 rounded-lg text-sm font-medium transition-all ${
                tab === t
                  ? "bg-slate-700 text-white shadow-sm"
                  : "text-slate-400 hover:text-slate-300"
              }`}
            >
              {t === "file" ? (
                <Upload className="w-4 h-4" />
              ) : (
                <Link2 className="w-4 h-4" />
              )}
              {t === "file" ? "Upload File" : "Paste URL"}
            </button>
          ))}
        </div>

        {tab === "file" ? (
          <div
            onClick={() => fileInputRef.current?.click()}
            onDragOver={(e) => { e.preventDefault(); setDragActive(true); }}
            onDragLeave={() => setDragActive(false)}
            onDrop={handleDrop}
            className={`relative border-2 border-dashed rounded-xl p-10 text-center cursor-pointer transition-all ${
              dragActive
                ? "border-indigo-500 bg-indigo-500/5"
                : "border-slate-700 hover:border-slate-500 hover:bg-slate-800/40"
            }`}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".csv,.parquet,.json,.jsonl,.tsv"
              className="hidden"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) handleFile(f);
              }}
            />
            <div className="flex flex-col items-center gap-3">
              {loading ? (
                <Loader2 className="w-10 h-10 text-indigo-400 animate-spin" />
              ) : (
                <div className="w-14 h-14 bg-indigo-500/10 border border-indigo-500/20 rounded-2xl flex items-center justify-center">
                  <Upload className="w-7 h-7 text-indigo-400" />
                </div>
              )}
              <div>
                <p className="text-slate-200 font-medium">
                  {loading ? "Uploading…" : "Drop your file here"}
                </p>
                <p className="text-slate-500 text-sm mt-1">
                  CSV · Parquet · JSON — up to 500 MB
                </p>
              </div>
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            <div className="flex gap-2">
              <input
                type="url"
                value={url}
                onChange={(e) => setUrl(e.target.value)}
                onKeyDown={(e) => e.key === "Enter" && handleUrl()}
                placeholder="https://example.com/data.csv"
                className="flex-1 bg-slate-800 border border-slate-700 rounded-xl px-4 py-3 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-indigo-500 transition-colors"
              />
              <button
                onClick={handleUrl}
                disabled={!url.trim() || loading}
                className="bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed text-white font-medium px-5 py-3 rounded-xl flex items-center gap-2 transition-colors"
              >
                {loading ? (
                  <Loader2 className="w-4 h-4 animate-spin" />
                ) : (
                  <ChevronRight className="w-4 h-4" />
                )}
                Analyse
              </button>
            </div>

            {/* Demo URLs */}
            <div>
              <p className="text-slate-500 text-xs mb-2 font-medium uppercase tracking-wider">
                Quick demos
              </p>
              <div className="flex flex-wrap gap-2">
                {DEMO_URLS.map((d) => (
                  <button
                    key={d.label}
                    onClick={() => setUrl(d.url)}
                    className="text-xs bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-300 px-3 py-1.5 rounded-lg transition-colors"
                  >
                    {d.label}
                  </button>
                ))}
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Feature pills */}
      <div className="mt-8 flex flex-wrap justify-center gap-3 text-xs text-slate-500">
        {["8 specialised agents", "DuckDB-powered", "Scales to millions of rows", "Interactive charts", "AI insights"].map((f) => (
          <span key={f} className="bg-slate-900 border border-slate-800 px-3 py-1.5 rounded-full">
            {f}
          </span>
        ))}
      </div>
    </div>
  );
}
