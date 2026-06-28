# PE Modeling Alignment — Updated with Portfolio Monitoring Market Learnings

## 0. Strategic Positioning

The project should be positioned as a **post-close PE value creation monitoring copilot**, not simply a forecasting dashboard.

The core promise:

```text
QPR / board pack / financial data arrives
→ KPIs are extracted and standardized
→ actual performance is compared against IC underwriting / entry thesis
→ Quant Agent projects forward EBITDA and return outcomes
→ covenant, thesis drift, and IRR/MOIC risk are flagged
→ board-ready memo / review queue is generated with evidence
```

The strongest market lesson from V7 Go is that portfolio teams want **thesis-linked monitoring, covenant/risk alerts, source-cited evidence, and board-ready outputs**, not just raw AI summaries or charts.

---

## 1. Important Industry Learnings to Lock In

### 1. Entry thesis is the anchor

Portfolio monitoring should compare performance against the **original underwriting model / IC thesis**, not only against the prior quarter.

Required in our Copilot:

```text
actual_vs_ic_revenue_gap
actual_vs_ic_ebitda_gap
forecast_vs_ic_ebitda_gap
irr_gap_vs_ic
moic_gap_vs_ic
thesis_drift_status
```

Why this matters:

```text
PE teams care whether the deal is still tracking toward the return committed at IC.
```

---

### 2. QPR and board-pack ingestion is the real production data path

EDGAR is useful for the prototype, but production must support:

```text
QPR PDFs
board packs
management reports
Excel financial models
data room exports
underwriting model files
IC memos
credit agreements
```

Prototype data source:

```text
SEC EDGAR + FRED + yfinance
```

Production data source:

```text
PortCo reports + underwriting model + IC memo + board packs
```

---

### 3. Covenant monitoring is a must-have risk layer

Portfolio monitoring is not only about growth. It must also detect downside risk and covenant pressure.

Add later:

```text
net_debt_to_ebitda
max_leverage_covenant
leverage_headroom
interest_coverage
minimum_liquidity
covenant_status
```

Simple first covenant logic:

```text
leverage_headroom = max_allowed_net_debt_to_ebitda - current_net_debt_to_ebitda
```

---

### 4. Source citations and auditability are non-negotiable

Every AI-generated KPI, alert, and memo statement should be tied to evidence.

Required evidence fields:

```text
source_document
source_page_or_sheet
source_section
source_metric_name
source_value
calculation_formula
computed_value
confidence
```

This is essential because finance users must verify numbers quickly.

---

### 5. The final output should be a decision memo, not only a dashboard

The end user wants a partner/board-ready artifact.

Final memo sections should include:

```text
executive_summary
financial_snapshot
actual_vs_ic_scorecard
P10/P50/P90 forward curve summary
IRR/MOIC scenario table
covenant_headroom
peer benchmark comparison
risk flags
recommended actions
evidence citations
HITL approval record
```

---

## 2. Numbers the Final Copilot Must Have

### A. Deal setup / entry assumptions

```text
entry_date
entry_revenue
entry_adjusted_ebitda
entry_ebitda_margin
entry_ev_ebitda_multiple
entry_enterprise_value
entry_net_debt
entry_equity_value
sponsor_equity_contribution
holding_period_years
ic_target_irr
ic_target_moic
```

Current status:

```text
demo_deal.json added for synthetic PE-deal mode
```

---

### B. Operating performance metrics

```text
revenue
revenue_growth
adjusted_ebitda
ebitda_margin
working_capital
capex
free_cash_flow
net_debt
net_debt_to_ebitda
```

Current status:

```text
EDGAR-based revenue, operating income, net debt, working capital, and EBITDA proxy are available.
Adjusted EBITDA and FCF are not yet fully modeled.
```

---

### C. Quant Agent forecast outputs

```text
p10_revenue
p50_revenue
p90_revenue
p10_adjusted_ebitda
p50_adjusted_ebitda
p90_adjusted_ebitda
forecast_confidence
macro_assumptions
model_count
model_diagnostics
```

Current status:

```text
P10/P50/P90 EBITDA proxy curves are working using STL, Holt-Winters, SARIMA, SARIMAX, and Prophet.
```

---

### D. Exit valuation metrics

```text
exit_annual_ebitda
exit_ev_ebitda_multiple
exit_enterprise_value
exit_net_debt
exit_equity_value
```

Correct calculation:

```text
exit_annual_ebitda = sum of final 4 forecast quarters
exit_enterprise_value = exit_annual_ebitda × exit_ev_ebitda_multiple
exit_equity_value = exit_enterprise_value - exit_net_debt
```

Correction already made:

```text
EV/EBITDA multiple is applied to annual / LTM EBITDA, not one quarter of EBITDA.
```

---

### E. PE return metrics

```text
MOIC = exit_equity_value / entry_equity_value
IRR = (MOIC ** (1 / holding_period_years)) - 1
IRR gap vs IC target
MOIC gap vs IC target
scenario_status
```

Current status:

```text
MOIC, IRR, IRR gap vs IC, and scenario status are implemented in PE-deal mode.
```

---

### F. Value creation attribution

Final product should explain return drivers:

```text
value_from_revenue_growth
value_from_margin_expansion
value_from_ebitda_growth
value_from_multiple_expansion_or_compression
value_from_debt_paydown
value_from_cash_generation
```

Current status:

```text
Not implemented yet.
This should come after debt schedule / FCF model.
```

---

## 3. What Is Still Missing for True Private-Company PE Accuracy

