# OrgMind — AI-Powered Organisational Memory

> 12-agent LangGraph system that ingests Slack, Notion, Google Drive and GitHub ADRs,
> extracts architectural decisions, detects conflicts, and answers questions in real-time.

[![Backend CI](https://github.com/dhanush1-2/OrgMind/actions/workflows/backend-ci.yml/badge.svg)](https://github.com/dhanush1-2/OrgMind/actions/workflows/backend-ci.yml)
[![Frontend CI](https://github.com/dhanush1-2/OrgMind/actions/workflows/frontend-ci.yml/badge.svg)](https://github.com/dhanush1-2/OrgMind/actions/workflows/frontend-ci.yml)

---

## Architecture

```
Sources → [Agent 1 Source Monitor]
        → [Agent 2 Chunker]
        → [Agent 3 Dedup Gate]        ← SHA-256 + Upstash Redis
        → [Agent 4 Extraction]        ← Groq llama-3.3-70b-versatile
        → [Agent 5 Splitter]          ← compound decision detection
        → [Agent 6 Review Queue]      ← Supabase flag table
        → [Agent 7 Entity Normalizer] ← difflib + Redis registry
        → [Agent 8 Resolution]        ← Neo4j MERGE + Supabase upsert
        → [Agent 9 Conflict Detector] ← Neo4j + Groq pairwise check

Direct API calls:
  Agent 10 Query Agent    → SSE streaming answers
  Agent 11 Onboarding     → role-based briefing
  Agent 12 Health Monitor → staleness scan (180-day threshold)
```

## Stack

| Layer | Technology |
|-------|-----------|
| Orchestration | LangGraph StateGraph |
| LLM | Groq `llama-3.3-70b-versatile` |
| API | FastAPI + APScheduler |
| Graph DB | Neo4j AuraDB |
| SQL | Supabase (PostgreSQL) |
| Cache / Dedup | Upstash Redis |
| Vector | ChromaDB (Docker) |
| Logging | structlog (JSON + console) |
| Frontend | React 19 + Vite + Tailwind CSS |
| Visualisation | D3 v7 force-directed graph |

## Repository Structure

```
orgmind/
├── backend/
│   ├── app/
│   │   ├── agents/          # 12 agent modules
│   │   ├── api/v1/routes/   # 10 API route files
│   │   ├── core/            # config, logger, database, scheduler, schema
│   │   ├── models/          # Pydantic models
│   │   └── pipeline/        # LangGraph graph.py
│   ├── migrations/          # Supabase SQL migration
│   ├── scripts/             # seed_data.py + demo_company.json
│   └── tests/               # 84 pytest-asyncio tests
├── frontend/
│   └── src/
│       ├── pages/           # AskPage, TimelinePage, GraphPage, StalenessPage, SettingsPage
│       └── components/      # Layout sidebar
├── docker-compose.yml        # ChromaDB + backend
└── render.yaml               # Render deployment spec
```

## Running Locally

### Backend

```bash
cd orgmind/backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example ../.env   # edit with real API keys

# Run all tests (no real credentials needed)
pytest tests/ -q

# Start server
python -m uvicorn app.main:app --reload
```

API docs: http://localhost:8000/docs

### Frontend

```bash
cd orgmind/frontend
npm install
cp .env.example .env.local   # set VITE_API_URL=http://localhost:8000/api/v1
npm run dev
```

Open http://localhost:5173

### Seed Data

```bash
cd backend
python scripts/seed_data.py --groq      # 25 Groq-generated NovaTech Labs decisions
python scripts/seed_data.py --adrs      # ingest public ADR repos via pipeline
python scripts/seed_data.py --dry-run  # preview without writing to DB
```

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/api/v1/ingest` | Trigger pipeline (background) |
| GET | `/api/v1/query?q=…` | SSE streaming answer |
| GET | `/api/v1/decisions` | Paginated decision list |
| GET | `/api/v1/graph` | D3 nodes + edges |
| GET | `/api/v1/timeline` | Chronological decisions |
| GET | `/api/v1/conflicts` | All conflict pairs |
| GET | `/api/v1/staleness` | Staleness metrics |
| POST | `/api/v1/onboarding` | Role-based briefing |
| GET | `/api/v1/review-queue` | Flagged decisions |
| GET | `/api/v1/integrations` | Service health |

## Environment Variables

| Variable | Description |
|----------|-------------|
| `GROQ_API_KEY` | Groq API key |
| `SUPABASE_URL` | Supabase project URL |
| `SUPABASE_KEY` | Supabase anon JWT key |
| `DATABASE_URL` | PostgreSQL connection string |
| `NEO4J_URI` | Neo4j AuraDB URI |
| `NEO4J_USER` | Neo4j username |
| `NEO4J_PASSWORD` | Neo4j password |
| `UPSTASH_REDIS_REST_URL` | Upstash Redis REST URL |
| `UPSTASH_REDIS_REST_TOKEN` | Upstash Redis token |

## Frontend Pages

| Route | Page | Description |
|-------|------|-------------|
| `/` | Ask | SSE streaming chat with Groq answers |
| `/timeline` | Timeline | Decision history + conflict alerts |
| `/graph` | Knowledge Graph | D3 force-directed graph (pan/zoom/drag) |
| `/staleness` | Staleness | Metrics dashboard + health check trigger |
| `/settings` | Settings | Integration status + review queue |

## Deployment

- **Backend**: Render web service — see `render.yaml`
- **Frontend**: Vercel — connect `frontend/` directory, set `VITE_API_URL`
- **CI**: GitHub Actions runs pytest + vite build on every push
