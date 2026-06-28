# Week 2 Summary — PE Value Creation Copilot

## 1. Updated Project Direction

This week, the project was realigned from a **forecast-first portfolio monitoring prototype** into a more focused **VCP-first PE Value Creation Copilot**.

The key learning from additional research was that the core post-close PE problem is not only forecasting KPIs or generating dashboards. The more important workflow is connecting the original **investment thesis / value creation plan (VCP)** to ongoing portfolio company performance.

The project is now framed around four core questions:

```text
1. What did we promise at deal close?
2. What is actually happening now?
3. Where is the company drifting from the value creation plan?
4. Which portfolio company needs operating partner attention first?
```

This changed the architecture from:

```text
Financial data → forecast → IRR table
```

to:

```text
IC memo / investment thesis
→ confirmed VCP milestones
→ recurring KPI normalization
→ VCP drift detection
→ portfolio alerts
→ operating partner action inbox
→ HITL / reporting layer
```

---

## 2. Updated Architecture

The architecture now has two separate paths.

### Path 1 — Setup Path

Runs once at deal close.

```text
IC memo / investment thesis / 100-day plan
→ VCP milestone extraction
→ human confirmation
→ VCPStore
```

For now, VCP milestones are seeded using structured synthetic JSON. Later, the VCP Extraction Agent will extract these milestones from IC memo markdown/PDF documents.

### Path 2 — Monitoring Path

Runs every reporting period or file upload.

```text
Financial source file
→ adapter / normalization layer
→ normalized KPI records
→ VCP Drift Node
→ portfolio alerts
→ action inbox
→ HITL review queue
```

The key architectural rule is:

```text
Raw files stop at adapters.
Analytical nodes consume normalized business records.
```

This means VCP Drift, alerts, and future reporting do not depend directly on CSV, Excel, EDGAR, or PDF structure.

---

## 3. Completed Work

### 3.1 Week 1 foundation retained

The original data and quant foundation remains in place:

```text
EDGAR data pipeline
FRED macro-ready feature matrix
yfinance valuation inputs
Quant forecasting engine
STL / Holt-Winters / SARIMA / SARIMAX / Prophet
P10 / P50 / P90 EBITDA proxy forecasts
PE-style IRR / MOIC scenario engine
demo deal metadata
```

This foundation is still useful as the forward-looking analytical layer of the monitoring graph.

---

### 3.2 Adapter-based KPI normalization

Implemented an adapter-based normalization layer.

Current adapters:

```text
EDGAR adapter
Excel/QPR adapter
Private portco CSV adapter
```

All adapters normalize source data into the same core outputs:

```text
KPIRecord
EvidenceRef
SourceQualityReport
model_feature_matrix.csv
```

This validates the source-agnostic design.

Current normalized input paths supported:

```text
EDGAR structured public-company data
Excel/QPR demo file
Private portfolio company CSV financials
```

---

### 3.3 Synthetic private portco data

Generated synthetic data for three portfolio companies:

```text
Company A — B2B SaaS
Company B — Industrial Manufacturing
Company C — Healthcare Services
```

Each company has:

```text
24 months of monthly financial data
CSV format
Excel format
synthetic IC memo markdown
seed VCP milestones
```

The synthetic financial data includes deliberate value creation drift:

```text
Months 1–12: company tracks close to plan
Month 13 onward: revenue growth slows and SG&A rises
Result: EBITDA margin compression and leverage pressure
```

Generated files include:

```text
data/raw/synthetic_portcos/<company_id>/<company_id>_monthly_financials.csv
data/raw/synthetic_portcos/<company_id>/<company_id>_monthly_financials.xlsx
data/raw/ic_memos/<company_id>_ic_memo.md
data/processed/synthetic_vcp_milestones_seed.json
data/processed/synthetic_source_manifest.json
```

---

### 3.4 VCPStore

Implemented a lightweight JSON-backed VCPStore.

