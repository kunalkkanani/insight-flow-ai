"""
Scaling Agent
─────────────
• Inspects row count and file size
• Selects processing strategy: full | sample | aggregate
• Creates a DuckDB view (sampled or direct) as the effective_table
• Prevents memory crashes for large datasets
"""
from __future__ import annotations

import datetime
import logging
from typing import Any

from langgraph.types import RunnableConfig

from ..config import settings
from ..graph.state import AgentLog, AnalysisState

logger = logging.getLogger(__name__)
AGENT = "ScalingAgent"


def _log(level: str, msg: str) -> AgentLog:
    return AgentLog(
        agent=AGENT,
        message=msg,
        timestamp=datetime.datetime.utcnow().isoformat(),
        level=level,
    )


async def scaling_agent(
    state: AnalysisState, config: RunnableConfig
) -> dict[str, Any]:
    from ..graph.orchestrator import get_session

    session = get_session(state["session_id"])
    queue = session.get("queue")
    logs: list[AgentLog] = []
    errors: list[str] = []

    row_count = state.get("row_count") or 0
    raw_table = state.get("raw_table") or "raw_data"

    try:
        logs.append(_log("info", f"Evaluating scale: {row_count:,} rows"))

        conn = session.get("conn")
        if conn is None:
            raise RuntimeError("DuckDB connection not found in session")

        # ── Decision tree ──────────────────────────────────────────────────
        if row_count <= settings.sample_threshold_rows:
            strategy = "full"
            effective_table = raw_table
            sample_size = None
            msg = f"Strategy → full scan ({row_count:,} rows, DuckDB)"

        elif row_count <= settings.large_dataset_threshold_rows:
            strategy = "sample"
            sample_size = settings.default_sample_rows
            effective_table = "sampled_data"
            conn.execute(f"""
                CREATE OR REPLACE VIEW {effective_table} AS
                SELECT * FROM {raw_table}
                USING SAMPLE {sample_size} ROWS
            """)
            msg = (
                f"Strategy → sample ({sample_size:,} rows from {row_count:,}, DuckDB)"
            )

        else:
            # Very large: aggregation-first, analysis on aggregated views
            strategy = "aggregate"
            sample_size = settings.default_sample_rows
            effective_table = "sampled_data"
            conn.execute(f"""
                CREATE OR REPLACE VIEW {effective_table} AS
                SELECT * FROM {raw_table}
                USING SAMPLE {sample_size} ROWS
            """)
            msg = (
                f"Strategy → aggregate-first (>{row_count:,} rows — "
                f"using {sample_size:,}-row representative sample)"
            )

        logs.append(_log("success", msg))
        if queue:
            await queue.put({"type": "log", "data": logs[-1]})

    except Exception as exc:
        logger.exception("ScalingAgent failed")
        msg = f"Scaling failed: {exc}"
        errors.append(msg)
        logs.append(_log("error", msg))
        if queue:
            await queue.put({"type": "log", "data": logs[-1]})
        return {
            "strategy": "full",
            "effective_table": raw_table,
            "agent_logs": logs,
            "errors": errors,
        }

    return {
        "strategy": strategy,
        "effective_table": effective_table,
        "sample_size": sample_size,
        "agent_logs": logs,
        "errors": errors,
    }
