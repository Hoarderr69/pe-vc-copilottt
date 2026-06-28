import os
from typing import Dict, List

import pandas as pd
from dotenv import load_dotenv
from fredapi import Fred

load_dotenv()

FRED_API_KEY = os.getenv("FRED_API_KEY")

DEFAULT_SERIES = {
    "fed_funds_rate": "DFF",
    "cpi": "CPIAUCSL",
    "credit_spread": "BAA10Y",
}


def get_fred_client() -> Fred:
    if not FRED_API_KEY:
        raise ValueError(
            "FRED_API_KEY is missing. Add it to .env or skip FRED tests for now."
        )

    return Fred(api_key=FRED_API_KEY)


def fetch_fred_series(series_id: str) -> pd.DataFrame:
    fred = get_fred_client()
    series = fred.get_series(series_id)

    df = series.reset_index()
    df.columns = ["date", "value"]
    df["date"] = pd.to_datetime(df["date"])

    return df


def fetch_macro_data(
    series_map: Dict[str, str] = DEFAULT_SERIES,
    quarterly: bool = True,
) -> pd.DataFrame:
    frames: List[pd.DataFrame] = []

    for name, series_id in series_map.items():
        df = fetch_fred_series(series_id)
        df = df.rename(columns={"value": name})
        frames.append(df)

    macro = frames[0]

    for df in frames[1:]:
        macro = macro.merge(df, on="date", how="outer")

    macro = macro.sort_values("date")

    if quarterly:
        macro = (
            macro.set_index("date")
            .resample("QE")
            .last()
            .reset_index()
            .rename(columns={"date": "period_end"})
        )

    return macro


def save_macro_data(output_path: str) -> str:
    df = fetch_macro_data()
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    df.to_csv(output_path, index=False)
    return output_path


if __name__ == "__main__":
    df = fetch_macro_data()
    print(df.tail())
    print(f"Rows: {len(df)}")