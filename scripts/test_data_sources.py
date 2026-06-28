import os

from dotenv import load_dotenv

from app.data_sources.edgar import fetch_kpi_wide, save_edgar_kpis
from app.data_sources.market_data import fetch_market_snapshot
from app.ingestion.build_feature_matrix import build_feature_matrix

load_dotenv()

DEFAULT_CIK = os.getenv("DEFAULT_CIK", "0000320193")
DEFAULT_TICKER = os.getenv("DEFAULT_TICKER", "AAPL")


def test_edgar():
    print("\n========== EDGAR TEST ==========")
    df = fetch_kpi_wide(DEFAULT_CIK)

    print(df.tail())
    print(f"EDGAR rows: {len(df)}")
    print(f"EDGAR columns: {list(df.columns)}")

    output_path = f"data/raw/edgar/{DEFAULT_CIK}_kpis.csv"
    save_edgar_kpis(DEFAULT_CIK, output_path)
    print(f"Saved EDGAR CSV: {output_path}")


def test_market_data():
    print("\n========== MARKET DATA TEST ==========")

    try:
        snapshot = fetch_market_snapshot(DEFAULT_TICKER)

        for key, value in snapshot.items():
            if key == "warning":
                print(f"{key}: {str(value)[:300]}...")
            else:
                print(f"{key}: {value}")

    except Exception as exc:
        print(f"[WARN] Market data test failed but pipeline will continue: {exc}")


def test_feature_matrix():
    print("\n========== FEATURE MATRIX TEST ==========")
    include_macro = bool(os.getenv("FRED_API_KEY"))

    df = build_feature_matrix(
        cik=DEFAULT_CIK,
        include_macro=include_macro,
        output_path="data/features/demo_feature_matrix.csv",
    )

    print(df.tail())
    print(f"Feature matrix rows: {len(df)}")
    print("Saved feature matrix: data/features/demo_feature_matrix.csv")


if __name__ == "__main__":
    test_edgar()
    test_market_data()
    test_feature_matrix()

    print("\nAll available data-source tests completed.")