# PE Value Creation Copilot — Final Project Document

**Role**: Data & AI Intern
**Duration**: 4 weeks (3 build + 1 demo)
**Stack**: Python · LangGraph · Claude API · GPT-4o · Streamlit · PostgreSQL · Azure
**Output**: A working agentic AI prototype that tracks PE investment theses against live portfolio company data, detects value creation drift, and generates board-ready output

---

## What This Is

When a private equity firm closes a deal, they write an investment thesis — specific commitments about how they'll grow the company: EBITDA from £12M to £20M by Year 3, revenue growth from 15% to 25%, SG&A ratio down from 32% to 24%. That thesis lives in a PDF. The moment the deal closes, it goes into a folder.

For the next 3-7 years, operating partners manage 8-15 portfolio companies simultaneously through quarterly board meetings and board decks. By the time a metric shows red in a board pack, it's been drifting for 6-9 months. There's no system that connects the original investment thesis to real-time operational data, detects drift early, and tells operating partners exactly where value is being lost.

This project builds that system — a Value Creation Copilot that reads the IC memo at deal close, extracts every commitment as a structured milestone, monitors portfolio company data continuously against those milestones, and generates alerts and board materials automatically.

---

## Architecture Overview

The system has two execution graphs and five distinct component types. Understanding the difference between them is architecturally important.

### Component Types

**True AI Agents** — LLM-powered nodes for tasks that require language understanding and contextual reasoning. Used where rules would fail and where the output is genuinely variable based on context.

**Analytical Nodes** — Python and statistical ML. Deterministic: same input always produces same output. Used for computation, transformation, and forecasting where precision matters more than flexibility.

**Infrastructure** — Scheduling, storage, and UI. Not part of the intelligence layer.

This separation is deliberate. Using an LLM to compute IRR is wrong (hallucination risk, slow, expensive). Using Python to read an unstructured IC memo is equally wrong (brittle, breaks on any phrasing variation). The system uses each tool where it belongs.

---

### Full Component Map

```
INFRASTRUCTURE
├── EDGAR Monitor              APScheduler · daily poll for new 10-K/10-Q/8-K
└── HITL Gate                  Streamlit modal · human review checkpoint

ANALYTICAL NODES (Python / Statistical ML)
├── KPI Normalization Node     Any source → unified financial DataFrame
├── Quant Forecasting Node     STL + SARIMA + Prophet → P10/P50/P90 + IRR scenarios
├── Peer Benchmarking Node     SIC code → EDGAR peers → sector medians + gap scores
└── VCP Drift Node             Arithmetic: actual vs stored VCP targets → drift %

TRUE AI AGENTS (LLM-powered reasoning)
├── VCP Extraction Agent       Claude: IC memo PDF → structured milestone objects
├── Alert & Synthesis Agent    GPT-4o: all signals → severity + lever + narrative
└── Report Narrative Agent     GPT-4o: structured data → board-ready executive prose
```

---

### Two Execution Graphs

The system runs two separate LangGraph graphs with different triggers, frequencies, and purposes.

**Graph 1: Setup Graph** — runs once at deal close when a new portfolio company is onboarded.

```
START
  │
  ▼
[Upload IC Memo PDF + Investment Thesis]
  │
  ▼
[VCP Extraction Agent]  ← Claude claude-sonnet-4-6
  Reads unstructured IC memo prose
  Extracts every forward-looking commitment
  Classifies by type: financial / operational / organisational / commercial
  Structures into typed VCPMilestone objects with targets, dates, owners
  Assigns confidence score per milestone
  │
  ▼
[HITL: Operating Partner Reviews Milestones]
  Edit / confirm / delete / add manually
  Human confirmation locks the VCP
  │
  ▼
[VCPStore Write]  ← Postgres table, versioned
  Ground truth for all subsequent monitoring runs
  │
END
```

**Graph 2: Monitoring Graph** — runs on every new filing or data period (daily/weekly/quarterly depending on data source).

