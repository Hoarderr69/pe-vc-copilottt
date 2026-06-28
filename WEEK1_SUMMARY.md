# Week 1 Summary — PE Value Creation Copilot

## Objective

Week 1 focused on building the **Data + Quant Foundation** for the PE Value Creation Copilot. The goal was to prove that the system can ingest public financial data, enrich it with macro variables, generate a forward EBITDA curve, and translate that forecast into PE-style IRR scenarios.

This aligns with the Week 1 milestone: **EDGAR XBRL pipeline + FRED integration + Quant Agent forecast + P10/P50/P90 bands + IRR scenario validation**.

---

## What was built

### 1. Data source layer

Built and tested the core data-source layer:

- **SEC EDGAR XBRL** for structured company financials.
- **FRED** for macro variables.
- **yfinance** for market valuation inputs and EV/EBITDA multiple.

Current default demo company:

| Field | Value |
|---|---|
| Company | Apple Inc. |
| Ticker | AAPL |
| CIK | 0000320193 |

---

### 2. Raw feature matrix

Generated:

```text
data/features/demo_feature_matrix.csv
```

This file combines company financials and macro variables.

Main columns:

```text
period_end
revenue
operating_income
net_income
ebitda_proxy
working_capital
net_debt
fed_funds_rate
cpi
credit_spread
```

Purpose:

```text
EDGAR + FRED aligned quarterly dataset
```

This is the raw analytical base used by the Quant Agent.

---

### 3. Model-ready feature matrix

Generated:

```text
data/features/demo_model_feature_matrix.csv
```

This is a cleaned copy of the raw feature matrix for modeling.

Why needed:

- EDGAR has reporting gaps in some fiscal-year / quarter-end records.
- Forecasting models cannot consume null values directly.
- We preserve raw data separately and create a model-ready copy for Quant Agent use.

Cleaning logic:

```text
numeric conversion
linear interpolation
forward fill
backward fill
```

---

## Quant Agent implementation

Created:

```text
app/quant/forecast_engine.py
```

The Quant Agent currently uses an explainable ensemble forecasting stack:

| Model | Purpose |
|---|---|
| STL decomposition | Breaks EBITDA series into trend, seasonality, residuals |
| Holt-Winters | Captures trend + seasonality baseline |
| SARIMA | Statistical seasonal ARIMA forecast |
| SARIMAX | SARIMA with FRED macro regressors |
| Prophet | Flexible trend/seasonality model with macro regressors |

Generated:

```text
data/processed/stl_components.csv
data/processed/quant_ebitda_forecast.csv
```

---

## Forecast output

The final forecast output is:

```text
data/processed/quant_ebitda_forecast.csv
```

Forecast horizon:

```text
20 quarters
2026-06-30 to 2031-03-31
```

Each forecast row contains:

```text
period_end
model
target_metric
p10
p50
p90
model_count
```

Interpretation:

| Column | Meaning |
|---|---|
| p10 | Downside / bear EBITDA forecast |
| p50 | Base-case EBITDA forecast |
| p90 | Upside / bull EBITDA forecast |
| model_count | Number of models contributing to ensemble |

Validation:

```text
Rows: 20
model_count: 4 for every row
```

This confirms all four model families contributed consistently to each forecast quarter.

---

## IRR scenario engine

Created:

```text
app/quant/irr_engine.py
```

Generated:

```text
data/processed/irr_scenarios.csv
```

The IRR engine translates the Quant Agent forecast into PE-style valuation scenarios.

Important correction made:

```text
EV/EBITDA multiples must be applied to annual EBITDA, not one quarter of EBITDA.
```

Therefore, terminal annual EBITDA is calculated as:

```text
sum of last 4 forecast quarters
```

Scenario logic:

| Scenario | EBITDA input | Multiple input |
|---|---|---|
| Bear | Sum of last 4 p10 values | Base EV/EBITDA × 0.85 |
| Base | Sum of last 4 p50 values | Base EV/EBITDA |
| Bull | Sum of last 4 p90 values | Base EV/EBITDA × 1.15 |

---

## Latest IRR output

Latest run produced:

