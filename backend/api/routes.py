"""
FastAPI route definitions
──────────────────────────
POST  /api/analyze/file   — Upload a file and start analysis
POST  /api/analyze/url    — Provide a public URL and start analysis
GET   /api/stream/{id}    — SSE stream of agent logs + final result
GET   /api/status/{id}    — Poll for completion (non-SSE)
POST  /api/question/{id}  — Ask a follow-up question
DELETE /api/session/{id}  — Clean up session
GET   /api/health         — Health check
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import uuid
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks, File, HTTPException, UploadFile
from fastapi.responses import StreamingResponse

from ..config import settings
from ..graph.orchestrator import cleanup_session, create_session, get_session, run_analysis, run_qa
from ..graph.state import AnalysisState
from .models import (
    AnalyzeResponse,
    AnalyzeURLRequest,
    HealthResponse,
    QuestionRequest,
    QuestionResponse,
    SessionStatus,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api")

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_initial_state(session_id: str) -> dict:
    return {
        "session_id": session_id,
        "input_type": None,
        "file_path": None,
        "url": None,
        "original_filename": None,
        "file_format": None,
        "file_size_mb": None,
        "row_count": None,
        "column_count": None,
        "preview_rows": None,
        "source_path": None,
        "raw_table": None,
        "strategy": None,
        "effective_table": None,
        "sample_size": None,
        "columns": None,
        "numeric_columns": None,
        "categorical_columns": None,
        "datetime_columns": None,
        "text_columns": None,
        "basic_stats": None,
        "analysis_plan": None,
        "query_results": None,
        "correlation_matrix_spec": None,
        "insights": None,
        "anomalies": None,
        "recommendations": None,
        "report": None,
        "agent_logs": [],
        "errors": [],
        "user_question": None,
        "qa_response": None,
        "conversation_history": None,
    }


# ---------------------------------------------------------------------------
# File upload analysis
# ---------------------------------------------------------------------------


@router.post("/analyze/file", response_model=AnalyzeResponse, tags=["Analysis"])
async def analyze_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
) -> AnalyzeResponse:
    """Upload a CSV / Parquet / JSON file and begin autonomous analysis."""
    session_id = str(uuid.uuid4())
    create_session(session_id)

    # Validate file size
    content = await file.read()
    size_mb = len(content) / (1024 * 1024)
    if size_mb > settings.max_upload_mb:
        raise HTTPException(
            status_code=413,
            detail=f"File too large ({size_mb:.1f} MB). Max: {settings.max_upload_mb} MB.",
        )

    # Persist to disk
    upload_dir = Path(settings.upload_dir) / session_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    safe_name = Path(file.filename or "upload").name
    file_path = str(upload_dir / safe_name)
    with open(file_path, "wb") as f:
        f.write(content)

    initial_state = AnalysisState(
        **{
            **_make_initial_state(session_id),
            "input_type": "file",
            "file_path": file_path,
            "original_filename": safe_name,
        }
    )

    background_tasks.add_task(run_analysis, session_id, initial_state)
    logger.info("Started analysis session %s for file %s", session_id, safe_name)
    return AnalyzeResponse(session_id=session_id)


# ---------------------------------------------------------------------------
# URL analysis
# ---------------------------------------------------------------------------


@router.post("/analyze/url", response_model=AnalyzeResponse, tags=["Analysis"])
async def analyze_url(
    background_tasks: BackgroundTasks,
    body: AnalyzeURLRequest,
) -> AnalyzeResponse:
    """Provide a public URL (CSV / Parquet / JSON) and begin analysis."""
    session_id = str(uuid.uuid4())
    create_session(session_id)

    initial_state = AnalysisState(
        **{
            **_make_initial_state(session_id),
            "input_type": "url",
            "url": body.url,
        }
    )

    background_tasks.add_task(run_analysis, session_id, initial_state)
    logger.info("Started analysis session %s for URL %s", session_id, body.url)
    return AnalyzeResponse(session_id=session_id)


# ---------------------------------------------------------------------------
# SSE stream
# ---------------------------------------------------------------------------


@router.get("/stream/{session_id}", tags=["Streaming"])
async def stream_events(session_id: str) -> StreamingResponse:
    """
    Server-Sent Events endpoint.
    Emits:
      event: log    — agent log entry
      event: result — final report (on completion)
      event: error  — error message
      event: done   — stream closed
    """
    session = get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    queue: asyncio.Queue = session.get("queue", asyncio.Queue())

    async def event_stream():
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30)
                except asyncio.TimeoutError:
                    # Keepalive
                    yield ": keepalive\n\n"
                    continue

                if event is None:
                    yield "event: done\ndata: {}\n\n"
                    break

                event_type = event.get("type", "log")
                data = json.dumps(event.get("data", {}), default=str)
                yield f"event: {event_type}\ndata: {data}\n\n"

        except asyncio.CancelledError:
            logger.debug("SSE client disconnected: %s", session_id)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ---------------------------------------------------------------------------
# Status poll (non-SSE)
# ---------------------------------------------------------------------------


@router.get("/status/{session_id}", response_model=SessionStatus, tags=["Analysis"])
async def get_status(session_id: str) -> SessionStatus:
    """Poll for analysis completion without SSE."""
    session = get_session(session_id)
    if not session:
        return SessionStatus(session_id=session_id, status="not_found")

    report = session.get("report")
    status = "complete" if report else "running"
    return SessionStatus(session_id=session_id, status=status, report=report)


# ---------------------------------------------------------------------------
# QA
# ---------------------------------------------------------------------------


@router.post("/question/{session_id}", response_model=QuestionResponse, tags=["QA"])
async def ask_question(
    session_id: str,
    body: QuestionRequest,
) -> QuestionResponse:
    """Ask a follow-up question about the analysed dataset."""
    session = get_session(session_id)
    if not session or not session.get("report"):
        raise HTTPException(
            status_code=404,
            detail="Session not found or analysis not complete.",
        )

    result = await run_qa(session_id, body.question)
    return QuestionResponse(
        response=result["response"],
        conversation_history=result.get("conversation_history", []),
    )


# ---------------------------------------------------------------------------
# Session cleanup
# ---------------------------------------------------------------------------


@router.delete("/session/{session_id}", tags=["Session"])
async def delete_session(session_id: str) -> dict:
    """Release session resources (DuckDB connection + temp files)."""
    cleanup_session(session_id)

    # Remove uploaded files
    upload_dir = Path(settings.upload_dir) / session_id
    if upload_dir.exists():
        shutil.rmtree(upload_dir, ignore_errors=True)

    return {"deleted": True, "session_id": session_id}


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@router.get("/health", response_model=HealthResponse, tags=["Health"])
async def health() -> HealthResponse:
    return HealthResponse(version=settings.app_version)