| Area | Current Prototype | True PE Requirement | Priority |
|---|---|---|---|
| Entry valuation | `demo_deal.json` synthetic assumptions | Actual deal model / IC entry assumptions | High |
| EBITDA | EBITDA proxy from EDGAR | QoE / adjusted EBITDA bridge | High |
| Exit multiple | yfinance EV/EBITDA ± scenario haircut/premium | Peer comps / precedent transactions / sector multiple range | High |
| Debt | Latest net debt only | Debt schedule + cash sweep + ending net debt | High |
| Free cash flow | Not modeled in detail | EBITDA - taxes - capex - NWC - interest | Medium |
| Thesis comparison | Deal metadata only | IC memo milestone extraction and actual/forecast variance | High |
| Covenants | Not implemented | Leverage, interest coverage, liquidity headroom | High |
| Citations | CSV outputs only | Source-linked evidence per KPI / alert | High |
| Memo output | Not implemented | Board-ready memo with evidence and HITL status | Medium |
| Value attribution | Not implemented | EBITDA growth, multiple expansion, debt paydown bridge | Medium |

---

## 4. Updated Timeline Additions

## Week 1 — Data & Quant Foundation ✅ Completed

Completed:

```text
EDGAR XBRL pipeline
FRED macro feature matrix
yfinance market valuation input
model-ready feature matrix
STL decomposition
Holt-Winters forecast
SARIMA forecast
SARIMAX macro forecast
Prophet forecast
ensemble P10/P50/P90 EBITDA proxy curve
IRR scenario table
MOIC
PE-deal mode using demo_deal.json
multi-company smoke testing
```

Key output files:

```text
data/features/demo_feature_matrix.csv
data/features/demo_model_feature_matrix.csv
data/processed/quant_ebitda_forecast.csv
data/processed/irr_scenarios.csv
data/raw/deal_metadata/demo_deal.json
```

---

## Week 2 — Agentic Portfolio Monitoring Layer

### Day 1 — LangGraph skeleton + shared state

Build:

```text
app/graph/state.py
app/graph/nodes.py
app/graph/graph_builder.py
scripts/run_agent_graph.py
```

State should include:

```text
company_metadata
deal_metadata
kpi_series
feature_matrix_path
forecast_path
irr_scenarios
thesis_milestones
peer_composite
covenant_results
alerts
evidence_refs
hitl_status
```

---

### Day 2 — Thesis / underwriting model alignment

Add synthetic thesis artifacts:

```text
data/raw/ic_memos/demo_ic_memo.pdf or .md
data/raw/deal_metadata/demo_underwriting_case.json
```

Extract / represent:

```text
IC revenue targets
IC EBITDA targets
IC leverage targets
IC target IRR
IC target MOIC
milestone dates
```

Build:

```text
app/agents/thesis_rag_agent.py
```

Output:

```text
thesis_milestones.json
actual_vs_ic_gap
forecast_vs_ic_gap
thesis_drift_status
```

---

### Day 3 — Peer Benchmarking Agent + basic covenant checks

Build:

```text
app/agents/peer_benchmarking_agent.py
app/agents/covenant_agent.py
```

Peer Benchmarking Agent should calculate:

```text
sector_median_revenue_growth
sector_median_ebitda_margin
sector_median_net_debt_to_ebitda
company_vs_sector_gap_score
```

Covenant Agent should calculate first-pass:

```text
current_net_debt_to_ebitda
max_allowed_net_debt_to_ebitda
leverage_headroom
covenant_status
```

---

### Day 4 — Alert & Synthesis Agent

Build:

```text
app/agents/alert_synthesis_agent.py
```

Alert inputs:

```text
IRR gap vs IC
MOIC gap vs IC
forecast EBITDA gap vs IC
peer underperformance
covenant headroom
thesis drift
```

Alert outputs:

```text
severity = Red / Amber / Green
alert_summary
risk_drivers
recommended_action
evidence_refs
```

---

### Day 5 — HITL review queue + memo skeleton

Build:

```text
data/processed/hitl_review_queue.json
app/reports/portfolio_memo_builder.py
```

Memo sections:

```text
financial summary
thesis scorecard
IRR/MOIC scenario table
covenant headroom
peer benchmark summary
risk flags
recommended actions
evidence citations
approval status
```

Do not overbuild frontend yet. The key is creating the **decision artifact**.

---

## Week 3 — Dashboard, Report, Evidence, and Deployment

Updated priorities:

```text
1. Dashboard only after alerts and memo data are available
2. Forward curve + IRR/MOIC heatmap
3. Thesis scorecard visualization
4. Covenant headroom widget
5. Peer benchmark chart
6. Board-ready PDF / memo
7. LangSmith tracing and audit log
8. Azure deployment only after graph is stable
```

---

## 5. Revised Product Differentiation

Market tools emphasize QPR automation, thesis drift, covenant checks, citations, and board memo generation.

Our differentiator should be:

```text
Forward-looking exit intelligence.
```

Specifically:

```text
Not only: What changed this quarter?
But: What does this quarter imply for exit IRR, MOIC, IC target achievement, and value creation risk?
```

This means our strongest demo flow should be:

```text
QPR / financial data
→ KPI extraction
→ actual vs IC thesis
→ Quant Agent forecast
→ IRR/MOIC scenario table
→ covenant and peer risk checks
→ source-cited alert
→ board-ready memo
→ HITL approval
```

---

## 6. Final Locked Direction

We will keep the current Week 1 Quant foundation and extend it into a portfolio monitoring workflow.

Immediate next implementation focus:

```text
1. LangGraph shared state
2. Thesis milestone schema
3. IC/underwriting comparison
4. Covenant check placeholder
5. Alert synthesis
6. HITL review queue
```

Avoid for now:

```text
frontend polish
deep learning forecasting experiments
complex deployment work
```

Reason:

```text
Industry need is workflow-grade, thesis-linked, source-cited monitoring — not model novelty or UI polish first.
```