```
START
  │
  ▼
[VCP Confirmation Check]
  ├── VCP not confirmed → prompt user, block → END
  └── VCP confirmed → proceed
  │
  ▼
[EDGAR Monitor / File Ingest]
  New 10-K / 10-Q / 8-K detected, or manual file upload
  │
  ▼
[Filing Type Router]
  ├── 8-K (earnings release) → [Guidance Extraction via GPT-4o] → merge → continue
  ├── 10-Q (quarterly)       → continue
  └── 10-K (annual)          → continue
  │
  ▼
[KPI Normalization Node]
  Source-agnostic transformation → unified pd.DataFrame
  Derived metrics computed in Python (margins, growth rates, ratios)
  │
  ├──────────────────────────┐
  ▼                          ▼
[Quant Forecasting Node]   [Peer Benchmarking Node]   ← parallel execution
 STL decomposition          SIC code → 20-50 EDGAR peers
 SARIMA(2,1,2) on trend     Sector medians: rev growth,
 Prophet + FRED regressors  EBITDA margin, leverage
 P10/P50/P90 forecast       Company-vs-sector gap scores
 20-quarter horizon
 IRR scenario table
  │                          │
  └──────────┬───────────────┘
             │
  [Confidence Check]
  ├── history < 8 quarters → cap horizon at 2yr, add warning flag
  └── sufficient history  → full 5-year projection
             │
             ▼
  [VCP Drift Node]  ← pure Python, no LLM
  Loads confirmed milestones from VCPStore
  actual vs target gap % per milestone
  on_track = gap > -10%
             │
             ▼
  [Alert & Synthesis Agent]  ← GPT-4o structured output
  Inputs: quant gaps + peer gaps + VCP drift + IRR shift
  Reasons about combined signal in context
  Output: severity (Red/Amber/Green) + headline + root cause
          + recommended lever category + citations
             │
  [Severity Router]
  ├── Red   → immediate HITL push
  ├── Amber → batch end-of-day HITL digest
  └── Green → dashboard update only, no HITL
             │
  [HITL Gate]
  Deal team reviews: forward curve + IRR shift + VCP milestone table
  Approve (with note) / Edit / Reject
  All decisions logged with timestamp and user
             │
  ├──────────────────────────┐
  ▼                          ▼
[Report Narrative Agent]  [Dashboard Update]
 GPT-4o: exec summary      Streamlit live refresh
 prose for board PDF
  │
[Report Generator]
 ReportLab assembles PDF:
 exec summary + forward curve + IRR table
 + VCP scorecard + sector comparison
 + evidence citations + HITL audit record
  │
END
```

---

## Data Ingestion: Two Paths

### Path 1 — VCP Data (once at deal close)

**Source**: IC memo PDF, investment thesis PDF, 100-day plan deck

These documents contain the investment thesis in unstructured prose. The VCP Extraction Agent reads them and produces typed, human-confirmed milestone objects that become the ground truth for all monitoring.

```
IC Memo PDF
Investment Thesis PDF
        │
        ▼
  Local PDF extraction (PyMuPDF4LLM fast path; Docling OCR fallback for scanned pages)
  — runs on-premise, no document bytes leave the machine
        │
        ▼
  VCP Extraction Agent (Claude)
  — Identifies every forward-looking commitment in the text
  — "We expect EBITDA to grow from £12M to £20M by Year 3"
  — "We will hire a Chief Revenue Officer within 90 days of close"
  — "SG&A as % of revenue will reduce from 32% to 24% by Year 2"
        │
        ▼
  Pydantic Validation
  VCPMilestone {
    id, initiative, metric,
    baseline_value, target_value, target_date,
    owner_role, category, source_text, confidence
  }
        │
        ▼
  HITL: Human confirms / edits / adds milestones
        │
        ▼
  VCPStore (Postgres)
  — Locked until operating partner explicitly updates thesis
  — Read-only during all monitoring runs
  — Referenced by VCP Drift Node on every filing
```

### Path 2 — Financial / Operational Data (recurring per period)

**Source**: Any — EDGAR XBRL (prototype), Excel uploads, CSV exports, PDF management accounts, production ERP connectors.

The key design principle: **the normalization layer makes the pipeline source-agnostic**. Every downstream node sees the same DataFrame regardless of where the data came from.

