import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

import numpy as np
import pandas as pd
from dotenv import load_dotenv

from app.data_sources.market_data import fetch_market_snapshot

load_dotenv()


@dataclass
class IRRConfig:
    forecast_path: str = "data/processed/quant_ebitda_forecast.csv"
    feature_path: str = "data/features/demo_model_feature_matrix.csv"
    ticker: str = os.getenv("DEFAULT_TICKER", "AAPL")
    output_path: str = "data/processed/irr_scenarios.csv"
    holding_period_years: float = 5.0

    # New: PE-deal mode metadata. If present, this overrides public market entry value.
    deal_metadata_path: Optional[str] = "data/raw/deal_metadata/demo_deal.json"

    # Multiple assumptions around market EV/EBITDA.
    bear_multiple_discount: float = 0.85
    bull_multiple_premium: float = 1.15

    # Used if yfinance multiple is unavailable.
    fallback_exit_multiple: float = float(os.getenv("DEFAULT_EXIT_EBITDA_MULTIPLE", "15.0"))


def _ensure_output_dir(path: str) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None

        value = float(value)

        if np.isnan(value) or np.isinf(value):
            return None

        return value
    except Exception:
        return None


def load_forecast(config: IRRConfig) -> pd.DataFrame:
    path = Path(config.forecast_path)

    if not path.exists():
        raise FileNotFoundError(
            f"Forecast file not found: {path}. "
            "Run: uv run python scripts\\run_week1_pipeline.py"
        )

    df = pd.read_csv(path)
    df["period_end"] = pd.to_datetime(df["period_end"])
    df = df.sort_values("period_end").reset_index(drop=True)

    required_cols = {"p10", "p50", "p90"}

    missing = required_cols - set(df.columns)
    if missing:
        raise ValueError(f"Forecast missing required columns: {missing}")

    return df


def load_latest_features(config: IRRConfig) -> Dict[str, Optional[float]]:
    path = Path(config.feature_path)

    if not path.exists():
        raise FileNotFoundError(
            f"Feature file not found: {path}. "
            "Run: uv run python scripts\\run_week1_pipeline.py"
        )

    df = pd.read_csv(path)
    df["period_end"] = pd.to_datetime(df["period_end"])
    df = df.sort_values("period_end").reset_index(drop=True)

    latest = df.iloc[-1]

    return {
        "latest_period_end": latest["period_end"],
        "latest_ebitda_proxy": _safe_float(latest.get("ebitda_proxy")),
        "latest_net_debt": _safe_float(latest.get("net_debt")),
        "latest_revenue": _safe_float(latest.get("revenue")),
    }


def load_deal_metadata(config: IRRConfig) -> Optional[Dict[str, Any]]:
    if not config.deal_metadata_path:
        return None

    path = Path(config.deal_metadata_path)
    if not path.exists():
        return None

    with path.open("r", encoding="utf-8") as f:
        deal = json.load(f)

    # Only use metadata if it matches the ticker/CIK context or is explicitly demo mode.
    deal_ticker = str(deal.get("ticker", "")).upper().strip()
    if deal_ticker and deal_ticker != config.ticker.upper().strip():
        return None

    return deal


def get_market_assumptions(config: IRRConfig) -> Dict[str, Optional[float]]:
    snapshot = fetch_market_snapshot(config.ticker)

    market_cap = _safe_float(snapshot.get("market_cap"))
    enterprise_value = _safe_float(snapshot.get("enterprise_value"))
    ev_to_ebitda = _safe_float(snapshot.get("enterprise_to_ebitda"))

    if ev_to_ebitda is None:
        ev_to_ebitda = config.fallback_exit_multiple

    return {
        "ticker": config.ticker,
        "company_name": snapshot.get("company_name"),
        "market_cap": market_cap,
        "enterprise_value": enterprise_value,
        "base_exit_multiple": ev_to_ebitda,
        "source": snapshot.get("source"),
        "is_fallback": snapshot.get("is_fallback"),
    }


def compute_irr(entry_equity_value: float, exit_equity_value: float, years: float) -> Optional[float]:
    if entry_equity_value <= 0 or exit_equity_value <= 0 or years <= 0:
        return None

    return (exit_equity_value / entry_equity_value) ** (1 / years) - 1


def classify_status(irr: Optional[float], moic: Optional[float], ic_target_irr: Optional[float]) -> str:
    if irr is None or moic is None:
        return "Review"

    if ic_target_irr is not None and irr >= ic_target_irr:
        return "Green"

    if moic < 1.0:
        return "Red"

    return "Amber"


