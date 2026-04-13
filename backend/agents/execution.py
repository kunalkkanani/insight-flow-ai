"""
Execution Agent
───────────────
• Iterates over the analysis plan produced by the Planner
• Generates SQL for each task (no hallucination — always uses DuckDB)
• Executes queries via DuckDB
• Builds Plotly chart specs from results
• Computes the correlation heatmap when needed
"""
from __future__ import annotations

import datetime
import logging
import uuid
from typing import Any

from langgraph.types import RunnableConfig

from ..graph.state import AgentLog, AnalysisState, QueryResult
from ..tools.chart_builder import build_correlation_heatmap, build_plotly_spec
from ..tools.duckdb_tool import execute_query

logger = logging.getLogger(__name__)
AGENT = "ExecutionAgent"


def _log(level: str, msg: str) -> AgentLog:
    return AgentLog(
        agent=AGENT,
        message=msg,
        timestamp=datetime.datetime.utcnow().isoformat(),
        level=level,
    )


async def execution_agent(
    state: AnalysisState, config: RunnableConfig
) -> dict[str, Any]:
    from ..graph.orchestrator import get_session

    session = get_session(state["session_id"])
    queue = session.get("queue")
    conn = session.get("conn")
    logs: list[AgentLog] = []
    errors: list[str] = []

    plan = state.get("analysis_plan") or []
    table = state.get("effective_table") or "raw_data"
    columns = state.get("columns") or []
    numeric_cols = state.get("numeric_columns") or []
    row_count = state.get("row_count") or 1

    col_lookup = {c["name"]: c for c in columns}

    logs.append(_log("info", f"Executing {len(plan)} analysis tasks…"))
    if queue:
        await queue.put({"type": "log", "data": logs[-1]})

    query_results: list[QueryResult] = []
    correlation_matrix_spec: dict | None = None

    # Sort by priority
    sorted_plan = sorted(plan, key=lambda t: t.get("priority", 3))

    for task in sorted_plan:
        task_id = str(uuid.uuid4())[:8]
        task_type = task.get("type", "overview")
        title = task.get("title", "Analysis")
        description = task.get("description", "")
        task_cols = [c for c in task.get("columns", []) if c in col_lookup]
        chart_type = task.get("chart_type", "bar")

        log_entry = _log("info", f"Running: {title}")
        logs.append(log_entry)
        if queue:
            await queue.put({"type": "log", "data": log_entry})

        try:
            # ── Generate SQL & chart config ──────────────────────────────
            sql, x_col, y_col = _generate_sql(
                task_type, task_cols, table, col_lookup, row_count, chart_type
            )

            if not sql:
                logs.append(_log("warning", f"Skipped (could not generate SQL): {title}"))
                continue

            # ── Special case: correlation heatmap ────────────────────────
            if task_type == "correlation" and chart_type == "heatmap":
                spec = build_correlation_heatmap(conn, table, task_cols or numeric_cols)
                correlation_matrix_spec = spec
                query_results.append(
                    QueryResult(
                        task_id=task_id,
                        task_type=task_type,
                        title=title,
                        description=description,
                        sql="-- computed via pairwise CORR()",
                        rows=[],
                        chart_spec=spec,
                        x_col=None,
                        y_col=None,
                        row_count=0,
                        error=None,
                    )
                )
                logs.append(_log("success", f"✓ {title}"))
                if queue:
                    await queue.put({"type": "log", "data": logs[-1]})
                continue

            # ── Execute query ─────────────────────────────────────────────
            rows = execute_query(conn, sql, max_rows=5_000)

            # ── Build chart spec ──────────────────────────────────────────
            spec: dict | None = None
            if rows and task_type != "overview":
                spec = build_plotly_spec(rows, chart_type, title, x_col, y_col)

            query_results.append(
                QueryResult(
                    task_id=task_id,
                    task_type=task_type,
                    title=title,
                    description=description,
                    sql=sql,
                    rows=rows if task_type == "overview" else rows[:500],
                    chart_spec=spec,
                    x_col=x_col,
                    y_col=y_col,
                    row_count=len(rows),
                    error=None,
                )
            )
            logs.append(_log("success", f"✓ {title} ({len(rows)} rows)"))

        except Exception as exc:
            logger.warning("Task '%s' failed: %s", title, exc)
            err_msg = f"Task '{title}' failed: {exc}"
            errors.append(err_msg)
            query_results.append(
                QueryResult(
                    task_id=task_id,
                    task_type=task_type,
                    title=title,
                    description=description,
                    sql="",
                    rows=[],
                    chart_spec=None,
                    x_col=None,
                    y_col=None,
                    row_count=0,
                    error=err_msg,
                )
            )
            logs.append(_log("error", err_msg))

        if queue:
            await queue.put({"type": "log", "data": logs[-1]})

    logs.append(
        _log("success", f"Execution complete — {len(query_results)} results")
    )
    if queue:
        await queue.put({"type": "log", "data": logs[-1]})

    return {
        "query_results": query_results,
        "correlation_matrix_spec": correlation_matrix_spec,
        "agent_logs": logs,
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# SQL generation
# ---------------------------------------------------------------------------


def _generate_sql(
    task_type: str,
    task_cols: list[str],
    table: str,
    col_lookup: dict,
    row_count: int,
    chart_type: str,
) -> tuple[str | None, str | None, str | None]:
    """Return (sql, x_col, y_col) for the given task."""

    def qc(col: str) -> str:
        return f'"{col}"'

    if task_type == "overview":
        return f"SELECT * FROM {table} LIMIT 100", None, None

    elif task_type == "distribution":
        if not task_cols:
            return None, None, None
        col = task_cols[0]
        info = col_lookup.get(col, {})

        if info.get("category") == "numeric":
            # Bucketed histogram
            sql = f"""
                WITH bounds AS (
                    SELECT
                        MIN({qc(col)})::DOUBLE AS lo,
                        MAX({qc(col)})::DOUBLE AS hi
                    FROM {table}
                    WHERE {qc(col)} IS NOT NULL
                ),
                bucketed AS (
                    SELECT
                        FLOOR(({qc(col)}::DOUBLE - lo) / NULLIF(hi - lo, 0) * 20) AS bucket_idx,
                        COUNT(*) AS count,
                        MIN({qc(col)})::DOUBLE AS bin_start,
                        MAX({qc(col)})::DOUBLE AS bin_end
                    FROM {table}, bounds
                    WHERE {qc(col)} IS NOT NULL
                    GROUP BY bucket_idx
                )
                SELECT
                    ROUND(bin_start, 4) AS bin_start,
                    ROUND(bin_end, 4)   AS bin_end,
                    count
                FROM bucketed
                ORDER BY bucket_idx
            """
            return sql, "bin_start", "count"
        else:
            sql = f"""
                SELECT {qc(col)} AS category, COUNT(*) AS count
                FROM {table}
                WHERE {qc(col)} IS NOT NULL
                GROUP BY {qc(col)}
                ORDER BY count DESC
                LIMIT 30
            """
            return sql, "category", "count"

    elif task_type == "correlation":
        if len(task_cols) >= 2:
            col1, col2 = task_cols[0], task_cols[1]
            sample = min(3_000, row_count)
            sql = f"""
                SELECT
                    {qc(col1)}::DOUBLE AS {col1},
                    {qc(col2)}::DOUBLE AS {col2}
                FROM {table}
                WHERE {qc(col1)} IS NOT NULL AND {qc(col2)} IS NOT NULL
                USING SAMPLE {sample} ROWS
            """
            return sql, col1, col2
        return None, None, None

    elif task_type == "time_series":
        if len(task_cols) >= 2:
            date_col, val_col = task_cols[0], task_cols[1]
            sql = f"""
                SELECT
                    DATE_TRUNC('month', TRY_CAST({qc(date_col)} AS TIMESTAMP)) AS period,
                    SUM({qc(val_col)}::DOUBLE)   AS total_value,
                    AVG({qc(val_col)}::DOUBLE)   AS avg_value,
                    COUNT(*)                      AS count
                FROM {table}
                WHERE {qc(date_col)} IS NOT NULL AND {qc(val_col)} IS NOT NULL
                GROUP BY period
                ORDER BY period
            """
            return sql, "period", "total_value"
        return None, None, None

    elif task_type == "aggregation":
        if len(task_cols) >= 2:
            cat_col, num_col = task_cols[0], task_cols[1]
            sql = f"""
                SELECT
                    {qc(cat_col)}                        AS category,
                    COUNT(*)                              AS count,
                    ROUND(AVG({qc(num_col)}::DOUBLE), 4) AS avg_value,
                    ROUND(SUM({qc(num_col)}::DOUBLE), 4) AS total_value
                FROM {table}
                WHERE {qc(cat_col)} IS NOT NULL AND {qc(num_col)} IS NOT NULL
                GROUP BY {qc(cat_col)}
                ORDER BY total_value DESC
                LIMIT 20
            """
            return sql, "category", "total_value"
        return None, None, None

    elif task_type == "anomaly":
        if not task_cols:
            return None, None, None
        col = task_cols[0]
        row_id_expr = "ROW_NUMBER() OVER ()"
        sql = f"""
            WITH stats AS (
                SELECT
                    AVG({qc(col)}::DOUBLE)    AS mean_val,
                    STDDEV({qc(col)}::DOUBLE) AS std_val
                FROM {table}
                WHERE {qc(col)} IS NOT NULL
            ),
            scored AS (
                SELECT
                    {row_id_expr}                                                          AS row_id,
                    {qc(col)}::DOUBLE                                                      AS value,
                    ABS(({qc(col)}::DOUBLE - mean_val) / NULLIF(std_val, 0))              AS z_score
                FROM {table}, stats
                WHERE {qc(col)} IS NOT NULL
            )
            SELECT row_id, value, ROUND(z_score, 3) AS z_score
            FROM scored
            WHERE z_score > 3
            ORDER BY z_score DESC
            LIMIT 50
        """
        return sql, "row_id", "value"

    return None, None, None
