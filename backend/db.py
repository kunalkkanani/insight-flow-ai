"""
SQLite persistence layer
─────────────────────────
Stores completed analysis reports so they survive server restarts.
Uses Python's built-in sqlite3 — no extra dependencies required.

Table: sessions
  id           TEXT  PRIMARY KEY
  created_at   TEXT
  filename     TEXT
  status       TEXT  (running | complete | error)
  report_json  TEXT  (JSON blob of the full report)
  error_msg    TEXT
  updated_at   TEXT
"""
from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import settings

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _db_path() -> Path:
    path = Path(settings.db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_db_path()), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Schema init
# ---------------------------------------------------------------------------

def init_db() -> None:
    """Create tables if they don't exist. Called once at app startup."""
    with _connect() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sessions (
                id          TEXT PRIMARY KEY,
                created_at  TEXT NOT NULL,
                filename    TEXT,
                status      TEXT NOT NULL DEFAULT 'running',
                report_json TEXT,
                error_msg   TEXT,
                updated_at  TEXT NOT NULL
            )
            """
        )
        conn.commit()
    logger.info("SQLite DB initialised at %s", _db_path())


# ---------------------------------------------------------------------------
# Write helpers
# ---------------------------------------------------------------------------

def upsert_session_running(session_id: str, filename: str | None = None) -> None:
    """Record that a session has started (idempotent)."""
    now = _now()
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO sessions (id, created_at, filename, status, updated_at)
            VALUES (?, ?, ?, 'running', ?)
            ON CONFLICT(id) DO UPDATE SET
                status     = 'running',
                updated_at = excluded.updated_at
            """,
            (session_id, now, filename, now),
        )
        conn.commit()


def update_session_complete(session_id: str, report: dict[str, Any]) -> None:
    """Persist the completed report JSON."""
    with _connect() as conn:
        conn.execute(
            """
            UPDATE sessions
            SET status      = 'complete',
                report_json = ?,
                updated_at  = ?
            WHERE id = ?
            """,
            (json.dumps(report, default=str), _now(), session_id),
        )
        conn.commit()
    logger.info("Persisted completed report for session %s", session_id)


def update_session_error(session_id: str, error: str) -> None:
    """Record a failed session."""
    with _connect() as conn:
        conn.execute(
            """
            UPDATE sessions
            SET status    = 'error',
                error_msg = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (error, _now(), session_id),
        )
        conn.commit()


# ---------------------------------------------------------------------------
# Read helpers
# ---------------------------------------------------------------------------

def load_session(session_id: str) -> dict[str, Any] | None:
    """
    Load a session from SQLite.
    Returns a dict with keys: id, status, filename, report (dict | None), error_msg.
    Returns None if the session doesn't exist.
    """
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, status, filename, report_json, error_msg FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()

    if row is None:
        return None

    report = None
    if row["report_json"]:
        try:
            report = json.loads(row["report_json"])
        except json.JSONDecodeError:
            logger.warning("Could not decode report_json for session %s", session_id)

    return {
        "id": row["id"],
        "status": row["status"],
        "filename": row["filename"],
        "report": report,
        "error_msg": row["error_msg"],
    }


def list_recent_sessions(limit: int = 20) -> list[dict[str, Any]]:
    """Return the most recent sessions (without full report blobs)."""
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT id, created_at, filename, status, error_msg, updated_at
            FROM sessions
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()

    return [dict(r) for r in rows]
