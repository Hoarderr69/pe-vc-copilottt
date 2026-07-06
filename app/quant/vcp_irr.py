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


def _ensure_forecast(company_id: str, refresh: bool = False) -> tuple[pd.DataFrame, str]:
    """
    Return the P10/P50/P90 EBITDA forecast for a company, caching to disk, plus
    the target column the forecast was fit on ("adjusted_ebitda" or the
    GAAP-proxy fallback "ebitda_proxy") — callers need this to tell a genuine
    EBITDA basis mismatch apart from ordinary forecast decay.

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
    # Forecast adjusted EBITDA when the source discloses it — that matches the
    # deal's entry-multiple basis. ebitda_proxy (GAAP operating income) is the
    # fallback for issuers without an adjusted figure.
    feature_cols = pd.read_csv(feature_path, nrows=0).columns
    target_col = "adjusted_ebitda" if "adjusted_ebitda" in feature_cols else "ebitda_proxy"
    forecast_path = FORECAST_DIR / f"{company_id}_quant_ebitda_forecast.csv"
    if forecast_path.exists() and not refresh:
        return pd.read_csv(forecast_path), target_col
    config = ForecastConfig(
        feature_path=str(feature_path),
        target_col=target_col,
        periods=20,
        output_path=str(forecast_path),
        stl_output_path=str(FORECAST_DIR / f"{company_id}_stl_components.csv"),
    )
    return run_quant_forecast(config), target_col


def _trailing_year_sum(kpi_records: List[Dict], fields: tuple[str, ...]) -> Optional[float]:
    """Sum a flow metric over the records inside the trailing 365 days.

    Date-window based so it is correct at any reporting cadence (monthly private
    CSVs, quarterly EDGAR filings) — never "last 12 rows".
    """
    dated = [
        (pd.Timestamp(r["period_end"]), r)
        for r in kpi_records
        if r.get("period_end") and any(r.get(f) is not None for f in fields)
    ]
    if not dated:
        return None
    latest = max(d for d, _ in dated)
    window = [r for d, r in dated if d > latest - pd.Timedelta(days=365)]
    total = 0.0
    for r in window:
        for f in fields:
            if r.get(f) is not None:
                total += float(r[f])
                break
    return total


def _annual_fcf(kpi_records: List[Dict]) -> float:
    """Latest annual free-cash-flow run-rate (trailing 365 days), for debt paydown."""
    total = _trailing_year_sum(kpi_records, ("free_cash_flow",))
    return float(total) if total is not None else 0.0


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

    # Unit-consistency guard: DealMetadata monetary fields are absolute currency
    # units, same as KPI records. A deal file denominated in millions makes every
    # exit-equity and MOIC figure off by ~1e6 — refuse loudly rather than render it.
    trailing_revenue = _trailing_year_sum(kpi_records, ("revenue",))
    if (
        trailing_revenue is not None
        and trailing_revenue > 0
        and deal.entry_enterprise_value > 0
        and deal.entry_enterprise_value < trailing_revenue / 1000
    ):
        raise ValueError(
            f"Deal metadata for {company_id} looks denominated in millions "
            f"(entry EV {deal.entry_enterprise_value:,.0f} vs trailing revenue "
            f"{trailing_revenue:,.0f}). DealMetadata fields must be absolute "
            "currency units — rescale data/raw/deal_metadata/"
            f"{company_id}.json."
        )

    forecast, forecast_target_col = _ensure_forecast(company_id)
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

    # Equity-at-risk: base-case exit equity is zero or negative — the model
    # projects that net debt exceeds EBITDA*multiple at exit. This is a
    # first-class signal, not a missing-data artefact: surface it explicitly
    # so the UI can render an alert rather than a blank "—" in the IRR grid.
    base_exit_equity = scenarios[1]["exit_equity"]
    equity_at_risk = base_exit_equity <= 0

    # Net debt / trailing EBITDA leverage ratio for the alert context.
    trailing_annual_ebitda = _trailing_year_sum(
        kpi_records, ("adjusted_ebitda", "ebitda_proxy")
    )
    nd_ebitda = (
        round(deal.entry_net_debt / trailing_annual_ebitda, 1)
        if trailing_annual_ebitda is not None and trailing_annual_ebitda > 0 else None
    )

    # Basis guard: the entry multiple was struck on the deal's entry EBITDA
    # basis (adjusted / non-GAAP). This is only a basis-comparability problem —
    # not distress — when the forecast itself had to fall back to the GAAP
    # operating-income proxy (no adjusted_ebitda disclosed). If the forecast
    # was fit on adjusted_ebitda (the same basis as entry) and still decays to
    # zero, that is real operating deterioration, not a basis artefact — it
    # must flow through to the equity-at-risk alarm below, not be suppressed.
    basis_mismatch = (
        forecast_target_col == "ebitda_proxy"
        and deal.entry_ebitda is not None
        and deal.entry_ebitda > 0
        and exit_ebitda["base"] <= 0
    )
    basis_warning = (
        "Entry EBITDA basis is positive but the quant forecast's EBITDA proxy is "
        "negative — the forecast basis (GAAP operating-income proxy) differs from "
        "the deal's entry EBITDA basis. IRR scenarios are not comparable; ingest an "
        "adjusted-EBITDA series to enable projection."
    ) if basis_mismatch else None

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
        "basis_mismatch": basis_mismatch,
        "basis_warning": basis_warning,
        # A negative-basis forecast is a data-basis problem, not evidence of
        # distress — don't raise the equity-at-risk alarm on top of it.
        "equity_at_risk": equity_at_risk and not basis_mismatch,
        "equity_at_risk_detail": {
            "base_exit_equity": round(base_exit_equity, 2),
            "entry_net_debt": deal.entry_net_debt,
            "terminal_ebitda_base": round(exit_ebitda["base"], 2),
            "nd_ebitda_trailing": nd_ebitda,
        } if equity_at_risk and not basis_mismatch else None,
        "scenario_detail": scenarios,
        # provenance / assumptions
        "entry_equity": entry_equity,
        "entry_ebitda": deal.entry_ebitda,
        "entry_net_debt": deal.entry_net_debt,
        "entry_multiple": base_multiple,
        "base_hold_years": base_hold,
        "annual_fcf_sweep": round(annual_fcf, 2),
        "terminal_ebitda": {k: round(v, 2) for k, v in exit_ebitda.items()},
        # quarterly P10/P50/P90 EBITDA path from the quant forecast ensemble — feeds
        # the report's EBITDA Forward Curve slide so it shows the same numbers as
        # this endpoint, not a separately-invented projection.
        "forecast_quarterly": [
            {
                "period_end": str(row["period_end"])[:10],
                "p10": round(float(row["p10"]), 2),
                "p50": round(float(row["p50"]), 2),
                "p90": round(float(row["p90"]), 2),
            }
            for row in forecast.to_dict(orient="records")
        ],
        "basis": "quant_forecast_p10_p50_p90",
    }
