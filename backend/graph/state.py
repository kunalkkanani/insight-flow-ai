"""Shared LangGraph analysis state — single source of truth across all agents."""
from __future__ import annotations

import operator
from typing import Annotated, Any, Optional

from typing_extensions import TypedDict

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------
JsonDict = dict[str, Any]


# ---------------------------------------------------------------------------
# Sub-structures
# ---------------------------------------------------------------------------


class AgentLog(TypedDict):
    agent: str
    message: str
    timestamp: str
    level: str  # "info" | "success" | "warning" | "error"


class ColumnInfo(TypedDict):
    name: str
    dtype: str
    category: str  # "numeric" | "categorical" | "datetime" | "text" | "boolean"
    missing_count: int
    missing_pct: float
    unique_count: int
    sample_values: list[Any]
    # Numeric extras (None for non-numeric)
    min_val: Optional[float]
    max_val: Optional[float]
    mean_val: Optional[float]
    median_val: Optional[float]
    std_val: Optional[float]


class AnalysisTask(TypedDict):
    type: str  # distribution | correlation | time_series | aggregation | anomaly | overview
    title: str
    description: str
    columns: list[str]
    chart_type: str  # bar | line | scatter | heatmap | pie | box | histogram
    priority: int  # 1 = highest


class QueryResult(TypedDict):
    task_id: str
    task_type: str
    title: str
    description: str
    sql: str
    rows: list[JsonDict]
    chart_spec: Optional[JsonDict]  # Plotly JSON
    x_col: Optional[str]
    y_col: Optional[str]
    row_count: int
    error: Optional[str]


# ---------------------------------------------------------------------------
# Main analysis state
# ---------------------------------------------------------------------------


class AnalysisState(TypedDict):
    # ── Session ───────────────────────────────────────────────────────────────
    session_id: str

    # ── Input ─────────────────────────────────────────────────────────────────
    input_type: Optional[str]        # "file" | "url"
    file_path: Optional[str]         # local path after upload
    url: Optional[str]               # remote URL
    original_filename: Optional[str]

    # ── Data access results ───────────────────────────────────────────────────
    file_format: Optional[str]       # csv | parquet | json
    file_size_mb: Optional[float]
    row_count: Optional[int]
    column_count: Optional[int]
    preview_rows: Optional[list[JsonDict]]
    source_path: Optional[str]       # path DuckDB queries
    raw_table: Optional[str]         # initial DuckDB view name

    # ── Scaling decisions ─────────────────────────────────────────────────────
    strategy: Optional[str]          # full | sample | aggregate
    effective_table: Optional[str]   # final DuckDB view/table for analysis
    sample_size: Optional[int]

    # ── Schema ────────────────────────────────────────────────────────────────
    columns: Optional[list[ColumnInfo]]
    numeric_columns: Optional[list[str]]
    categorical_columns: Optional[list[str]]
    datetime_columns: Optional[list[str]]
    text_columns: Optional[list[str]]
    basic_stats: Optional[JsonDict]

    # ── Planning ──────────────────────────────────────────────────────────────
    analysis_plan: Optional[list[AnalysisTask]]

    # ── Execution results ─────────────────────────────────────────────────────
    query_results: Optional[list[QueryResult]]
    correlation_matrix_spec: Optional[JsonDict]  # Plotly heatmap spec

    # ── Insights ──────────────────────────────────────────────────────────────
    insights: Optional[list[str]]
    anomalies: Optional[list[str]]
    recommendations: Optional[list[str]]

    # ── Final report ──────────────────────────────────────────────────────────
    report: Optional[JsonDict]

    # ── Streaming (append-only via LangGraph reducers) ────────────────────────
    agent_logs: Annotated[list[AgentLog], operator.add]
    errors: Annotated[list[str], operator.add]

    # ── QA conversation ───────────────────────────────────────────────────────
    user_question: Optional[str]
    qa_response: Optional[str]
    conversation_history: Optional[list[JsonDict]]
