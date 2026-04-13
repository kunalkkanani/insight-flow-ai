"""
QA Agent
─────────
• Answers follow-up questions about the dataset
• Maintains conversation history
• Can generate and execute SQL queries when needed
• Keeps context token-efficient (schema + summaries, no raw data)
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
from ..tools.duckdb_tool import execute_query

logger = logging.getLogger(__name__)
AGENT = "QAAgent"

_SYSTEM = """You are a data analyst assistant. You have access to a dataset and its analysis results. Answer the user's question accurately and concisely.

You may generate a DuckDB SQL query to answer the question. If you do, wrap it in:
<sql>SELECT ... FROM data_table ...</sql>

Use "data_table" as the table name placeholder — it will be replaced with the actual table.

Rules:
- Be concise (2–5 sentences)
- Quote specific numbers from the data
- If you generate SQL, it must be valid DuckDB SQL
- Do not hallucinate data — only report what the schema and results show
- Keep answers under 200 words"""


def _log(level: str, msg: str) -> AgentLog:
    return AgentLog(
        agent=AGENT,
        message=msg,
        timestamp=datetime.datetime.utcnow().isoformat(),
        level=level,
    )


async def qa_agent(
    state: AnalysisState, config: RunnableConfig
) -> dict[str, Any]:
    from ..graph.orchestrator import get_session

    session = get_session(state["session_id"])
    queue = session.get("queue")
    conn = session.get("conn")
    logs: list[AgentLog] = []
    errors: list[str] = []

    question = state.get("user_question", "")
    history = state.get("conversation_history") or []
    columns = state.get("columns") or []
    numeric_cols = state.get("numeric_columns") or []
    categorical_cols = state.get("categorical_columns") or []
    insights = state.get("insights") or []
    effective_table = state.get("effective_table") or "raw_data"
    row_count = state.get("row_count") or 0

    if not question:
        return {"qa_response": "", "agent_logs": logs, "errors": errors}

    logs.append(_log("info", f"Answering: {question[:60]}…"))
    if queue:
        await queue.put({"type": "log", "data": logs[-1]})

    if not settings.anthropic_api_key:
        response = "No Anthropic API key configured. Please set ANTHROPIC_API_KEY to enable question answering."
        return {
            "qa_response": response,
            "conversation_history": history + [
                {"role": "user", "content": question},
                {"role": "assistant", "content": response},
            ],
            "agent_logs": logs,
            "errors": errors,
        }

    # ── Build context ──────────────────────────────────────────────────────
    schema_summary = (
        f"Dataset: {row_count:,} rows\n"
        f"Numeric columns: {', '.join(numeric_cols[:8])}\n"
        f"Categorical columns: {', '.join(categorical_cols[:8])}\n"
        f"Key insights: " + "; ".join(insights[:3])
    )

    col_schema = "\n".join(
        f"  {c['name']} ({c['dtype']}, {c['category']}, missing: {c['missing_pct']}%)"
        for c in columns[:20]
    )

    system_with_context = (
        _SYSTEM
        + f"\n\n---\nDataset schema:\n{col_schema}\n\nSummary:\n{schema_summary}"
    )

    # Build messages
    messages: list[dict] = []
    for h in history[-6:]:  # Keep last 3 turns
        messages.append(h)
    messages.append({"role": "user", "content": question})

    try:
        client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        response_obj = await client.messages.create(
            model=settings.claude_model,
            max_tokens=600,
            temperature=0.2,
            system=system_with_context,
            messages=messages,
        )
        answer = response_obj.content[0].text.strip()

        # ── Execute any SQL in the response ────────────────────────────────
        sql_match = re.search(r"<sql>(.*?)</sql>", answer, re.DOTALL | re.IGNORECASE)
        if sql_match and conn:
            raw_sql = sql_match.group(1).strip()
            actual_sql = raw_sql.replace("data_table", effective_table)
            try:
                rows = execute_query(conn, actual_sql, max_rows=20)
                sql_result = json.dumps(rows[:10], indent=2) if rows else "No rows returned"
                # Append query result and re-ask Claude to interpret
                follow_up = await client.messages.create(
                    model=settings.claude_model,
                    max_tokens=400,
                    temperature=0.1,
                    system=system_with_context,
                    messages=messages + [
                        {"role": "assistant", "content": answer},
                        {"role": "user", "content": f"SQL result:\n{sql_result}\n\nNow answer the original question using this data."},
                    ],
                )
                answer = follow_up.content[0].text.strip()
                logs.append(_log("info", f"Executed SQL: {actual_sql[:80]}…"))
            except Exception as sql_exc:
                logger.warning("QA SQL execution failed: %s", sql_exc)
                logs.append(_log("warning", f"SQL execution failed: {sql_exc}"))

        logs.append(_log("success", "Answer generated"))
        if queue:
            await queue.put({"type": "log", "data": logs[-1]})

        updated_history = history + [
            {"role": "user", "content": question},
            {"role": "assistant", "content": answer},
        ]

        return {
            "qa_response": answer,
            "conversation_history": updated_history[-20:],  # Keep last 10 turns
            "agent_logs": logs,
            "errors": errors,
        }

    except Exception as exc:
        logger.exception("QAAgent failed")
        err_msg = f"QA failed: {exc}"
        errors.append(err_msg)
        logs.append(_log("error", err_msg))
        return {
            "qa_response": "Sorry, I could not answer that question at this time.",
            "agent_logs": logs,
            "errors": errors,
        }
