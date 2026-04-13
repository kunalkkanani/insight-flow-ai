"""
Report Agent
────────────
Assembles the final structured report from all upstream agent outputs.
This is a pure state-assembly step — no LLM or database calls.
"""
from __future__ import annotations

import datetime
import logging
from typing import Any

from langgraph.types import RunnableConfig

from ..graph.state import AgentLog, AnalysisState

logger = logging.getLogger(__name__)
AGENT = "ReportAgent"


def _log(level: str, msg: str) -> AgentLog:
    return AgentLog(
        agent=AGENT,
        message=msg,
        timestamp=datetime.datetime.utcnow().isoformat(),
        level=level,
    )


async def report_agent(
    state: AnalysisState, config: RunnableConfig
) -> dict[str, Any]:
    from ..graph.orchestrator import get_session

    session = get_session(state["session_id"])
    queue = session.get("queue")
    logs: list[AgentLog] = []

    logs.append(_log("info", "Assembling final report…"))

    query_results = state.get("query_results") or []

    # Build chart list (only those with a spec and no error)
    charts = [
        {
            "id": r["task_id"],
            "title": r["title"],
            "description": r["description"],
            "chart_spec": r["chart_spec"],
        }
        for r in query_results
        if r.get("chart_spec") and not r.get("error")
    ]

    # Add correlation matrix if available
    if state.get("correlation_matrix_spec"):
        charts.insert(
            0,
            {
                "id": "correlation_matrix",
                "title": "Correlation Matrix",
                "description": "Pearson correlation between numeric columns",
                "chart_spec": state["correlation_matrix_spec"],
            },
        )

    report: dict[str, Any] = {
        "session_id": state["session_id"],
        "generated_at": datetime.datetime.utcnow().isoformat(),
        "dataset": {
            "filename": state.get("original_filename", "dataset"),
            "format": state.get("file_format", "unknown"),
            "size_mb": state.get("file_size_mb", 0),
            "row_count": state.get("row_count", 0),
            "column_count": state.get("column_count", 0),
            "strategy": state.get("strategy", "full"),
            "sample_size": state.get("sample_size"),
        },
        "schema": {
            "columns": state.get("columns") or [],
            "numeric_columns": state.get("numeric_columns") or [],
            "categorical_columns": state.get("categorical_columns") or [],
            "datetime_columns": state.get("datetime_columns") or [],
            "text_columns": state.get("text_columns") or [],
            "basic_stats": state.get("basic_stats") or {},
        },
        "preview_rows": state.get("preview_rows") or [],
        "insights": state.get("insights") or [],
        "anomalies": state.get("anomalies") or [],
        "recommendations": state.get("recommendations") or [],
        "charts": charts,
        "query_results": query_results,
        "agent_logs": state.get("agent_logs") or [],
        "errors": state.get("errors") or [],
    }

    logs.append(
        _log(
            "success",
            f"Report ready — {len(charts)} charts, "
            f"{len(report['insights'])} insights",
        )
    )
    if queue:
        await queue.put({"type": "log", "data": logs[-1]})

    return {"report": report, "agent_logs": logs, "errors": []}