Files:

```text
app/schemas/vcp_schema.py
app/store/vcp_store.py
scripts/check_vcp_store.py
```

VCPStore currently loads:

```text
data/processed/synthetic_vcp_milestones_seed.json
```

Capabilities:

```text
load all milestones
load milestones for one company
load confirmed milestones
check whether VCP is confirmed
summarize milestones by company
```

The seed store currently contains:

```text
15 total milestones
3 companies
5 milestones per company
```

Milestone types include:

```text
Revenue growth plan
EBITDA margin expansion
Deleveraging plan
Chief Revenue Officer hire
Monthly KPI reporting upgrade
```

---

### 3.5 VCP Drift Node

Implemented deterministic VCP drift computation.

Files:

```text
app/analytics/vcp_drift.py
scripts/run_vcp_drift_check.py
scripts/run_vcp_drift_from_kpi_records.py
```

The VCP Drift Node compares latest KPI actuals against confirmed VCP milestones.

Supported financial metrics:

```text
annual_revenue
ebitda_margin
net_debt_to_ebitda
```

Operational / organizational milestones are not guessed from financial data. They are marked safely as:

```text
Not Evaluable
```

This avoids hallucinating progress on non-financial commitments such as:

```text
cro_hired
reporting_cadence_upgrade_complete
```

---

### 3.6 Clean VCP Monitoring Graph

Built a dedicated clean VCP monitoring graph.

Files:

```text
app/graph/vcp_nodes.py
app/graph/vcp_monitoring_graph_builder.py
scripts/run_vcp_monitoring_graph.py
```

Current graph flow:

```text
initialize
→ vcp_confirmation_check
→ vcp_drift_from_kpi_records
→ vcp_alert_summary
→ END
```

Important cleanup completed:

```text
The graph no longer reads raw CSV paths or synthetic source manifest for drift.
It consumes normalized KPI records only.
```

Example output for Company A:

```text
VCP confirmed: True
Drift results: 5
Status counts: {'Red': 3, 'Amber': 0, 'Green': 0, 'Not Evaluable': 2}
Alerts: 3
```

---

### 3.7 Batch private portco normalization

Implemented batch KPI normalization across all three synthetic portcos.

File:

```text
scripts/run_all_private_portco_kpi_normalization.py
```

Output:

```text
Companies processed: 3
Each company produced 24 KPI records
Each company produced 216 evidence references
Each source quality report passed
```

Generated files include:

```text
data/processed/portco_a_saas_kpi_records.json
data/processed/portco_b_industrial_kpi_records.json
data/processed/portco_c_healthcare_kpi_records.json
```

---

### 3.8 Portfolio-level VCP monitoring

Implemented portfolio-level VCP monitoring across all three synthetic companies.

File:

```text
scripts/run_portfolio_vcp_monitoring.py
```

Output:

```text
Companies monitored: 3
Total alerts: 9
Red alerts: 8
Amber alerts: 1
```

Company-level results:

```text
Company A — B2B SaaS: 3 Red alerts
Company B — Industrial Manufacturing: 3 Red alerts
Company C — Healthcare Services: 2 Red alerts, 1 Amber alert
```

Generated file:

```text
data/processed/portfolio_vcp_monitoring_summary.json
```

This is the first portfolio-level monitoring output.

---

### 3.9 Operating Partner Action Inbox

Implemented a deterministic portfolio action inbox.

File:

```text
app/analytics/portfolio_action_inbox.py
scripts/run_portfolio_action_inbox.py
```

The action inbox converts raw alerts into ranked operating partner action items.

Output:

```text
Action items: 3
Company A: P1
Company B: P1
Company C: P1
```

Each action item includes:

```text
priority_rank
priority
priority_score
company_id
headline
primary_risks
recommended_action
evidence
```

Generated file:

```text
data/processed/portfolio_action_inbox.json
```

This is the first version of the operating partner workflow:

```text
Which company needs attention first?
Why?
What should we do next?
What evidence supports it?
```

---

## 4. Latest Working Flow

The current working end-to-end deterministic flow is:

```text
Synthetic private portco financials
→ PrivatePortcoFinancialAdapter
→ normalized KPI records
→ VCPStore
→ VCP Monitoring Graph
→ VCP drift alerts
→ Portfolio monitoring summary
→ Operating Partner Action Inbox
```

Commands executed successfully:

```powershell
uv run python scriptsun_all_private_portco_kpi_normalization.py
uv run python scriptsun_portfolio_vcp_monitoring.py
uv run python scriptsun_portfolio_action_inbox.py
```

Latest summary:

```text
Portfolio companies: 3
Total alerts: 9
Severity counts: {'Red': 8, 'Amber': 1}
Action items: 3
```

---

## 5. Key Architecture Decisions

### 5.1 Deterministic calculations stay in Python

Financial calculations are handled by Python, not LLMs:

```text
KPI normalization
VCP drift
IRR / MOIC
forecasting
alert scoring
```

This avoids hallucination risk and keeps financial outputs auditable.

### 5.2 LLMs will be used only where they add value

Future LLM agents will be used for:

```text
VCP extraction from IC memo prose
alert synthesis narrative
board-ready report language
```

### 5.3 Raw files are not analytical inputs

Raw files are only used by adapters and for evidence lineage.

Analytical nodes consume normalized records:

```text
KPIRecord
EvidenceRef
SourceQualityReport
VCPMilestone
```

### 5.4 Source manifests are upstream inventory only

The synthetic source manifest remains useful for ingestion and batch normalization, but it is no longer used directly by VCP Drift.

---

## 6. What Is Not Built Yet

The following items are intentionally not built yet:

```text
Docling PDF extraction
VCP Extraction Agent from IC memo documents
LLM-based Alert & Synthesis Agent
Peer Benchmarking Agent
Streamlit HITL UI
Board memo / PDF report
LangSmith tracing
Azure deployment
```

These will come after the deterministic monitoring core is stable.

---

## 7. Immediate Next Steps

### Next Milestone 1 — HITL Review Queue

Convert:

```text
portfolio_action_inbox.json
```

into:

```text
hitl_review_queue.json
```

The HITL queue should include:

```text
review_id
status
priority
company_id
headline
recommended_action
evidence
decision fields for approve/edit/reject
```

### Next Milestone 2 — Portfolio Memo Skeleton

Create a first markdown memo from:

```text
portfolio_action_inbox.json
portfolio_vcp_monitoring_summary.json
hitl_review_queue.json
```

Sections:

```text
Executive summary
Portfolio alert overview
Company-level action items
Evidence citations
Pending review items
```

### Next Milestone 3 — VCP Extraction from Documents

Start with:

```text
IC memo markdown → structured milestones
```

Then add:

```text
Markdown → PDF
Docling PDF extraction
PDF → markdown/text → VCP Extraction Agent
```

---

## 8. Current Demo Narrative

The current demo story is:

```text
Most PE firms track the value creation plan manually after deal close.
This prototype turns the VCP into structured milestones,
normalizes recurring financial data,
compares actuals against the VCP,
and produces a portfolio-level action inbox for operating partners.
```

Current proof:

```text
3 synthetic portfolio companies
24 months of financials each
15 VCP milestones
9 portfolio drift alerts
3 ranked action items
```

---

## 9. Summary

Week 2 successfully shifted the project into a VCP-first architecture and delivered the deterministic monitoring core.

Completed:

```text
Source-agnostic KPI normalization
Synthetic private portco data
VCPStore
VCP Drift Node
Clean VCP Monitoring Graph
Portfolio VCP monitoring
Operating Partner Action Inbox
```

The project is now ready to move into:

```text
HITL review queue
portfolio memo skeleton
VCP extraction from IC memo documents
```
