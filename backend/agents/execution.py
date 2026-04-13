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
            # Anomaly tasks always render as scatter — box with unique row_ids
            # produces one legend entry per row, completely cluttering the chart.
            if task_type == "anomaly":
                chart_type = "scatter"

            # ── Generate SQL & chart config ──────────────────────────────
            sql, x_col, y_col = _generate_sql(
                task_type, task_cols, table, col_lookup, row_count, chart_type,
                title=title,
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

            # ── Smart chart-type selection & data validation ───────────────
            spec: dict | None = None
            if rows and task_type != "overview" and x_col is not None:
                chart_type = _smart_chart_type(rows, chart_type, x_col, y_col)
                if _is_plottable(rows, x_col, y_col):
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
# Chart intelligence helpers
# ---------------------------------------------------------------------------


def _smart_chart_type(
    rows: list[dict],
    chart_type: str,
    x_col: str,
    y_col: str | None,
) -> str:
    """
    Override the planner's chart_type when the data shape makes the
    original choice inappropriate:

    - scatter on categorical x → bar  (e.g. Male/Female on x-axis)
    - pie with > 10 slices → bar      (pie becomes unreadable)
    - bar with 2 categories → pie     (e.g. True/False, Male/Female)
    """
    x_vals = [r.get(x_col) for r in rows if r.get(x_col) is not None]
    if not x_vals:
        return chart_type

    unique_x = len(set(str(v) for v in x_vals))

    # Detect whether x is categorical (strings / very few unique integers)
    x_is_categorical = False
    try:
        float(x_vals[0])
        # numeric x — check if it looks like a category code (few uniques)
        if unique_x <= 15:
            x_is_categorical = True
    except (ValueError, TypeError):
        x_is_categorical = True  # definitely a string column

    # scatter on categorical x → bar
    if chart_type == "scatter" and x_is_categorical:
        chart_type = "bar"

    # pie gets unreadable beyond 10 slices
    if chart_type == "pie" and unique_x > 10:
        chart_type = "bar"

    # binary/small-category distributions → pie is cleaner
    if chart_type == "bar" and x_is_categorical and 2 <= unique_x <= 5 and y_col:
        chart_type = "pie"

    return chart_type


def _is_plottable(
    rows: list[dict],
    x_col: str,
    y_col: str | None,
) -> bool:
    """
    Return False when the data has no meaningful variation worth charting:
    - fewer than 2 rows
    - all y-values are 0 or None  (null-converted column)
    - only 1 unique x-value
    """
    if len(rows) < 2:
        return False

    x_vals = [r.get(x_col) for r in rows if r.get(x_col) is not None]
    if len(set(str(v) for v in x_vals)) < 1:
        return False

    if y_col is not None:
        y_vals = [r.get(y_col) for r in rows if r.get(y_col) is not None]
        if not y_vals:
            return False
        try:
            numeric_y = [float(v) for v in y_vals]
            # All zeros almost certainly means null→0 coercion on a wrong column
            if all(v == 0.0 for v in numeric_y):
                return False
        except (ValueError, TypeError):
            pass

    return True


# ---------------------------------------------------------------------------
# SQL generation
# ---------------------------------------------------------------------------


def _safe_alias(col: str) -> str:
    """Return a SQL-safe alias for a column name (replace spaces/special chars with _)."""
    import re
    return re.sub(r"[^A-Za-z0-9_]", "_", col)


def _generate_sql(
    task_type: str,
    task_cols: list[str],
    table: str,
    col_lookup: dict,
    row_count: int,
    chart_type: str,
    title: str = "",
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
            # Use 1st–99th percentile bounds so extreme outliers don't
            # crush all the real data into invisible thin buckets.
            sql = f"""
                WITH bounds AS (
                    SELECT
                        PERCENTILE_CONT(0.01) WITHIN GROUP (ORDER BY {qc(col)}::DOUBLE) AS lo,
                        PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY {qc(col)}::DOUBLE) AS hi
                    FROM {table}
                    WHERE {qc(col)} IS NOT NULL
                ),
                bucketed AS (
                    SELECT
                        FLOOR(({qc(col)}::DOUBLE - lo) / NULLIF(hi - lo, 0) * 30) AS bucket_idx,
                        COUNT(*) AS count,
                        MIN({qc(col)}::DOUBLE) AS bin_start,
                        MAX({qc(col)}::DOUBLE) AS bin_end
                    FROM {table}, bounds
                    WHERE {qc(col)} IS NOT NULL
                      AND {qc(col)}::DOUBLE >= lo
                      AND {qc(col)}::DOUBLE <= hi
                    GROUP BY bucket_idx
                )
                SELECT
                    ROUND(bin_start, 4) AS bin_start,
                    ROUND(bin_end, 4)   AS bin_end,
                    count
                FROM bucketed
                WHERE bucket_idx IS NOT NULL
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
        # Filter to only the numeric columns the planner specified.
        numeric_task_cols = [
            c for c in task_cols if col_lookup.get(c, {}).get("category") == "numeric"
        ]
        if len(numeric_task_cols) >= 2:
            col1, col2 = numeric_task_cols[0], numeric_task_cols[1]
            sample = min(3_000, row_count)
            # Use 1st-99th percentile bounds on both axes to exclude corrupt
            # outlier rows (e.g. trip_distance = 1972.0) that would otherwise
            # collapse all the real data into an invisible sliver on the chart.
            sql = f"""
                WITH bounds AS (
                    SELECT
                        PERCENTILE_CONT(0.01) WITHIN GROUP (ORDER BY {qc(col1)}::DOUBLE) AS x_lo,
                        PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY {qc(col1)}::DOUBLE) AS x_hi,
                        PERCENTILE_CONT(0.01) WITHIN GROUP (ORDER BY {qc(col2)}::DOUBLE) AS y_lo,
                        PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY {qc(col2)}::DOUBLE) AS y_hi
                    FROM {table}
                    WHERE {qc(col1)} IS NOT NULL AND {qc(col2)} IS NOT NULL
                ),
                filtered AS (
                    SELECT {qc(col1)}::DOUBLE AS x_val, {qc(col2)}::DOUBLE AS y_val
                    FROM {table}, bounds
                    WHERE {qc(col1)} IS NOT NULL AND {qc(col2)} IS NOT NULL
                      AND {qc(col1)}::DOUBLE BETWEEN x_lo AND x_hi
                      AND {qc(col2)}::DOUBLE BETWEEN y_lo AND y_hi
                )
                SELECT x_val AS {_safe_alias(col1)}, y_val AS {_safe_alias(col2)}
                FROM filtered
                USING SAMPLE {sample} ROWS
            """
            return sql, _safe_alias(col1), _safe_alias(col2)
        return None, None, None

    elif task_type == "time_series":
        if len(task_cols) >= 2:
            date_col, val_col = task_cols[0], task_cols[1]
            title_lower = title.lower()

            # Detect desired granularity from the task title, then fall back
            # to "day" which works well for datasets up to ~2 years of data.
            if "hour" in title_lower or "hourly" in title_lower or "time of day" in title_lower:
                # Group by hour-of-day (0–23) — a recurring daily pattern
                sql = f"""
                    SELECT
                        CAST(EXTRACT(HOUR FROM TRY_CAST({qc(date_col)} AS TIMESTAMP)) AS INTEGER) AS hour_of_day,
                        COUNT(*)                      AS count,
                        SUM({qc(val_col)}::DOUBLE)   AS total_value,
                        AVG({qc(val_col)}::DOUBLE)   AS avg_value
                    FROM {table}
                    WHERE {qc(date_col)} IS NOT NULL
                    GROUP BY hour_of_day
                    ORDER BY hour_of_day
                """
                return sql, "hour_of_day", "count"

            elif "week" in title_lower or "weekly" in title_lower:
                trunc = "week"
            elif "year" in title_lower or "annual" in title_lower or "monthly" in title_lower:
                trunc = "month"
            else:
                # Default: day — gives ~7–365 points for typical datasets.
                trunc = "day"

            # Filter dates to the 1st–99th percentile range to exclude corrupt
            # epoch rows (e.g. 1970-01-01 entries in the NYC Taxi dataset).
            sql = f"""
                WITH date_bounds AS (
                    SELECT
                        PERCENTILE_CONT(0.01) WITHIN GROUP (
                            ORDER BY EPOCH(TRY_CAST({qc(date_col)} AS TIMESTAMP))
                        ) AS lo_epoch,
                        PERCENTILE_CONT(0.99) WITHIN GROUP (
                            ORDER BY EPOCH(TRY_CAST({qc(date_col)} AS TIMESTAMP))
                        ) AS hi_epoch
                    FROM {table}
                    WHERE {qc(date_col)} IS NOT NULL
                )
                SELECT
                    DATE_TRUNC('{trunc}', TRY_CAST({qc(date_col)} AS TIMESTAMP)) AS period,
                    SUM({qc(val_col)}::DOUBLE)   AS total_value,
                    AVG({qc(val_col)}::DOUBLE)   AS avg_value,
                    COUNT(*)                      AS count
                FROM {table}, date_bounds
                WHERE {qc(date_col)} IS NOT NULL AND {qc(val_col)} IS NOT NULL
                  AND EPOCH(TRY_CAST({qc(date_col)} AS TIMESTAMP)) >= lo_epoch
                  AND EPOCH(TRY_CAST({qc(date_col)} AS TIMESTAMP)) <= hi_epoch
                GROUP BY period
                ORDER BY period
                LIMIT 365
            """
            return sql, "period", "total_value"
        return None, None, None

    elif task_type == "aggregation":
        if len(task_cols) >= 2:
            cat_col, num_col = task_cols[0], task_cols[1]
            num_info  = col_lookup.get(num_col, {})
            cat_info  = col_lookup.get(cat_col, {})

            if num_info.get("category") == "numeric":
                # Standard case: aggregate a numeric column by a categorical one.
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

            else:
                # Both columns are categorical (e.g. Survived × Sex, or Port × Pclass).
                # Build a cross-count: each (cat_col, num_col) pair becomes one bar
                # labelled "A / B", ordered by count descending.
                sql = f"""
                    SELECT
                        CAST({qc(cat_col)} AS VARCHAR)
                            || ' / '
                            || CAST({qc(num_col)} AS VARCHAR)  AS category,
                        COUNT(*)                               AS count
                    FROM {table}
                    WHERE {qc(cat_col)} IS NOT NULL AND {qc(num_col)} IS NOT NULL
                    GROUP BY {qc(cat_col)}, {qc(num_col)}
                    ORDER BY count DESC
                    LIMIT 30
                """
                return sql, "category", "count"

        return None, None, None

    elif task_type == "anomaly":
        if not task_cols:
            return None, None, None
        # Only numeric columns can have z-score outliers — skip if categorical.
        col = next(
            (c for c in task_cols if col_lookup.get(c, {}).get("category") == "numeric"),
            None,
        )
        if col is None:
            return None, None, None
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