def build_irr_scenarios(config: IRRConfig | None = None) -> pd.DataFrame:
    if config is None:
        config = IRRConfig()

    forecast_df = load_forecast(config)
    latest_features = load_latest_features(config)
    market = get_market_assumptions(config)
    deal = load_deal_metadata(config)

    if len(forecast_df) < 4:
        raise ValueError("Need at least 4 forecast quarters to compute terminal annual EBITDA.")

    # Terminal annual / LTM-style EBITDA = final 4 forecast quarters.
    terminal_window = forecast_df.tail(4).copy()
    terminal_period_start = terminal_window.iloc[0]["period_end"]
    terminal_period_end = terminal_window.iloc[-1]["period_end"]

    latest_net_debt = latest_features["latest_net_debt"] or 0.0
    latest_ebitda = latest_features["latest_ebitda_proxy"]
    base_exit_multiple = market["base_exit_multiple"] or config.fallback_exit_multiple

    # Default mode: public-market proxy.
    valuation_mode = "public_market_proxy"
    company_name = market["company_name"]
    entry_enterprise_value = market["enterprise_value"]
    entry_equity_value = market["market_cap"]
    entry_valuation_basis = "current_market_cap"
    holding_period_years = config.holding_period_years
    ic_target_irr = None
    ic_target_moic = None

    # PE-deal mode: use deal metadata when present.
    if deal is not None:
        valuation_mode = "pe_deal"
        company_name = deal.get("company_name") or company_name
        entry_enterprise_value = _safe_float(deal.get("entry_enterprise_value"))
        entry_equity_value = _safe_float(
            deal.get("entry_equity_value") or deal.get("sponsor_equity_contribution")
        )
        holding_period_years = _safe_float(deal.get("holding_period_years")) or holding_period_years
        ic_target_irr = _safe_float(deal.get("ic_target_irr"))
        ic_target_moic = _safe_float(deal.get("ic_target_moic"))
        entry_valuation_basis = "deal_metadata"

    # Fallback if yfinance/deal metadata entry EV is missing.
    if entry_enterprise_value is None and latest_ebitda is not None:
        # latest_ebitda is quarterly, so annualize it.
        entry_enterprise_value = latest_ebitda * 4 * base_exit_multiple

    if entry_equity_value is None and entry_enterprise_value is not None:
        entry_equity_value = entry_enterprise_value - latest_net_debt

    if entry_enterprise_value is None or entry_equity_value is None:
        raise ValueError(
            "Could not determine entry valuation. Need deal metadata, yfinance market_cap/enterprise_value, "
            "or latest EBITDA fallback."
        )

    scenarios = [
        {
            "scenario": "bear",
            "forecast_column": "p10",
            "exit_annual_ebitda": float(terminal_window["p10"].sum()),
            "exit_multiple": base_exit_multiple * config.bear_multiple_discount,
            "scenario_description": "p10 EBITDA + 15% multiple compression",
        },
        {
            "scenario": "base",
            "forecast_column": "p50",
            "exit_annual_ebitda": float(terminal_window["p50"].sum()),
            "exit_multiple": base_exit_multiple,
            "scenario_description": "p50 EBITDA + current market multiple",
        },
        {
            "scenario": "bull",
            "forecast_column": "p90",
            "exit_annual_ebitda": float(terminal_window["p90"].sum()),
            "exit_multiple": base_exit_multiple * config.bull_multiple_premium,
            "scenario_description": "p90 EBITDA + 15% multiple expansion",
        },
    ]

    rows = []

    for scenario in scenarios:
        exit_enterprise_value = scenario["exit_annual_ebitda"] * scenario["exit_multiple"]
        exit_equity_value = exit_enterprise_value - latest_net_debt
        moic = exit_equity_value / entry_equity_value if entry_equity_value else None

        irr = compute_irr(
            entry_equity_value=entry_equity_value,
            exit_equity_value=exit_equity_value,
            years=holding_period_years,
        )

        irr_gap_vs_ic = None
        if irr is not None and ic_target_irr is not None:
            irr_gap_vs_ic = irr - ic_target_irr

        moic_gap_vs_ic = None
        if moic is not None and ic_target_moic is not None:
            moic_gap_vs_ic = moic - ic_target_moic

        rows.append(
            {
                "valuation_mode": valuation_mode,
                "ticker": config.ticker,
                "company_name": company_name,
                "terminal_period_start": terminal_period_start.date().isoformat(),
                "terminal_period_end": terminal_period_end.date().isoformat(),
                "terminal_window_quarters": 4,
                "terminal_ebitda_basis": "sum_last_4_forecast_quarters",
                "scenario": scenario["scenario"],
                "scenario_description": scenario["scenario_description"],
                "forecast_column": scenario["forecast_column"],
                "exit_annual_ebitda": scenario["exit_annual_ebitda"],
                "exit_multiple": scenario["exit_multiple"],
                "exit_enterprise_value": exit_enterprise_value,
                "latest_net_debt": latest_net_debt,
                "exit_equity_value": exit_equity_value,
                "entry_enterprise_value": entry_enterprise_value,
                "entry_equity_value": entry_equity_value,
                "entry_valuation_basis": entry_valuation_basis,
                "holding_period_years": holding_period_years,
                "moic": moic,
                "irr": irr,
                "irr_percent": None if irr is None else irr * 100,
                "ic_target_irr": ic_target_irr,
                "irr_gap_vs_ic": irr_gap_vs_ic,
                "irr_gap_vs_ic_bps": None if irr_gap_vs_ic is None else irr_gap_vs_ic * 10000,
                "ic_target_moic": ic_target_moic,
                "moic_gap_vs_ic": moic_gap_vs_ic,
                "scenario_status": classify_status(irr, moic, ic_target_irr),
                "market_multiple_source": market["source"],
                "market_data_fallback": market["is_fallback"],
                "deal_metadata_used": deal is not None,
            }
        )

    result = pd.DataFrame(rows)

    _ensure_output_dir(config.output_path)
    result.to_csv(config.output_path, index=False)

    print(f"[IRR] IRR scenarios saved: {config.output_path}")
    print(
        result[
                [
                    "valuation_mode",
                    "scenario",
                    "exit_annual_ebitda",
                    "exit_multiple",
                    "exit_equity_value",
                    "moic",
                    "irr_percent",
                    "irr_gap_vs_ic_bps",
                    "scenario_status",
                    "deal_metadata_used",
                ]
        ]
    )

    return result


if __name__ == "__main__":
    build_irr_scenarios()
