from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from app.ingestion.quarterly_resample import infer_periods_per_year
from app.schemas.vcp_schema import VCPMilestone
from app.store.kpi_records_store import load_kpi_records
from app.store.vcp_store import VCPStore


@dataclass
class VCPDriftResult:
    company_id: str
    company_name: str
    initiative: str
    metric: str
    category: str
    target_value: Any
    actual_value: Any
    target_date: Optional[str]
    latest_period_end: Optional[str]
    gap_value: Optional[float]
    gap_pct: Optional[float]
    status: str
    severity_score: int
    reason: str
    source_path: Optional[str]
    source_column: Optional[str]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


# Human-readable names for metric enum keys used in user-facing text.
METRIC_DISPLAY_NAMES: Dict[str, str] = {
    "annual_revenue": "Annual Revenue",
    "ebitda_margin": "EBITDA Margin",
    "net_debt_to_ebitda": "Net Debt / EBITDA",
    "sga_ratio": "SG&A Ratio",
    "gross_margin": "Gross Margin",
    "revenue_growth": "Revenue Growth (YoY)",
    "capex_intensity": "CapEx Intensity",
    "fcf_margin": "FCF Margin",
    "net_revenue_retention": "Net Revenue Retention",
    "arr": "Annual Recurring Revenue",
    "cro_hired": "Chief Revenue Officer Hire",
    "reporting_cadence_upgrade_complete": "Monthly Reporting Upgrade",
    "headcount": "Headcount",
    "churn_rate": "Logo Churn Rate",
}


def metric_display_name(metric: str) -> str:
    return METRIC_DISPLAY_NAMES.get(metric, metric.replace("_", " ").title())


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        return float(value)
    except Exception:
        return None


def _status_higher_is_better(actual: Optional[float], target: Optional[float]) -> Dict[str, Any]:
    if actual is None or target is None or target == 0:
        return {
            "gap_value": None,
            "gap_pct": None,
            "status": "Not Evaluable",
            "severity_score": 0,
            "reason": "Actual or target value is missing.",
        }

    gap_value = actual - target
    gap_pct = (actual / target) - 1

    if gap_pct >= -0.05:
        status = "Green"
        severity_score = 0
        reason = "Actual is within 5% of target or better."
    elif gap_pct >= -0.10:
        status = "Amber"
        severity_score = 1
        reason = "Actual is 5–10% below target."
    else:
        status = "Red"
        severity_score = 2
        reason = "Actual is more than 10% below target."

    return {
        "gap_value": gap_value,
        "gap_pct": gap_pct,
        "status": status,
        "severity_score": severity_score,
        "reason": reason,
    }


def _status_lower_is_better(actual: Optional[float], target: Optional[float]) -> Dict[str, Any]:
    if actual is None or target is None or target == 0:
        return {
            "gap_value": None,
            "gap_pct": None,
            "status": "Not Evaluable",
            "severity_score": 0,
            "reason": "Actual or target value is missing.",
        }

    # Positive gap means actual is better than target.
    gap_value = target - actual
    gap_pct = (target / actual) - 1 if actual != 0 else None

    if actual <= target:
        status = "Green"
        severity_score = 0
        reason = "Actual is at or below target."
    elif actual <= target * 1.10:
        status = "Amber"
        severity_score = 1
        reason = "Actual is within 10% above the target limit."
    else:
        status = "Red"
        severity_score = 2
        reason = "Actual is more than 10% above the target limit."

    return {
        "gap_value": gap_value,
        "gap_pct": gap_pct,
        "status": status,
        "severity_score": severity_score,
        "reason": reason,
    }


def load_latest_financial_snapshot(financial_path: str) -> Dict[str, Any]:
    path = Path(financial_path)

    if not path.exists():
        raise FileNotFoundError(f"Financial file not found: {financial_path}")

    if path.suffix.lower() == ".csv":
        df = pd.read_csv(path)
    elif path.suffix.lower() in {".xlsx", ".xls"}:
        df = pd.read_excel(path, sheet_name="Financials", engine="openpyxl")
    else:
        raise ValueError(f"Unsupported financial file type: {path.suffix}")

    if df.empty:
        raise ValueError(f"Financial file is empty: {financial_path}")

    if "period_end" not in df.columns:
        raise ValueError("Financial file must contain period_end column.")

    df["period_end"] = pd.to_datetime(df["period_end"])
    df = df.sort_values("period_end")

    latest = df.iloc[-1].to_dict()

    # Reporting cadence varies by source (monthly private CSVs, quarterly EDGAR
    # filings); annualize by the actual periods-per-year, never a fixed ×12.
    periods_per_year = infer_periods_per_year(df)

    period_revenue = _safe_float(latest.get("revenue"))
    period_ebitda = _safe_float(latest.get("ebitda"))
    ebitda_margin = _safe_float(latest.get("ebitda_margin"))
    net_debt = _safe_float(latest.get("net_debt"))

    annualized_revenue = period_revenue * periods_per_year if period_revenue is not None else None
    annualized_ebitda = period_ebitda * periods_per_year if period_ebitda is not None else None

    net_debt_to_ebitda = None
    if net_debt is not None and annualized_ebitda not in {None, 0}:
        net_debt_to_ebitda = net_debt / annualized_ebitda

    return {
        "company_id": latest.get("company_id"),
        "company_name": latest.get("company_name"),
        "latest_period_end": latest.get("period_end").date().isoformat(),
        "source_path": financial_path,
        "annual_revenue": annualized_revenue,
        "ebitda_margin": ebitda_margin,
        "net_debt_to_ebitda": net_debt_to_ebitda,
        "period_revenue": period_revenue,
        "period_ebitda": period_ebitda,
        "periods_per_year": periods_per_year,
        "net_debt": net_debt,
    }