| Scenario | Exit Annual EBITDA | Exit Multiple | Exit Equity Value | IRR |
|---|---:|---:|---:|---:|
| Bear | ~$131.1B | 23.44x | ~$3.04T | -7.14% |
| Base | ~$226.2B | 27.57x | ~$6.20T | 7.12% |
| Bull | ~$321.1B | 31.71x | ~$10.14T | 18.21% |

Interpretation:

- Bear case shows downside if EBITDA underperforms and multiple compresses.
- Base case gives a mature public-equity-like return profile.
- Bull case shows strong upside if EBITDA growth and valuation multiple both improve.

The base-case IRR of ~7.1% is directionally sensible for a large mature compounder like Apple.

---

## Key assumptions

### Current mode: public-market proxy analysis

The current IRR engine uses:

```text
entry equity value = current market cap from yfinance
entry enterprise value = current enterprise value from yfinance
exit multiple = current EV/EBITDA multiple with bear/base/bull adjustments
```

This is useful for sanity-checking the model using Apple as a public-market proxy.

### Future PE-prototype mode

For the actual PE Value Creation Copilot story, we should add deal metadata:

```text
entry EBITDA
entry EV/EBITDA multiple
entry enterprise value
entry net debt
entry equity value
holding period
IC target IRR
```

That will allow the system to answer:

```text
Is the deal still tracking toward the IC return target?
```

instead of only:

```text
What is the return from buying AAPL at current public market value?
```

---

## Files created / updated

```text
app/data_sources/edgar.py
app/data_sources/fred.py
app/data_sources/market_data.py
app/ingestion/build_feature_matrix.py
app/quant/forecast_engine.py
app/quant/irr_engine.py
scripts/test_data_sources.py
scripts/test_prophet.py
scripts/run_week1_pipeline.py
```

Generated outputs:

```text
data/raw/edgar/0000320193_kpis.csv
data/features/demo_feature_matrix.csv
data/features/demo_model_feature_matrix.csv
data/processed/stl_components.csv
data/processed/quant_ebitda_forecast.csv
data/processed/irr_scenarios.csv
```

---

## How to run

From project root:

```powershell
Remove-Item Env:\UV_NATIVE_TLS -ErrorAction SilentlyContinue
$env:UV_SYSTEM_CERTS="true"
uv run python scripts\run_week1_pipeline.py
```

Verify forecast output:

```powershell
uv run python -c "import pandas as pd; df=pd.read_csv('data/processed/quant_ebitda_forecast.csv'); print(df); print('Rows:', len(df)); print('Model counts:', df['model_count'].unique())"
```

Verify IRR output:

```powershell
uv run python -c "import pandas as pd; print(pd.read_csv('data/processed/irr_scenarios.csv')[['scenario','exit_annual_ebitda','exit_multiple','exit_equity_value','irr_percent']])"
```

---

## Week 1 status

```text
[✅] EDGAR XBRL pipeline
[✅] FRED macro integration
[✅] yfinance market valuation input
[✅] model-ready feature matrix
[✅] STL decomposition
[✅] Holt-Winters forecast
[✅] SARIMA forecast
[✅] SARIMAX macro forecast
[✅] Prophet macro forecast
[✅] ensemble P10/P50/P90 forward curve
[✅] IRR scenario table
[✅] IRR sanity correction using annual terminal EBITDA
```

Week 1 Data + Quant Foundation is complete.

---

## Next steps

### Immediate smoke testing

Run the same pipeline on additional companies to ensure the data-source and Quant Agent logic generalizes.

Suggested smoke-test companies:

| Company | Ticker | CIK |
|---|---|---|
| Microsoft | MSFT | 0000789019 |
| Alphabet | GOOGL | 0001652044 |
| Amazon | AMZN | 0001018724 |
| Meta | META | 0001326801 |
| NVIDIA | NVDA | 0001045810 |

### Next development milestone

After smoke testing:

```text
Peer Benchmarking Agent
```

Expected role:

```text
identify sector/SIC peers
pull peer financials from EDGAR
calculate sector medians
compare company vs sector on revenue growth, EBITDA margin, leverage
produce peer_composite and gap_score
```
