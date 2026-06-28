from __future__ import annotations

import json
import os
from pathlib import Path

from dotenv import load_dotenv

from app.agents.kpi_extraction_agent import run_kpi_extraction_agent
from app.graph.state import PortfolioMonitorState
from app.quant.forecast_engine import ForecastConfig, run_quant_forecast
from app.quant.irr_engine import IRRConfig, build_irr_scenarios
from app.schemas.kpi_schema import KPIExtractionConfig

load_dotenv()


def _safe_slug(ticker: str) -> str:
    return ticker.lower().replace(".", "_").replace("-", "_")


def initialize_state_node(state: PortfolioMonitorState) -> PortfolioMonitorState:
    """Populate defaults and deterministic output paths."""

    ticker = state.get("ticker") or os.getenv("DEFAULT_TICKER", "AAPL")
    cik = state.get("cik") or os.getenv("DEFAULT_CIK", "0000320193")
    company_name = state.get("company_name") or ticker
    slug = _safe_slug(ticker)

    is_default_demo = ticker.upper() == "AAPL" and cik == "0000320193"
    company_id = state.get("company_id") or (
        "demo_aapl_proxy_001" if is_default_demo else f"demo_{slug}_proxy"
    )

    state.update(
        {
            "company_id": company_id,
            "company_name": company_name,
            "ticker": ticker,
            "cik": cik,
            "valuation_mode": state.get("valuation_mode", "pe_deal"),
            "source_type": state.get("source_type", "edgar"),
            "source_registry": state.get(
                "source_registry",
                [
                    {
                        "source_type": state.get("source_type", "edgar"),
                        "description": "Prototype EDGAR/FRED structured financial source",
                    }
                ],
            ),
            "deal_metadata_path": state.get(
                "deal_metadata_path",
                "data/raw/deal_metadata/demo_deal.json" if is_default_demo else "",
            ),
            "raw_feature_matrix_path": state.get(
                "raw_feature_matrix_path",
                "data/features/demo_feature_matrix.csv"
                if is_default_demo
                else f"data/features/{slug}_feature_matrix.csv",
            ),
            "model_feature_matrix_path": state.get(
                "model_feature_matrix_path",
                "data/features/demo_model_feature_matrix.csv"
                if is_default_demo
                else f"data/features/{slug}_model_feature_matrix.csv",
            ),
            "kpi_records_path": state.get(
                "kpi_records_path",
                "data/processed/kpi_records.json"
                if is_default_demo
                else f"data/processed/{slug}_kpi_records.json",
            ),
            "evidence_refs_path": state.get(
                "evidence_refs_path",
                "data/processed/evidence_refs.json"
                if is_default_demo
                else f"data/processed/{slug}_evidence_refs.json",
            ),
            "source_quality_report_path": state.get(
                "source_quality_report_path",
                "data/processed/source_quality_report.json"
                if is_default_demo
                else f"data/processed/{slug}_source_quality_report.json",
            ),
            "stl_components_path": state.get(
                "stl_components_path",
                "data/processed/stl_components.csv"
                if is_default_demo
                else f"data/processed/{slug}_stl_components.csv",
            ),
            "forecast_path": state.get(
                "forecast_path",
                "data/processed/quant_ebitda_forecast.csv"
                if is_default_demo
                else f"data/processed/{slug}_quant_ebitda_forecast.csv",
            ),
            "irr_scenarios_path": state.get(
                "irr_scenarios_path",
                "data/processed/irr_scenarios.csv"
                if is_default_demo
                else f"data/processed/{slug}_irr_scenarios.csv",
            ),
            "errors": state.get("errors", []),
            "evidence_refs": state.get("evidence_refs", []),
            "alerts": state.get("alerts", []),
            "hitl_status": state.get("hitl_status", "not_started"),
            "status": "initialized",
        }
    )

    deal_path = state.get("deal_metadata_path")
    if deal_path and Path(deal_path).exists():
        with open(deal_path, "r", encoding="utf-8") as f:
            state["deal_metadata"] = json.load(f)

    return state


