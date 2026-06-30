"""
VCP IRR view — projections from the quant engine, benchmarked against deal targets.

Architecture (per PE_VCP_Copilot_Final_Project.md):

* The IRR **scenarios are projections** and therefore come ONLY from the quant
  forecast engine: exit EBITDA = P10/P50/P90 of the forecast at the exit horizon.
* **Entry equity is fixed at deal close** and comes from the DealMetadata store
  (the IC-memo Sources & Uses table) — it is the IRR denominator, never re-derived.
* **VCP targets are ground truth for drift only** and never feed this projection.
  The single VCP-derived number here is the IC-underwritten IRR target, shown purely
  as the benchmark the projected base case is measured against.

Outputs:
* ``scenarios``      — Bear/Base/Bull = IRR on P10/P50/P90 exit EBITDA at base terms.
* ``matrix``         — exit-multiple × hold-year sensitivity grid on the P50 forecast.
* ``ic_underwritten``— DealMetadata.ic_target_irr (the underwritten benchmark).
"""

from __future__ import annotations

import math
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from app.quant.forecast_engine import ForecastConfig, run_quant_forecast
from app.store.deal_store import DealMetadata, DealStore

PROJECT_ROOT = Path(__file__).resolve().parents[2]
FEATURES_DIR = PROJECT_ROOT / "data" / "features"
FORECAST_DIR = PROJECT_ROOT / "data" / "processed"

EXIT_MULTIPLES = [8.0, 10.0, 12.0, 14.0, 16.0]
HOLD_YEARS = [3.0, 4.0, 5.0, 6.0]


def _irr(entry_equity: float, exit_equity: float, years: float) -> Optional[float]:
    """Annualized equity IRR. None when undefined (non-positive equity/horizon)."""
    if entry_equity <= 0 or exit_equity <= 0 or years <= 0:
        return None
    irr = (exit_equity / entry_equity) ** (1.0 / years) - 1.0
    return None if math.isnan(irr) or math.isinf(irr) else irr


def _ensure_forecast(company_id: str, refresh: bool = False) -> pd.DataFrame:
    """
    Return the P10/P50/P90 EBITDA forecast for a company, caching to disk.

    The ensemble (SARIMA/Prophet) is stochastic and slow, so we run it once and
    reuse the cached CSV on subsequent calls — this keeps the IRR endpoint fast and
    deterministic. Pass ``refresh=True`` to force a re-run.
    """
    feature_path = FEATURES_DIR / f"{company_id}_model_feature_matrix.csv"
    if not feature_path.exists():
        raise FileNotFoundError(
            f"No model feature matrix for {company_id}: {feature_path}. "
            "Run the KPI ingestion pipeline first."
        )
    forecast_path = FORECAST_DIR / f"{company_id}_quant_ebitda_forecast.csv"
    if forecast_path.exists() and not refresh:
        return pd.read_csv(forecast_path)
    config = ForecastConfig(
        feature_path=str(feature_path),
        target_col="ebitda_proxy",
        periods=20,
        output_path=str(forecast_path),
        stl_output_path=str(FORECAST_DIR / f"{company_id}_stl_components.csv"),
    )
    return run_quant_forecast(config)


def _annual_fcf(kpi_records: List[Dict]) -> float:
    """Latest annual free-cash-flow run-rate (sum of last 12 months), for debt paydown."""
    fcf = [r.get("free_cash_flow") for r in kpi_records if r.get("free_cash_flow") is not None]
    if not fcf:
        return 0.0
    return float(sum(fcf[-12:]))


def _exit_net_debt(deal: DealMetadata, annual_fcf: float, hold_years: float) -> float:
    """Debt-paydown curve: entry net debt swept down by free cash flow over the hold."""
    return max(0.0, deal.entry_net_debt - max(0.0, annual_fcf) * hold_years)


def build_vcp_irr(company_id: str, kpi_records: List[Dict]) -> Dict[str, Any]:
    """Quant-projected IRR scenarios + sensitivity matrix, benchmarked to deal targets."""
    deal = DealStore().load(company_id)
    if deal is None:
        raise FileNotFoundError(
            f"No deal metadata for {company_id}. Entry equity is required for IRR; "
            "seed data/raw/deal_metadata/{company_id}.json."
        )

    forecast = _ensure_forecast(company_id)
    if len(forecast) < 4:
        raise ValueError("Need at least 4 forecast periods to derive terminal annual EBITDA.")

    # Terminal annual EBITDA per scenario = sum of the final 4 forecast quarters.
    terminal = forecast.tail(4)
    exit_ebitda = {
        "bear": float(terminal["p10"].sum()),
        "base": float(terminal["p50"].sum()),
        "bull": float(terminal["p90"].sum()),
    }

    entry_equity = deal.entry_equity_value
    base_multiple = deal.entry_ev_multiple
    base_hold = deal.holding_period_years
    annual_fcf = _annual_fcf(kpi_records)

    # ── Bear / Base / Bull strip — projection at base exit multiple + base hold ──
    exit_nd_base = _exit_net_debt(deal, annual_fcf, base_hold)
    scenarios = []
    for name, pctl in (("bear", "p10"), ("base", "p50"), ("bull", "p90")):
        exit_equity = exit_ebitda[name] * base_multiple - exit_nd_base
        irr = _irr(entry_equity, exit_equity, base_hold)
        scenarios.append({
            "scenario": name,
            "forecast_percentile": pctl,
            "exit_ebitda": round(exit_ebitda[name], 2),
            "exit_multiple": base_multiple,
            "exit_equity": round(exit_equity, 2),
            "moic": round(exit_equity / entry_equity, 3) if entry_equity else None,
            "irr_percent": round(irr * 100, 1) if irr is not None else None,
        })

    base_irr = next((s["irr_percent"] for s in scenarios if s["scenario"] == "base"), None)
    ic_underwritten = round(deal.ic_target_irr * 100, 1) if deal.ic_target_irr is not None else None
    gap_bps = (
        round((base_irr - ic_underwritten) * 100)
        if base_irr is not None and ic_underwritten is not None
        else None
    )

    # ── Sensitivity matrix — exit multiple × hold year on the P50 forecast ──
    matrix_rows = []
    for em in EXIT_MULTIPLES:
        for hy in HOLD_YEARS:
            exit_equity = exit_ebitda["base"] * em - _exit_net_debt(deal, annual_fcf, hy)
            irr = _irr(entry_equity, exit_equity, hy)
            if irr is not None:
                matrix_rows.append({
                    "exit_multiple": em,
                    "hold_years": hy,
                    "irr_percent": round(irr * 100, 2),
                })

    return {
        "company_id": company_id,
        "currency": deal.currency,
        # projection basis
        "exit_multiples": EXIT_MULTIPLES,
        "hold_years": HOLD_YEARS,
        "scenarios": matrix_rows,  # matrix cells (kept key name for the existing grid)
        # bear/base/bull strip + benchmark
        "summary": {
            "bear_p10": scenarios[0]["irr_percent"],
            "base_p50": scenarios[1]["irr_percent"],
            "bull_p90": scenarios[2]["irr_percent"],
            "ic_underwritten": ic_underwritten,
            "gap_bps": gap_bps,
        },
        "scenario_detail": scenarios,
        # provenance / assumptions
        "entry_equity": entry_equity,
        "entry_multiple": base_multiple,
        "base_hold_years": base_hold,
        "annual_fcf_sweep": round(annual_fcf, 2),
        "terminal_ebitda": {k: round(v, 2) for k, v in exit_ebitda.items()},
        "basis": "quant_forecast_p10_p50_p90",
    }
