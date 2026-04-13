"""
Planner Agent  (the Brain)
──────────────────────────
• Receives schema information (NO raw data)
• Calls Claude to decide which analyses to perform
• Falls back to a heuristic planner when no API key is set
• Returns an ordered list of AnalysisTask objects
"""
from __future__ import annotations

import datetime
import json
import logging
import re
from typing import Any

import anthropic
from langgraph.types import RunnableConfig

from ..config import settings
from ..graph.state import AgentLog, AnalysisState, AnalysisTask

logger = logging.getLogger(__name__)
AGENT = "PlannerAgent"

# ---------------------------------------------------------------------------
# System prompt (token-efficient — LLM sees only schema, never raw data)
# ---------------------------------------------------------------------------

_SYSTEM = """You are an expert data analyst. Given a dataset schema summary, design the best exploratory data analysis plan.

Return ONLY a JSON array (no markdown, no explanation) of 5–7 analysis tasks. Each element:
{
  "type": "distribution" | "correlation" | "time_series" | "aggregation" | "anomaly" | "overview",
  "title": "Short human-readable title",
  "description": "One sentence: what this analysis reveals",
  "columns": ["col1", ...],
  "chart_type": "bar" | "line" | "scatter" | "heatmap" | "pie" | "box" | "histogram",
  "priority": 1–5
}

Rules:
- Always include exactly one "overview" task (priority 1)
- Prefer "heatmap" chart_type for correlation tasks with many columns
- Prefer "scatter" for two-column correlation
- Prefer "line" for time_series
- Prefer "histogram" for numeric distributions
- Prefer "bar" for categorical distributions and aggregations
- If datetime columns exist, include time_series using the most relevant numeric column
- Choose analyses that reveal the most business/domain insight
- Columns must be from the provided schema"""


def _log(level: str, msg: str) -> AgentLog:
    return AgentLog(
        agent=AGENT,
        message=msg,
        timestamp=datetime.datetime.utcnow().isoformat(),
        level=level,
    )


async def planner_agent(
    state: AnalysisState, config: RunnableConfig
) -> dict[str, Any]:
    from ..graph.orchestrator import get_session

    session = get_session(state["session_id"])
    queue = session.get("queue")
    logs: list[AgentLog] = []
    errors: list[str] = []

    numeric_cols = state.get("numeric_columns") or []
    categorical_cols = state.get("categorical_columns") or []
    datetime_cols = state.get("datetime_columns") or []
    columns = state.get("columns") or []
    row_count = state.get("row_count") or 0
    filename = state.get("original_filename", "dataset")

    logs.append(_log("info", "Building analysis plan…"))
    if queue:
        await queue.put({"type": "log", "data": logs[-1]})

    # Build a compact schema summary (token-efficient)
    stats_summary: dict[str, Any] = {}
    for col in columns:
        if col["category"] == "numeric":
            stats_summary[col["name"]] = {
                "min": col.get("min_val"),
                "max": col.get("max_val"),
                "mean": col.get("mean_val"),
                "missing_pct": col.get("missing_pct"),
            }

    # ── LLM planning ──────────────────────────────────────────────────────
    plan: list[AnalysisTask] = []

    if settings.anthropic_api_key:
        logs.append(_log("info", "Calling Claude for analysis planning…"))
        if queue:
            await queue.put({"type": "log", "data": logs[-1]})
        try:
            plan = await _llm_plan(filename, row_count, numeric_cols, categorical_cols, datetime_cols, stats_summary)
            logs.append(_log("success", f"Claude generated {len(plan)}-task analysis plan"))
        except Exception as exc:
            logger.warning("LLM planning failed, using heuristics: %s", exc)
            logs.append(_log("warning", f"LLM planning failed ({exc}), using heuristics"))
            plan = _heuristic_plan(numeric_cols, categorical_cols, datetime_cols)
    else:
        logs.append(_log("info", "No API key — using heuristic planner"))
        plan = _heuristic_plan(numeric_cols, categorical_cols, datetime_cols)
        logs.append(_log("success", f"Heuristic plan: {len(plan)} tasks"))

    if queue:
        await queue.put({"type": "log", "data": logs[-1]})

    # Log individual tasks
    for task in plan:
        task_log = _log("info", f"  → [{task['type']}] {task['title']}")
        logs.append(task_log)
        if queue:
            await queue.put({"type": "log", "data": task_log})

    return {
        "analysis_plan": plan,
        "agent_logs": logs,
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# LLM planner
# ---------------------------------------------------------------------------


async def _llm_plan(
    filename: str,
    row_count: int,
    numeric_cols: list[str],
    categorical_cols: list[str],
    datetime_cols: list[str],
    stats_summary: dict,
) -> list[AnalysisTask]:
    client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)

    user_msg = (
        f"Dataset: {filename}\n"
        f"Rows: {row_count:,}\n\n"
        f"Numeric columns ({len(numeric_cols)}): {', '.join(numeric_cols[:10])}\n"
        f"Categorical columns ({len(categorical_cols)}): {', '.join(categorical_cols[:10])}\n"
        f"Datetime columns ({len(datetime_cols)}): {', '.join(datetime_cols[:5])}\n\n"
        f"Numeric stats (sample):\n{json.dumps(stats_summary, indent=2)[:1500]}"
    )

    response = await client.messages.create(
        model=settings.claude_model,
        max_tokens=1200,
        temperature=settings.claude_temperature,
        system=_SYSTEM,
        messages=[{"role": "user", "content": user_msg}],
    )

    raw = response.content[0].text.strip()
    # Robustly extract JSON array
    match = re.search(r"\[.*\]", raw, re.DOTALL)
    parsed = json.loads(match.group() if match else raw)

    # Validate and normalise
    validated: list[AnalysisTask] = []
    for item in parsed:
        if isinstance(item, dict) and "type" in item and "title" in item:
            validated.append(
                AnalysisTask(
                    type=item.get("type", "overview"),
                    title=item.get("title", "Analysis"),
                    description=item.get("description", ""),
                    columns=item.get("columns", []),
                    chart_type=item.get("chart_type", "bar"),
                    priority=int(item.get("priority", 3)),
                )
            )
    return validated


