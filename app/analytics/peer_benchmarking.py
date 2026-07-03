"""
Peer Benchmarking Node — deterministic (no LLM).

Answers: "Is this portfolio company's performance good *for its sector*, or does the
whole sector look like this?" VCP drift tells you vs-plan; peer benchmarking tells you
vs-market. Together they let the Alert Agent separate company-specific execution
problems from sector-wide headwinds.

Computation (pure Python / pandas):
  1. From the company's normalized KPI records, derive latest-period metrics:
     revenue_growth_yoy, ebitda_margin, gross_margin, net_debt_to_ebitda.
  2. Compare each against the sector median from the benchmark reference.
  3. Score the gap, directionally (higher-is-better vs lower-is-better), into a
     status: Outperform / In-line / Underperform.

Prototype uses a curated sector-median reference. In production this node pulls
20-50 EDGAR peers by SIC code and computes the medians live — the consuming
contract (company metrics vs sector medians -> gap scores) is identical.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

from app.ingestion.quarterly_resample import infer_periods_per_year

DEFAULT_BENCHMARKS = "data/reference/sector_benchmarks.json"

# How far from the sector median counts as "in-line" before we call it out.
_INLINE_BAND = 0.10  # ±10% of the median

# Fallback metric set/directions so we can always emit a well-formed (if Not Evaluable)
# payload even when the benchmark reference is missing its _metric_direction block.
_DEFAULT_METRIC_DIRECTION = {
    "revenue_growth_yoy": "higher_is_better",
    "ebitda_margin": "higher_is_better",
    "gross_margin": "higher_is_better",
    "net_debt_to_ebitda": "lower_is_better",
}


def _safe_float(value: Any) -> Optional[float]:
    try:
        if value is None:
            return None
        v = float(value)
        return v if v == v else None  # filter NaN
    except Exception:
        return None


@dataclass
class PeerMetricResult:
    metric: str
    direction: str
    company_value: Optional[float]
    sector_median: Optional[float]
    gap: Optional[float]          # company - median (raw units)
    gap_pct: Optional[float]      # company vs median, signed fraction
    status: str                   # Outperform | In-line | Underperform | Not Evaluable
    reason: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _load_benchmarks(path: str) -> Dict[str, Any]:
    """Load the sector benchmark reference. Returns ``{}`` if it's absent.

    Benchmarking never hard-fails: a missing reference just means every metric ends up
    "Not Evaluable", not an exception that swallows the whole report.
    """
    p = Path(path)
    if not p.exists():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def _resolve_sector_key(
    company_id: str, benchmarks: Dict[str, Any], explicit: Optional[str] = None
) -> Optional[str]:
    """Resolve a company's sector: explicit arg → company meta → deal store → legacy map."""
    if explicit:
        return explicit

    # Sector stored with the company (the post-refactor source of truth).
    try:
        from app.store.company_store import load_company_meta

        meta = load_company_meta(company_id)
        if meta and meta.sector_key:
            return meta.sector_key
    except Exception:
        pass

    # Deal metadata may also carry it.
    try:
        from app.store.deal_store import DealStore

        deal = DealStore().load(company_id)
        if deal and getattr(deal, "sector_key", None):
            return deal.sector_key
    except Exception:
        pass

    # Legacy fallback: the company→sector map baked into the reference file.
    return (benchmarks.get("company_sector_map") or {}).get(company_id)


def _not_evaluable_payload(
    company_id: str,
    company_name: str,
    sector_key: Optional[str],
    latest_period_end: Optional[str],
    directions: Dict[str, str],
    reason: str,
    benchmarks_path: str,
    output_path: Optional[str] = None,
) -> Dict[str, Any]:
    """A well-formed benchmark payload with every metric Not Evaluable and a clear reason."""
    results = [
        PeerMetricResult(
            metric=metric, direction=directions.get(metric, "higher_is_better"),
            company_value=None, sector_median=None, gap=None, gap_pct=None,
            status="Not Evaluable", reason=reason,
        )
        for metric in directions
    ]
    payload = {
        "company_id": company_id,
        "company_name": company_name,
        "sector_key": sector_key,
        "sector_label": None,
        "peer_set_size": None,
        "benchmarks_path": benchmarks_path,
        "latest_period_end": latest_period_end,
        "composite_outperformance": None,
        "status_counts": {"Not Evaluable": len(results)},
        "results": [r.to_dict() for r in results],
        "reason": reason,
    }
    if output_path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
    return payload


