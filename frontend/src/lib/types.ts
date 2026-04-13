// ---------------------------------------------------------------------------
// Shared TypeScript types — mirror the Python state models
// ---------------------------------------------------------------------------

export type LogLevel = "info" | "success" | "warning" | "error";

export interface AgentLog {
  agent: string;
  message: string;
  timestamp: string;
  level: LogLevel;
}

export interface ColumnInfo {
  name: string;
  dtype: string;
  category: "numeric" | "categorical" | "datetime" | "text" | "boolean";
  missing_count: number;
  missing_pct: number;
  unique_count: number;
  sample_values: unknown[];
  min_val?: number | null;
  max_val?: number | null;
  mean_val?: number | null;
  median_val?: number | null;
  std_val?: number | null;
}

export interface PlotlySpec {
  data: unknown[];
  layout: Record<string, unknown>;
}

export interface ChartItem {
  id: string;
  title: string;
  description: string;
  chart_spec: PlotlySpec | null;
}

export interface DatasetInfo {
  filename: string;
  format: string;
  size_mb: number;
  row_count: number;
  column_count: number;
  strategy: string;
  sample_size?: number | null;
}

export interface SchemaInfo {
  columns: ColumnInfo[];
  numeric_columns: string[];
  categorical_columns: string[];
  datetime_columns: string[];
  text_columns: string[];
  basic_stats: Record<string, unknown>;
}

export interface Report {
  session_id: string;
  generated_at: string;
  dataset: DatasetInfo;
  schema: SchemaInfo;
  preview_rows: Record<string, unknown>[];
  insights: string[];
  anomalies: string[];
  recommendations: string[];
  charts: ChartItem[];
  query_results: QueryResult[];
  agent_logs: AgentLog[];
  errors: string[];
}

export interface QueryResult {
  task_id: string;
  task_type: string;
  title: string;
  description: string;
  sql: string;
  rows: Record<string, unknown>[];
  chart_spec: PlotlySpec | null;
  x_col?: string | null;
  y_col?: string | null;
  row_count: number;
  error?: string | null;
}

// ---------------------------------------------------------------------------
// App state machine
// ---------------------------------------------------------------------------

export type AppPhase = "idle" | "uploading" | "analyzing" | "complete" | "error";

export interface AppState {
  phase: AppPhase;
  sessionId: string | null;
  logs: AgentLog[];
  report: Report | null;
  errorMessage: string | null;
}
