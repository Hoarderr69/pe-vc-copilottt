import os
import sys
from pathlib import Path
from dataclasses import replace

import pandas as pd
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.ingestion.build_feature_matrix import build_feature_matrix, build_model_feature_matrix
from app.quant.forecast_engine import ForecastConfig, run_quant_forecast
from app.quant.irr_engine import IRRConfig, build_irr_scenarios

load_dotenv()

SMOKE_COMPANIES = [
    {"company": "Microsoft", "ticker": "MSFT", "cik": "0000789019"},
    {"company": "Alphabet", "ticker": "GOOGL", "cik": "0001652044"},
    {"company": "Amazon", "ticker": "AMZN", "cik": "0001018724"},
    {"company": "Meta", "ticker": "META", "cik": "0001326801"},
    {"company": "NVIDIA", "ticker": "NVDA", "cik": "0001045810"},
]


def safe_name(ticker: str) -> str:
    return ticker.lower().replace(".", "_").replace("-", "_")


def run_company_smoke(company: dict) -> dict:
    company_name = company["company"]
    ticker = company["ticker"]
    cik = company["cik"]
    slug = safe_name(ticker)

    print("\n" + "=" * 80)
    print(f"SMOKE TEST: {company_name} | {ticker} | {cik}")
    print("=" * 80)

    include_macro = bool(os.getenv("FRED_API_KEY"))

    raw_feature_path = f"data/features/{slug}_feature_matrix.csv"
    model_feature_path = f"data/features/{slug}_model_feature_matrix.csv"
    stl_path = f"data/processed/{slug}_stl_components.csv"
    forecast_path = f"data/processed/{slug}_quant_ebitda_forecast.csv"
    irr_path = f"data/processed/{slug}_irr_scenarios.csv"

    status = {
        "company": company_name,
        "ticker": ticker,
        "cik": cik,
        "status": "started",
        "raw_rows": None,
        "model_rows": None,
        "forecast_rows": None,
        "forecast_model_counts": None,
        "base_irr_percent": None,
        "error": None,
    }

    try:
        raw_df = build_feature_matrix(
            cik=cik,
            include_macro=include_macro,
            output_path=raw_feature_path,
        )
        status["raw_rows"] = len(raw_df)
        print(f"[OK] Raw feature matrix: {raw_feature_path} | rows={len(raw_df)}")

        model_df = build_model_feature_matrix(
            cik=cik,
            include_macro=include_macro,
            output_path=model_feature_path,
        )
        status["model_rows"] = len(model_df)
        print(f"[OK] Model feature matrix: {model_feature_path} | rows={len(model_df)}")

        forecast_config = ForecastConfig(
            feature_path=model_feature_path,
            target_col="ebitda_proxy",
            periods=20,
            output_path=forecast_path,
            stl_output_path=stl_path,
        )
        forecast_df = run_quant_forecast(forecast_config)
        status["forecast_rows"] = len(forecast_df)
        status["forecast_model_counts"] = ",".join(
            str(x) for x in sorted(forecast_df["model_count"].dropna().unique())
        )
        print(f"[OK] Forecast: {forecast_path} | rows={len(forecast_df)}")

        irr_config = IRRConfig(
            forecast_path=forecast_path,
            feature_path=model_feature_path,
            ticker=ticker,
            output_path=irr_path,
            holding_period_years=5.0,
        )
        irr_df = build_irr_scenarios(irr_config)
        print(f"[OK] IRR scenarios: {irr_path}")

        base_row = irr_df[irr_df["scenario"] == "base"]
        if not base_row.empty:
            status["base_irr_percent"] = float(base_row.iloc[0]["irr_percent"])

        status["status"] = "passed"

    except Exception as exc:
        status["status"] = "failed"
        status["error"] = str(exc)
        print(f"[FAIL] {ticker}: {exc}")

    return status


def main():
    print("\n========== MULTI-COMPANY WEEK 1 SMOKE TEST ==========")
    print(f"Companies: {', '.join(c['ticker'] for c in SMOKE_COMPANIES)}")

    results = []
    for company in SMOKE_COMPANIES:
        results.append(run_company_smoke(company))

    summary_df = pd.DataFrame(results)
    output_path = PROJECT_ROOT / "data" / "processed" / "smoke_test_summary.csv"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    summary_df.to_csv(output_path, index=False)

    print("\n========== SMOKE TEST SUMMARY ==========")
    print(summary_df)
    print(f"\nSaved: {output_path}")

    failed = summary_df[summary_df["status"] == "failed"]
    if not failed.empty:
        print("\nSome companies failed. Review the 'error' column in smoke_test_summary.csv.")
        sys.exit(1)

    print("\nAll smoke tests passed.")


if __name__ == "__main__":
    main()