def _company_metrics_from_records(records: List[Dict[str, Any]]) -> Dict[str, Optional[float]]:
    """Derive the latest-period peer-comparison metrics from KPI records."""
    df = pd.DataFrame(records)
    if df.empty or "period_end" not in df.columns:
        return {}

    df["period_end"] = pd.to_datetime(df["period_end"])
    df = df.sort_values("period_end").reset_index(drop=True)
    latest = df.iloc[-1]

    revenue = _safe_float(latest.get("revenue"))
    ebitda = _safe_float(latest.get("adjusted_ebitda"))
    if ebitda is None:
        ebitda = _safe_float(latest.get("ebitda_proxy"))
    gross_profit = _safe_float(latest.get("gross_profit"))
    net_debt = _safe_float(latest.get("net_debt"))

    ebitda_margin = (ebitda / revenue) if (revenue and ebitda is not None) else None
    gross_margin = (gross_profit / revenue) if (revenue and gross_profit is not None) else None

    # Annualize EBITDA (run-rate) for a leverage multiple consistent with VCP drift.
    # Cadence varies by source (monthly private CSVs vs quarterly EDGAR filings).
    periods_per_year = infer_periods_per_year(df)
    annual_ebitda = ebitda * periods_per_year if ebitda is not None else None
    net_debt_to_ebitda = (
        net_debt / annual_ebitda if (net_debt is not None and annual_ebitda not in {None, 0}) else None
    )

    # YoY revenue growth: latest period vs the record closest to one year earlier,
    # matched by date rather than row offset so any reporting cadence works.
    revenue_growth_yoy = None
    rev_now = _safe_float(latest.get("revenue"))
    if rev_now is not None and len(df) >= 2:
        year_ago_date = latest["period_end"] - pd.DateOffset(years=1)
        prior = df.iloc[:-1].copy()
        prior["_dist_days"] = (prior["period_end"] - year_ago_date).abs().dt.days
        best = prior.loc[prior["_dist_days"].idxmin()]
        # Accept only if the match is within half a reporting period of the
        # true one-year mark — otherwise YoY would silently compare wrong periods.
        if best["_dist_days"] <= (365 / periods_per_year) / 2:
            rev_year_ago = _safe_float(best.get("revenue"))
            if rev_year_ago not in {None, 0}:
                revenue_growth_yoy = (rev_now / rev_year_ago) - 1

    return {
        "revenue_growth_yoy": revenue_growth_yoy,
        "ebitda_margin": ebitda_margin,
        "gross_margin": gross_margin,
        "net_debt_to_ebitda": net_debt_to_ebitda,
    }


def _score_metric(metric: str, direction: str, value: Optional[float], median: Optional[float]) -> PeerMetricResult:
    if value is None or median is None or median == 0:
        return PeerMetricResult(
            metric=metric, direction=direction, company_value=value, sector_median=median,
            gap=None, gap_pct=None, status="Not Evaluable",
            reason="Company value or sector median is missing.",
        )

    gap = value - median
    gap_pct = (value / median) - 1

    higher_is_better = direction == "higher_is_better"
    # Relative outperformance, signed so positive always means "better than sector".
    rel = gap_pct if higher_is_better else -gap_pct

    if abs(gap_pct) <= _INLINE_BAND:
        status = "In-line"
        reason = "Within ±10% of the sector median."
    elif rel > 0:
        status = "Outperform"
        reason = "Better than the sector median by more than 10%."
    else:
        status = "Underperform"
        reason = "Worse than the sector median by more than 10%."

    return PeerMetricResult(
        metric=metric, direction=direction, company_value=value, sector_median=median,
        gap=gap, gap_pct=gap_pct, status=status, reason=reason,
    )


def run_peer_benchmark_for_company(
    company_id: str,
    kpi_records_path: str,
    benchmarks_path: str = DEFAULT_BENCHMARKS,
    output_path: Optional[str] = None,
    sector_key: Optional[str] = None,
) -> Dict[str, Any]:
    """Benchmark one company's latest metrics against its sector medians.

    ``sector_key`` resolution: explicit arg → company meta / deal store → legacy
    ``company_sector_map`` in the reference file. When the sector still can't be
    resolved (or has no medians), this returns a Not-Evaluable payload with a clear
    reason rather than raising — benchmarking never hard-fails the surrounding report.
    """
    benchmarks = _load_benchmarks(benchmarks_path)
    directions = benchmarks.get("_metric_direction") or _DEFAULT_METRIC_DIRECTION

    path = Path(kpi_records_path)
    if not path.exists():
        raise FileNotFoundError(f"KPI records not found: {kpi_records_path}")
    records = json.loads(path.read_text(encoding="utf-8"))
    if not records:
        return _not_evaluable_payload(
            company_id, company_id, None, None, directions,
            "No KPI records available for this company.", benchmarks_path, output_path,
        )

    company_name = records[-1].get("company_name", company_id)
    latest_period_end = records[-1].get("period_end")

    resolved_sector = _resolve_sector_key(company_id, benchmarks, explicit=sector_key)
    sector = (benchmarks.get("sectors") or {}).get(resolved_sector) if resolved_sector else None
    if not sector:
        reason = (
            f"No sector could be resolved for company '{company_id}'."
            if not resolved_sector
            else f"Sector '{resolved_sector}' has no benchmark medians in {benchmarks_path}."
        )
        return _not_evaluable_payload(
            company_id, company_name, resolved_sector, latest_period_end,
            directions, reason, benchmarks_path, output_path,
        )

    medians = sector["medians"]
    metrics = _company_metrics_from_records(records)

    results: List[PeerMetricResult] = []
    for metric, median in medians.items():
        direction = directions.get(metric, "higher_is_better")
        results.append(_score_metric(metric, direction, metrics.get(metric), median))

    status_counts: Dict[str, int] = {}
    for r in results:
        status_counts[r.status] = status_counts.get(r.status, 0) + 1

    # Composite: share of evaluated metrics that beat the sector.
    evaluated = [r for r in results if r.status != "Not Evaluable"]
    outperform = sum(1 for r in evaluated if r.status == "Outperform")
    composite_score = (outperform / len(evaluated)) if evaluated else None

    payload = {
        "company_id": company_id,
        "company_name": company_name,
        "sector_key": resolved_sector,
        "sector_label": sector.get("label"),
        "peer_set_size": sector.get("peer_set_size"),
        "benchmarks_path": benchmarks_path,
        "latest_period_end": latest_period_end,
        "composite_outperformance": composite_score,
        "status_counts": status_counts,
        "results": [r.to_dict() for r in results],
    }

    if output_path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    return payload