def evaluate_milestone(
    milestone: VCPMilestone,
    snapshot: Dict[str, Any],
) -> VCPDriftResult:
    metric = milestone.metric
    actual_value = None
    source_column = None

    if metric == "annual_revenue":
        actual_value = snapshot.get("annual_revenue")
        source_column = "revenue"
        comparison = _status_higher_is_better(
            _safe_float(actual_value),
            _safe_float(milestone.target_value),
        )

    elif metric == "ebitda_margin":
        actual_value = snapshot.get("ebitda_margin")
        source_column = "ebitda_margin"
        comparison = _status_higher_is_better(
            _safe_float(actual_value),
            _safe_float(milestone.target_value),
        )

    elif metric == "net_debt_to_ebitda":
        actual_value = snapshot.get("net_debt_to_ebitda")
        source_column = "net_debt / annualized_ebitda"
        comparison = _status_lower_is_better(
            _safe_float(actual_value),
            _safe_float(milestone.target_value),
        )

    else:
        comparison = {
            "gap_value": None,
            "gap_pct": None,
            "status": "Not Evaluable",
            "severity_score": 0,
            "reason": (
                f"{metric_display_name(metric)} does not yet have a mapped financial actual. "
                "This may be an operational or organisational milestone."
            ),
        }

    return VCPDriftResult(
        company_id=milestone.company_id,
        company_name=milestone.company_name,
        initiative=milestone.initiative,
        metric=milestone.metric,
        category=milestone.category,
        target_value=milestone.target_value,
        actual_value=actual_value,
        target_date=milestone.target_date,
        latest_period_end=snapshot.get("latest_period_end"),
        gap_value=comparison["gap_value"],
        gap_pct=comparison["gap_pct"],
        status=comparison["status"],
        severity_score=comparison["severity_score"],
        reason=comparison["reason"],
        source_path=snapshot.get("source_path"),
        source_column=source_column,
    )


def run_vcp_drift_for_company(
    company_id: str,
    financial_path: str,
    vcp_store_path: str = "data/processed/synthetic_vcp_milestones_seed.json",
) -> List[Dict[str, Any]]:
    store = VCPStore(vcp_store_path)
    milestones = store.load_confirmed_for_company(company_id)

    if not milestones:
        return []

    snapshot = load_latest_financial_snapshot(financial_path)

    results = [
        evaluate_milestone(milestone, snapshot).to_dict()
        for milestone in milestones
    ]

    return results


