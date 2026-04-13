"""
Insight Agent
─────────────
• Receives execution results and schema summary (NO raw data)
• Calls Claude to generate human-readable insights, anomalies, and recommendations
• Falls back to template-based insights when no API key is available
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
from ..graph.state import AgentLog, AnalysisState

logger = logging.getLogger(__name__)
AGENT = "InsightAgent"

_SYSTEM = """You are a senior data analyst. Given EDA results (statistics and query summaries — NOT raw data), generate concise, business-relevant insights.

Return ONLY a JSON object (no markdown) with exactly these keys:
{
  "insights": ["...", "...", "...", "...", "..."],
  "anomalies": ["...", "..."],
  "recommendations": ["...", "...", "..."]
}

Rules:
- insights: 4–6 bullet-point facts discovered from the data
- anomalies: 0–3 unusual patterns or outlier findings
- recommendations: 2–4 actionable next steps
- Each string is one sentence, max 25 words
- Be specific: include numbers/percentages where available
- Never hallucinate — only reference what is in the results"""


def _log(level: str, msg: str) -> AgentLog:
    return AgentLog(
        agent=AGENT,
        message=msg,
        timestamp=datetime.datetime.utcnow().isoformat(),
        level=level,
    )


async def insight_agent(
    state: AnalysisState, config: RunnableConfig
) -> dict[str, Any]:
    from ..graph.orchestrator import get_session

    session = get_session(state["session_id"])
    queue = session.get("queue")
    logs: list[AgentLog] = []
    errors: list[str] = []

    query_results = state.get("query_results") or []
    columns = state.get("columns") or []
    numeric_cols = state.get("numeric_columns") or []
    row_count = state.get("row_count") or 0
    filename = state.get("original_filename", "dataset")

    logs.append(_log("info", "Generating insights…"))
    if queue:
        await queue.put({"type": "log", "data": logs[-1]})

    # ── Build compact result summary (no raw data) ─────────────────────────
    result_summaries = []
    for r in query_results[:6]:
        if r.get("error"):
            continue
        summary = {
            "title": r["title"],
            "task_type": r["task_type"],
            "row_count": r.get("row_count", 0),
        }
        # Include top-5 rows of non-overview results
        if r["task_type"] != "overview" and r.get("rows"):
            summary["top_rows"] = r["rows"][:5]
        result_summaries.append(summary)

    # Numeric column stats summary
    stats_lines = []
    for col in columns:
        if col["category"] == "numeric" and col.get("mean_val") is not None:
            stats_lines.append(
                f"{col['name']}: mean={col['mean_val']}, "
                f"min={col['min_val']}, max={col['max_val']}, "
                f"missing={col['missing_pct']}%"
            )

    insights: list[str] = []
    anomalies: list[str] = []
    recommendations: list[str] = []

    if settings.anthropic_api_key:
        try:
            logs.append(_log("info", "Calling Claude for insights…"))
            if queue:
                await queue.put({"type": "log", "data": logs[-1]})

            client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
            user_msg = (
                f"Dataset: {filename} ({row_count:,} rows)\n\n"
                f"Numeric column statistics:\n" + "\n".join(stats_lines[:10]) + "\n\n"
                f"Analysis results:\n{json.dumps(result_summaries, indent=2)[:3000]}"
            )

            response = await client.messages.create(
                model=settings.claude_model,
                max_tokens=900,
                temperature=settings.claude_temperature,
                system=_SYSTEM,
                messages=[{"role": "user", "content": user_msg}],
            )
            raw = response.content[0].text.strip()
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            parsed = json.loads(match.group() if match else raw)
            insights = parsed.get("insights", [])
            anomalies = parsed.get("anomalies", [])
            recommendations = parsed.get("recommendations", [])
            logs.append(_log("success", f"Generated {len(insights)} insights via Claude"))

        except Exception as exc:
            logger.warning("Insight LLM call failed: %s", exc)
            logs.append(_log("warning", f"LLM insight failed ({exc}), using templates"))
            insights, anomalies, recommendations = _template_insights(
                columns, numeric_cols, row_count, query_results
            )
    else:
        insights, anomalies, recommendations = _template_insights(
            columns, numeric_cols, row_count, query_results
        )
        logs.append(_log("success", f"Template insights: {len(insights)} insights"))

    if queue:
        await queue.put({"type": "log", "data": logs[-1]})

    return {
        "insights": insights,
        "anomalies": anomalies,
        "recommendations": recommendations,
        "agent_logs": logs,
        "errors": errors,
    }


# ---------------------------------------------------------------------------
# Template-based fallback insights
# ---------------------------------------------------------------------------


def _template_insights(
    columns: list,
    numeric_cols: list[str],
    row_count: int,
    query_results: list,
) -> tuple[list[str], list[str], list[str]]:
    insights = [f"Dataset contains {row_count:,} rows across {len(columns)} columns."]
    anomalies = []
    recommendations = []

    # Missing data
    high_missing = [c for c in columns if c.get("missing_pct", 0) > 20]
    if high_missing:
        names = ", ".join(c["name"] for c in high_missing[:3])
        insights.append(f"Columns with >20% missing values: {names}.")
        recommendations.append(f"Investigate and impute missing values in {names}.")

    # Numeric stats
    for col in columns:
        if col["category"] == "numeric" and col.get("mean_val") is not None:
            if col.get("std_val") and col["std_val"] > 0:
                cv = col["std_val"] / abs(col["mean_val"] + 1e-9)
                if cv > 1.5:
                    anomalies.append(
                        f"{col['name']} shows high variability (CV={cv:.1f}), suggesting outliers."
                    )
            insights.append(
                f"{col['name']} ranges from {col['min_val']} to {col['max_val']} "
                f"(mean: {col['mean_val']:.2f})."
            )
            break  # Just one example

    # Anomaly results
    for r in query_results:
        if r.get("task_type") == "anomaly" and r.get("row_count", 0) > 0:
            anomalies.append(
                f"{r['row_count']} statistical outliers detected (z-score > 3)."
            )

    if numeric_cols:
        recommendations.append(
            f"Explore correlations between numeric columns: {', '.join(numeric_cols[:3])}."
        )
    recommendations.append("Consider removing or binning high-cardinality categorical columns.")

    return insights[:6], anomalies[:3], recommendations[:4]
