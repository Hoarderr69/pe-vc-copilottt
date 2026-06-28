# PE Value Creation Copilot — Rebased Alignment After Week 1 + Competitor Learnings

## 1. Why this rebaseline exists

The initial plan was correct directionally, but after reviewing portfolio-monitoring competitors and building the first working graph, we need to avoid two risks:

1. Building too many downstream agents before the input layer is stable.
2. Over-polishing dashboard/reporting before the system has trusted, source-backed KPI data.

So the updated principle is:

```text
First make the data ingestion and KPI extraction layer source-agnostic and evidence-backed.
Then build thesis, peer, agreement/risk, alert, HITL, and memo layers on top.
```

This preserves the original project goal while reducing rework later.

---

## 2. Current confirmed progress

### Week 1 foundation — complete

Completed:

```text
EDGAR + FRED + yfinance data pipeline
model-ready feature matrix
Quant Agent forecast engine
STL / Holt-Winters / SARIMA / SARIMAX / Prophet models
20-quarter P10/P50/P90 EBITDA proxy forecasts
IRR scenario table
MOIC calculation
PE-deal mode with synthetic deal metadata
IRR gap vs IC target
scenario status: Red / Amber / Green
multi-company smoke testing
```

Important financial correction already made:

```text
EV/EBITDA multiple is applied to terminal annual EBITDA,
where terminal annual EBITDA = sum of final 4 forecast quarters.
```

This fixed the earlier issue of applying EV/EBITDA to a single forecast quarter.

---

### Week 2 foundation — partially complete

Completed so far:

```text
LangGraph smoke run
shared graph state
adapter folder created
BaseKPIAdapter contract
EDGARFeatureMatrixAdapter
PlaceholderKPIAdapter
adapter registry
KPI Extraction Agent refactored to call adapters
standardized kpi_records.json
evidence_refs.json
source_quality_report.json
end-to-end graph still runs after adapter refactor
```

Latest confirmed output:

```text
Raw rows: 60
Model rows: 60
KPI records: 60
Evidence refs: 360
Forecast rows: 20
IRR rows: 3
HITL status: pending_review
Alerts: 1
```

This proves that the system has moved from:

```text
EDGAR-specific pipeline
```

to:

```text
source-aware KPI extraction architecture
```

---

## 3. Original timeline vs updated interpretation

The original timeline expected Week 2 to cover:

```text
LangGraph setup
KPI Extraction Agent
Peer Benchmarking Agent
IC memo indexing
Thesis RAG Agent
Alert & Synthesis Agent
HITL gate
```

That remains directionally correct, but the sequencing needs refinement.

The updated order should be:

```text
1. LangGraph orchestrator
2. Source-agnostic KPI Extraction Agent
3. Second source adapter proof, preferably Excel/QPR
4. Thesis/underwriting alignment
5. Peer benchmarking
6. Agreement/risk checks
7. Alert synthesis
8. HITL queue
9. Memo/report skeleton
```

Reason:

```text
If KPI extraction is not source-agnostic and evidence-backed,
then thesis, peer, alert, and memo agents will all be built on fragile inputs.
```

---

## 4. Competitor learning translated into project scope

Competitor/market learning:

```text
Portfolio-monitoring tools emphasize QPR ingestion, thesis comparison,
risk flags, evidence citations, and board-ready outputs.
```

What we should adopt:

```text
source-agnostic KPI extraction
standard KPI schema
evidence-backed metrics
actual vs IC thesis comparison
agreement/risk checks
board-ready decision artifact
```

What we should not overbuild right now:

```text
full MCP server
full legal agreement parser
complex dashboard polish
deep learning forecast models
production deployment before graph stability
```

---

## 5. Updated architecture direction

### Core architecture

```text
LangGraph Orchestrator
    ↓
KPI Extraction Agent
    ↓
Source Adapters
    ├── EDGAR Adapter — implemented
    ├── Excel/QPR Adapter — next
    ├── Board Pack PDF Adapter — later
    ├── Underwriting Model Adapter — later
    └── MCP Adapter — future
    ↓
Standard KPIRecord + EvidenceRef schema
    ↓
Quant Agent
    ↓
IRR/MOIC Scenario Agent
    ↓
Thesis / Peer / Agreement-Risk / Alert Agents
    ↓
HITL + Memo Builder
```

### Key design principle

```text
Downstream agents should never parse raw EDGAR, Excel, PDF, or MCP outputs directly.
They should consume standardized KPIRecord and EvidenceRef artifacts.
```

---

## 6. Updated Week 2 plan

### Week 2 milestone A — Orchestrator + source-agnostic KPI layer

Status: mostly complete.

Deliverables:

```text
app/graph/state.py
app/graph/nodes.py
app/graph/graph_builder.py
scripts/run_agent_graph.py
app/schemas/kpi_schema.py
app/adapters/base.py
app/adapters/edgar_adapter.py
app/adapters/placeholder_adapter.py
app/adapters/registry.py
app/agents/kpi_extraction_agent.py
data/processed/kpi_records.json
data/processed/evidence_refs.json
data/processed/source_quality_report.json
```

