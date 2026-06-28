import os
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.ingestion.build_feature_matrix import (
    build_feature_matrix,
    build_model_feature_matrix,
)
from app.quant.forecast_engine import ForecastConfig, run_quant_forecast
from app.quant.irr_engine import IRRConfig, build_irr_scenarios

load_dotenv()

DEFAULT_CIK = os.getenv("DEFAULT_CIK", "0000320193")


def main():
    print("\n========== WEEK 1 PIPELINE ==========")
    print(f"CIK: {DEFAULT_CIK}")

    include_macro = bool(os.getenv("FRED_API_KEY"))

    print("\n[1/3] Building raw feature matrix...")
    raw_df = build_feature_matrix(
        cik=DEFAULT_CIK,
        include_macro=include_macro,
        output_path="data/features/demo_feature_matrix.csv",
    )
    print(f"Raw feature matrix rows: {len(raw_df)}")
    print("Saved: data/features/demo_feature_matrix.csv")

    print("\n[2/3] Building model-ready feature matrix...")
    model_df = build_model_feature_matrix(
        cik=DEFAULT_CIK,
        include_macro=include_macro,
        output_path="data/features/demo_model_feature_matrix.csv",
    )
    print(f"Model feature matrix rows: {len(model_df)}")
    print("Saved: data/features/demo_model_feature_matrix.csv")

    print("\n[3/4] Running Quant Agent forecast engine...")
    config = ForecastConfig(
        feature_path="data/features/demo_model_feature_matrix.csv",
        target_col="ebitda_proxy",
        periods=20,
        output_path="data/processed/quant_ebitda_forecast.csv",
        stl_output_path="data/processed/stl_components.csv",
    )

    forecast_df = run_quant_forecast(config)

    print("\n[4/4] Building IRR scenario table...")

    irr_config = IRRConfig(
        forecast_path="data/processed/quant_ebitda_forecast.csv",
        feature_path="data/features/demo_model_feature_matrix.csv",
        ticker=os.getenv("DEFAULT_TICKER", "AAPL"),
        output_path="data/processed/irr_scenarios.csv",
        holding_period_years=5.0,
    )

    irr_df = build_irr_scenarios(irr_config)

    print("\n========== WEEK 1 OUTPUTS ==========")
    print("Saved: data/features/demo_feature_matrix.csv")
    print("Saved: data/features/demo_model_feature_matrix.csv")
    print("Saved: data/processed/stl_components.csv")
    print("Saved: data/processed/quant_ebitda_forecast.csv")
    print("Saved: data/processed/irr_scenarios.csv")
    
    print("\nLatest forecast rows:")
    print(forecast_df.tail())

    print("\nIRR scenarios:")
    print(irr_df[["scenario", "exit_annual_ebitda", "exit_multiple", "exit_equity_value", "irr_percent"]])


if __name__ == "__main__":
    main()