"""
LangGraph orchestrator
───────────────────────
• Defines the agent graph (8 nodes in a directed pipeline)
• Manages per-session state: DuckDB connection + SSE queue
• Exposes run_analysis() for background execution
• Exposes run_qa() for follow-up questions
"""
from __future__ import annotations

import asyncio
import datetime
import logging
from typing import Any

from langgraph.graph import END, StateGraph

from ..agents.data_access import data_access_agent
from ..agents.execution import execution_agent
from ..agents.insight import insight_agent
from ..agents.planner import planner_agent
from ..agents.qa import qa_agent
from ..agents.report import report_agent
from ..agents.scaling import scaling_agent
from ..agents.schema import schema_agent
from ..graph.state import AgentLog, AnalysisState

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Session store (in-process; replace with Redis for multi-worker deployments)
# ---------------------------------------------------------------------------

_sessions: dict[str, dict[str, Any]] = {}


def get_session(session_id: str) -> dict[str, Any]:
    return _sessions.setdefault(session_id, {})


def create_session(session_id: str) -> dict[str, Any]:
    _sessions[session_id] = {
        "conn": None,
        "queue": asyncio.Queue(),
        "created_at": datetime.datetime.utcnow(),
        "report": None,
    }
    return _sessions[session_id]


def cleanup_session(session_id: str) -> None:
    session = _sessions.pop(session_id, {})
    conn = session.get("conn")
    if conn:
        try:
            conn.close()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Graph definition
# ---------------------------------------------------------------------------

def _build_graph() -> Any:
    """Compile the LangGraph StateGraph."""
    graph = StateGraph(AnalysisState)

    # Register all nodes
    graph.add_node("data_access", data_access_agent)
    graph.add_node("scaling", scaling_agent)
    graph.add_node("schema", schema_agent)
    graph.add_node("planner", planner_agent)
    graph.add_node("execution", execution_agent)
    graph.add_node("insight", insight_agent)
    graph.add_node("report", report_agent)

    # Sequential pipeline
    graph.set_entry_point("data_access")
    graph.add_edge("data_access", "scaling")
    graph.add_edge("scaling", "schema")
    graph.add_edge("schema", "planner")
    graph.add_edge("planner", "execution")
    graph.add_edge("execution", "insight")
    graph.add_edge("insight", "report")
    graph.add_edge("report", END)

    return graph.compile()


# Build once at import time
_graph = _build_graph()

# ---------------------------------------------------------------------------
# QA sub-graph (single-node, re-uses same state)
# ---------------------------------------------------------------------------

def _build_qa_graph() -> Any:
    graph = StateGraph(AnalysisState)
    graph.add_node("qa", qa_agent)
    graph.set_entry_point("qa")
    graph.add_edge("qa", END)
    return graph.compile()


_qa_graph = _build_qa_graph()

# ---------------------------------------------------------------------------
# Public runners
# ---------------------------------------------------------------------------


async def run_analysis(session_id: str, initial_state: AnalysisState) -> None:
    """
    Run the full analysis pipeline in the background.
    Pushes SSE events to session queue; sends sentinel None when done.
    """
    session = get_session(session_id)
    queue: asyncio.Queue = session["queue"]

    try:
        final_state = await _graph.ainvoke(
            initial_state,
            config={"configurable": {"session_id": session_id}},
        )
        session["report"] = final_state.get("report")
        session["state"] = final_state

        await queue.put(
            {
                "type": "result",
                "data": final_state.get("report", {}),
            }
        )
    except Exception as exc:
        logger.exception("Analysis pipeline failed for session %s", session_id)
        await queue.put(
            {
                "type": "error",
                "data": {"message": f"Analysis failed: {exc}"},
            }
        )
    finally:
        await queue.put(None)  # SSE sentinel — close stream


async def run_qa(session_id: str, question: str) -> dict[str, Any]:
    """
    Run the QA agent against the session's existing analysis state.
    Returns {response, conversation_history}.
    """
    session = get_session(session_id)
    existing_state = session.get("state")

    if not existing_state:
        return {"response": "No analysis found for this session. Please run an analysis first."}

    qa_state = {
        **existing_state,
        "user_question": question,
        "agent_logs": [],
        "errors": [],
    }

    result = await _qa_graph.ainvoke(
        qa_state,
        config={"configurable": {"session_id": session_id}},
    )

    # Persist updated conversation history
    session["state"]["conversation_history"] = result.get("conversation_history", [])

    return {
        "response": result.get("qa_response", ""),
        "conversation_history": result.get("conversation_history", []),
    }
