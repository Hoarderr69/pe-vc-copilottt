"""
Cadence normalization for the quant forecast engine's model feature matrix.

forecast_engine.py assumes every row of a model feature matrix is one quarter
(seasonal_periods=4, future dates stepped at freq="QE"). Several ingestion
sources hand it monthly data instead (private portco CSVs, PDF-extracted
financials default to period_type="month"). Feeding monthly rows through a
quarterly-seasonal model silently mislabels monthly EBITDA as quarterly EBITDA,
which understates annualized terminal EBITDA by ~3-4x downstream in vcp_irr.py.

This module detects the actual cadence of a feature matrix from its
period_end spacing and resamples it to quarterly when it isn't already, using
flow-vs-stock-aware aggregation (sum for P&L/cash-flow metrics, last-value for
balance-sheet snapshots, recomputed margins).

Only the model feature matrix should be resampled. Raw feature matrices and
KPI records stay at native cadence — vcp_drift, peer_benchmarking, the board
pack's monthly EBITDA chart, and vcp_irr's trailing-12-month FCF sweep all
depend on the original monthly granularity.
"""

from __future__ import annotations

from typing import Iterable, Optional, Tuple

import pandas as pd

# Balance-sheet / point-in-time metrics: aggregate by taking the last value in
# the quarter, never sum.
STOCK_COLUMNS = {
    "cash",
    "net_debt",
    "debt",
    "working_capital",
    "ar",
    "accounts_receivable",
    "inventory",
    "ap",
    "accounts_payable",
}

# Cadence thresholds, in median days between consecutive period_end values.
_MONTHLY_MAX_DAYS = 45
_QUARTERLY_MIN_DAYS = 75
_QUARTERLY_MAX_DAYS = 135

# period_type values as written by the adapters, mapped to periods per year.
_PERIOD_TYPE_FREQUENCY = {
    "month": 12,
    "monthly": 12,
    "quarter": 4,
    "quarterly": 4,
    "year": 1,
    "annual": 1,
    "fy": 1,
}


def _median_period_days(dates: pd.Series) -> Optional[float]:
    sorted_dates = pd.to_datetime(dates).dropna().sort_values()
    diffs = sorted_dates.diff().dropna().dt.days
    if diffs.empty:
        return None
    return float(diffs.median())


def infer_periods_per_year(
    records_or_df,
    date_col: str = "period_end",
    period_type_col: str = "period_type",
    default: int = 12,
) -> int:
    """
    How many periods make up a year for this dataset: 12 (monthly), 4 (quarterly)
    or 1 (annual). Every consumer that annualizes a per-period flow value
    (revenue, EBITDA, FCF) must scale by this instead of assuming monthly ×12 —
    EDGAR-sourced companies report quarterly, private portcos report monthly.

    Resolution order: explicit period_type on the records → median period_end
    spacing → ``default``.
    """
    df = records_or_df if isinstance(records_or_df, pd.DataFrame) else pd.DataFrame(records_or_df)
    if df.empty:
        return default

    if period_type_col in df.columns:
        declared = (
            df[period_type_col].dropna().astype(str).str.strip().str.lower()
        )
        if not declared.empty:
            freq = _PERIOD_TYPE_FREQUENCY.get(declared.mode().iloc[0])
            if freq is not None:
                return freq

    if date_col in df.columns and len(df) >= 2:
        median_days = _median_period_days(df[date_col])
        if median_days is not None:
            if median_days <= _MONTHLY_MAX_DAYS:
                return 12
            if median_days <= _QUARTERLY_MAX_DAYS:
                return 4
            return 1

    return default


def needs_quarterly_resample(df: pd.DataFrame, date_col: str = "period_end") -> bool:
    """True when period_end spacing looks monthly (or finer) rather than quarterly+."""
    if date_col not in df.columns or len(df) < 2:
        return False
    median_days = _median_period_days(df[date_col])
    if median_days is None:
        return False
    return median_days <= _MONTHLY_MAX_DAYS


def _is_margin_like(col: str) -> bool:
    lowered = col.lower()
    return any(token in lowered for token in ("margin", "ratio", "_rate", "multiple"))


def resample_to_quarterly(
    df: pd.DataFrame,
    date_col: str = "period_end",
    stock_columns: Iterable[str] = STOCK_COLUMNS,
) -> Tuple[pd.DataFrame, bool]:
    """
    Resample a feature matrix to quarterly cadence if it isn't already.

    Returns (resampled_df, was_resampled). If the input is already quarterly
    (or sparser, e.g. annual), or too short to infer cadence, returns the
    input unchanged with was_resampled=False.

    Aggregation rules per column:
    - stock_columns (cash, net_debt, working_capital, ...): last value in the quarter
    - columns matching margin/ratio/rate/multiple: recomputed post-aggregation
      where a numerator/denominator pair is derivable, else mean
    - other numeric columns (revenue, ebitda, capex, free_cash_flow, ...): summed
    - non-numeric columns: last value in the quarter
    """
    if not needs_quarterly_resample(df, date_col=date_col):
        return df, False

    work = df.copy()
    work[date_col] = pd.to_datetime(work[date_col])
    work = work.sort_values(date_col)
    work["_quarter"] = work[date_col].dt.to_period("Q")

    stock_cols = set(stock_columns)
    agg_spec = {}
    margin_cols = []

    for col in work.columns:
        if col in (date_col, "_quarter"):
            continue
        if _is_margin_like(col):
            margin_cols.append(col)
            agg_spec[col] = "mean"
        elif col in stock_cols:
            agg_spec[col] = "last"
        elif pd.api.types.is_numeric_dtype(work[col]):
            agg_spec[col] = "sum"
        else:
            agg_spec[col] = "last"

    resampled = work.groupby("_quarter", as_index=False).agg(agg_spec)
    resampled[date_col] = resampled["_quarter"].dt.to_timestamp("Q")
    resampled = resampled.drop(columns="_quarter")

    # Recompute EBITDA-style margins from the now-quarterly flow values rather
    # than averaging monthly margin percentages (averaging understates margin
    # drift and is internally inconsistent with the summed revenue/EBITDA).
    ebitda_col = next(
        (c for c in ("adjusted_ebitda", "ebitda_proxy", "ebitda") if c in resampled.columns),
        None,
    )
    if ebitda_col and "revenue" in resampled.columns:
        for margin_col in margin_cols:
            if "ebitda" in margin_col.lower():
                resampled[margin_col] = (
                    resampled[ebitda_col] / resampled["revenue"].replace(0, pd.NA)
                ).round(4)

    if "period_type" in resampled.columns:
        resampled["period_type"] = "quarter"

    resampled = resampled.sort_values(date_col).reset_index(drop=True)
    return resampled, True