def run_vcp_drift_for_manifest(
    manifest_path: str = "data/processed/synthetic_source_manifest.json",
    vcp_store_path: str = "data/processed/synthetic_vcp_milestones_seed.json",
    output_path: str = "data/processed/vcp_drift_scores.json",
) -> Dict[str, Any]:
    manifest_file = Path(manifest_path)

    if not manifest_file.exists():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")

    with open(manifest_file, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    all_results: List[Dict[str, Any]] = []

    # Prefer CSV for deterministic testing. Excel has same numbers and can be tested separately.
    financial_sources = [
        item
        for item in manifest
        if item.get("doc_type") == "financials_monthly"
        and item.get("source_type") == "csv"
    ]

    for source in financial_sources:
        company_id = source["company_id"]
        financial_path = source["path"]

        company_results = run_vcp_drift_for_company(
            company_id=company_id,
            financial_path=financial_path,
            vcp_store_path=vcp_store_path,
        )

        all_results.extend(company_results)

    red_count = sum(1 for r in all_results if r["status"] == "Red")
    amber_count = sum(1 for r in all_results if r["status"] == "Amber")
    green_count = sum(1 for r in all_results if r["status"] == "Green")
    not_evaluable_count = sum(1 for r in all_results if r["status"] == "Not Evaluable")

    payload = {
        "manifest_path": manifest_path,
        "vcp_store_path": vcp_store_path,
        "result_count": len(all_results),
        "status_counts": {
            "Red": red_count,
            "Amber": amber_count,
            "Green": green_count,
            "Not Evaluable": not_evaluable_count,
        },
        "results": all_results,
    }

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    with open(output, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)

    return payload


def load_latest_kpi_snapshot_from_records(kpi_records_path: str) -> Dict[str, Any]:
    """
    Load latest financial snapshot from normalized KPIRecord JSON.

    This keeps VCP Drift source-agnostic:
    raw CSV / Excel / EDGAR should be handled by adapters,
    while drift consumes only normalized KPI records.
    """

    records = load_kpi_records(kpi_records_path)

    if not records:
        raise ValueError(f"No KPI records found in: {kpi_records_path}")

    df = pd.DataFrame(records)

    if "period_end" not in df.columns:
        raise ValueError("KPI records must contain period_end field.")

    df["period_end"] = pd.to_datetime(df["period_end"])
    df = df.sort_values("period_end")

    latest = df.iloc[-1].to_dict()

    # Reporting cadence varies by source (monthly private CSVs, quarterly EDGAR
    # filings); annualize by the actual periods-per-year, never a fixed ×12.
    periods_per_year = infer_periods_per_year(df)

    period_revenue = _safe_float(latest.get("revenue"))

    # Prefer adjusted EBITDA for private-company PE monitoring.
    # Fall back to ebitda_proxy if adjusted_ebitda is unavailable.
    period_ebitda = _safe_float(latest.get("adjusted_ebitda"))
    if period_ebitda is None:
        period_ebitda = _safe_float(latest.get("ebitda_proxy"))

    ebitda_margin = _safe_float(latest.get("ebitda_margin"))

    # If margin is not stored, derive it safely.
    if ebitda_margin is None and period_revenue not in {None, 0} and period_ebitda is not None:
        ebitda_margin = period_ebitda / period_revenue

    net_debt = _safe_float(latest.get("net_debt"))

    annualized_revenue = (
        period_revenue * periods_per_year if period_revenue is not None else None
    )
    annualized_ebitda = (
        period_ebitda * periods_per_year if period_ebitda is not None else None
    )

    net_debt_to_ebitda = None
    if net_debt is not None and annualized_ebitda not in {None, 0}:
        net_debt_to_ebitda = net_debt / annualized_ebitda

    return {
        "company_id": latest.get("company_id"),
        "company_name": latest.get("company_name"),
        "latest_period_end": latest.get("period_end").date().isoformat(),
        "source_path": kpi_records_path,
        "annual_revenue": annualized_revenue,
        "ebitda_margin": ebitda_margin,
        "net_debt_to_ebitda": net_debt_to_ebitda,
        "period_revenue": period_revenue,
        "period_ebitda": period_ebitda,
        "periods_per_year": periods_per_year,
        "net_debt": net_debt,
    }


def run_vcp_drift_for_kpi_records(
    company_id: str,
    kpi_records_path: str,
    vcp_store_path: str = "data/processed/synthetic_vcp_milestones_seed.json",
    output_path: str | None = None,
    milestones: Optional[List[VCPMilestone]] = None,
) -> Dict[str, Any]:
    """
    Run VCP drift using normalized KPIRecord JSON instead of raw CSV/Excel.

    This is the preferred path for downstream architecture:
    adapters normalize raw data, analytical nodes consume normalized records.

    `milestones` lets a caller that already loaded the company's confirmed VCP
    milestones (e.g. a portfolio loop iterating every company) pass them in,
    instead of this function opening its own VCPStore and re-fetching the same
    Postgres row — each fetch is a real network round trip.
    """

    if milestones is None:
        store = VCPStore(vcp_store_path)
        milestones = store.load_confirmed_for_company(company_id)

    if not milestones:
        payload = {
            "company_id": company_id,
            "kpi_records_path": kpi_records_path,
            "vcp_store_path": vcp_store_path,
            "result_count": 0,
            "status_counts": {
                "Red": 0,
                "Amber": 0,
                "Green": 0,
                "Not Evaluable": 0,
            },
            "results": [],
            "warning": "No confirmed VCP milestones found for company.",
        }

        if output_path:
            output = Path(output_path)
            output.parent.mkdir(parents=True, exist_ok=True)
            with open(output, "w", encoding="utf-8") as f:
                json.dump(payload, f, indent=2, default=str)

        return payload

    snapshot = load_latest_kpi_snapshot_from_records(kpi_records_path)

    results = [
        evaluate_milestone(milestone, snapshot).to_dict()
        for milestone in milestones
    ]

    red_count = sum(1 for r in results if r["status"] == "Red")
    amber_count = sum(1 for r in results if r["status"] == "Amber")
    green_count = sum(1 for r in results if r["status"] == "Green")
    not_evaluable_count = sum(
        1 for r in results if r["status"] == "Not Evaluable"
    )

    payload = {
        "company_id": company_id,
        "company_name": snapshot.get("company_name"),
        "latest_period_end": snapshot.get("latest_period_end"),
        "kpi_records_path": kpi_records_path,
        "vcp_store_path": vcp_store_path,
        "result_count": len(results),
        "status_counts": {
            "Red": red_count,
            "Amber": amber_count,
            "Green": green_count,
            "Not Evaluable": not_evaluable_count,
        },
        "results": results,
    }

    if output_path:
        output = Path(output_path)
        output.parent.mkdir(parents=True, exist_ok=True)

        with open(output, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, default=str)

    return payload