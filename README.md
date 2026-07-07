# PE Value Creation Copilot

Tracks a private equity portfolio company's investment thesis (Value Creation Plan)
against live financial data, detects drift early, and generates board-ready reports
— with a human review gate before anything reaches an operating partner or a board.

> Full architecture, data flow diagrams, and the complete API reference live in
> [Architecture.md](Architecture.md). This file is the quickstart + orientation.

## What it is

When a PE firm closes a deal, the investment thesis — specific commitments like
"EBITDA margin from 12% to 20% by Year 3" — gets written into an IC memo and then
largely forgotten until it shows up red in a board pack, months after the drift
started. This app:

1. **Extracts** those commitments from the IC memo into structured, dated
   milestones (once, at deal close).
2. **Monitors** portfolio company financials against those milestones as new data
   arrives — management accounts, board packs, or EDGAR filings for take-privates.
3. **Detects drift** and quantifies the exit-IRR impact using a statistical
   forecast ensemble (STL + SARIMA + Prophet, P10/P50/P90 bands).
4. **Gates every finding through human review (HITL)** before it reaches an
   operating partner's action list.
5. **Generates board-ready reports** (editable PPTX + PDF) from the same live data.

## Tech stack

| Layer | Technology |
|---|---|
| Frontend | React 19 + TypeScript, Vite, Recharts |
| Backend | FastAPI (Python 3.13), Pydantic |
| Orchestration | LangGraph (3 graphs: VCP extraction, VCP monitoring, report generation), checkpointed on Postgres |
| Quant / forecasting | pandas, statsmodels, Prophet, scikit-learn |
| LLM | Azure OpenAI (structured extraction/narrative), with a fully-functional offline heuristic fallback when no LLM is configured; traced via LangSmith when configured |
| Document parsing | PyMuPDF4LLM (fast path), Docling (OCR fallback for scanned PDFs) |
| Report generation | python-pptx + matplotlib (editable deck), reportlab (PDF), LibreOffice headless (PPTX→PDF) |
| External data | SEC EDGAR XBRL, FRED (macro), Yahoo Finance (exit multiples) |
| Storage | Azure Database for PostgreSQL — one JSONB table (`app_documents`) holds every document store (VCP milestones, deal/company metadata, reports, HITL queue/audit log, KPI records, portfolio memo) plus the LangGraph checkpoint tables. Feature-matrix CSVs and uploaded source documents stay on local disk. See [Architecture.md §12](Architecture.md#12-langgraph--postgres-migration-live-2026-07-06) |

## Quickstart

Two processes, run from the repo root in separate terminals. Requires a
`DATABASE_URL` in `.env` (Postgres) — the app has no local-file fallback for its
document stores.

**Backend** (FastAPI, port 8000):
```bash
.venv/bin/python -m uvicorn app.api.main:app --reload --port 8000
```

**Frontend** (React + Vite, port 5173):
```bash
cd frontend
npm install   # first time only
npm run dev
```

Open http://localhost:5173. No LLM credentials are required to run — every LLM
agent falls back to a deterministic offline heuristic when Azure OpenAI isn't
configured (see below).

### Regenerating demo data

```bash
.venv/bin/python scripts/generate_synthetic_portco_data.py
.venv/bin/python scripts/run_all_private_portco_kpi_normalization.py
.venv/bin/python scripts/run_portfolio_vcp_monitoring.py
.venv/bin/python scripts/run_portfolio_action_inbox.py
.venv/bin/python scripts/run_hitl_queue_builder.py
```
These write KPI records, milestones, and the HITL queue into Postgres (via the
same stores the live API reads) plus feature-matrix CSVs under `data/features/`.
The portfolio memo is no longer a batch script — generate it live via
`POST /api/vcp/memo/generate` (the Portfolio Memo view's "Regenerate" button).

## Environment variables

LLM credentials are optional (see below); `DATABASE_URL` is required. Set these in
a repo-root `.env`:

| Variable | Enables |
|---|---|
| `DATABASE_URL` | **Required.** Postgres connection string — backs every document store and the LangGraph checkpointer |
| `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_KEY` | Live LLM extraction/narrative (else: offline heuristics) |
| `AZURE_OPENAI_DEPLOYMENT`, `AZURE_OPENAI_API_VERSION` | Override defaults (`gpt-4o`, `2024-10-21`) |
| `LANGCHAIN_TRACING_V2`, `LANGCHAIN_API_KEY`, `LANGCHAIN_PROJECT` | LangSmith tracing of every LLM call (off by default) |
| `FRED_API_KEY` | Macro regressors in the quant forecast |
| `SEC_USER_AGENT` | Respectful identification to SEC EDGAR (has a default, override for production) |
| `CORS_ORIGINS` | Comma-separated allowed origins (defaults to local Vite ports) |
| `VITE_API_BASE_URL` (frontend) | Point the SPA at a non-localhost backend |

Full list, including quant/market-data fallbacks: [Architecture.md §13](Architecture.md#13-environment-variables-current-complete).

## Repo layout

```
app/
  api/          FastAPI routers: vcp_routes, ingest_routes, report_routes
  agents/       LLM-powered nodes (VCP extraction, alert synthesis, report narrative)
  analytics/    Deterministic drift/peer-benchmark/freshness/sector logic
  adapters/     Financial-document → KPIRecord normalizers (registry pattern)
  data_sources/ SEC EDGAR, FRED, Yahoo Finance clients
  ingestion/    Document loading, currency normalization, feature-matrix assembly
  quant/        Forecast ensemble + IRR scenario engine
  reports/      Slide-data builder, PPTX/PDF generators
  store/        Postgres-backed document stores (VCP milestones, deal/company
                metadata, reports, KPI records, portfolio memo) via PostgresJsonStore
  workflows/    HITL queue + decision/audit log, VCP confirmation (all Postgres-backed)
  schemas/      Shared data models
  llm/          Azure OpenAI client wrapper (LangSmith-traced when configured)
  graph/        3 live LangGraph workflows (VCP extraction, VCP monitoring, report
                generation) + the Postgres checkpointer
frontend/src/
  views/        One component per screen (Portfolio, CompanyDetail, Setup, Ingest, ...)
  components/   Shared UI, charts, board-pack slide renderers
  lib/          api.ts (fetch client) + format.ts
data/           Feature-matrix CSVs and uploaded source documents only — everything
                else lives in Postgres (see Architecture.md §12)
scripts/        Standalone CLI scripts — demo data generation, batch pipeline exports
```

## Current limitations

- **No auth** — anyone who can reach the API can read/write any company's data.
- **Uploaded source documents and feature-matrix CSVs are still local disk** — fine
  for a single-instance deployment, not yet migrated to blob storage.
- Report generation runs as a background task (checkpointed, polled via
  `GET /api/reports/graph/{thread_id}/status`) — not fully synchronous, but still a
  single in-process task queue, not a real job runner.

## More docs

- [Architecture.md](Architecture.md) — full system architecture, data flow diagrams, API reference, the Postgres/LangGraph migration, and known remaining debt
- [HOW_TO_RUN_DEMO.md](HOW_TO_RUN_DEMO.md) — guided demo walkthrough
- [README_SYNTHETIC_DATA.md](README_SYNTHETIC_DATA.md) — synthetic portfolio company data generator


<!-- LANGSMITH_TRACING=true
LANGSMITH_ENDPOINT=https://apac.api.smith.langchain.com
LANGSMITH_A PI_K EY=lsv 2_pt_388806e0bcbb43e88b41ff32979ba5 2b_d97f5bebb8
LANGSMITH_PROJECT=demo_pevc -->