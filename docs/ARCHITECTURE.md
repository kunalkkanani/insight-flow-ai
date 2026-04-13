# Insight Flow AI — Architecture

## Overview

Insight Flow AI is a multi-agent autonomous data analysis system. Users upload a dataset (or provide a URL) and the system autonomously performs full exploratory data analysis, generates visualisations, and produces AI-powered insights.

```
User → Upload/URL → FastAPI → LangGraph Pipeline → SSE Stream → Next.js UI
```

---

## Agent Pipeline

The system uses a **LangGraph StateGraph** with 8 nodes in a directed acyclic pipeline:

```
DataAccessAgent
      ↓
ScalingAgent
      ↓
SchemaAgent
      ↓
PlannerAgent  ← Calls Claude (planning)
      ↓
ExecutionAgent ← Runs DuckDB SQL queries
      ↓
InsightAgent  ← Calls Claude (insights)
      ↓
ReportAgent
```

### Agent Responsibilities

| Agent | Responsibility | Uses LLM? |
|-------|---------------|-----------|
| **DataAccessAgent** | Detect format, register DuckDB view, preview | No |
| **ScalingAgent** | Choose full/sample/aggregate strategy | No |
| **SchemaAgent** | Column types, missing %, stats, cardinality | No |
| **PlannerAgent** | Decide which analyses to run | ✅ Claude |
| **ExecutionAgent** | Generate + run SQL, build Plotly specs | No |
| **InsightAgent** | Convert results into readable insights | ✅ Claude |
| **ReportAgent** | Assemble final report JSON | No |
| **QAAgent** | Answer follow-up questions | ✅ Claude |

**LLM constraint:** Claude only sees schema summaries and aggregated statistics — never raw data. This keeps token usage minimal and prevents data leakage.

---

## Shared State

All agents communicate through a single `AnalysisState` TypedDict, managed by LangGraph:

```python
class AnalysisState(TypedDict):
    session_id: str
    # Input
    input_type: str            # "file" | "url"
    file_path: str | None
    url: str | None
    # Data access
    row_count: int
    column_count: int
    file_format: str           # csv | parquet | json
    # Scaling
    strategy: str              # full | sample | aggregate
    effective_table: str       # DuckDB view for queries
    # Schema
    columns: list[ColumnInfo]
    numeric_columns: list[str]
    # ...
    # Streaming (append-only)
    agent_logs: Annotated[list[AgentLog], operator.add]
    errors: Annotated[list[str], operator.add]
```

---

## Data Processing

### DuckDB as Compute Engine

DuckDB is the primary query engine. It can:
- Read CSV/Parquet/JSON directly from URLs (httpfs extension)
- Run analytical SQL on local files
- Handle 100M+ rows with minimal memory via streaming aggregation

### Scaling Strategy

| Dataset Size | Strategy | Description |
|---|---|---|
| < 500K rows | `full` | Direct DuckDB scan |
| 500K – 5M rows | `sample` | 100K-row random sample view |
| > 5M rows | `aggregate` | Aggregation-first with 100K-row sample |

### SQL Query Generation

The `ExecutionAgent` generates deterministic SQL for each analysis type:

| Analysis Type | SQL Pattern |
|---|---|
| distribution (numeric) | Bucketed histogram with `FLOOR()` |
| distribution (categorical) | `GROUP BY + ORDER BY count DESC` |
| correlation | `CORR()` pairwise or scatter sample |
| time_series | `DATE_TRUNC('month')` + aggregation |
| aggregation | `GROUP BY categorical + SUM/AVG numeric` |
| anomaly | Z-score: `ABS((val - mean) / std) > 3` |

---

## Streaming Architecture

```
Browser                  FastAPI               Background Task
  |                         |                        |
  |─ POST /analyze/file ───→|                        |
  |←─ {session_id} ─────────|                        |
  |                         |─ create_task() ────────→|
  |                         |                         | DuckDB
  |─ GET /stream/{id} ─────→|                         | ┌──────┐
  |                         |                         | │agent1│ → queue
  |←─ SSE: event:log ───────|←── queue.put(log) ──────│      │
  |←─ SSE: event:log ───────|                         └──────┘
  |←─ SSE: event:result ────|←── queue.put(report) ────
  |←─ SSE: event:done ──────|
```

Each agent pushes `AgentLog` events to an `asyncio.Queue`. The SSE endpoint reads from this queue and forwards events to the browser as Server-Sent Events.

---

## Frontend Architecture

```
page.tsx (state machine)
├── idle      → DataInput.tsx
├── uploading → Loader
├── analyzing → AgentLog.tsx (real-time SSE)
└── complete  → Dashboard.tsx
                ├── Tab: Overview  → DataOverview.tsx
                ├── Tab: Charts    → ChartGrid.tsx (react-plotly.js)
                ├── Tab: Insights  → InsightCards.tsx
                ├── Tab: Ask AI    → ChatBox.tsx
                └── Tab: Logs      → AgentLog.tsx
```

---

## API Reference

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/analyze/file` | Upload file, returns `session_id` |
| `POST` | `/api/analyze/url` | URL analysis, returns `session_id` |
| `GET` | `/api/stream/{id}` | SSE event stream |
| `GET` | `/api/status/{id}` | Poll for completion |
| `POST` | `/api/question/{id}` | Ask follow-up question |
| `DELETE` | `/api/session/{id}` | Clean up session |
| `GET` | `/api/health` | Health check |

---

## Session Management

Sessions are stored in a module-level dict (in-process). Each session contains:
- `conn`: DuckDB connection (in-memory, per session)
- `queue`: `asyncio.Queue` for SSE events
- `state`: Final `AnalysisState` after pipeline completes
- `report`: Assembled report JSON

For multi-worker deployments, replace the in-process dict with Redis.

---

## Token Efficiency

The system is designed to minimise LLM token usage:

1. **Planner**: Receives schema summary only (~500 tokens input)
2. **InsightAgent**: Receives aggregated stats + top-5 rows per query (~2000 tokens)
3. **QAAgent**: Receives schema + last 3 conversation turns (~1000 tokens)
4. **No raw data** is ever sent to the LLM
