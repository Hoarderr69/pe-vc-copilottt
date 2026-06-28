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

DEFAULT_BENCHMARKS = "data/reference/sector_benchmarks.json"

# How far from the sector median counts as "in-line" before we call it out.
_INLINE_BAND = 0.10  # ±10% of the median


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
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Sector benchmark reference not found: {path}")
    return json.loads(p.read_text(encoding="utf-8"))


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
    annual_ebitda = ebitda * 12 if ebitda is not None else None
    net_debt_to_ebitda = (
        net_debt / annual_ebitda if (net_debt is not None and annual_ebitda not in {None, 0}) else None
    )

    # YoY revenue growth: latest month vs 12 months earlier (needs >=13 records).
    revenue_growth_yoy = None
    if len(df) >= 13:
        rev_now = _safe_float(df.iloc[-1].get("revenue"))
        rev_year_ago = _safe_float(df.iloc[-13].get("revenue"))
        if rev_now is not None and rev_year_ago not in {None, 0}:
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
) -> Dict[str, Any]:
    """Benchmark one company's latest metrics against its sector medians."""
    benchmarks = _load_benchmarks(benchmarks_path)
    sector_key = benchmarks.get("company_sector_map", {}).get(company_id)
    if sector_key is None:
        raise ValueError(f"No sector mapping for company '{company_id}' in {benchmarks_path}")

    sector = benchmarks["sectors"][sector_key]
    directions = benchmarks["_metric_direction"]
    medians = sector["medians"]

    path = Path(kpi_records_path)
    if not path.exists():
        raise FileNotFoundError(f"KPI records not found: {kpi_records_path}")
    records = json.loads(path.read_text(encoding="utf-8"))
    if not records:
        raise ValueError(f"No KPI records in: {kpi_records_path}")

    company_name = records[-1].get("company_name", company_id)
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
        "sector_key": sector_key,
        "sector_label": sector.get("label"),
        "peer_set_size": sector.get("peer_set_size"),
        "benchmarks_path": benchmarks_path,
        "latest_period_end": records[-1].get("period_end"),
        "composite_outperformance": composite_score,
        "status_counts": status_counts,
        "results": [r.to_dict() for r in results],
    }

    if output_path:
        out = Path(output_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    return payload
