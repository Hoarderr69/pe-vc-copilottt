# PE Value Creation Copilot

Tracks a private equity portfolio company's investment thesis (Value Creation Plan)
against live financial data, detects drift early, and generates board-ready reports
— with a human review gate before anything reaches an operating partner or a board.

> Full architecture, data flow diagrams, and the current Azure/LangSmith migration
> plan live in [Architecture.md](Architecture.md). This file is the quickstart +
> orientation.

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
| Quant / forecasting | pandas, statsmodels, Prophet, scikit-learn |
| LLM | Azure OpenAI (structured extraction/narrative), with a fully-functional offline heuristic fallback when no LLM is configured |
| Document parsing | PyMuPDF4LLM (fast path), Docling (OCR fallback for scanned PDFs) |
| Report generation | python-pptx + matplotlib (editable deck), reportlab (PDF), LibreOffice headless (PPTX→PDF) |
| External data | SEC EDGAR XBRL, FRED (macro), Yahoo Finance (exit multiples) |
| Storage | Flat JSON files under `data/` today — Azure DB migration in progress, see [Architecture.md §12](Architecture.md#12-planned-azure-services-migration--langsmith-in-progress) |

## Quickstart

Two processes, run from the repo root in separate terminals.

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

Open http://localhost:5173. The backend needs no credentials to run — every LLM
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
These write into `data/processed/` and `data/features/`, which the live API reads
directly — there's no separate database to seed.

## Environment variables

None are required to run the app. Set these in a repo-root `.env` to enable the
corresponding feature:

| Variable | Enables |
|---|---|
| `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_KEY` | Live LLM extraction/narrative (else: offline heuristics) |
| `AZURE_OPENAI_DEPLOYMENT`, `AZURE_OPENAI_API_VERSION` | Override defaults (`gpt-4o`, `2024-10-21`) |
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
  store/        JSON-file persistence (VCP milestones, deal/company metadata, reports)
  workflows/    HITL queue + decision/audit log
  schemas/      Shared data models
  llm/          Azure OpenAI client wrapper
  graph/        Legacy, orphaned LangGraph pipeline — see Architecture.md §11
frontend/src/
  views/        One component per screen (Portfolio, CompanyDetail, Setup, Ingest, ...)
  components/   Shared UI, charts, board-pack slide renderers
  lib/          api.ts (fetch client) + format.ts
data/           Flat-file JSON/CSV store (see Architecture.md §6 for the full map)
scripts/        Standalone CLI scripts — demo data generation, legacy batch pipeline
```

## Current limitations

- **No database** — everything is JSON/CSV on local disk. Fine for a single-user
  internal tool, not for concurrent writers or multi-instance deployment. This is
  the subject of the in-progress Azure migration.
- **No auth** — anyone who can reach the API can read/write any company's data.
- **Report generation is synchronous** — a board pack generation request blocks
  until the full pipeline (drift → LLM narrative → slide build) completes.
- **Single-instance only** — no locking around the JSON stores; concurrent writes
  to the same company are not safe.

## In progress (today)

Migrating file-based storage to Azure services and wiring up LangSmith tracing for
the LLM agents. `langsmith`/`langchain`/`langchain-openai` are already project
dependencies but currently unused — see
[Architecture.md §12](Architecture.md#12-planned-azure-services-migration--langsmith-in-progress)
for the concrete target design and the fastest integration path for each.

## More docs

- [Architecture.md](Architecture.md) — full system architecture, data flow diagrams, API reference, known legacy/orphaned code, planned Azure/LangSmith migration
- [HOW_TO_RUN_DEMO.md](HOW_TO_RUN_DEMO.md) — guided demo walkthrough
- [README_SYNTHETIC_DATA.md](README_SYNTHETIC_DATA.md) — synthetic portfolio company data generator
