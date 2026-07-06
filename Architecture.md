# PE Value Creation Copilot — Architecture

> **Status of this document**: finalized 2026-07-06 after a full frontend-to-backend
> architecture review (every route traced from the React UI through to its backend
> module and back) and the Postgres migration that review's findings triggered. It
> supersedes the earlier aspirational version of this file (Streamlit / Azure AI
> Search RAG / APScheduler polling) — those pieces were part of the original design
> but were never built. Every route, storage table, and dead-code note below
> reflects the codebase as it exists today, verified by running the app end-to-end
> (see §11).

---

## 1. What this system does

A private equity firm's investment thesis (the "Value Creation Plan", or **VCP**) is
a set of forward-looking commitments made at deal close — revenue growth, EBITDA
margin expansion, leverage paydown, specific operational milestones ("hire a CRO by
Q2"). This app:

1. **Extracts** those commitments from an IC memo into structured, dated,
   confidence-scored milestones (once, at deal close).
2. **Monitors** portfolio company financials against those milestones continuously
   as new data arrives (management accounts, board packs, EDGAR filings for
   take-privates).
3. **Detects drift** — where actuals diverge from the plan — and quantifies the
   impact on exit IRR using a statistical forecast ensemble.
4. **Routes findings through a human-in-the-loop (HITL) review** before anything
   reaches an operating partner's action list or a board pack.
5. **Generates board-ready reports** (PPTX + PDF) from the same live data.

---

## 2. High-level architecture

```mermaid
flowchart LR
    subgraph Client["Frontend — frontend/src"]
        FE["React 19 + TypeScript SPA\nVite dev server / static build\nviews/, components/, lib/api.ts"]
    end

    subgraph Backend["FastAPI Backend — app/api"]
        VCP["vcp_routes.py\nprefix /api/vcp\nVCP setup · monitoring · IRR · HITL"]
        ING["ingest_routes.py\nprefix /api/ingest\nfinancial document ingestion"]
        REP["report_routes.py\nprefix /api/reports\nboard pack generation"]
    end

    subgraph Intelligence["Intelligence layer"]
        AGENTS["LLM Agents — app/agents\nAzure OpenAI, offline-heuristic fallback"]
        QUANT["Quant Engine — app/quant\nSTL + SARIMA + Prophet ensemble, IRR"]
        ANALYTICS["Analytics — app/analytics\ndrift · peer benchmarking · data freshness"]
    end

    subgraph Storage["Azure Database for PostgreSQL"]
        DS[("VCPStore · DealStore · CompanyMeta\nReportStore · HITL queue/audit\nKPI records · portfolio memo\n(one JSONB table, partitioned by collection)")]
        FILES[("data/ — feature-matrix CSVs\nuploaded source documents only")]
    end

    subgraph External["External services"]
        EDGAR["SEC EDGAR XBRL\n(companyfacts + submissions)"]
        FRED["FRED\nmacro indicators"]
        YF["Yahoo Finance\nexit multiples"]
        AOAI["Azure OpenAI\nstructured extraction/narrative"]
    end

    FE <-->|REST / JSON| VCP
    FE <-->|REST / JSON| ING
    FE <-->|REST / JSON| REP

    VCP --> AGENTS
    VCP --> QUANT
    VCP --> ANALYTICS
    ING --> AGENTS
    REP --> AGENTS
    REP --> QUANT

    AGENTS --> AOAI
    QUANT --> FRED
    QUANT --> YF
    ANALYTICS --> DS
    AGENTS --> DS
    QUANT --> DS
    VCP --> DS
    ING --> DS
    REP --> DS
    ING --> FILES
    QUANT --> FILES
    ING -.EDGAR pull.-> EDGAR
    VCP -.EDGAR pull + SIC lookup.-> EDGAR
```

**No message queue, no dedicated scheduler in the live path** — report generation
runs as a FastAPI `BackgroundTasks` job (checkpointed via LangGraph on Postgres, so
it survives a restart), and the VCP monitoring graph runs synchronously per request.
Every route computes drift/IRR live at request time from current KPI records — there
is no pre-computation job. §12 covers what moved to Postgres and why.

---

## 3. The two-path onboarding model

The system separates two kinds of input, on two different cadences (this split is
literally in the code comments, not just a doc convention):

| | **Path 1 — VCP Setup** | **Path 2 — Financial Monitoring** |
|---|---|---|
| Cadence | Once, at deal close (or re-run to amend) | Recurring, every reporting period |
| Input | IC memo (PDF/DOCX/MD) | Management accounts, QPRs, EDGAR filings |
| Route | `POST /api/vcp/extract-upload` → `POST /api/vcp/extract/{id}/confirm` | `POST /api/ingest/financials-upload` |
| Output | Confirmed `VCPMilestone[]` in `VCPStore` (Postgres) | Normalized `KPIRecord[]` in the `kpi_records` Postgres collection |
| Human gate | Operating partner edits/confirms milestones before they lock | None at ingestion; HITL applies later, at the alert stage |

---

## 4. Backend module map

| Folder | Purpose |
|---|---|
| `app/api/` | 3 FastAPI routers + `main.py` (app assembly, CORS, `/health`) |
| `app/agents/` | LLM-powered nodes (see §6) |
| `app/analytics/` | Deterministic Python: VCP drift scoring, peer benchmarking, data freshness, sector inference, portfolio action inbox |
| `app/adapters/` | Source-agnostic financial-document → `KPIRecord` normalizers (registry pattern) |
| `app/data_sources/` | Thin clients for SEC EDGAR, FRED, Yahoo Finance |
| `app/ingestion/` | Document loading (PyMuPDF4LLM/Docling), currency/scale normalization, feature-matrix assembly, quarterly resampling |
| `app/quant/` | Forecast ensemble (`forecast_engine.py`) + IRR scenario builder (`vcp_irr.py` — the superseded `irr_engine.py` was deleted, see §11) |
| `app/reports/` | Slide-data builder + PPTX (`python-pptx`) + PDF (`reportlab`) generators |
| `app/store/` | Postgres-backed document stores — `postgres_json_store.py` (the shared `get/put/list/delete` wrapper) plus `VCPStore`, `DealStore`, `company_store.py`, `ReportStore`, `kpi_records_store.py`, `portfolio_memo_store.py` |
| `app/workflows/` | HITL queue building + decision application/audit log, VCP confirmation — all Postgres-backed |
| `app/schemas/` | Shared dataclasses/Pydantic models (`VCPMilestone`, `KPIRecord`, `KPIExtractionConfig`, ...) |
| `app/llm/` | Azure OpenAI client wrapper with `is_configured()` capability check, LangSmith-traced when configured |
| `app/graph/` | **3 live LangGraph workflows** (VCP extraction, VCP monitoring, report generation) + the shared Postgres checkpointer — see §12 |

## 5. Frontend module map

| Folder | Purpose |
|---|---|
| `frontend/src/views/` | One component per app screen: `PortfolioOverview`, `CompanyDetail`, `SetupView` (Path 1), `IngestView` (Path 2), `Alerts` (HITL queue), `MemoView`, `ReportsView`, `ReportViewer`, `VcpTracker` |
| `frontend/src/components/` | Shared UI (`ui.tsx` — badges/cards), `ForwardCurveChart.tsx` (actual/plan/P10-P90 band chart), `EditableSlideText.tsx` (inline report editing, used by `SlideExecutiveSummary.tsx`) |
| `frontend/src/components/slides/` | One renderer per board-pack slide type, mirroring `app/reports/slide_data_builder.py`'s 10 slides |
| `frontend/src/lib/api.ts` | Single fetch client — every backend call goes through here, `API_BASE_URL` from `VITE_API_BASE_URL` env var (default `http://localhost:8000`) |
| `frontend/src/lib/format.ts` | Currency/percent/date formatting, metric display names |

---

## 6. Data model (core schemas)

| Model | File | Key fields |
|---|---|---|
| `VCPMilestone` | `app/schemas/vcp_schema.py` | `company_id, initiative, metric, target_value, target_date, category, baseline_value, confidence, confirmed, version` |
| `KPIRecord` | `app/schemas/kpi_schema.py` | `company_id, period_end, revenue, gross_profit, operating_income, adjusted_ebitda, ebitda_proxy, net_debt, free_cash_flow, source_confidence, evidence_refs` |
| `EvidenceRef` | `app/schemas/kpi_schema.py` | `metric, value, source_type, source_document, source_page_or_sheet, confidence` — the "show your work" citation attached to every extracted number |
| `SourceQualityReport` | `app/schemas/kpi_schema.py` | `required_fields_present, missing_required_fields, null_counts, status` |
| `DealMetadata` | `app/store/deal_store.py` | `entry_ebitda, entry_ev_multiple, entry_net_debt, entry_equity_value, holding_period_years, ic_target_irr, sector_key, deal_close_date` |
| `CompanyMeta` | `app/store/company_store.py` | `company_id, company_name, sector_key, source_type, cik, sic` — sector decided once at ingestion, survives a wipe of `data/processed`/`data/features` |
| `ReportRecord` | `app/store/report_store.py` | narrative content, `drift_results`, `milestones`, `irr_scenarios`, `slides` (per-slide payload), `status` (`draft`/`pending_review`/`approved`) |

### Storage layer — Postgres-backed document stores (§12)

Every document store lives in one physical Postgres table (`app_documents`,
partitioned by a `collection` column), accessed through `PostgresJsonStore`'s
`get(id)/put(id, doc)/list()/delete(id)`. The "path" strings below are legacy
identity keys carried over from when each store really was a JSON file — every
caller already shared the same constant, so switching the internals to Postgres
didn't require touching call sites:

| Store | Collection | Identity key | Class |
|---|---|---|---|
| VCP milestones | `vcp_milestones` | `data/processed/synthetic_vcp_milestones_seed.json` (one doc, all companies) | `VCPStore` |
| Deal metadata | `deals` | `{company_id}` | `DealStore` |
| Company metadata | `company_meta` | `{company_id}` | `app/store/company_store.py` (module functions, not a class) |
| KPI records | `kpi_records` | `data/processed/{company_id}_kpi_records.json` | `app/store/kpi_records_store.py` |
| Portfolio memo | `portfolio_memo` | `data/processed/portfolio_memo.md` (one doc, whole portfolio) | `app/store/portfolio_memo_store.py` |
| Generated reports | `reports` / `report_pdfs` | `{report_id}` | `ReportStore` (PDF bytes base64-encoded in the companion collection) |
| HITL queue / audit log | `hitl_queue` / `hitl_audit_log` | `data/processed/hitl_review_queue.json` / `hitl_audit_log.json` | `app/workflows/hitl_queue.py` / `hitl_decisions.py` |

Still on local disk, deliberately out of scope for the Postgres migration:

| Artifact | Path pattern | Why it stayed on disk |
|---|---|---|
| Feature matrices | `data/features/{company_id}_{raw,model}_feature_matrix.csv` | High-volume time series consumed by `app/quant/forecast_engine.py` — a relational table would need a real schema, not a JSONB blob |
| Cached quant forecast | `data/processed/{company_id}_quant_ebitda_forecast.csv` | Same as above; regenerable from feature matrices |
| Evidence refs / source quality reports | `data/processed/{company_id}_{evidence_refs,source_quality_report}.json` | Written by `kpi_extraction_agent.py`, never read back by any route — not on the query path |
| Uploaded source docs | `data/raw/ic_memos/`, `data/raw/qpr/`, `data/raw/synthetic_portcos/` | Read once at ingestion, not re-read later |

Adapters implement one interface — `BaseKPIAdapter.extract(config: KPIExtractionConfig) -> dict` — and are looked up by `source_type` in `app/adapters/registry.py`. Registered adapters: `EDGARFeatureMatrixAdapter`, `ExcelQPRAdapter`, `PrivatePortcoFinancialAdapter`, `PdfFinancialAdapter` (PyMuPDF4LLM fast path + Docling OCR fallback), `PlaceholderKPIAdapter` (stub for future MCP sources).

---

## 7. Complete API reference (current, post-cleanup)

### `/api/vcp` — `app/api/vcp_routes.py`

| Method | Path | Purpose |
|---|---|---|
| GET | `/portfolio` | Portfolio overview + ranked action inbox (drift, freshness, alerts) |
| GET | `/company/{id}` | Milestones, live drift, KPI series, freshness, basis-mismatch flag |
| GET | `/company/{id}/irr` | Quant forecast (P10/P50/P90) + Bear/Base/Bull IRR scenarios |
| GET | `/company/{id}/peers` | Sector peer benchmarking |
| GET | `/hitl` | HITL review queue |
| POST | `/hitl/decision` | Record approve/edit/reject (writes audit log) |
| GET | `/audit-log` | Full HITL decision audit trail |
| POST | `/companies` | Onboard a company: deal metadata + optional EDGAR ingestion by CIK |
| GET | `/extract/status` | Whether live LLM extraction is configured |
| POST | `/extract/{id}` | Run VCP extraction over a pre-staged IC memo (demo path — no graph equivalent) |
| POST | `/extract/{id}/confirm` | Lock reviewed milestones into `VCPStore` (companion to the demo path above) |
| GET | `/store/{id}` | Raw confirmed VCP store contents for a company |
| GET | `/memo` | Portfolio memo markdown |
| POST | `/memo/generate` | Generate portfolio memo from live portfolio data |
| POST | `/graph/monitor/{company_id}` | Run the monitoring graph — interrupts on Red/Amber for HITL, checkpointed on Postgres |
| POST | `/graph/extract-upload` | **Live path for Setup's upload flow.** Extraction graph: extract → pause for review |
| POST | `/graph/{thread_id}/confirm` | Resume a paused extraction graph run with reviewed milestones |

### `/api/ingest` — `app/api/ingest_routes.py`

| Method | Path | Purpose |
|---|---|---|
| GET | `/status` | Whether the live LLM table-reader is configured |
| POST | `/financials-upload` | Ingest a financial document into normalized `KPIRecord`s |

### `/api/reports` — `app/api/report_routes.py`

| Method | Path | Purpose |
|---|---|---|
| GET | `` (root) | List all generated reports |
| POST | `/graph/generate` | **Live path.** Runs the report graph (drift → alert → narrative → slides → PDF) as a checkpointed background task; returns `{report_id, thread_id}` immediately |
| GET | `/graph/{thread_id}/status` | Real per-node progress via `graph.get_state()` — drives the in-app "Generating…" UI |
| GET | `/{id}` | Full report detail (for the in-app viewer) |
| GET | `/{id}/status` | Generation progress record (legacy field, always `complete`/100 for graph-generated reports) |
| GET | `/{id}/pdf` | Direct download of the reportlab-generated PDF |
| GET | `/{id}/export/pptx` | Editable PowerPoint deck |
| GET | `/{id}/export/pdf` | PDF rendered from the PPTX via LibreOffice (falls back to the reportlab PDF) |
| PATCH | `/{id}/approve` | Operating-partner approval |
| DELETE | `/{id}` | Delete a report |
| PATCH | `/{id}/section` | Inline edit of one narrative section |

### Top-level — `app/api/main.py`

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | Infra health check |

---

## 8. Sequence diagrams

### Path 1 — VCP Setup

```mermaid
sequenceDiagram
    participant U as Operating Partner
    participant FE as React (SetupView)
    participant API as vcp_routes.py
    participant AG as vcp_extraction_agent
    participant AOAI as Azure OpenAI
    participant VS as VCPStore (Postgres)

    U->>FE: Upload IC memo (PDF/DOCX/MD)
    FE->>API: POST /api/vcp/extract-upload
    API->>AG: extract_from_document()
    AG->>AOAI: structured extraction (if configured)
    AOAI-->>AG: milestone candidates + confidence
    AG-->>API: VCPMilestone[] (confirmed=false)
    API-->>FE: candidates for review
    U->>FE: Edit / confirm milestones
    FE->>API: POST /api/vcp/extract/{id}/confirm
    API->>VS: save_all() confirmed=true
    FE->>API: POST /api/vcp/companies (deal metadata + optional CIK)
    API->>API: fetch_company_sic() + infer_sector_key()
    API-->>FE: onboarding complete
```

### Path 2 — Financial Monitoring Ingestion

```mermaid
sequenceDiagram
    participant U as Portco CFO / Operating Partner
    participant FE as React (IngestView)
    participant API as ingest_routes.py
    participant AD as Adapter (registry)
    participant AOAI as Azure OpenAI
    participant KS as kpi_records_store (Postgres)
    participant FS as data/features (CSV)

    U->>FE: Upload management accounts (PDF/XLSX/CSV)
    FE->>API: POST /api/ingest/financials-upload
    API->>AD: dispatch by file suffix / source_type
    AD->>AOAI: structured table extraction (PDF path only)
    AD-->>API: KPIRecord[] + EvidenceRef[] + SourceQualityReport
    API->>KS: save_kpi_records() — normalized KPI series
    API->>FS: write feature-matrix CSVs, evidence_refs.json
    API-->>FE: period preview + quality report
```

### Portfolio monitoring — computed on demand, no batch job

```mermaid
sequenceDiagram
    participant FE as React (PortfolioOverview)
    participant API as GET /api/vcp/portfolio
    participant VS as VCPStore (Postgres)
    participant KS as kpi_records_store (Postgres)
    participant FR as data_freshness.py
    participant DR as vcp_drift.py

    FE->>API: GET /api/vcp/portfolio
    loop for each confirmed company
        API->>VS: load_confirmed_for_company()
        API->>KS: load_kpi_records()
        API->>FR: compute_freshness()
        API->>DR: run_vcp_drift_for_kpi_records()
        DR-->>API: status + drift % per milestone
    end
    API-->>FE: companies[], action_items[] ranked by severity
```

### Report generation

```mermaid
sequenceDiagram
    participant U as Operating Partner
    participant FE as React (ReportsView)
    participant API as POST /api/reports/generate
    participant DR as vcp_drift + alert_synthesis_agent
    participant NA as report_narrative_agent (Azure OpenAI)
    participant SDB as slide_data_builder
    participant PPTX as pptx_generator (python-pptx)
    participant PDF as LibreOffice / reportlab fallback
    participant RS as ReportStore (Postgres, PDF base64)

    U->>FE: Generate Board Pack
    FE->>API: POST /api/reports/graph/generate (background task)
    API->>DR: drift + alert synthesis
    API->>NA: narrative, board questions, risks (LLM)
    API->>SDB: build_slides() — 10 slide payloads
    API->>RS: save ReportRecord (status=draft)
    API-->>FE: report summary
    U->>FE: Review → Approve
    FE->>API: PATCH /api/reports/{id}/approve
    U->>FE: Export
    FE->>API: GET /api/reports/{id}/export/pptx
    API->>PPTX: generate_pptx(slides)
    FE->>API: GET /api/reports/{id}/export/pdf
    API->>PDF: pptx→pdf (fallback: pre-built reportlab PDF)
```

---

## 9. LLM integration

`app/llm/azure_openai.py` wraps a single `AzureOpenAI`/`OpenAI` client. Every agent
checks `azure_openai.is_configured()` (all of `AZURE_OPENAI_ENDPOINT`,
`AZURE_OPENAI_KEY` set) and falls back to a deterministic offline heuristic if not —
**the app is fully functional with zero LLM credentials**, just with lower-quality
extraction/narrative.

| Agent | File | Mode when configured | Offline fallback |
|---|---|---|---|
| VCP Extraction Agent | `app/agents/vcp_extraction_agent.py` | Structured extraction of milestones from IC memo prose | Regex/keyword heuristic parser |
| KPI Extraction (via adapters) | `app/adapters/pdf_financial_adapter.py` | Structured table extraction from scanned/unstructured financial PDFs | Deterministic markdown table parser |
| Alert & Synthesis Agent | `app/agents/alert_synthesis_agent.py` | Multi-signal severity + recommended action synthesis | Rule-based synthesis from drift scores |
| Report Narrative Agent | `app/agents/report_narrative_agent.py` | Executive summary, board questions, structured risks | Templated prose from structured data |

Deployment is configured via `AZURE_OPENAI_DEPLOYMENT` (code default `"gpt-4o"`; this
project's actual configured deployment may differ — check `.env`).

---

## 10. Quant engine

`app/quant/forecast_engine.py`: STL decomposition → SARIMA + Holt-Winters + Prophet
ensemble → quarterly P10/P50/P90 EBITDA forecast, cached to
`data/processed/{id}_quant_ebitda_forecast.csv` (re-run only when the cache is
absent or `refresh=True`). `app/quant/vcp_irr.py` (`build_vcp_irr`) turns that
forecast plus `DealMetadata` (entry equity, entry multiple, holding period) into
Bear/Base/Bull exit IRR scenarios, with a basis guard that suppresses a false
"equity at risk" alarm when the forecast had to fall back from `adjusted_ebitda` to
the GAAP `ebitda_proxy` (a basis-comparability artifact, not real deterioration).

---

## 11. Full architecture review (2026-07-06) and known remaining debt

A full frontend-to-backend review traced every route the React SPA calls through
to its backend module and back, checking for dead code, unwired features, and
hardcoded values that should be config. Findings and what was done about them:

**Dead code — deleted, not kept as debt:**

- **`app/graph/nodes.py` / `graph_builder.py`** — a pre-existing "Week 2"
  KPI/quant/IRR monitor graph using demo AAPL data and the superseded
  `irr_engine.py`. Not the same code as the live monitoring graph
  (`vcp_nodes.py` / `vcp_monitoring_graph_builder.py`) or the extraction/report
  graphs. Deleted, along with its only callers `scripts/run_agent_graph.py` and
  `scripts/run_agent_graph_excel.py`.
- **`app/quant/irr_engine.py`** — older IRR engine superseded by
  `app/quant/vcp_irr.py` for the live API. Deleted, along with its only callers
  `scripts/run_week1_pipeline.py` and `scripts/smoke_test_companies.py`.
- **`app/workflows/portfolio_memo.py`'s `build_portfolio_memo()`** — duplicated
  what the live `POST /api/vcp/memo/generate` does inline in `vcp_routes.py`, but
  read pre-computed batch artifacts instead of live data. Deleted, along with its
  only caller `scripts/run_portfolio_memo.py`; `HOW_TO_RUN_DEMO.md` updated to
  drop that step in favor of the live endpoint.
- **`frontend/src/components/EditableSection.tsx`** — unreferenced anywhere.
  Deleted. (Its sibling, `EditableSlideText.tsx`, is *not* dead — it's used by
  `SlideExecutiveSummary.tsx`, wired into `SlideRenderer.tsx`.)

**File-backed state — migrated to Postgres, closing the hybrid-storage gap left by
the §12 migration:**

The HITL queue/audit log were already Postgres-backed before this review
(`app/workflows/hitl_queue.py` / `hitl_decisions.py`) — the "path" strings passed
around are identity keys, not real file I/O. **KPI records** and the **portfolio
memo** genuinely were still flat files, read/written directly across
`vcp_routes.py`, `ingest_routes.py`, `kpi_extraction_agent.py`, `vcp_drift.py`,
`peer_benchmarking.py`, and `app/graph/report_nodes.py`. Both now go through
`app/store/kpi_records_store.py` (collection `"kpi_records"`) and
`app/store/portfolio_memo_store.py` (collection `"portfolio_memo"`), following the
same identity-key pattern as `VCPStore`/`DealStore` (§12, §6). Pre-existing data in
`data/processed/{company}_kpi_records.json` and `portfolio_memo.md` was backfilled
into Postgres as part of the cutover — moving the code path without backfilling the
data would have made every company show "no data" until re-ingested.

Two regressions this cutover would have caused, caught before/during verification:

- `GET /api/vcp/company/{id}/peers` checked `Path.exists()` on the (no-longer
  written) local KPI file and would have 404'd unconditionally — fixed to check the
  store instead.
- The KPI-records backfill step itself: without it, the live app would run cleanly
  but show empty data for every pre-existing company, since the write path moved to
  Postgres but nothing had populated it yet. Caught by actually running the app and
  looking at the Portfolio Overview, not just by tests passing.

**Remaining known debt, deliberately kept:**

- **`GET /api/vcp/extract/{id}` + `POST /api/vcp/extract/{id}/confirm`** (the
  pre-staged-demo-memo path) intentionally stay on the old synchronous code —
  there's no demo-memo equivalent of the extraction graph, only the upload path
  (`POST /api/vcp/graph/extract-upload`) was cut over.
- **`azure-search-documents` and `apscheduler`** are pyproject dependencies with
  zero imports anywhere in `app/` — remnants of the original design (a RAG search
  index over IC memos, a daily EDGAR-filing poller) that were never built.
- **Feature-matrix CSVs, quant-forecast cache, evidence refs, and uploaded source
  documents** stay on local disk — see §6 for why each one was left out of the
  Postgres migration.
- **No auth** on any route — anyone who can reach the API can read/write any
  company's data.

---

## 12. LangGraph + Postgres migration (live, 2026-07-06)

This supersedes the earlier Cosmos-primary proposal that used to live in this
section. The actual decision: **one Azure Database for PostgreSQL instance** is
both the LangGraph checkpoint store and the primary document store — not a
Cosmos + Postgres split. Rationale: LangGraph ships an official Postgres
checkpointer (`langgraph-checkpoint-postgres`'s `PostgresSaver`); Cosmos DB has no
official LangGraph checkpointer, so using it would have meant hand-writing a
custom `BaseCheckpointSaver` before anything else could proceed.

### 12.1 Storage → Postgres (live)

```mermaid
flowchart LR
    subgraph Before["Before — data/processed/*.json (flat files)"]
        J1["VCPStore · DealStore · CompanyMeta\nReportStore · HITL queue/audit\nKPI records · portfolio memo"]
    end

    subgraph Now["Now — Azure Database for PostgreSQL"]
        PG[("app_documents table\nJSONB doc, keyed by\n(collection, id)")]
        CKPT[("LangGraph checkpoint tables\n(PostgresSaver.setup())")]
    end

    J1 -- "app/store/postgres_json_store.py\nPostgresJsonStore.get/put/list" --> PG
    PG -. "same DATABASE_URL" .-> CKPT
```

`app/store/postgres_json_store.py`'s `PostgresJsonStore` is a minimal
`get(id)/put(id, doc)/list()/delete(id)` wrapper around one physical table
(`app_documents`), partitioned by a `collection` column: `"vcp_milestones"`,
`"deals"`, `"company_meta"`, `"reports"`, `"report_pdfs"`, `"hitl_queue"`,
`"hitl_audit_log"`, `"kpi_records"`, `"portfolio_memo"`. Every one of `VCPStore`,
`DealStore`, `app.store.company_store`, `ReportStore`, `app.workflows.hitl_queue`,
`app.workflows.hitl_decisions`, `app.store.kpi_records_store`, and
`app.store.portfolio_memo_store` reads/writes through this instead of flat JSON —
their public method signatures are unchanged, so no caller in
`vcp_routes.py`/`report_routes.py`/`ingest_routes.py` had to change beyond the
import. PDFs are stored base64-encoded in a companion `report_pdfs` collection
(JSONB holds text, not raw bytes). `PostgresJsonStore.put()` also strips stray
`\x00` bytes from strings recursively — Postgres text/JSONB rejects the null
codepoint outright, and PDF/OCR-extracted source text occasionally carries one.

Still file-backed, deliberately out of scope for the Postgres migration: feature
matrices (CSV, high-volume time series — a relational table would need a real
schema, not a JSONB blob), the cached quant forecast, evidence refs / source
quality reports (write-only, never read back), uploaded source documents, and
generated PPTX files. See §6 for the full breakdown.

### 12.2 LangGraph checkpointer (live)

`app/graph/checkpointer.py`'s `get_checkpointer()` builds a `PostgresSaver` against
`DATABASE_URL` and runs `.setup()` once from a FastAPI startup event
(`app/api/main.py`'s `lifespan`), which also calls `PostgresJsonStore.ensure_table()`
for the document store. All three graphs — monitoring (`vcp_monitoring_graph_builder.py`),
extraction (`extraction_graph.py`), and report (`report_graph.py`) — compile with
this shared checkpointer, so a paused HITL review or an in-flight report generation
survives a server restart.

### 12.3 LangSmith tracing (live)

`app/llm/azure_openai.py`'s `get_client()` wraps the returned client with
LangSmith's `wrap_openai()` — every `.chat.completions.create()` call across all
4 agent call sites (`vcp_extraction_agent`, `pdf_financial_adapter`,
`alert_synthesis_agent`, `report_narrative_agent`) is traced automatically when
`LANGCHAIN_TRACING_V2`/`LANGSMITH_TRACING` is set; it's a no-op otherwise. No
agent-side code changes were needed.

Env vars: `LANGCHAIN_TRACING_V2=true`, `LANGCHAIN_API_KEY`, `LANGCHAIN_PROJECT`
(e.g. `pe-vcp-copilot`), `LANGCHAIN_ENDPOINT` (optional, defaults to
`https://api.smith.langchain.com`).

---

## 13. Environment variables (current, complete)

| Variable | Required | Default | Used by |
|---|---|---|---|
| `AZURE_OPENAI_ENDPOINT` | for live LLM | — | `app/llm/azure_openai.py` |
| `AZURE_OPENAI_KEY` | for live LLM | — | `app/llm/azure_openai.py` |
| `AZURE_OPENAI_DEPLOYMENT` | no | `"gpt-4o"` | `app/llm/azure_openai.py` |
| `AZURE_OPENAI_API_VERSION` | no | `"2024-10-21"` | `app/llm/azure_openai.py` |
| `FRED_API_KEY` | no | — (macro data skipped if absent) | `app/data_sources/fred.py` |
| `YFINANCE_VERIFY_SSL` | no | `"true"` | `app/data_sources/market_data.py` |
| `DEFAULT_EXIT_EBITDA_MULTIPLE` | no | `15.0` | `app/data_sources/market_data.py` fallback |
| `SEC_USER_AGENT` | no | `"value-creation-copilot contact@example.com"` | `app/data_sources/edgar.py` |
| `DEFAULT_CIK` | no | Apple demo value (`0000320193`) | `app/ingestion/build_feature_matrix.py`, `app/data_sources/edgar.py` dev/demo convenience |
| `CORS_ORIGINS` | no | localhost:5173/5174 (both `http`/`127.0.0.1`) | `app/api/main.py` |
| `VITE_API_BASE_URL` | no | `http://localhost:8000` | `frontend/src/lib/api.ts` |
| `DATABASE_URL` | **yes** | — (raises `RuntimeError` on first store access if absent) | `app/graph/checkpointer.py`, `app/store/postgres_json_store.py` — every document store and all 3 LangGraph checkpoints |
| `LANGCHAIN_TRACING_V2` / `LANGSMITH_TRACING` | no | off | `app/llm/azure_openai.py` (`wrap_openai`) |
| `LANGCHAIN_API_KEY` | for LangSmith tracing | — | `app/llm/azure_openai.py` |
| `LANGCHAIN_PROJECT` | no | — | `app/llm/azure_openai.py` |

All backend env vars load via `python-dotenv` from a repo-root `.env`.
