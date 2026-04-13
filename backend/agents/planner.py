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

_SYSTEM = """You are an expert data analyst. Given a dataset schema, design the most insightful EDA plan.

Return ONLY a JSON array (no markdown, no explanation) of 6–8 analysis tasks. Each element:
{
  "type": "distribution" | "correlation" | "time_series" | "aggregation" | "anomaly" | "overview",
  "title": "Short human-readable title",
  "description": "One sentence: what this reveals",
  "columns": ["col1", ...],
  "chart_type": "bar" | "line" | "scatter" | "heatmap" | "pie" | "histogram",
  "priority": 1–5
}

STRICT RULES — follow every one:
1. Always include exactly one "overview" task (priority 1).
2. NEVER use high-cardinality text columns (marked [TEXT/ID]) in grouping or correlation — they are IDs or free text.
3. For categorical grouping/aggregation, ONLY use LOW-CARDINALITY categoricals (marked [CAT], unique_count < 50).
4. For numeric distributions: use "histogram" chart_type — do NOT use "bar".
5. For categorical distributions (value counts): use "bar" chart_type.
6. For correlation with 3+ numeric cols → "heatmap"; exactly 2 → "scatter".
7. For time_series: always pair a datetime column with a meaningful numeric column.
8. Choose tasks that expose real patterns, trends, or anomalies — avoid redundant or trivial analyses.
9. Columns listed in "columns" MUST exist exactly in the provided schema."""


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

    # Build a rich schema summary so Claude can make smarter chart choices.
    # Include cardinality tags so Claude avoids grouping by ID/free-text columns.
    stats_summary: dict[str, Any] = {}
    for col in columns:
        cat = col["category"]
        uniq = col.get("unique_count", 0)
        missing = col.get("missing_pct", 0)
        samples = col.get("sample_values") or []

        entry: dict[str, Any] = {"category": cat, "unique": uniq, "missing_pct": missing}

        if cat == "numeric":
            entry.update({
                "min": col.get("min_val"),
                "max": col.get("max_val"),
                "mean": col.get("mean_val"),
                "std": col.get("std_val"),
            })
        elif cat in ("categorical", "text", "boolean"):
            # Show top sample values so Claude knows what the column contains
            entry["samples"] = [str(v) for v in samples[:5]]
            # Tag cardinality so Claude knows what's safe to group by
            if cat == "text" or uniq > 500:
                entry["tag"] = "[TEXT/ID — do not group]"
            elif uniq <= 2:
                entry["tag"] = "[BINARY]"
            elif uniq <= 20:
                entry["tag"] = "[CAT — low cardinality, good for grouping]"
            else:
                entry["tag"] = "[CAT — medium cardinality]"
        elif cat == "datetime":
            entry["samples"] = [str(v) for v in samples[:3]]

        stats_summary[col["name"]] = entry

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
            plan = _heuristic_plan(numeric_cols, categorical_cols, datetime_cols, columns)
    else:
        logs.append(_log("info", "No API key — using heuristic planner"))
        plan = _heuristic_plan(numeric_cols, categorical_cols, datetime_cols, columns)
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
        f"Dataset: {filename}  |  Rows: {row_count:,}\n\n"
        f"=== FULL SCHEMA (use ONLY these column names) ===\n"
        f"{json.dumps(stats_summary, indent=2)[:3000]}\n\n"
        f"Numeric cols: {numeric_cols[:15]}\n"
        f"Low-cardinality categoricals (safe to group): "
        f"{[c for c in categorical_cols if (stats_summary.get(c, {}).get('unique', 999)) <= 50][:10]}\n"
        f"Datetime cols: {datetime_cols[:5]}"
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
    columns: list[dict] | None = None,
) -> list[AnalysisTask]:
    # Filter categoricals to only low-cardinality ones that are safe to group by.
    col_lookup = {c["name"]: c for c in (columns or [])}
    safe_cats = [
        c for c in categorical_cols
        if col_lookup.get(c, {}).get("unique_count", 999) <= 50
    ] or categorical_cols[:3]  # fallback if no column metadata
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

    # 3. Distribution — first safe categorical
    if safe_cats:
        tasks.append(AnalysisTask(
            type="distribution",
            title=f"Top Values — {safe_cats[0]}",
            description=f"Frequency count for {safe_cats[0]}",
            columns=[safe_cats[0]],
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

    # 5. Aggregation — safe categorical × numeric
    if safe_cats and numeric_cols:
        tasks.append(AnalysisTask(
            type="aggregation",
            title=f"{numeric_cols[0]} by {safe_cats[0]}",
            description=f"Total {numeric_cols[0]} grouped by {safe_cats[0]}",
            columns=[safe_cats[0], numeric_cols[0]],
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
