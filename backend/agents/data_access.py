"""
Data Access Agent
─────────────────
• Detects input type (file or URL)
• Detects file format (CSV / Parquet / JSON)
• Registers source as a DuckDB view
• Fetches row/column counts and a 5-row preview
"""
from __future__ import annotations

import datetime
import logging
from typing import Any

from langgraph.types import RunnableConfig

from ..graph.state import AgentLog, AnalysisState
from ..tools.duckdb_tool import create_connection, execute_query, execute_scalar
from ..tools.metadata_tool import get_file_metadata, get_url_metadata

logger = logging.getLogger(__name__)
AGENT = "DataAccessAgent"

_READ_FN = {
    "csv": "read_csv_auto",
    "parquet": "read_parquet",
    "json": "read_json_auto",
}


def _log(level: str, msg: str) -> AgentLog:
    return AgentLog(
        agent=AGENT,
        message=msg,
        timestamp=datetime.datetime.utcnow().isoformat(),
        level=level,
    )


async def data_access_agent(
    state: AnalysisState, config: RunnableConfig
) -> dict[str, Any]:
    from ..graph.orchestrator import get_session

    session = get_session(state["session_id"])
    logs: list[AgentLog] = []
    errors: list[str] = []

    try:
        logs.append(_log("info", "Detecting input source…"))
        queue = session.get("queue")

        input_type = state.get("input_type")
        file_path = state.get("file_path")
        url = state.get("url")

        # ── 1. Gather metadata ──────────────────────────────────────────────
        if input_type == "file" and file_path:
            meta = await get_file_metadata(file_path)
            source_path = file_path
        elif input_type == "url" and url:
            meta = await get_url_metadata(url)
            source_path = url
        else:
            raise ValueError("No valid input: provide a file upload or a URL.")

        fmt = meta["format"]
        size_mb = meta["size_mb"]
        name = meta["name"]

        logs.append(_log("info", f"Source: {name} ({size_mb:.1f} MB · {fmt.upper()})"))
        if queue:
            await queue.put({"type": "log", "data": logs[-1]})

        # ── 2. Create DuckDB connection (per-session) ───────────────────────
        conn = session.get("conn")
        if conn is None:
            conn = create_connection()
            session["conn"] = conn
            logs.append(_log("info", "DuckDB connection initialised"))

        # ── 3. Register source as a DuckDB view ────────────────────────────
        read_fn = _READ_FN.get(fmt, "read_csv_auto")
        raw_table = "raw_data"

        # Quote the path to handle spaces and special chars
        escaped = source_path.replace("'", "''")
        view_sql = f"CREATE OR REPLACE VIEW {raw_table} AS SELECT * FROM {read_fn}('{escaped}')"
        conn.execute(view_sql)

        logs.append(_log("info", f"Registered view via {read_fn}()"))
        if queue:
            await queue.put({"type": "log", "data": logs[-1]})

        # ── 4. Row / column counts ──────────────────────────────────────────
        row_count = int(execute_scalar(conn, f"SELECT COUNT(*) FROM {raw_table}") or 0)
        schema_rows = execute_query(conn, f"DESCRIBE {raw_table}")
        column_count = len(schema_rows)

        logs.append(_log("success", f"Dataset ready: {row_count:,} rows × {column_count} columns"))
        if queue:
            await queue.put({"type": "log", "data": logs[-1]})

        # ── 5. Preview (5 rows) ─────────────────────────────────────────────
        preview_rows = execute_query(conn, f"SELECT * FROM {raw_table} LIMIT 5")
        logs.append(_log("info", "Preview captured (5 rows)"))

    except Exception as exc:
        logger.exception("DataAccessAgent failed")
        msg = f"Data access failed: {exc}"
        errors.append(msg)
        logs.append(_log("error", msg))
        if session.get("queue"):
            await session["queue"].put({"type": "log", "data": logs[-1]})
        return {"agent_logs": logs, "errors": errors}

    return {
        "file_format": fmt,
        "file_size_mb": size_mb,
        "original_filename": name,
        "row_count": row_count,
        "column_count": column_count,
        "preview_rows": preview_rows,
        "source_path": source_path,
        "raw_table": raw_table,
        "effective_table": raw_table,
        "agent_logs": logs,
        "errors": errors,
    }
