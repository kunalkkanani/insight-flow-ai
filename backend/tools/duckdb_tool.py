"""DuckDB execution tool — per-session connections, retry logic, safe serialisation."""
from __future__ import annotations

import datetime
import decimal
import logging
from typing import Any

import duckdb

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Connection factory
# ---------------------------------------------------------------------------


def create_connection() -> duckdb.DuckDBPyConnection:
    """Create an in-memory DuckDB connection with HTTP(S) + JSON support."""
    conn = duckdb.connect(database=":memory:", read_only=False)
    for ext in ("httpfs", "json"):
        try:
            conn.execute(f"INSTALL {ext}; LOAD {ext};")
        except Exception as exc:
            logger.warning("Could not load DuckDB extension '%s': %s", ext, exc)
    return conn


# ---------------------------------------------------------------------------
# Query execution
# ---------------------------------------------------------------------------


def execute_query(
    conn: duckdb.DuckDBPyConnection,
    sql: str,
    params: list[Any] | None = None,
    max_rows: int = 50_000,
    retries: int = 2,
) -> list[dict[str, Any]]:
    """Execute SQL and return rows as a list of JSON-serialisable dicts."""
    last_error: Exception | None = None

    for attempt in range(retries + 1):
        try:
            rel = conn.execute(sql, params or [])
            if rel.description is None:
                return []
            columns = [desc[0] for desc in rel.description]
            rows = rel.fetchmany(max_rows)
            result = [
                {col: _safe(val) for col, val in zip(columns, row)}
                for row in rows
            ]
            logger.debug("Query OK (%d rows) | %s…", len(result), sql[:80])
            return result
        except duckdb.Error as exc:
            last_error = exc
            logger.warning(
                "DuckDB attempt %d/%d failed: %s", attempt + 1, retries + 1, exc
            )
        except Exception as exc:
            raise RuntimeError(f"Unexpected error: {exc}") from exc

    raise RuntimeError(
        f"Query failed after {retries + 1} attempts: {last_error}\nSQL: {sql[:500]}"
    ) from last_error


def execute_scalar(
    conn: duckdb.DuckDBPyConnection,
    sql: str,
    params: list[Any] | None = None,
) -> Any:
    """Return the first column of the first row, or None."""
    rows = execute_query(conn, sql, params, max_rows=1)
    if not rows:
        return None
    return next(iter(rows[0].values()), None)


def table_exists(conn: duckdb.DuckDBPyConnection, name: str) -> bool:
    """Check whether a table or view exists in DuckDB."""
    try:
        conn.execute(f"SELECT 1 FROM {name} LIMIT 0")
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Value serialisation helpers
# ---------------------------------------------------------------------------


def _safe(value: Any) -> Any:
    """Convert DuckDB-native types that are not JSON-serialisable."""
    if isinstance(value, (datetime.date, datetime.datetime)):
        return value.isoformat()
    if isinstance(value, datetime.timedelta):
        return str(value)
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, (list, tuple)):
        return [_safe(v) for v in value]
    return value
