# Running the Demo (Backend + React Frontend)

Two processes. Run each in its own terminal from the repo root.

## 1. Backend API (FastAPI, port 8000)

```bash
uv run uvicorn app.api.main:app --reload --port 8000
```

Serves the VCP monitoring endpoints the dashboard consumes:

| Endpoint | Purpose |
|---|---|
| `GET /api/vcp/portfolio` | Portfolio overview + action inbox |
| `GET /api/vcp/company/{id}` | Milestones, live drift, KPI time series |
| `GET /api/vcp/hitl` | Review queue |
| `POST /api/vcp/hitl/decision` | Record approve / edit / reject (writes audit log) |
| `GET /api/vcp/memo` | Portfolio memo markdown |

## 2. Frontend (React + Vite, port 5173)

```bash
cd frontend
npm install        # first time only
npm run dev
```

Open http://localhost:5173

## Regenerating the data (if needed)

The dashboard reads `data/processed/*.json`. To rebuild from scratch:

```bash
uv run python scripts/generate_synthetic_portco_data.py
uv run python scripts/run_all_private_portco_kpi_normalization.py
uv run python scripts/run_portfolio_vcp_monitoring.py
uv run python scripts/run_portfolio_action_inbox.py
uv run python scripts/run_hitl_queue_builder.py
uv run python scripts/run_portfolio_memo.py
```

## VCP Extraction Agent (first LLM agent)

Reads an IC memo (prose) → structured, confidence-scored milestone candidates (all `confirmed=false` until HITL).

```bash
uv run python scripts/run_vcp_extraction.py            # all companies + eval vs seed
uv run python scripts/run_vcp_extraction.py --no-llm   # force offline heuristic
```

API: `GET /api/vcp/extract/status` · `POST /api/vcp/extract/{company_id}`.

**Modes:** runs **offline_heuristic** until Azure is configured, then **azure_openai** (GPT-4o) automatically.
To enable live extraction, set in `.env`: `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_KEY`
(and optionally `AZURE_OPENAI_DEPLOYMENT`, `AZURE_OPENAI_API_VERSION`).

## Demo flow (suggested)

1. **Portfolio Overview** — "3 companies, 2 need attention." Action inbox ranks them; Company C (Healthcare) is on plan (Green).
2. **Open Company A** — VCP scorecard (Revenue/Margin/Leverage all Red) and the charts: actual vs the dashed plan path, with the drift visible after month 13. Contrast with Company C (actual tracks plan).
3. **Review Queue** — approve an item; point out it's timestamped to the audit log (`data/processed/hitl_audit_log.json`).
4. **Portfolio Memo** — the board-ready decision artifact, generated from the same state.
