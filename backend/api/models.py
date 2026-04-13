"""Pydantic request / response models for the FastAPI routes."""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------


class AnalyzeURLRequest(BaseModel):
    url: str = Field(..., description="Public URL to a CSV / Parquet / JSON file")


class AnalyzeResponse(BaseModel):
    session_id: str
    message: str = "Analysis started. Connect to /api/stream/{session_id} for live updates."


# ---------------------------------------------------------------------------
# QA
# ---------------------------------------------------------------------------


class QuestionRequest(BaseModel):
    question: str = Field(..., min_length=1, max_length=1000)


class QuestionResponse(BaseModel):
    response: str
    conversation_history: list[dict[str, str]] = []


# ---------------------------------------------------------------------------
# Session status
# ---------------------------------------------------------------------------


class SessionStatus(BaseModel):
    session_id: str
    status: str  # "running" | "complete" | "error" | "not_found"
    report: Optional[dict[str, Any]] = None


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


class HealthResponse(BaseModel):
    status: str = "ok"
    version: str
