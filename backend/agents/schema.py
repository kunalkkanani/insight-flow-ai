"""
Schema Agent
────────────
• Introspects column names, DuckDB types, and inferred categories
• Computes missing-value percentages, unique-value counts, and sample values
• Computes basic statistics (min, max, mean, median, std) for numeric columns
• Categorises columns: numeric | categorical | datetime | text | boolean
"""
from __future__ import annotations

import datetime
import logging
from typing import Any

from langgraph.types import RunnableConfig

from ..graph.state import AgentLog, AnalysisState, ColumnInfo
from ..tools.duckdb_tool import execute_query, execute_scalar

logger = logging.getLogger(__name__)
AGENT = "SchemaAgent"

# DuckDB type → logical category
_TYPE_MAP: dict[str, str] = {
    "integer": "numeric",
    "bigint": "numeric",
    "hugeint": "numeric",
    "smallint": "numeric",
    "tinyint": "numeric",
    "float": "numeric",
    "double": "numeric",
    "decimal": "numeric",
    "numeric": "numeric",
    "real": "numeric",
    "date": "datetime",
    "timestamp": "datetime",
    "timestamp with time zone": "datetime",
    "time": "datetime",
    "interval": "datetime",
    "boolean": "boolean",
    "bool": "boolean",
    "varchar": "categorical",
    "text": "text",
    "blob": "text",
    "json": "text",
}


def _log(level: str, msg: str) -> AgentLog:
    return AgentLog(
        agent=AGENT,
        message=msg,
        timestamp=datetime.datetime.utcnow().isoformat(),
        level=level,
    )


def _detect_category(dtype: str, unique_count: int, row_count: int) -> str:
    """Refine category using cardinality heuristics."""
    base = _TYPE_MAP.get(dtype.lower(), "categorical")
    if base == "categorical":
        ratio = unique_count / max(row_count, 1)
        if ratio > 0.8 and unique_count > 100:
            return "text"  # high-cardinality string → treat as free text
    return base


async def schema_agent(
    state: AnalysisState, config: RunnableConfig
) -> dict[str, Any]:
    from ..graph.orchestrator import get_session

    session = get_session(state["session_id"])
    queue = session.get("queue")
    conn = session.get("conn")
    logs: list[AgentLog] = []
    errors: list[str] = []

    effective_table = state.get("effective_table") or "raw_data"
    row_count = state.get("row_count") or 1

    try:
        logs.append(_log("info", "Analysing schema…"))
        if queue:
            await queue.put({"type": "log", "data": logs[-1]})

        # ── 1. DuckDB DESCRIBE ─────────────────────────────────────────────
        describe_rows = execute_query(conn, f"DESCRIBE {effective_table}")
        columns: list[ColumnInfo] = []
        numeric_cols, categorical_cols, datetime_cols, text_cols = [], [], [], []

        for row in describe_rows:
            col_name = row.get("column_name", row.get("Field", ""))
            dtype = str(row.get("column_type", row.get("Type", "varchar"))).lower()

            # Missing value count
            try:
                missing = int(
                    execute_scalar(
                        conn,
                        f'SELECT COUNT(*) FROM {effective_table} WHERE "{col_name}" IS NULL',
                    )
                    or 0
                )
            except Exception:
                missing = 0

            # Unique count (capped for speed)
            try:
                unique = int(
                    execute_scalar(
                        conn,
                        f'SELECT COUNT(DISTINCT "{col_name}") FROM {effective_table}',
                    )
                    or 0
                )
            except Exception:
                unique = 0

            # Sample values (up to 5 non-null)
            try:
                sample_rows = execute_query(
                    conn,
                    f'SELECT "{col_name}" FROM {effective_table} WHERE "{col_name}" IS NOT NULL LIMIT 5',
                    max_rows=5,
                )
                samples = [r[col_name] for r in sample_rows]
            except Exception:
                samples = []

            category = _detect_category(dtype, unique, row_count)
            missing_pct = round(missing / max(row_count, 1) * 100, 2)

            info: ColumnInfo = {
                "name": col_name,
                "dtype": dtype,
                "category": category,
                "missing_count": missing,
                "missing_pct": missing_pct,
                "unique_count": unique,
                "sample_values": samples,
                "min_val": None,
                "max_val": None,
                "mean_val": None,
                "median_val": None,
                "std_val": None,
            }

            # Numeric statistics
            if category == "numeric":
                try:
                    stat_rows = execute_query(
                        conn,
                        f"""
                        SELECT
                            MIN("{col_name}")::DOUBLE    AS min_val,
                            MAX("{col_name}")::DOUBLE    AS max_val,
                            AVG("{col_name}")::DOUBLE    AS mean_val,
                            MEDIAN("{col_name}")::DOUBLE AS median_val,
                            STDDEV("{col_name}")::DOUBLE AS std_val
                        FROM {effective_table}
                        WHERE "{col_name}" IS NOT NULL
                        """,
                        max_rows=1,
                    )
                    if stat_rows:
                        s = stat_rows[0]
                        info["min_val"] = _round(s.get("min_val"))
                        info["max_val"] = _round(s.get("max_val"))
                        info["mean_val"] = _round(s.get("mean_val"))
                        info["median_val"] = _round(s.get("median_val"))
                        info["std_val"] = _round(s.get("std_val"))
                except Exception as exc:
                    logger.debug("Stats failed for %s: %s", col_name, exc)

            columns.append(info)

            if category == "numeric":
                numeric_cols.append(col_name)
            elif category == "categorical":
                categorical_cols.append(col_name)
            elif category == "datetime":
                datetime_cols.append(col_name)
            elif category == "text":
                text_cols.append(col_name)

        # ── 2. Summarise ────────────────────────────────────────────────────
        basic_stats = {
            "total_columns": len(columns),
            "numeric_count": len(numeric_cols),
            "categorical_count": len(categorical_cols),
            "datetime_count": len(datetime_cols),
            "text_count": len(text_cols),
            "high_missing": [
                c["name"] for c in columns if c["missing_pct"] > 30
            ],
        }

        logs.append(
            _log(
                "success",
                f"Schema: {len(numeric_cols)} numeric, "
                f"{len(categorical_cols)} categorical, "
                f"{len(datetime_cols)} datetime, "
                f"{len(text_cols)} text columns",
            )
        )
        if queue:
            await queue.put({"type": "log", "data": logs[-1]})

        if basic_stats["high_missing"]:
            logs.append(
                _log(
                    "warning",
                    f"High missing data (>30%): {', '.join(basic_stats['high_missing'][:5])}",
                )
            )
            if queue:
                await queue.put({"type": "log", "data": logs[-1]})

    except Exception as exc:
        logger.exception("SchemaAgent failed")
        msg = f"Schema analysis failed: {exc}"
        errors.append(msg)
        logs.append(_log("error", msg))
        if queue:
            await queue.put({"type": "log", "data": logs[-1]})
        return {"agent_logs": logs, "errors": errors}

    return {
        "columns": columns,
        "numeric_columns": numeric_cols,
        "categorical_columns": categorical_cols,
        "datetime_columns": datetime_cols,
        "text_columns": text_cols,
        "basic_stats": basic_stats,
        "agent_logs": logs,
        "errors": errors,
    }


def _round(val: Any) -> float | None:
    if val is None:
        return None
    try:
        return round(float(val), 6)
    except (ValueError, TypeError):
        return None