def kpi_extraction_node(state: PortfolioMonitorState) -> PortfolioMonitorState:
    """Run source-agnostic KPI Extraction Agent."""

    config = KPIExtractionConfig(
        company_id=state["company_id"],
        company_name=state["company_name"],
        ticker=state["ticker"],
        cik=state["cik"],
        source_type=state.get("source_type", "edgar"),
        raw_feature_matrix_path=state["raw_feature_matrix_path"],
        model_feature_matrix_path=state["model_feature_matrix_path"],
        kpi_records_path=state["kpi_records_path"],
        evidence_refs_path=state["evidence_refs_path"],
        source_quality_report_path=state["source_quality_report_path"],
        include_macro=bool(os.getenv("FRED_API_KEY")),
    )

    result = run_kpi_extraction_agent(config)

    state["raw_rows"] = result["raw_rows"]
    state["model_rows"] = result["model_rows"]
    state["kpi_records_path"] = result["kpi_records_path"]
    state["kpi_records_count"] = result["kpi_records_count"]
    state["evidence_refs_path"] = result["evidence_refs_path"]
    state["evidence_refs_count"] = result["evidence_refs_count"]
    state["source_quality_report_path"] = result["source_quality_report_path"]
    state["source_quality_report"] = result["source_quality_report"]
    state["status"] = "kpi_records_ready"

    state.setdefault("evidence_refs", []).append(
        {
            "agent": "kpi_extraction_node",
            "source_type": "generated_file",
            "source_path": state["kpi_records_path"],
            "description": "Standardized KPI records generated by source-agnostic KPI Extraction Agent.",
        }
    )

    return state


def quant_forecast_node(state: PortfolioMonitorState) -> PortfolioMonitorState:
    """Run Quant Agent forecast and store forecast path in graph state."""

    config = ForecastConfig(
        feature_path=state["model_feature_matrix_path"],
        target_col="ebitda_proxy",
        periods=20,
        output_path=state["forecast_path"],
        stl_output_path=state["stl_components_path"],
    )

    forecast_df = run_quant_forecast(config)

    state["forecast_rows"] = len(forecast_df)
    state["status"] = "forecast_ready"

    state.setdefault("evidence_refs", []).append(
        {
            "agent": "quant_forecast_node",
            "source_type": "generated_file",
            "source_path": state["forecast_path"],
            "description": "P10/P50/P90 EBITDA proxy forward curve generated by Quant Agent.",
        }
    )

    return state


def irr_scenario_node(state: PortfolioMonitorState) -> PortfolioMonitorState:
    """Run IRR/MOIC scenario engine using public-market or PE-deal mode."""

    deal_metadata_path = state.get("deal_metadata_path") or None

    config = IRRConfig(
        forecast_path=state["forecast_path"],
        feature_path=state["model_feature_matrix_path"],
        ticker=state["ticker"],
        output_path=state["irr_scenarios_path"],
        holding_period_years=5.0,
        deal_metadata_path=deal_metadata_path,
    )

    irr_df = build_irr_scenarios(config)

    state["irr_rows"] = len(irr_df)
    state["status"] = "irr_scenarios_ready"
    state["irr_scenarios"] = irr_df.to_dict(orient="records")

    state.setdefault("evidence_refs", []).append(
        {
            "agent": "irr_scenario_node",
            "source_type": "generated_file",
            "source_path": state["irr_scenarios_path"],
            "description": "IRR/MOIC scenario table generated from forecast and deal metadata.",
        }
    )

    return state


def placeholder_covenant_node(state: PortfolioMonitorState) -> PortfolioMonitorState:
    """Placeholder for upcoming agreement/risk checking agent."""

    state["covenant_results"] = {
        "status": "not_implemented",
        "message": "Agreement/risk-checking placeholder. Later: calculate leverage and legal/loan agreement headroom.",
    }
    return state


def placeholder_alert_node(state: PortfolioMonitorState) -> PortfolioMonitorState:
    """Placeholder Alert & Synthesis Agent using IRR scenario statuses."""

    alerts = []

    for scenario in state.get("irr_scenarios", []):
        status = scenario.get("scenario_status")

        if status in {"Red", "Amber"}:
            alerts.append(
                {
                    "alert_type": "return_risk",
                    "severity": status,
                    "scenario": scenario.get("scenario"),
                    "summary": (
                        f"{scenario.get('scenario')} scenario status is {status} "
                        "based on IRR/MOIC output."
                    ),
                    "source_path": state.get("irr_scenarios_path"),
                }
            )

    state["alerts"] = alerts
    state["hitl_status"] = "pending_review" if alerts else "no_review_required"
    state["status"] = "alerts_ready"

    return state
