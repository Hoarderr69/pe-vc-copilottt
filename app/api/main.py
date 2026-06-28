import os
from typing import Any

import numpy as np
import pandas as pd
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from app.api.vcp_routes import router as vcp_router
from app.api.report_routes import router as report_router
from app.api.ingest_routes import router as ingest_router
from app.data_sources.edgar import fetch_kpi_wide
from app.data_sources.fred import fetch_macro_data
from app.data_sources.market_data import fetch_market_snapshot
from app.ingestion.build_feature_matrix import build_feature_matrix

load_dotenv()

app = FastAPI(title="PE Value Creation Copilot API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5174",
        "http://127.0.0.1:5174",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(vcp_router)
app.include_router(report_router)
app.include_router(ingest_router)


def dataframe_to_json_records(df: pd.DataFrame, tail: int | None = None) -> list[dict[str, Any]]:
    """
    Convert DataFrame to JSON-safe records:
    - NaN -> None
    - inf/-inf -> None
    - Timestamp -> ISO date string
    """

    if df is None or df.empty:
        return []

    safe_df = df.copy()

    if tail:
        safe_df = safe_df.tail(tail)

    # Convert datetime columns to string before object conversion
    for col in safe_df.columns:
        if pd.api.types.is_datetime64_any_dtype(safe_df[col]):
            safe_df[col] = safe_df[col].dt.strftime("%Y-%m-%d")

    # Replace inf values first
    safe_df = safe_df.replace([np.inf, -np.inf], np.nan)

    # Convert all columns to object so None can actually replace NaN
    safe_df = safe_df.astype(object)

    # Replace NaN/NaT with None
    safe_df = safe_df.where(pd.notna(safe_df), None)

    return safe_df.to_dict(orient="records")


def sanitize_dict(obj: dict[str, Any]) -> dict[str, Any]:
    """
    Clean regular dictionaries that may contain NaN/inf values.
    Useful for yfinance output.
    """

    cleaned = {}

    for key, value in obj.items():
        if isinstance(value, float):
            if np.isnan(value) or np.isinf(value):
                cleaned[key] = None
            else:
                cleaned[key] = value
        else:
            cleaned[key] = value

    return cleaned


@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": "PE Value Creation Copilot API",
    }


@app.get("/api/portfolio")
def get_portfolio():
    return {
        "companies": [
            {
                "id": "demo-apple",
                "name": "Apple Inc.",
                "ticker": "AAPL",
                "cik": "0000320193",
                "status": "ready_for_ingestion",
            }
        ]
    }


@app.get("/api/data/edgar/{cik}")
def get_edgar_kpis(cik: str):
    try:
        df = fetch_kpi_wide(cik)

        return {
            "cik": cik,
            "rows": int(len(df)),
            "columns": list(df.columns),
            "data": dataframe_to_json_records(df, tail=40),
        }

    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/data/macro")
def get_macro():
    try:
        df = fetch_macro_data()

        return {
            "rows": int(len(df)),
            "columns": list(df.columns),
            "data": dataframe_to_json_records(df, tail=40),
        }

    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/data/market/{ticker}")
def get_market_data(ticker: str):
    try:
        snapshot = fetch_market_snapshot(ticker)
        return sanitize_dict(snapshot)

    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/data/features/{cik}")
def get_feature_matrix(cik: str):
    try:
        include_macro = bool(os.getenv("FRED_API_KEY"))

        df = build_feature_matrix(
            cik=cik,
            include_macro=include_macro,
        )

        return {
            "cik": cik,
            "rows": int(len(df)),
            "columns": list(df.columns),
            "data": dataframe_to_json_records(df, tail=40),
        }

    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))