```
SOURCE (any of the following):
│
├── EDGAR XBRL API ──────────── Structured JSON, no parsing needed
│   GET /companyfacts/{cik}     60-quarter history, free, no auth
│   Revenue, EBITDA, NetDebt   → dict lookup → pd.DataFrame
│
├── Excel upload (.xlsx) ─────── openpyxl parser
│   Management accounts         Formula-aware (traces cell values, not formulas)
│   Income statement template   → pd.DataFrame
│
├── CSV export ───────────────── pandas read_csv
│   QuickBooks / Xero export    Column name fuzzy mapping
│   (column names vary)         [optional: Claude for ambiguous headers]
│                               → pd.DataFrame
│
├── PDF management accounts ──── Local parse (PyMuPDF4LLM → Docling OCR) + Claude
│   Scanned or native PDF       Native text/tables fast; scanned pages via local
│   (hardest format)            OCR (TableFormer). On-premise → pd.DataFrame
│
└── [Production] ERP connectors  NetSuite, Salesforce, HRIS
    (not built in prototype)     → pd.DataFrame
                │
                ▼
    ┌─────────────────────────────┐
    │   NORMALIZATION LAYER       │
    │   Unified schema:           │
    │   columns: revenue,         │
    │   gross_profit, ebitda,     │
    │   net_debt, cash, ar_days,  │
    │   ap_days, headcount        │
    │   index: period (YYYY-QQ)   │
    └──────────────┬──────────────┘
                   │
                   ▼
    KPI Computation (Python only — never LLM)
    gross_margin        = gross_profit / revenue
    ebitda_margin       = ebitda / revenue
    revenue_growth_yoy  = (rev_t / rev_t-4) - 1
    net_debt_to_ebitda  = net_debt / ebitda_ttm
                   │
                   ▼
    kpi_series (time-series DataFrame)  →  Quant Forecasting Node
                                        →  Peer Benchmarking Node
                                        →  VCP Drift Node
```

---

## Synthetic Data to Build

Since the prototype uses synthetic data alongside real EDGAR data, three assets need to be created.

### 1. Synthetic IC Memos (3 PDFs, one per fake portco)

Each PDF is 4-5 pages. Write in realistic IC memo language — prose, not tables. The VCP Extraction Agent must find commitments in natural language.

Each memo should contain:
- 2-3 financial milestones: revenue target, EBITDA margin target, leverage ratio target
- 1-2 operational milestones: e.g., "complete ERP migration by Year 1 Q3", "reduce SG&A from 30% to 22% by Year 2"
- 1 organisational milestone: e.g., "hire Chief Revenue Officer within 90 days of close"
- Write at least one milestone ambiguously (confidence should be < 0.7) to test the HITL review flow

**Build tool**: Write in Markdown, convert to PDF with `fpdf2` or `reportlab`. ~1-2 hours per memo.

**Three portco profiles to use**:
- **Company A** — B2B SaaS, £20M ARR, 18% EBITDA margin, target 24% by Year 3
- **Company B** — Industrial manufacturing, £45M revenue, 12% EBITDA margin, target 18%
- **Company C** — Healthcare services, £30M revenue, strong growth, working capital issue

### 2. Synthetic Financial Data (Excel + CSV, per portco)

24 months of monthly P&L + balance sheet per company:
- Columns: Revenue, COGS, Gross Profit, SG&A, EBITDA, Cash, AR, Inventory, AP, Net Debt
- Generate the same underlying numbers in both `.xlsx` and `.csv` format — this lets you demo that the normalization layer produces identical output from two different sources

**Deliberate anomaly design (critical for the demo)**:
- Months 1-12: tracking close to VCP target (±5%)
- Month 13: revenue growth plateaus
- Months 14-18: headcount continues growing while revenue is flat → EBITDA margin compresses 300-400bps below plan
- This is the signal the Quant Forecasting Node catches and the Alert Agent flags

**Build tool**: Python script using `faker` + `numpy` with configurable trend parameters and a `np.random.seed` for reproducibility.

### 3. EDGAR Public Company Proxy

Pick one real mid-size public company per sector (EDGAR XBRL):
- Gives 15 years of real quarterly data for the Quant Forecasting Node
- Makes P10/P50/P90 curves statistically grounded, not synthetic
- Good choices: A mid-cap industrial ($500M-2B revenue), a B2B services company, a healthcare services business
- Find via EDGAR company search: `https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany`

---

## Week-by-Week Build Plan

### Week 1 — Data Foundation & Quant Engine

**Goal**: Build the complete data ingestion and forecasting layer. This is the technical core. Prove the quant output makes financial sense before building agents on top of it.

