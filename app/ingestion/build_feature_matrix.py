import os
from typing import Optional

import pandas as pd

from app.data_sources.edgar import fetch_kpi_wide
from app.data_sources.fred import fetch_macro_data


def build_feature_matrix(
    cik: str,
    include_macro: bool = True,
    output_path: Optional[str] = None,
) -> pd.DataFrame:
    kpi_df = fetch_kpi_wide(cik)

    if kpi_df.empty:
        raise ValueError(f"No EDGAR KPI data found for CIK={cik}")

    kpi_df["period_end"] = pd.to_datetime(kpi_df["period_end"])
    kpi_df = kpi_df.sort_values("period_end")

    if include_macro:
        try:
            macro_df = fetch_macro_data()
            macro_df["period_end"] = pd.to_datetime(macro_df["period_end"])
            macro_df = macro_df.sort_values("period_end")

            feature_df = pd.merge_asof(
                kpi_df,
                macro_df,
                on="period_end",
                direction="backward",
            )
        except Exception as exc:
            print(f"[WARN] Macro data skipped: {exc}")
            feature_df = kpi_df
    else:
        feature_df = kpi_df

    if output_path:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        feature_df.to_csv(output_path, index=False)

    return feature_df


def build_model_feature_matrix(
    cik: str,
    include_macro: bool = True,
    output_path: Optional[str] = None,
) -> pd.DataFrame:
    """
    Model-ready feature matrix for Quant Agent.

    Raw EDGAR data can contain missing quarter values because some fiscal-year
    records are annual/cumulative rather than clean quarterly facts.

    This function keeps raw features separate and creates a clean modeling copy.
    """

    df = build_feature_matrix(
        cik=cik,
        include_macro=include_macro,
        output_path=None,
    )

    df = df.sort_values("period_end").reset_index(drop=True)

    model_cols = [
        "revenue",
        "operating_income",
        "net_income",
        "gross_profit",
        "arr_proxy",
        "ebitda_proxy",
        "adjusted_ebitda",
        "working_capital",
        "net_debt",
        "fed_funds_rate",
        "cpi",
        "credit_spread",
    ]

    for col in model_cols:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
            df[col] = df[col].interpolate(method="linear")
            df[col] = df[col].ffill()
            df[col] = df[col].bfill()

    if output_path:
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        df.to_csv(output_path, index=False)

    return df


if __name__ == "__main__":
    df = build_feature_matrix(
        cik=os.getenv("DEFAULT_CIK", "0000320193"),
        include_macro=bool(os.getenv("FRED_API_KEY")),
        output_path="data/features/demo_feature_matrix.csv",
    )
    print(df.tail())
    print(f"Rows: {len(df)}")