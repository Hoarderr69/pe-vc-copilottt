"""
Data freshness layer — separates "the company is drifting" from "we don't know
what's happening because data is late."

Derived entirely from real signals already available at the call site: the actual
latest ``period_end`` in a company's KPI records, its inferred reporting cadence
(:func:`app.ingestion.quarterly_resample.infer_periods_per_year`), its data source,
and the deal's close date. No fabricated per-company overrides — a company is
AWAITING if it has no KPI records at all, HISTORICAL if its public-filing data
structurally ends at/before take-private close, and otherwise FRESH/STALE/OVERDUE
based on how far today is past its next expected reporting date.
"""

from __future__ import annotations

from datetime import date, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel

from app.ingestion.quarterly_resample import infer_periods_per_year


class FreshnessStatus(str, Enum):
    FRESH = "fresh"
    STALE = "stale"
    OVERDUE = "overdue"
    AWAITING = "awaiting"
    HISTORICAL = "historical"


class CompanyDataFreshness(BaseModel):
    company_id: str
    reporting_cadence: Optional[str] = None
    last_data_received: Optional[str] = None
    next_expected: Optional[str] = None
    days_overdue: int = 0
    freshness_status: FreshnessStatus
    structural_cutoff: bool = False
    structural_cutoff_reason: Optional[str] = None
    message: str


def _cadence_label(periods_per_year: int) -> str:
    if periods_per_year >= 12:
        return "monthly"
    if periods_per_year >= 4:
        return "quarterly"
    return "annual"


def compute_freshness(
    company_id: str,
    kpi_records: List[Dict[str, Any]],
    deal_close_date: Optional[str] = None,
    today: Optional[date] = None,
) -> CompanyDataFreshness:
    today = today or date.today()

    if not kpi_records:
        return CompanyDataFreshness(
            company_id=company_id,
            freshness_status=FreshnessStatus.AWAITING,
            message="Connect a management-accounts data source to activate monitoring.",
        )

    periods = sorted(r["period_end"] for r in kpi_records if r.get("period_end"))
    if not periods:
        return CompanyDataFreshness(
            company_id=company_id,
            freshness_status=FreshnessStatus.AWAITING,
            message="Connect a management-accounts data source to activate monitoring.",
        )

    last_period_str = periods[-1]
    last_period = date.fromisoformat(last_period_str)
    data_source = kpi_records[0].get("source_type")

    # A public-filing series (EDGAR) that stops at or before the deal actually
    # closed is a structural cutoff, not a late submission: the company stopped
    # filing publicly because it went private, and no management-accounts source
    # has been connected yet.
    if data_source == "edgar" and deal_close_date:
        close = date.fromisoformat(deal_close_date)
        if last_period <= close:
            reason = (
                f"Public filing data ends {last_period_str} (pre-take-private — "
                f"deal closed {deal_close_date}). Drift detection and IRR scenarios "
                "activate when the portco team connects management accounts."
            )
            return CompanyDataFreshness(
                company_id=company_id,
                freshness_status=FreshnessStatus.HISTORICAL,
                structural_cutoff=True,
                structural_cutoff_reason=reason,
                last_data_received=last_period_str,
                message=reason,
            )

    periods_per_year = infer_periods_per_year(kpi_records)
    cadence = _cadence_label(periods_per_year)
    cadence_days = round(365 / periods_per_year) if periods_per_year else 91

    next_expected = last_period + timedelta(days=cadence_days)
    days_overdue = max(0, (today - next_expected).days)

    if days_overdue == 0:
        status = FreshnessStatus.FRESH
        message = f"Data current as of {last_period_str}."
    elif days_overdue <= cadence_days:
        status = FreshnessStatus.STALE
        message = (
            f"Based on data as of {last_period_str} — next {cadence} submission "
            f"expected {next_expected.isoformat()}."
        )
    else:
        status = FreshnessStatus.OVERDUE
        message = (
            f"{cadence.capitalize()} management accounts {days_overdue} days overdue "
            f"(expected {next_expected.isoformat()}). Signals paused — contact portco CFO."
        )

    return CompanyDataFreshness(
        company_id=company_id,
        reporting_cadence=cadence,
        last_data_received=last_period_str,
        next_expected=next_expected.isoformat(),
        days_overdue=days_overdue,
        freshness_status=status,
        message=message,
    )