| Day | Focus | Deliverable |
|---|---|---|
| Mon | EDGAR XBRL pipeline | Script pulls Revenue, EBITDA, NetDebt, WorkingCapital for a test company via `GET /companyfacts/{cik}.json`. Clean 60-quarter `pd.DataFrame`. Data quality checks pass. |
| Tue | FRED macro integration | FRED API client pulling DFF (fed funds rate), CPIAUCSL (CPI), BAA10Y (credit spread). Aligned to quarterly frequency. Merged into EDGAR DataFrame as macro feature matrix. |
| Wed | Quant Node — Part 1 | `statsmodels` STL decomposition on EBITDA series (trend + seasonal + residual). SARIMA(2,1,2) fit on trend component. Holt-Winters as alternative. Ensemble weights tuned. Point forecast produces sensible output. |
| Thu | Quant Node — Part 2 | Prophet model with FRED regressors added. P10/P50/P90 uncertainty quantile extraction. 20-quarter forecast horizon. Confidence score computed from history length. |
| Fri | IRR scenario table + synthetic data | Exit EV/EBITDA multiples via FMP/yfinance. Entry EV from deal metadata. Exit EBITDA = P10/P50/P90 at Year 5. IRR calculated for each scenario. Synthetic IC memo draft 1 created. |

**End-of-week check**: Quant engine runs on EDGAR data and produces a sensible P10/P50/P90 EBITDA chart and bear/base/bull IRR table with numbers that make financial sense when checked manually.

---

### Week 2 — Agents & LangGraph Pipeline

**Goal**: Wire the LangGraph state machine. Add the VCP Extraction Agent (the core AI agent). Complete the monitoring pipeline end-to-end.

| Day | Focus | Deliverable |
|---|---|---|
| Mon | LangGraph setup + state schema | `TypedDict` state defined with all fields: `filing_metadata, kpi_series, kpi_vs_vcp, forward_curves, irr_scenarios, peer_composite, vcp_milestones, vcp_drift_scores, alerts, hitl_status`. Graph compiled. EDGAR Monitor with APScheduler. Filing type router (10-K / 10-Q / 8-K paths). `VCPMilestone` Pydantic model defined. `VCPStore` class (read/write JSON or Postgres). |
| Tue | KPI Normalization Node + Peer Benchmarking Node | KPI Node: EDGAR XBRL → DataFrame, derived metrics computed in Python. Also: `kpi_vs_vcp` dict computed by comparing latest actuals against VCPStore targets. Peer Node: SIC lookup, 10-20 EDGAR peers, sector medians and gap scores written to state. |
| Wed | VCP Extraction Agent | **Main AI agent build.** Local PDF extraction (PyMuPDF4LLM + Docling OCR fallback). Claude prompt engineered to find every forward-looking commitment in IC memo prose. Pydantic-validated `VCPMilestone` output. HITL review UI in Streamlit: milestone table with edit/confirm/delete. Evaluation: manually annotate 10 milestones from one test memo, measure extraction precision. |
| Thu | Alert & Synthesis Agent | GPT-4o structured output. Prompt combines: quant gaps, VCP drift scores, peer gaps, IRR shift. Output schema: `{severity, headline, irr_at_risk_bps, vcp_milestones_at_risk, root_cause, recommended_action, lever_category, citations}`. Severity classification tested across Red/Amber/Green cases. |
| Fri | HITL gate + end-to-end test | Streamlit approval modal: forward curve preview, VCP milestone drift table, IRR shift, approve/edit/reject with note. Full pipeline test: synthetic 10-Q trigger → KPI → [Quant ∥ Peer] → VCP Drift → Alert → HITL modal. No breaks in the chain. |

**End-of-week check**: A mock filing triggers the full Monitoring Graph end-to-end. VCP milestones correctly flagged as at-risk. Alert card appears in Streamlit with correct severity and cited lever.

---

### Week 3 — Dashboard, Reports & Deploy

**Goal**: Build the output layer. Private portco data path. Observability. Ship to Azure.

