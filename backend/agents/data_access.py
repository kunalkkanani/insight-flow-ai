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
from pathlib import Path
from typing import Any

import httpx
from langgraph.types import RunnableConfig

from ..config import settings
from ..graph.state import AgentLog, AnalysisState
from ..tools.duckdb_tool import create_connection, execute_query, execute_scalar
from ..tools.metadata_tool import get_file_metadata, get_url_metadata

logger = logging.getLogger(__name__)
AGENT = "DataAccessAgent"

# Common NA sentinel strings that appear in real-world CSVs.
# DuckDB will treat any of these as NULL rather than trying to cast them.
_CSV_NULL_STRINGS = ["NA", "N/A", "n/a", "nan", "NaN", "NAN", "null", "NULL", "None", "NONE", "#N/A", "#NA", ""]

_READ_FN = {
    "csv": "read_csv_auto",
    "parquet": "read_parquet",
    "json": "read_json_auto",
}


async def _download_url(url: str, dest_dir: Path, filename: str) -> Path:
    """Stream-download *url* into *dest_dir/filename* and return the local path."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / filename
    async with httpx.AsyncClient(timeout=300, follow_redirects=True) as client:
        async with client.stream("GET", url) as r:
            r.raise_for_status()
            with open(dest, "wb") as fh:
                async for chunk in r.aiter_bytes(chunk_size=1 << 20):  # 1 MB chunks
                    fh.write(chunk)
    return dest


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
            # Download the remote file to local disk so every subsequent DuckDB
            # query reads from disk instead of making repeated HTTP range requests
            # to the CDN (which causes ECONNRESET / HTTP 0 errors on large files).
            dest_dir = Path(settings.upload_dir) / state["session_id"]
            logs.append(_log("info", f"Downloading {meta['name']} ({meta['size_mb']:.1f} MB)…"))
            if queue:
                await queue.put({"type": "log", "data": logs[-1]})
            local_path = await _download_url(url, dest_dir, meta["name"])
            source_path = str(local_path)
            # Refresh metadata from the local file (size is now exact)
            meta = await get_file_metadata(source_path)
            logs.append(_log("success", f"Downloaded to local cache ({meta['size_mb']:.1f} MB)"))
            if queue:
                await queue.put({"type": "log", "data": logs[-1]})
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

        if fmt == "csv":
            # Build nullstr list so DuckDB treats "NA", "N/A", "nan", etc. as NULL
            # instead of crashing when it hits them in a column it inferred as numeric.
            # sample_size=-1 scans the full file for type detection, preventing
            # late-row surprises like the football CSV's unplayed future fixtures.
            null_list = ", ".join(f"'{s}'" for s in _CSV_NULL_STRINGS)

            def _csv_view_sql(encoding: str = "") -> str:
                enc_part = f", encoding='{encoding}'" if encoding else ""
                return (
                    f"CREATE OR REPLACE VIEW {raw_table} AS "
                    f"SELECT * FROM {read_fn}('{escaped}', "
                    f"nullstr=[{null_list}], "
                    f"sample_size=-1, "
                    f"ignore_errors=false{enc_part})"
                )

            try:
                conn.execute(_csv_view_sql())
            except Exception as enc_exc:
                # Retry with LATIN-1 if the file has non-UTF-8 characters
                # (e.g. datasets with names containing ü, é, ñ etc.)
                if "unicode" in str(enc_exc).lower() or "utf" in str(enc_exc).lower():
                    logs.append(_log("warning", "Non-UTF-8 characters detected — retrying with LATIN-1 encoding"))
                    if queue:
                        await queue.put({"type": "log", "data": logs[-1]})
                    conn.execute(_csv_view_sql("LATIN-1"))
                else:
                    raise
        else:
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
