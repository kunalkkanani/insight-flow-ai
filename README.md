# Insight Flow AI

**Autonomous AI-powered data analyst.**  
Upload any CSV, Parquet, or JSON dataset and 8 specialised agents automatically perform full exploratory data analysis, generate interactive visualisations, and surface AI-powered insights.

---

## Demo

```
Upload data.csv
    ↓
📂 DataAccessAgent   → Registers DuckDB view (5M rows? No problem)
⚖️  ScalingAgent      → "500K rows — using full DuckDB scan"
🔍 SchemaAgent       → "12 columns: 5 numeric, 4 categorical, 1 datetime"
🧠 PlannerAgent      → Calls Claude → 6-task analysis plan
⚡ ExecutionAgent    → Runs SQL queries, builds Plotly charts
💡 InsightAgent      → Calls Claude → 5 key insights
📊 ReportAgent       → Assembles final dashboard
    ↓
Interactive dashboard with charts, insights, and Q&A
```

---

## Features

- **8 specialised agents** orchestrated with LangGraph
- **DuckDB-powered** — handles millions of rows without memory issues
- **Adaptive scaling** — full / sample / aggregate strategies
- **Real-time progress** via Server-Sent Events
- **Interactive charts** — Plotly (bar, line, scatter, heatmap, pie, box)
- **AI insights** — Claude generates human-readable findings
- **Follow-up Q&A** — ask questions about the dataset in natural language
- **Formats**: CSV, Parquet, JSON (local file or public URL)

---

## Quick Start

### Option 1 — Docker (recommended)

```bash
git clone https://github.com/you/insight-flow-ai
cd insight-flow-ai

# Copy and fill in your API key
cp .env.example backend/.env
# Edit backend/.env → set ANTHROPIC_API_KEY=sk-ant-...

docker-compose up
```

Open [http://localhost:3000](http://localhost:3000)

### Option 2 — Local development

**Prerequisites**: Python 3.11+, Node.js 20+

```bash
# Backend
pip install -r backend/requirements.txt
cp .env.example backend/.env
# Edit backend/.env

uvicorn backend.main:app --host 0.0.0.0 --port 8000 --reload

# Frontend (new terminal)
cd frontend
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000)

### Option 3 — Make

```bash
make install       # Install all deps
# Edit backend/.env
make dev-backend   # Terminal 1
make dev-frontend  # Terminal 2
```

---

## Configuration

Edit `backend/.env` (copy from `.env.example`):

```env
ANTHROPIC_API_KEY=sk-ant-...    # Required for AI planning and insights
CLAUDE_MODEL=claude-sonnet-4-6  # Model to use
MAX_UPLOAD_MB=500               # Max upload size
SAMPLE_THRESHOLD_ROWS=500000    # Switch to sampling above this
```

**Without an API key**: the system still works — it uses a heuristic planner and template-based insights instead of Claude.

---

## Project Structure

```
insight-flow-ai/
├── backend/
│   ├── agents/          # 8 specialised agent implementations
│   │   ├── data_access.py
│   │   ├── scaling.py
│   │   ├── schema.py
│   │   ├── planner.py   ← calls Claude
│   │   ├── execution.py ← runs DuckDB SQL
│   │   ├── insight.py   ← calls Claude
│   │   ├── report.py
│   │   └── qa.py        ← calls Claude
│   ├── tools/
│   │   ├── duckdb_tool.py    # DuckDB query executor
│   │   ├── metadata_tool.py  # File/URL metadata
│   │   └── chart_builder.py  # Plotly spec builder
│   ├── graph/
│   │   ├── state.py          # AnalysisState TypedDict
│   │   └── orchestrator.py   # LangGraph graph + session store
│   ├── api/
│   │   ├── routes.py         # FastAPI endpoints
│   │   └── models.py         # Pydantic models
│   ├── config.py             # Pydantic Settings
│   └── main.py               # FastAPI app
├── frontend/
│   └── src/
│       ├── app/              # Next.js 14 App Router
│       ├── components/       # React components
│       └── lib/              # Types + API client
├── examples/
│   └── generate_sample.py   # Generates sample_sales.csv
├── docs/
│   └── ARCHITECTURE.md      # Detailed architecture docs
├── docker-compose.yml
├── Dockerfile.backend
├── Dockerfile.frontend
├── Makefile
└── .env.example
```

---

## Supported Data Sources

| Source | Formats |
|--------|---------|
| File upload | `.csv`, `.tsv`, `.parquet`, `.json`, `.jsonl` |
| Public URL | Any of the above formats |

**File size limit**: 500 MB (configurable)  
**URL requirement**: Publicly accessible (no auth)

---

## Architecture

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the full technical architecture.

Key design decisions:
- **LangGraph** for agent orchestration (graph-based, streaming, typed state)
- **DuckDB** as compute engine (SQL on files, aggregation, no Pandas for large data)
- **SSE streaming** for real-time agent progress updates
- **LLM token efficiency**: Claude only sees schema summaries and aggregated stats, never raw data

---

## Generating Sample Data

```bash
python examples/generate_sample.py
# Generates: examples/sample_sales.csv (5,000 rows)
```

The sample dataset is a synthetic sales dataset with:
- `order_date` (datetime), `region`, `category`, `sub_category` (categorical)
- `revenue`, `cost`, `profit`, `unit_price` (numeric)
- `customer_rating` (numeric, with 3% missing values)

---

## API Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/analyze/file` | POST | Upload file, start analysis |
| `/api/analyze/url` | POST | URL-based analysis |
| `/api/stream/{session_id}` | GET | SSE stream (logs + result) |
| `/api/status/{session_id}` | GET | Poll for status |
| `/api/question/{session_id}` | POST | Ask follow-up question |
| `/api/session/{session_id}` | DELETE | Clean up |
| `/api/health` | GET | Health check |
| `/docs` | GET | Swagger UI |

---

## License

MIT