Success criteria:

```text
run_agent_graph.py passes
KPI records are generated
Evidence refs are generated
Source quality report is generated
Quant forecast still runs
IRR/MOIC scenario table still runs
```

Status:

```text
Complete for EDGAR source.
```

---

### Week 2 milestone B — Add second source adapter proof

Next priority.

Build:

```text
data/raw/qpr/demo_qpr.xlsx
app/adapters/excel_qpr_adapter.py
```

Goal:

```text
Prove that a non-EDGAR source can map into the same KPIRecord schema.
```

Success criteria:

```text
source_type = excel
Excel adapter produces kpi_records.json
evidence_refs.json includes source_page_or_sheet
source_quality_report.json passes
Downstream graph can still run using standardized KPI output
```

This is the most important next step because it validates the product claim:

```text
EDGAR, QPRs, Excel files, and board packs can all map into one standard KPI format.
```

---

### Week 2 milestone C — Thesis / underwriting alignment

After second source adapter proof.

Build:

```text
data/raw/ic_memos/demo_ic_memo.md
or
data/raw/deal_metadata/demo_underwriting_case.json
app/agents/thesis_alignment_agent.py
```

For now, prefer structured JSON/Markdown before full RAG.

Reason:

```text
We need thesis comparison logic before we need complex vector retrieval.
```

Required outputs:

```text
thesis_milestones.json
actual_vs_ic_revenue_gap
actual_vs_ic_ebitda_gap
forecast_vs_ic_ebitda_gap
irr_gap_vs_ic
moic_gap_vs_ic
thesis_drift_status
```

---

### Week 2 milestone D — Peer benchmarking and agreement/risk checks

Build after thesis alignment.

Peer Benchmarking Agent:

```text
sector peer set
median revenue growth
median EBITDA margin
median leverage
company vs peer gap score
```

Agreement/risk-checking Agent:

```text
net_debt_to_ebitda
max_allowed_net_debt_to_ebitda
leverage_headroom
interest_coverage, if available
risk_status
```

Note:

```text
Use simple structured thresholds first.
Do not build a full legal agreement parser yet.
```

---

### Week 2 milestone E — Alert synthesis + HITL queue

Build after thesis, peer, and agreement/risk signals exist.

Inputs:

```text
IRR gap vs IC
MOIC gap vs IC
forecast EBITDA gap vs IC
peer underperformance
agreement/risk headroom
source quality status
```

Outputs:

```text
severity
summary
risk_drivers
recommended_action
evidence_refs
hitl_status
```

HITL artifact:

```text
data/processed/hitl_review_queue.json
```

---

## 7. Updated Week 3 plan

Week 3 should remain focused on output and demo readiness, but only after the Week 2 state is reliable.

Updated priority order:

```text
1. Memo/report skeleton from graph state
2. Streamlit dashboard only after memo data is available
3. Forward curve chart
4. IRR/MOIC scenario table
5. Thesis scorecard
6. Peer comparison view
7. Agreement/risk status card
8. Evidence citations
9. LangSmith tracing
10. Deployment only after graph is stable
```

Important change:

```text
Board-ready memo comes before dashboard polish.
```

Reason:

```text
The final product should be a decision artifact, not only a visual dashboard.
```

---

## 8. Updated Week 4 demo story

Demo flow should be:

```text
1. Show source input — EDGAR or demo QPR Excel
2. KPI Extraction Agent normalizes into KPIRecord schema
3. Show evidence_refs for one KPI
4. Quant Agent generates P10/P50/P90 EBITDA forecast
5. IRR/MOIC scenario table compares to IC target
6. Thesis/peer/agreement-risk signal creates alert
7. HITL queue shows review item
8. Memo/report summarizes evidence-backed decision
```

Strong demo message:

```text
The ingestion source can change, but the downstream monitoring workflow stays the same.
```

---

## 9. Scope guardrails to avoid delay

Do not build now:

```text
full MCP server
full legal contract parser
full board-pack PDF parser
advanced deep learning forecasting
production Azure deployment before graph stability
complex Streamlit UI before memo/report state is reliable
```

Build now:

```text
Excel/QPR adapter
thesis comparison schema
simple peer benchmarking
simple agreement/risk thresholds
alert synthesis
HITL queue
memo skeleton
```

---

## 10. Final rebased direction

The project remains aligned with the original timeline:

```text
Week 1 = Data and Quant Foundation
Week 2 = Agents and LangGraph Pipeline
Week 3 = Dashboard, Report, Evidence, Deployment
Week 4 = Demo
```

But Week 2 is now re-centered around the correct foundation:

```text
source-agnostic, evidence-backed KPI extraction.
```

This avoids downstream rework and makes the final PE Value Creation Copilot more credible.
