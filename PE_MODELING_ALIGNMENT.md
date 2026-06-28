# PE Modeling Alignment — Final Copilot Numbers & Accuracy Gaps

## 1. What the final PE Value Creation Copilot must show

The final Copilot should not only forecast KPIs. It should translate operating performance into **PE return impact**.

### A. Deal setup / entry assumptions

These define the starting point of the investment.

```text
entry_date
entry_revenue
entry_adjusted_ebitda
entry_ebitda_margin
entry_ev_ebitda_multiple
entry_enterprise_value
entry_net_debt
entry_equity_value / sponsor_equity_contribution
holding_period_years
ic_target_irr
ic_target_moic
```

Why this matters:

```text
IRR and MOIC are calculated from sponsor equity invested to sponsor equity received at exit.
Without entry value / sponsor equity, the return calculation is not truly PE-specific.
```

---

### B. Operating performance metrics

These track whether the portfolio company is actually improving.

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

Why this matters:

```text
PE value creation depends heavily on revenue growth, margin expansion, cash generation, and leverage reduction.
```

---

### C. Quant Agent forecast outputs

These are the forward-looking outputs from the forecasting layer.

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

Current prototype status:

```text
We forecast EBITDA proxy using STL, Holt-Winters, SARIMA, SARIMAX, and Prophet.
```

Target state:

```text
Forecast adjusted EBITDA, not only operating-income proxy.
```

---

### D. Exit valuation metrics

These convert forecast operating performance into exit value.

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

Important correction already made:

```text
EV/EBITDA multiple should be applied to annual / LTM EBITDA, not a single quarter of EBITDA.
```

---

### E. PE return metrics

These are the numbers PE deal teams care about most.

```text
MOIC = exit_equity_value / entry_equity_value
IRR = (MOIC ** (1 / holding_period_years)) - 1
IRR gap vs IC target
MOIC gap vs IC target
scenario status: Red / Amber / Green
```

Recommended status logic:

```text
Green  = base IRR meets or exceeds IC target
Amber  = base IRR below IC target but bear case not value destructive
Red    = base IRR materially below IC target or bear MOIC < 1.0x
```

---

### F. Value creation attribution

The final Copilot should explain *why* returns changed.

```text
value_from_revenue_growth
value_from_margin_expansion
value_from_ebitda_growth
value_from_multiple_expansion_or_compression
value_from_debt_paydown
value_from_cash_generation
```

This is important because PE users do not only ask:

```text
What is the IRR?
```

They ask:

```text
What is driving the IRR?
```

---

## 2. What is missing for true private-company PE accuracy

### 1. Deal metadata

Current prototype:

```text
Uses yfinance market cap / enterprise value as entry valuation.
```

True PE workflow:

```text
Uses deal-close entry valuation from IC / deal model.
```

Required next file:

```text
data/raw/deal_metadata/demo_deal.json
```

---

### 2. Adjusted EBITDA bridge

Current prototype:

```text
ebitda_proxy = operating-income-style metric from EDGAR.
```

True PE workflow:

```text
adjusted_ebitda = reported EBITDA + validated add-backs / normalizations
```

Why it matters:

```text
PE valuation and exit readiness often depend on adjusted EBITDA, not raw reported operating income.
```

---

### 3. Debt schedule / debt paydown

Current prototype:

```text
Uses latest net debt as a simple exit adjustment.
```

True PE workflow:

```text
Projects debt annually/quarterly using free cash flow available for debt repayment.
```

Needed metrics:

```text
opening_debt
cash_interest
mandatory_amortization
cash_sweep
ending_debt
ending_cash
ending_net_debt
```

---

### 4. Free cash flow model

Current prototype:

```text
No detailed FCF bridge yet.
```

True PE workflow:

```text
EBITDA
- cash taxes
- capex
- change in net working capital
- cash interest
= cash available for debt paydown / distributions
```

---

### 5. Peer-based exit multiple

Current prototype:

```text
Uses current yfinance EV/EBITDA and applies ± scenario adjustments.
```

True PE workflow:

```text
Uses peer trading comps / precedent transactions / sector multiple range.
```

Target metrics:

```text
peer_p25_ev_ebitda
peer_p50_ev_ebitda
peer_p75_ev_ebitda
selected_exit_multiple
multiple_rationale
```

---

### 6. IC thesis comparison

Current prototype:

```text
No IC target comparison yet.
```

True PE workflow:

```text
Compare actual and forecast performance against IC memo targets.
```

Needed outputs:

```text
revenue_gap_vs_ic
ebitda_gap_vs_ic
leverage_gap_vs_ic
irr_gap_vs_ic
recommended_alert_severity
```

---

## 3. Final architecture direction

The project should support two modes.

### Mode 1 — Public-market proxy mode

Purpose:

```text
Smoke-test the data and Quant Agent pipeline on listed companies.
```

Inputs:

```text
EDGAR financials
FRED macro variables
yfinance market cap / EV / EV-EBITDA
```

Good for:

```text
AAPL, MSFT, GOOGL, AMZN, META, NVDA smoke tests
```

---

### Mode 2 — PE deal mode

Purpose:

```text
Represent a real private-equity portfolio monitoring workflow.
```

Inputs:

```text
data room financials / board packs
adjusted EBITDA bridge
IC memo targets
deal metadata
peer comps
```

Good for:

```text
IRR vs IC target
value creation tracking
Red / Amber / Green alerts
board-ready reporting
```

---

## 4. Immediate implementation decision

We should now add:

```text
data/raw/deal_metadata/demo_deal.json
```

Then update:

```text
app/quant/irr_engine.py
```

to use deal metadata when available.

Priority order:

```text
1. Add demo_deal.json
2. Load deal metadata in IRR engine
3. Use deal entry equity value instead of public market cap in PE mode
4. Add MOIC and IRR gap vs IC target
5. Add scenario status
```

---

## 5. Summary

Current implementation is directionally correct for Week 1.

It already proves:

```text
EDGAR + FRED + yfinance ingestion
model-ready feature matrix
multi-model Quant Agent forecast
P10 / P50 / P90 EBITDA proxy curve
IRR scenario table
multi-company smoke testing
```

To make it truly PE-accurate, the next layer must add:

```text
deal metadata
adjusted EBITDA
free cash flow / debt paydown
MOIC
IC target comparison
value creation attribution
```