# ---------------------------------------------------------------------------
# Heuristic fallback planner
# ---------------------------------------------------------------------------


def _heuristic_plan(
    numeric_cols: list[str],
    categorical_cols: list[str],
    datetime_cols: list[str],
) -> list[AnalysisTask]:
    tasks: list[AnalysisTask] = []

    # 1. Always: overview
    tasks.append(AnalysisTask(
        type="overview",
        title="Dataset Overview",
        description="First 100 rows preview and structure",
        columns=[],
        chart_type="bar",
        priority=1,
    ))

    # 2. Distribution — first numeric
    if numeric_cols:
        tasks.append(AnalysisTask(
            type="distribution",
            title=f"Distribution of {numeric_cols[0]}",
            description=f"Histogram showing spread of {numeric_cols[0]}",
            columns=[numeric_cols[0]],
            chart_type="histogram",
            priority=2,
        ))

    # 3. Distribution — first categorical
    if categorical_cols:
        tasks.append(AnalysisTask(
            type="distribution",
            title=f"Top Values — {categorical_cols[0]}",
            description=f"Frequency count for {categorical_cols[0]}",
            columns=[categorical_cols[0]],
            chart_type="bar",
            priority=2,
        ))

    # 4. Correlation heatmap if 3+ numeric
    if len(numeric_cols) >= 3:
        tasks.append(AnalysisTask(
            type="correlation",
            title="Numeric Correlation Matrix",
            description="Pearson correlations between all numeric columns",
            columns=numeric_cols[:8],
            chart_type="heatmap",
            priority=3,
        ))
    elif len(numeric_cols) == 2:
        tasks.append(AnalysisTask(
            type="correlation",
            title=f"{numeric_cols[0]} vs {numeric_cols[1]}",
            description=f"Scatter plot of {numeric_cols[0]} against {numeric_cols[1]}",
            columns=numeric_cols[:2],
            chart_type="scatter",
            priority=3,
        ))

    # 5. Aggregation — if both categorical and numeric
    if categorical_cols and numeric_cols:
        tasks.append(AnalysisTask(
            type="aggregation",
            title=f"{numeric_cols[0]} by {categorical_cols[0]}",
            description=f"Total {numeric_cols[0]} grouped by {categorical_cols[0]}",
            columns=[categorical_cols[0], numeric_cols[0]],
            chart_type="bar",
            priority=3,
        ))

    # 6. Time series — if datetime + numeric
    if datetime_cols and numeric_cols:
        tasks.append(AnalysisTask(
            type="time_series",
            title=f"{numeric_cols[0]} Over Time",
            description=f"Trend of {numeric_cols[0]} over {datetime_cols[0]}",
            columns=[datetime_cols[0], numeric_cols[0]],
            chart_type="line",
            priority=2,
        ))

    # 7. Anomaly — if numeric available
    if numeric_cols:
        tasks.append(AnalysisTask(
            type="anomaly",
            title=f"Outliers in {numeric_cols[0]}",
            description=f"Statistical anomalies (z-score > 3) in {numeric_cols[0]}",
            columns=[numeric_cols[0]],
            chart_type="scatter",
            priority=4,
        ))

    return tasks[:7]