| Day | Focus | Deliverable |
|---|---|---|
| Mon | Streamlit dashboard shell | Multi-page app: (1) Portfolio Overview — company cards with VCP health score colour coding, top 3 alerts across portfolio; (2) Company Deep Dive — KPI metric cards, period selector, filing timeline; (3) Alerts Feed — HITL queue with severity badges; (4) VCP Tracker — milestone list with progress bars, status badges, due date timeline. |
| Tue | Plotly charts | Forward curve chart: historical EBITDA (solid) + P10/P50/P90 bands (shaded) + IC milestone dots overlaid. IRR scenario heatmap: entry multiple × exit multiple → IRR colour grid. VCP milestone bar chart: actual vs target per milestone, colour coded. Sector comparison bar chart. |
| Wed | Private portco data path + ReportLab board pack | **Morning (3h)**: Excel/PDF upload path — Streamlit file uploader, openpyxl parser for Excel, local PDF parse (PyMuPDF4LLM + Docling OCR fallback), output identical DataFrame format as EDGAR path. Demo: same numbers from Excel and CSV produce identical output. **Afternoon (3h)**: ReportLab board pack PDF — exec summary (Report Narrative Agent, GPT-4o), forward curve chart embedded, P10/P50/P90 IRR table, VCP milestone scorecard, sector benchmark comparison, evidence citations, HITL audit record. |
| Thu | Observability + deploy | LangSmith: `@traceable` on each agent node. Token counts and latency visible. Azure Container Apps: Dockerfile, `az containerapp up`, secrets via Azure Key Vault. Dashboard reachable at public URL. |
| Fri | Demo dry run + cleanup | Full demo run against live EDGAR data. Time the flow (target: trigger → board PDF ready in < 2 minutes). Fix formatting. GitHub repo: README, `requirements.txt`, `.env.example`, architecture diagram. Demo script rehearsed. |

**End-of-week check**: Live Azure deployment at public URL. Full demo flow runs cleanly in under 2 minutes. Board PDF downloads with all sections correct. LangSmith trace shows all agent steps with token usage.

---

### Week 4 — Demo

| Day | Activity |
|---|---|
| Mon–Tue | Two full dry runs. Fix any final issues. Rehearse narrative arc: problem → demo flow → production path → discussion. |
| Wed | Mentor demo |

---

## Demo Script (2.5 minutes)

**Opening**: *"Most PE firms spend more time analysing a deal before they buy it than managing it for the next 5 years. This is the system that changes that."*

**Scene 1 — Deal Close (30s)**
Upload the synthetic IC memo PDF. VCP Extraction Agent runs (or show pre-run result). Dashboard switches to VCP Tracker: 6 milestones extracted, structured, with targets, dates, confidence scores.

*"The system has read the investment thesis and now knows exactly what success looks like for this company. Every commitment. Every deadline. Confirmed by the operating partner in 10 minutes instead of a 2-hour manual process."*

**Scene 2 — Filing Detected (30s)**
Trigger the EDGAR pipeline (or show pre-run). KPI DataFrame populates. Forward curve chart loads: P10/P50/P90 bands, IC milestone dots sitting above the P50 line.

*"Three quarters post-close, a new 10-Q drops. The quant engine runs STL decomposition and a Prophet model with macro regressors — the base case EBITDA forecast is £17.2M at exit. The IC thesis assumed £20M. There's a gap, and it's widening."*

**Scene 3 — VCP Drift (30s)**
Switch to VCP Tracker. Revenue milestone: 🔴 -12% below target. EBITDA margin: 🟡 -280bps below target. ERP go-live: 🔴 2 months delayed.

*"Three milestones are drifting. The IRR gap is already 280 basis points below the underwritten case. This is 6 months before it would appear in a board deck."*

**Scene 4 — Alert (20s)**
Red alert card: headline, root cause, lever category: `pricing_and_revenue_growth`, citations. Approve in HITL modal with note.

*"Every number in this alert is cited back to its source — EDGAR filing, FRED macro data, IC memo page 4. Every approval is logged."*

**Scene 5 — Board Pack (20s)**
Click download. Show PDF: exec summary paragraph, forward curve with IC overlay, IRR scenario table, VCP milestone scorecard, evidence citations, HITL audit record.

*"This used to be 2 weeks and 3 analysts. It's now 90 seconds."*

**Close**: *"In production, the EDGAR ingestion path swaps to the firm's own board packs and ERP exports — same agents, private data, identical pipeline. We built both paths."* (show file upload demo)

---

## Tech Stack

