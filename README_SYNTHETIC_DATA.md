# Synthetic Data Patch — PE Value Creation Copilot

This patch adds a deterministic synthetic data generator for the new VCP-first architecture.

## Files added

```text
scripts/generate_synthetic_portco_data.py
```

## What it generates

```text
data/raw/synthetic_portcos/<company_id>/<company_id>_monthly_financials.csv
data/raw/synthetic_portcos/<company_id>/<company_id>_monthly_financials.xlsx
data/raw/ic_memos/<company_id>_ic_memo.md
data/processed/synthetic_vcp_milestones_seed.json
data/processed/synthetic_source_manifest.json
```

## Synthetic companies

```text
Company A — B2B SaaS
Company B — Industrial Manufacturing
Company C — Healthcare Services
```

## Run

```powershell
uv run python scripts\generate_synthetic_portco_data.py
```

## Purpose

This supports the two-path architecture:

```text
Path 1: IC memo / VCP ingestion — once at deal close
Path 2: Financial data ingestion — recurring every period
```

The generated financial data deliberately includes margin compression after Month 13 so the VCP Drift and Alert layers have a signal to detect.