| Component | Tool | Why |
|---|---|---|
| Language | Python 3.11+ | Full ecosystem for ML, data, and LLM work |
| Agent framework | LangGraph | Stateful graphs, conditional routing, HITL, LangSmith integration |
| LLM — extraction + narrative | Claude claude-sonnet-4-6 (Anthropic API) | Best for long financial documents, structured extraction |
| LLM — synthesis + structured output | GPT-4o (Azure OpenAI) | Structured output mode, fast, strong at multi-signal reasoning |
| PDF parsing | PyMuPDF4LLM (fast path) + Docling OCR/TableFormer (scanned fallback) | Fully on-premise — confidential PE/dataroom data never leaves the machine. Native text + tables in ms; local OCR only when a page has no text layer. (Cloud parsers like LlamaParse/Mistral OCR ruled out on data-residency grounds.) |
| Structured output validation | Pydantic v2 | Type-safe agent outputs, catches hallucinations at the schema level |
| Time-series / forecasting | statsmodels + Prophet | STL decomp, SARIMA, Prophet — classical but reliable |
| Embeddings + semantic search | Azure AI Search (BM25 + dense vector) | IC memo indexing, hybrid retrieval |
| Database | PostgreSQL (Azure / Supabase) | VCPStore, audit log, financial time-series |
| Dashboard | Streamlit | Fast to build, sufficient for a prototype, handles file upload natively |
| Charts | Plotly | Interactive, professional, PE-style financial visualisations |
| Excel parsing | openpyxl | Formula-aware, handles cross-sheet references |
| PDF generation | ReportLab | Board-quality PDF assembly |
| Observability | LangSmith | Full agent trace, token usage, latency per node |
| Scheduling | APScheduler | EDGAR daily poll trigger |
| Deploy | Azure Container Apps | Serverless, scales to zero, EY Azure subscription |

---

## What This Demonstrates

**Data Engineering**
- Designed a multi-entity relational schema for PE deal tracking
- Built a source-agnostic normalization pipeline handling EDGAR JSON, Excel, CSV, and PDF
- Implemented data quality validation and period-aligned time-series construction

**Machine Learning**
- Time-series forecasting with STL decomposition + SARIMA + Prophet ensemble
- Macro regressor integration (FRED economic indicators)
- Probabilistic forecasting: P10/P50/P90 uncertainty quantification
- IRR scenario modelling under bear/base/bull exit assumptions

**AI / LLM Engineering**
- Designed a correct agentic architecture distinguishing AI agents from analytical nodes
- Prompt engineering for structured extraction from long financial documents
- Pydantic-validated structured output — schema enforcement on LLM responses
- Evaluation methodology: precision/recall on VCP extraction vs manually annotated ground truth
- Multi-signal synthesis agent with cited structured output

**Domain Knowledge**
- PE investment lifecycle: IC memo, VCP, 100-day plan, value creation tracking
- Financial metrics: IRR, TVPI, EBITDA, net debt, working capital ratios
- ILPA Performance Template 2025 reporting standards
- EDGAR XBRL API structure and GAAP tag normalisation

**Systems Thinking**
- Two distinct execution graphs with different triggers and frequencies
- Four genuine conditional routing points in the monitoring graph
- Human-in-the-loop at two stages with full audit trail
- Separation of LLM reasoning from deterministic computation

---

## How to Talk About This

**One-sentence version**: *"I built an agentic AI system that reads a PE investment thesis at deal close, extracts every value creation commitment, monitors portfolio company financial data against those commitments, and alerts operating partners when value is drifting — before it shows up in a board meeting."*

**The architecture point that matters**: *"We have three true LLM agents for tasks that require language understanding — VCP extraction from IC memos, multi-signal alert synthesis, and board-ready narrative generation. The remaining nodes are deterministic: a time-series forecasting engine, a peer benchmarking computation, and a KPI normalization pipeline. We deliberately separated them because using an LLM to compute IRR is wrong, and using Python to read an unstructured IC memo is equally wrong."*

**The product angle**: *"The system is designed around the operating partner's actual workflow — they want to know which of their 10 portfolio companies needs attention this week, what's wrong, and what lever to pull. The VCP Tracker and alert digest are the product. The quant engine and agents are the infrastructure."*

---

## Resources

**Domain:**
- ILPA Performance Template 2025 — ilpa.org (free download)
- "The PE Value Creation Playbook" — McKinsey & Company
- SEC EDGAR XBRL API docs — `https://data.sec.gov/api/xbrl/`
- Damodaran industry financial ratios — `pages.stern.nyu.edu/~adamodar`

**Technical:**
- LangGraph documentation — `langchain-ai.github.io/langgraph`
- Anthropic Cookbook (structured output examples) — `github.com/anthropics/anthropic-cookbook`
- Prophet documentation — `facebook.github.io/prophet`
- PyMuPDF4LLM documentation — `pymupdf.readthedocs.io/en/latest/pymupdf4llm`
- Docling documentation — `ds4sd.github.io/docling`
- Azure OpenAI structured output — `learn.microsoft.com/azure/ai-services/openai`

---

*Demo target: July 15. All three build weeks ship a demoable checkpoint. Week 4 is rehearsal only.*
