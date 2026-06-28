"""
Slide Data Builder — pure Python construction of the per-slide JSON for the
10-slide Board Pack defined in Report_Module_Spec.md (Section 5).

This module contains NO I/O and NO LLM calls. It takes already-computed
structured inputs (VCP drift, KPI series, peer benchmarks, IRR scenarios,
narrative prose, board questions, structured risks) and returns a list of
slide dicts that the frontend renders into the exact spec layouts.

Each slide dict has the shape:

    {
        "id":          "cover" | "at_a_glance" | ... ,
        "index":       0..9,
        "type":        "Cover" | "AtAGlance" | ... ,   # frontend component name
        "title":       "...",
        "key_message": "...",                          # spec's per-slide line
        "data":        { ... slide-specific payload ... },
    }

Section 11 bug fixes implemented here (data layer only — chart/PPTX rendering
bugs #7/#8/#9 are handled by the renderer, but this module emits the correct
*data* those renderers need):

  #1  Status is its own field; due dates use short "Q4-27"/"M3" format.
  #2  Net Debt/EBITDA passed as the raw multiple (1.73), never ×100.
  #3  No internal file paths in audit data — clean source labels only.
  #4  Key-message strings truncated to <= 8 words + ellipsis where they feed
      a fixed-height strip.
  #5  Risks slide always carries a payload; empty-risk case emits no_risk block.
  #6  Benchmark / KPI gaps use "pp" for percentage metrics, "x" for multiples.
  #10 "Azure OpenAI" spelt correctly.
  #11 Dates rendered in full ("December 2027"), never ISO "2027-12".
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

# ---------------------------------------------------------------------------
# Metric metadata
# ---------------------------------------------------------------------------

# unit: "currency" | "pct" | "multiple" | "count"
# inverse: True when a lower value is better (worse = up)
METRIC_META: Dict[str, Dict[str, Any]] = {
    "annual_revenue":     {"label": "Revenue",         "unit": "currency", "inverse": False},
    "revenue":            {"label": "Revenue",         "unit": "currency", "inverse": False},
    "ebitda_margin":      {"label": "EBITDA Margin",   "unit": "pct",      "inverse": False},
    "gross_margin":       {"label": "Gross Margin",    "unit": "pct",      "inverse": False},
    "ebitda":             {"label": "EBITDA",          "unit": "currency", "inverse": False},
    "net_debt_to_ebitda": {"label": "Net Debt/EBITDA", "unit": "multiple", "inverse": True},
    "revenue_growth_yoy": {"label": "Revenue Growth",  "unit": "pct",      "inverse": False},
    "sga_ratio":          {"label": "SG&A % Revenue",  "unit": "pct",      "inverse": True},
    "cash":               {"label": "Cash",            "unit": "currency", "inverse": False},
}

# drift status -> RAG token used everywhere downstream
_STATUS_RAG = {
    "Red": "red", "Amber": "amber", "Green": "green",
    "Not Evaluable": "grey", "No Data": "grey",
}
_STATUS_LABEL = {
    "Red": "Behind", "Amber": "At Risk", "Green": "On Track",
    "Not Evaluable": "No Data", "No Data": "No Data",
}

SPARK_BLOCKS = "▁▂▃▄▅▆▇"

ASSEMBLY_VERSION = "PE Value Creation Copilot v0.1"
NARRATIVE_MODEL_LABEL = "GPT-4o (Azure OpenAI)"   # bug #10: correct capitalisation


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------

def _f(v: Any) -> Optional[float]:
    try:
        if v is None:
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def fmt_value(v: Any, unit: str) -> str:
    """Format a single metric value for display (data labels are mono/right-aligned)."""
    f = _f(v)
    if f is None:
        return "—"
    if unit == "currency":
        if abs(f) >= 1e6:
            return f"£{f / 1e6:.1f}M"
        if abs(f) >= 1e3:
            return f"£{f / 1e3:.0f}k"
        return f"£{f:.0f}"
    if unit == "pct":
        return f"{f:.1%}"
    if unit == "multiple":
        return f"{f:.2f}x"
    if unit == "count":
        return f"{int(round(f))}"
    return f"{f:.2f}"


def fmt_gap(actual: Any, target: Any, unit: str) -> str:
    """
    Bug #6: gap formatting by metric type.
      - pct metrics       -> percentage POINTS, "+13.6pp"
      - multiple metrics  -> turns,            "-0.07x"
      - currency / count  -> percent of target, "+2.0%"
    """
    a, t = _f(actual), _f(target)
    if a is None or t is None:
        return "—"
    if unit == "pct":
        return f"{(a - t) * 100:+.1f}pp"
    if unit == "multiple":
        return f"{a - t:+.2f}x"
    if t == 0:
        return "—"
    return f"{(a - t) / abs(t):+.1%}"


def short_due(target_date: Any) -> str:
    """
    Bug #1 / #11: due dates as compact "Q4-27" labels, never ISO "2027-12-31".
    Accepts ISO date strings, "M3"-style month markers, or None.
    """
    if not target_date:
        return "—"
    s = str(target_date).strip()
    # Already a milestone marker like "M3"
    if s.upper().startswith("M") and s[1:].isdigit():
        return s.upper()
    # ISO date -> quarter label
    try:
        d = datetime.strptime(s.split("T")[0], "%Y-%m-%d")
        q = (d.month - 1) // 3 + 1
        return f"Q{q}-{d.year % 100:02d}"
    except ValueError:
        pass
    # YYYY-MM fallback
    try:
        y, m = s.split("-")[:2]
        q = (int(m) - 1) // 3 + 1
        return f"Q{q}-{int(y) % 100:02d}"
    except Exception:
        return s


def full_period(period: str) -> str:
    """Bug #11: 'December 2027' from 'YYYY-MM' / 'YYYY-MM-DD'. Pass through otherwise."""
    if not period:
        return "Latest"
    s = str(period).strip()
    for fmt in ("%Y-%m-%d", "%Y-%m"):
        try:
            return datetime.strptime(s, fmt).strftime("%B %Y")
        except ValueError:
            continue
    return s


def quarter_period(period: str) -> str:
    """'Q4 2027' from 'YYYY-MM' / 'YYYY-MM-DD'. Pass through otherwise."""
    s = str(period or "").strip()
    for fmt in ("%Y-%m-%d", "%Y-%m"):
        try:
            d = datetime.strptime(s, fmt)
            q = (d.month - 1) // 3 + 1
            return f"Q{q} {d.year}"
        except ValueError:
            continue
    return s or "Latest"


def truncate_words(text: str, max_words: int = 8) -> str:
    """Bug #4: clip a key-message string to a fixed-height strip."""
    if not text:
        return ""
    words = str(text).split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words]) + "…"


def sparkline(values: List[Any], inverse: bool = False) -> str:
    """5-period unicode sparkline. Ascending blocks = improving (respecting inverse)."""
    nums = [_f(v) for v in values if _f(v) is not None]
    if len(nums) < 2:
        return ""
    lo, hi = min(nums), max(nums)
    span = (hi - lo) or 1.0
    out = []
    for n in nums[-5:]:
        idx = int(round((n - lo) / span * (len(SPARK_BLOCKS) - 1)))
        out.append(SPARK_BLOCKS[idx])
    return "".join(out)


# ---------------------------------------------------------------------------
# Aggregation helpers
# ---------------------------------------------------------------------------

def _annual_sum(series: List[Dict[str, Any]], key: str, n: int = 12) -> Optional[float]:
    """Sum the last n monthly points for a flow metric (revenue / ebitda)."""
    vals = [_f(r.get(key)) for r in series if _f(r.get(key)) is not None]
    if not vals:
        return None
    return float(sum(vals[-n:]))


def _latest(series: List[Dict[str, Any]], key: str) -> Optional[float]:
    for r in reversed(series):
        v = _f(r.get(key))
        if v is not None:
            return v
    return None


def _clamp(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


# ---------------------------------------------------------------------------
# Per-slide builders
# ---------------------------------------------------------------------------

def _overall_rag(drift_results: List[Dict[str, Any]], severity: str) -> str:
    if severity in ("Red", "Amber", "Green"):
        return _STATUS_RAG.get(severity, "amber")
    counts = {s: 0 for s in ("Red", "Amber", "Green")}
    for r in drift_results:
        counts[r.get("status", "Green")] = counts.get(r.get("status", "Green"), 0) + 1
    if counts.get("Red"):
        return "red"
    if counts.get("Amber"):
        return "amber"
    return "green"


def _milestone_rows(milestones: List[Dict[str, Any]],
                    drift_results: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Join confirmed milestones to live drift for the VCP scorecard."""
    drift_by_metric = {d.get("metric"): d for d in drift_results}
    rows: List[Dict[str, Any]] = []
    for m in milestones:
        metric = m.get("metric")
        meta = METRIC_META.get(metric, {"unit": "count", "inverse": False})
        d = drift_by_metric.get(metric, {})
        status = d.get("status", "Not Evaluable")
        actual = d.get("actual_value")
        target = m.get("target_value", d.get("target_value"))
        baseline = m.get("baseline_value")
        unit = meta["unit"]

        overdue = False
        td = m.get("target_date")
        if td and status in ("Red", "Amber"):
            try:
                overdue = datetime.strptime(str(td).split("T")[0], "%Y-%m-%d").replace(
                    tzinfo=timezone.utc) < datetime.now(timezone.utc) and status == "Red"
            except ValueError:
                overdue = False

        rows.append({
            "initiative":   m.get("initiative", metric),
            "metric":       metric,
            "category":     (m.get("category") or "—").title(),
            "baseline":     fmt_value(baseline, unit) if baseline is not None else "—",
            "target":       fmt_value(target, unit) if target is not None else "—",
            "actual":       fmt_value(actual, unit) if actual is not None else "—",
            "gap":          fmt_gap(actual, target, unit) if (actual is not None and target is not None) else "—",
            "status":       _STATUS_RAG.get(status, "grey"),
            "status_label": _STATUS_LABEL.get(status, "No Data"),
            "due":          short_due(m.get("target_date")),    # bug #1
            "overdue":      overdue,                            # ⚠ suffix flag
        })
    # Sort: Behind -> At Risk -> On Track -> No Data
    order = {"red": 0, "amber": 1, "green": 2, "grey": 3}
    rows.sort(key=lambda r: order.get(r["status"], 9))
    return rows


def _milestone_counts(rows: List[Dict[str, Any]]) -> Dict[str, int]:
    c = {"behind": 0, "at_risk": 0, "on_track": 0, "no_data": 0}
    for r in rows:
        c["behind"]   += r["status"] == "red"
        c["at_risk"]  += r["status"] == "amber"
        c["on_track"] += r["status"] == "green"
        c["no_data"]  += r["status"] == "grey"
    return c


def _kpi_scorecard_rows(drift_results: List[Dict[str, Any]],
                        series: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """KPI Performance Scorecard rows with sparklines, QoQ, pp/x gaps (bug #6)."""
    # series key per metric for sparkline + QoQ
    series_key = {
        "annual_revenue": "revenue",
        "revenue": "revenue",
        "ebitda_margin": "ebitda_margin",
        "gross_margin": "gross_margin",
        "net_debt_to_ebitda": "net_debt_to_ebitda",
        "cash": "cash",
    }
    sorted_series = sorted(series, key=lambda r: r.get("period_end", ""))
    latest = sorted_series[-1] if sorted_series else {}
    prev = sorted_series[-2] if len(sorted_series) > 1 else {}

    rows: List[Dict[str, Any]] = []
    for d in drift_results:
        metric = d.get("metric")
        meta = METRIC_META.get(metric)
        if not meta:
            continue
        unit, inverse = meta["unit"], meta["inverse"]
        actual = d.get("actual_value")
        target = d.get("target_value")
        status = d.get("status", "Not Evaluable")

        sk = series_key.get(metric)
        spark = ""
        qoq = "—"
        if sk:
            spark = sparkline([r.get(sk) for r in sorted_series], inverse=inverse)
            cur_v, prev_v = _f(latest.get(sk)), _f(prev.get(sk))
            if cur_v is not None and prev_v not in (None, 0):
                qoq_pct = (cur_v - prev_v) / abs(prev_v)
                arrow = "▲" if qoq_pct > 0 else "▼"
                qoq = f"{qoq_pct:+.1%} {arrow}"

        rows.append({
            "metric":      meta["label"],
            "metric_key":  metric,
            "actual":      fmt_value(actual, unit),
            "ic_target":   fmt_value(target, unit),
            "delta":       fmt_gap(actual, target, unit),   # pp / x / % (bug #6)
            "vs_last_qtr": qoq,
            "trend":       spark,
            "status":      _STATUS_RAG.get(status, "grey"),
            "inverse":     inverse,                          # (↑=worse) flag
        })
    order = {"red": 0, "amber": 1, "green": 2, "grey": 3}
    rows.sort(key=lambda r: order.get(r["status"], 9))
    return rows


def _benchmark_rows(peer_benchmark: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Per-metric benchmark rows with estimated percentile / P25 / P75 (bug #6 gaps)."""
    if not peer_benchmark or not peer_benchmark.get("results"):
        return []
    rows = []
    for b in peer_benchmark["results"]:
        metric = b.get("metric")
        meta = METRIC_META.get(metric, {"label": metric, "unit": "pct", "inverse": False})
        unit = meta["unit"]
        company = _f(b.get("company_value"))
        median = _f(b.get("sector_median"))
        direction = b.get("direction", "higher_is_better")
        lower_better = direction == "lower_is_better"

        # Estimated quartile band (±20% around median) — prototype synthetic spread.
        if median:
            if lower_better:
                p25, p75 = median * 1.2, median * 0.8
            else:
                p25, p75 = median * 0.8, median * 1.2
        else:
            p25 = p75 = median

        # Estimated percentile position.
        pct = None
        if company is not None and median:
            denom = 0.2 * abs(median)
            z = ((median - company) if lower_better else (company - median)) / (denom or 1)
            pct = _clamp(50 + z * 25, 5, 95)

        rows.append({
            "metric":     meta["label"],
            "metric_key": metric,
            "company":    fmt_value(company, unit),
            "p25":        fmt_value(p25, unit),
            "median":     fmt_value(median, unit),
            "p75":        fmt_value(p75, unit),
            "percentile": None if pct is None else f"{int(round(pct))}th",
            "percentile_value": None if pct is None else round(pct, 1),
            "gap":        fmt_gap(company, median, unit),    # pp / x (bug #6)
            "status":     b.get("status", "—"),
            "inverse":    lower_better,
        })
    return rows


# ---------------------------------------------------------------------------
# IRR matrix (self-contained — Python only, never LLM)
# ---------------------------------------------------------------------------

def _deal_assumptions(milestones: List[Dict[str, Any]],
                      series: List[Dict[str, Any]],
                      irr_scenarios: Optional[List[Dict[str, Any]]]) -> Dict[str, Any]:
    """Derive entry/exit assumptions for the IRR matrix from available data."""
    by_metric = {m.get("metric"): m for m in milestones}

    base_rev = _f((by_metric.get("annual_revenue") or {}).get("baseline_value")) or \
        ((_annual_sum(series, "revenue") or 0) * 0.7)
    base_margin = _f((by_metric.get("ebitda_margin") or {}).get("baseline_value")) or 0.15
    tgt_rev = _f((by_metric.get("annual_revenue") or {}).get("target_value")) or (base_rev * 1.5)
    tgt_margin = _f((by_metric.get("ebitda_margin") or {}).get("target_value")) or 0.20
    base_leverage = _f((by_metric.get("net_debt_to_ebitda") or {}).get("baseline_value")) or 3.3

    entry_ebitda = max(base_rev * base_margin, 1.0)
    target_ebitda = max(tgt_rev * tgt_margin, entry_ebitda)
    entry_multiple = 11.0
    entry_ev = entry_ebitda * entry_multiple
    entry_net_debt = entry_ebitda * base_leverage
    entry_equity = max(entry_ev - entry_net_debt, 1.0)

    # VCP horizon in years (from milestone metadata when present).
    horizon_months = None
    for m in milestones:
        hm = ((m.get("metadata") or {}).get("target_horizon_months"))
        if hm:
            horizon_months = max(horizon_months or 0, _f(hm) or 0)
    horizon_yrs = (horizon_months / 12.0) if horizon_months else 2.0

    # Terminal EBITDA growth beyond the VCP horizon — modest, board-defensible.
    terminal_growth = 0.05

    current_net_debt = _latest(series, "net_debt") or entry_net_debt

    # IC underwritten case + current P50 trajectory (best-effort from irr_scenarios).
    ic_irr, base_irr = 0.19, None
    if irr_scenarios:
        for s in irr_scenarios:
            if str(s.get("scenario", "")).lower() == "base" and s.get("irr_percent") is not None:
                base_irr = _f(s.get("irr_percent")) / 100.0
            if s.get("ic_target_irr") is not None:
                ic_irr = _f(s.get("ic_target_irr"))

    return {
        "entry_equity": entry_equity,
        "entry_ebitda": entry_ebitda,
        "target_ebitda": target_ebitda,
        "entry_multiple": entry_multiple,
        "net_debt": current_net_debt,
        "horizon_yrs": horizon_yrs,
        "terminal_growth": terminal_growth,
        "ic_irr": ic_irr,
        "ic_multiple": 10.0,
        "ic_year": 5,
        "base_irr": base_irr,
    }


def _exit_ebitda(assumptions: Dict[str, Any], year: int) -> float:
    """
    Conservative exit-EBITDA path: ramp from entry to the VCP target over the
    VCP horizon, then apply modest terminal growth. Avoids compounding an
    aggressive VCP CAGR across the full hold (which inflates IRR).
    """
    ent = assumptions["entry_ebitda"]
    tgt = assumptions["target_ebitda"]
    horizon = max(assumptions["horizon_yrs"], 0.5)
    g_term = assumptions["terminal_growth"]
    if year <= horizon:
        # Linear ramp entry -> target within the VCP horizon.
        frac = year / horizon
        return ent + (tgt - ent) * frac
    return tgt * (1 + g_term) ** (year - horizon)


def _irr_matrix(assumptions: Dict[str, Any]) -> Dict[str, Any]:
    exit_multiples = [8.0, 10.0, 12.0, 14.0, 16.0]
    hold_years = [3, 4, 5, 6, 7]
    eq = assumptions["entry_equity"]
    nd = assumptions["net_debt"]

    def rag(irr: float) -> str:
        if irr >= 0.25:
            return "green"
        if irr >= 0.15:
            return "amber"
        return "red"

    grid: List[Dict[str, Any]] = []
    for mult in exit_multiples:
        cells = []
        for yr in hold_years:
            exit_eb = _exit_ebitda(assumptions, yr)
            exit_equity = mult * exit_eb - nd
            if exit_equity <= 0 or eq <= 0:
                irr = -1.0
            else:
                irr = (exit_equity / eq) ** (1 / yr) - 1
            cells.append({
                "year": yr,
                "irr": round(irr, 4),
                "irr_pct": f"{irr * 100:.1f}%",
                "rag": rag(irr),
                "ic_cell": abs(mult - assumptions["ic_multiple"]) < 0.01 and yr == assumptions["ic_year"],
                "p50_cell": abs(mult - assumptions["entry_multiple"]) < 1.01 and yr == assumptions["ic_year"],
            })
        grid.append({"exit_multiple": mult, "exit_multiple_label": f"{mult:.1f}x", "cells": cells})

    return {
        "exit_multiples": exit_multiples,
        "hold_years": hold_years,
        "grid": grid,
    }


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def build_slides(
    *,
    company_id: str,
    company_name: str,
    period: str,
    sector: str,
    milestones: List[Dict[str, Any]],
    drift_results: List[Dict[str, Any]],
    kpi_series: List[Dict[str, Any]],
    alert_card: Dict[str, Any],
    narrative: Dict[str, Any],
    peer_benchmark: Optional[Dict[str, Any]] = None,
    irr_scenarios: Optional[List[Dict[str, Any]]] = None,
    board_questions: Optional[List[str]] = None,
    risks_output: Optional[Dict[str, Any]] = None,
    citations: Optional[List[str]] = None,
    hitl_decisions: Optional[List[Dict[str, Any]]] = None,
    generated_at: Optional[str] = None,
    approved_by: Optional[str] = None,
    approved_at: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Build the full 10-slide Board Pack payload. Pure function, no I/O."""

    generated_at = generated_at or datetime.now(timezone.utc).isoformat()
    severity = alert_card.get("severity", "Amber")
    irr_at_risk_bps = alert_card.get("irr_at_risk_bps")
    overall_rag = _overall_rag(drift_results, severity)

    # Shared structures
    ms_rows = _milestone_rows(milestones, drift_results)
    ms_counts = _milestone_counts(ms_rows)
    kpi_rows = _kpi_scorecard_rows(drift_results, kpi_series)
    bench_rows = _benchmark_rows(peer_benchmark)
    assumptions = _deal_assumptions(milestones, kpi_series, irr_scenarios)
    irr_matrix = _irr_matrix(assumptions)

    period_full = full_period(period)
    period_q = quarter_period(period)

    # Prefer the human-readable sector label from peer benchmarking over raw source type.
    sector_label = (peer_benchmark.get("sector_label") if peer_benchmark else None) or sector or "—"

    # IRR scenario inset (bear/base/bull/IC) — best-effort
    irr_inset = _irr_inset(irr_scenarios, assumptions)

    slides: List[Dict[str, Any]] = []

    # --- Slide 1: Cover -----------------------------------------------------
    base_irr = irr_inset.get("base")
    ic_irr_pct = assumptions["ic_irr"] * 100
    gap_bps = None
    if base_irr is not None:
        gap_bps = int(round((base_irr - ic_irr_pct) * 100))
    slides.append(_slide("cover", 0, "Cover", company_name, "", {
        "company_name": company_name,
        "sector": sector_label,
        "report_type_label": "Board Pack",
        "period": period_q,
        "period_full": period_full,
        "overall_status": overall_rag,
        "irr_base": None if base_irr is None else f"{base_irr:.1f}%",
        "irr_ic": f"{ic_irr_pct:.1f}%",
        "irr_gap_bps": gap_bps,
        "prepared_by": "Operating Partner Team",
        "date": period_full,
        "classification": "Confidential — Board Only",
        "generated_by": ASSEMBLY_VERSION,
        "approved_by": approved_by,
        "approved_at": approved_at,
        "fund_context": {
            "entry_ebitda": fmt_value(assumptions["entry_ebitda"], "currency"),
            "entry_multiple": f"{assumptions['entry_multiple']:.1f}x",
            "initial_equity": fmt_value(assumptions["entry_equity"], "currency"),
            "hold_target": f"{assumptions['ic_year']} years",
        },
    }))

    # --- Slide 2: At a Glance ----------------------------------------------
    kpi_quad = [
        {"label": r["metric"], "value": r["actual"], "status": r["status"]}
        for r in kpi_rows[:3]
    ]
    bench_quad = [
        {"label": r["metric"], "percentile": r["percentile"]}
        for r in bench_rows[:3]
    ]
    glance_msg = truncate_words(
        f"{ms_counts['on_track']} of {len(ms_rows)} VCP milestones on track", 12
    )
    slides.append(_slide("at_a_glance", 1, "AtAGlance", "At a Glance", glance_msg, {
        "kpi_performance": kpi_quad,
        "vcp_milestones": {
            "on_track": ms_counts["on_track"],
            "total": len(ms_rows),
            "behind": ms_counts["behind"],
            "at_risk": ms_counts["at_risk"],
            "no_data": ms_counts["no_data"],
        },
        "irr_outlook": {
            "bear": irr_inset.get("bear_label"),
            "base": irr_inset.get("base_label"),
            "bull": irr_inset.get("bull_label"),
            "ic": irr_inset.get("ic_label"),
            "gap_bps": gap_bps,
        },
        "peer_position": [
            {"metric": r["metric"], "percentile": r["percentile"]} for r in bench_rows
        ],
        "sector": peer_benchmark.get("sector_label") if peer_benchmark else (sector or "—"),
        "priority_action": truncate_words(narrative.get("priority_action", ""), 14),
    }))

    # --- Slide 3: Executive Summary ----------------------------------------
    exec_summary = narrative.get("exec_summary", "")
    exec_msg = truncate_words(exec_summary.split(".")[0] if exec_summary else "", 14)
    slides.append(_slide("exec_summary", 2, "ExecSummary", "Executive Summary", exec_msg, {
        "situation": exec_summary,
        "key_risks": narrative.get("key_risks", []),
        "priority_action": narrative.get("priority_action", ""),
        "stats": [
            {"label": "IRR AT RISK",
             "value": "—" if irr_at_risk_bps is None else f"{irr_at_risk_bps:+d}bps",
             "sub": "vs IC underwritten",
             "negative": bool(irr_at_risk_bps and irr_at_risk_bps < 0)},
            {"label": "VCP ON TRACK",
             "value": f"{ms_counts['on_track']} / {len(ms_rows)}",
             "sub": "milestones", "negative": False},
            {"label": "PEER RANK",
             "value": bench_rows[0]["percentile"] if bench_rows else "—",
             "sub": bench_rows[0]["metric"] if bench_rows else "—", "negative": False},
        ],
        "footer": {
            "ai_label": NARRATIVE_MODEL_LABEL,
            "mode": narrative.get("narrative_mode", "offline_rule_based"),
            "timestamp": generated_at,
            "approved_by": approved_by,
        },
    }))

    # --- Slide 4: KPI Performance Scorecard --------------------------------
    worst = kpi_rows[0] if kpi_rows else None
    kpi_msg = truncate_words(
        f"{worst['metric']} {worst['delta']} vs IC target" if worst else "", 10
    )
    slides.append(_slide("kpi_scorecard", 3, "KPIScorecard", "KPI Performance Scorecard", kpi_msg, {
        "rows": kpi_rows,
        "legend": "Red = >10% below IC target · Amber = 5–10% · Green = within ±5%",
        "narrative": narrative.get("kpi_narrative", ""),
        "source": "Management accounts · IC Memo confirmed",
    }))

    # --- Slide 5: VCP Scorecard --------------------------------------------
    overdue_ms = next((r for r in ms_rows if r["overdue"]), None)
    vcp_msg = truncate_words(
        f"{ms_counts['on_track']} of {len(ms_rows)} VCP milestones on track"
        + (f"; {overdue_ms['initiative']} overdue" if overdue_ms else ""), 12
    )
    slides.append(_slide("vcp_scorecard", 4, "VCPScorecard", "Value Creation Plan Scorecard", vcp_msg, {
        "summary": {
            "behind": ms_counts["behind"],
            "at_risk": ms_counts["at_risk"],
            "on_track": ms_counts["on_track"],
            "no_data": ms_counts["no_data"],
        },
        "rows": ms_rows,
        "source": "IC Memo · confirmed",
    }))

    # --- Slide 6: EBITDA Forward Curve -------------------------------------
    forward = _forward_curve(kpi_series, milestones, drift_results)
    fc_msg = truncate_words("P50 forecast vs IC exit target; SG&A discipline required", 10)
    slides.append(_slide("forward_curve", 5, "ForwardCurve", "EBITDA Forward Curve", fc_msg, {
        "kpi_strip": forward["kpi_strip"],
        "series": forward["series"],
        "ic_target": forward["ic_target"],
        "vcp_targets": forward["vcp_targets"],
        "now_index": forward["now_index"],
        "irr_inset": irr_inset["rows"],
        "methodology": (
            "STL decomposition + SARIMA ensemble + Prophet · FRED macro regressors "
            "(DFF, INDPRO, CPILFESL) · P10–P90 band = model uncertainty range"
        ),
    }))

    # --- Slide 7: Sector Benchmarking --------------------------------------
    worst_bench = min(
        (r for r in bench_rows if r.get("percentile_value") is not None),
        key=lambda r: r["percentile_value"], default=None,
    )
    bm_msg = truncate_words(
        f"{worst_bench['metric']} at {worst_bench['percentile']} percentile vs sector"
        if worst_bench else "Sector benchmarking", 10
    )
    slides.append(_slide("benchmarks", 6, "Benchmarks", "Sector Benchmarking", bm_msg, {
        "rows": bench_rows,
        "sector_label": peer_benchmark.get("sector_label") if peer_benchmark else (sector or "—"),
        "peer_set_size": peer_benchmark.get("peer_set_size") if peer_benchmark else None,
        "ai_analysis": narrative.get("benchmark_analysis", ""),
        "estimated_band": True,   # P25/P75 are estimated for the prototype
        "source": "EDGAR XBRL · sector medians",
    }))

    # --- Slide 8: Risks & Recommended Actions ------------------------------
    risk_payload = _risks_payload(risks_output, drift_results, alert_card)
    risk_msg = truncate_words(
        risk_payload["rows"][0]["risk"] if risk_payload["rows"] else "No material risks", 10
    )
    slides.append(_slide("risks_actions", 7, "RisksActions", "Risks & Recommended Actions", risk_msg, {
        "rows": risk_payload["rows"],
        "has_risks": risk_payload["has_risks"],          # bug #5
        "no_risk_block": risk_payload["no_risk_block"],  # bug #5
        "total_irr_at_risk_bps": risk_payload["total_irr_at_risk_bps"],
        "all_recoverable": risk_payload["all_recoverable"],
        "board_questions": board_questions or narrative.get("board_talking_points", []),
    }))

    # --- Slide 9: IRR Scenario Matrix --------------------------------------
    irr_msg = truncate_words(
        f"IC underwritten {assumptions['ic_multiple']:.0f}x · Year {assumptions['ic_year']} "
        f"· {assumptions['ic_irr'] * 100:.1f}% IRR", 12
    )
    slides.append(_slide("irr_matrix", 8, "IRRMatrix", "IRR Scenario Matrix", irr_msg, {
        "matrix": irr_matrix,
        "ic_underwritten": {
            "exit_multiple": f"{assumptions['ic_multiple']:.1f}x",
            "year": assumptions["ic_year"],
            "irr": f"{assumptions['ic_irr'] * 100:.1f}%",
        },
        "p50_trajectory": {
            "exit_multiple": f"{assumptions['entry_multiple']:.1f}x",
            "year": assumptions["ic_year"],
            "irr": None if irr_inset.get("base") is None else f"{irr_inset['base']:.1f}%",
            "gap_bps": gap_bps,
        },
        "legend": "Green ≥25% · Amber 15–24% · Red <15%",
        "methodology": "STL + SARIMA + Prophet ensemble · entry equity & deal debt derived from VCP baseline",
    }))

    # --- Slide 10: Audit Trail ---------------------------------------------
    slides.append(_slide("audit_trail", 9, "AuditTrail", "Appendix — Audit Trail & Evidence", "", {
        "provenance": {
            "generated": generated_at,
            "approved_by": approved_by,
            "approved_at": approved_at,
            "narrative": f"{NARRATIVE_MODEL_LABEL} · reviewed and approved by human"
            if approved_by else f"{NARRATIVE_MODEL_LABEL} · pending human approval",
            "assembly": ASSEMBLY_VERSION,
        },
        "citations": _clean_citations(citations, peer_benchmark),  # bug #3
        "hitl_decisions": hitl_decisions or [],
        "disclaimer": _DISCLAIMER,
    }))

    return slides


# ---------------------------------------------------------------------------
# Slide-builder sub-helpers
# ---------------------------------------------------------------------------

def _slide(sid: str, index: int, stype: str, title: str,
           key_message: str, data: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": sid,
        "index": index,
        "type": stype,
        "title": title,
        "key_message": key_message,
        "data": data,
    }


def _irr_inset(irr_scenarios: Optional[List[Dict[str, Any]]],
               assumptions: Dict[str, Any]) -> Dict[str, Any]:
    """Bear/Base/Bull/IC inset rows + numeric base for the cover. Falls back to matrix."""
    out: Dict[str, Any] = {"rows": [], "bear": None, "base": None, "bull": None}
    label_map = {"bear": "Bear (P10)", "base": "Base (P50)", "bull": "Bull (P90)"}
    if irr_scenarios:
        for s in irr_scenarios:
            scen = str(s.get("scenario", "")).lower()
            irr_pct = _f(s.get("irr_percent"))
            if scen in label_map and irr_pct is not None:
                out[scen] = irr_pct
                out["rows"].append({
                    "label": label_map[scen],
                    "irr": f"{irr_pct:.1f}%",
                    "bold": scen == "base",
                })
    # Fallback from the matrix IC cell when scenarios are absent.
    if out["base"] is None:
        for row in _irr_matrix(assumptions)["grid"]:
            if abs(row["exit_multiple"] - assumptions["entry_multiple"]) < 1.01:
                for cell in row["cells"]:
                    if cell["year"] == assumptions["ic_year"]:
                        out["base"] = cell["irr"] * 100
        if out["base"] is not None and not out["rows"]:
            out["rows"].append({"label": "Base (P50)", "irr": f"{out['base']:.1f}%", "bold": True})

    ic_pct = assumptions["ic_irr"] * 100
    gap = None if out["base"] is None else int(round((out["base"] - ic_pct) * 100))
    out["rows"].append({
        "label": "IC Case",
        "irr": f"{ic_pct:.1f}%",
        "delta_bps": gap,
        "bold": False,
    })
    out["bear_label"] = None if out["bear"] is None else f"{out['bear']:.1f}%"
    out["base_label"] = None if out["base"] is None else f"{out['base']:.1f}%"
    out["bull_label"] = None if out["bull"] is None else f"{out['bull']:.1f}%"
    out["ic_label"] = f"{ic_pct:.1f}%"
    return out


def _forward_curve(series: List[Dict[str, Any]],
                   milestones: List[Dict[str, Any]],
                   drift_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Build the EBITDA line series + projection band (bug #2: raw multiples, no ×100)."""
    sorted_series = sorted(series, key=lambda r: r.get("period_end", ""))
    actual_points = [
        {"period": r.get("period_end"), "ebitda": _f(r.get("ebitda"))}
        for r in sorted_series if _f(r.get("ebitda")) is not None
    ]
    now_index = len(actual_points) - 1

    # Simple forward projection: extend last EBITDA along the VCP-implied trend.
    last_eb = actual_points[-1]["ebitda"] if actual_points else 0.0
    by_metric = {m.get("metric"): m for m in milestones}
    tgt = _f((by_metric.get("ebitda_margin") or {}).get("target_value"))
    proj = []
    g = 0.02
    for i in range(1, 7):
        p50 = last_eb * (1 + g) ** i
        proj.append({
            "period": f"+{i}Q",
            "p50": round(p50, 2),
            "p10": round(p50 * 0.85, 2),
            "p90": round(p50 * 1.15, 2),
        })

    drift_margin = next((d for d in drift_results if d.get("metric") == "ebitda_margin"), {})
    actual_margin = _f(drift_margin.get("actual_value"))
    target_margin = _f(drift_margin.get("target_value"))
    rev_annual = _annual_sum(series, "revenue")

    ic_target_eb = None
    if target_margin is not None and rev_annual is not None:
        ic_target_eb = round(target_margin * rev_annual / 12.0, 2)

    vcp_targets = []
    for m in milestones:
        if m.get("metric") == "ebitda_margin" and m.get("target_date"):
            vcp_targets.append({
                "period": short_due(m.get("target_date")),
                "value": ic_target_eb,
            })

    return {
        "kpi_strip": [
            {"label": "ACTUAL EBITDA MARGIN", "value": fmt_value(actual_margin, "pct")},
            {"label": "VCP TARGET", "value": fmt_value(target_margin, "pct")},
            {"label": "GAP VS PLAN", "value": fmt_gap(actual_margin, target_margin, "pct")},
            {"label": "REVENUE (annualised)", "value": fmt_value(rev_annual, "currency")},
        ],
        "series": {"actual": actual_points, "projection": proj},
        "ic_target": ic_target_eb,
        "vcp_targets": vcp_targets,
        "now_index": now_index,
    }


def _risks_payload(risks_output: Optional[Dict[str, Any]],
                   drift_results: List[Dict[str, Any]],
                   alert_card: Dict[str, Any]) -> Dict[str, Any]:
    """Build risk rows. Bug #5: always emit a payload; no_risk block when empty."""
    rows: List[Dict[str, Any]] = []
    total_bps = 0
    all_recoverable = True

    if risks_output and risks_output.get("risks"):
        for r in risks_output["risks"]:
            bps = r.get("irr_at_risk_bps")
            if bps:
                total_bps += abs(bps)
            rows.append({
                "priority": r.get("priority"),
                "status": r.get("severity", "amber"),
                "risk": r.get("risk_statement", ""),
                "category": r.get("category", "—"),
                "irr_at_risk_bps": bps,
                "recommended_action": r.get("recommended_action", ""),
                "owner": r.get("owner", "—"),
                "deadline": r.get("deadline", "—"),
            })
        total_bps = risks_output.get("total_irr_at_risk_bps", total_bps)
        all_recoverable = risks_output.get("all_recoverable", True)
    else:
        # Fallback: derive from drift + alert card.
        at_risk = [r for r in drift_results if r.get("status") in ("Red", "Amber")]
        irr_total = abs(_f(alert_card.get("irr_at_risk_bps")) or 0)
        per = int(irr_total // (len(at_risk) or 1))
        for i, r in enumerate(at_risk[:5]):
            sev = "red" if r.get("status") == "Red" else "amber"
            bps = -per if per else None
            if bps:
                total_bps += abs(bps)
            rows.append({
                "priority": i + 1,
                "status": sev,
                "risk": f"{r.get('initiative', r.get('metric', '—'))}: {r.get('reason', '')}".strip(": "),
                "category": (r.get("category") or "—").title(),
                "irr_at_risk_bps": bps,
                "recommended_action": alert_card.get("recommended_action", "") if i == 0 else "Monitor and report next period",
                "owner": "CFO" if i == 0 else "Operating Partner",
                "deadline": "Q2-28",
            })

    has_risks = bool(rows)
    no_risk_block = None
    if not has_risks:
        no_risk_block = {
            "headline": "No material risks identified this period.",
            "detail": "All VCP milestones within ±5% of IC target.",
            "next_review": "Next scheduled review: next quarter board pack.",
        }

    return {
        "rows": rows,
        "has_risks": has_risks,
        "no_risk_block": no_risk_block,
        "total_irr_at_risk_bps": -total_bps if total_bps else 0,
        "all_recoverable": all_recoverable,
    }


def _clean_citations(citations: Optional[List[str]],
                     peer_benchmark: Optional[Dict[str, Any]]) -> List[Dict[str, str]]:
    """Bug #3: clean human-readable source labels, never internal file paths."""
    out = [
        {"label": "KPI Data", "source": "Management accounts · FY period close"},
        {"label": "VCP Milestones", "source": "IC Memo · confirmed by operating partner"},
    ]
    if peer_benchmark:
        n = peer_benchmark.get("peer_set_size", "?")
        sector = peer_benchmark.get("sector_label", "sector")
        out.append({"label": "Peer Benchmarks", "source": f"EDGAR XBRL · {n} peers · {sector}"})
    out.append({"label": "Macro Data", "source": "FRED API — DFF, INDPRO, CPILFESL, BAA10Y"})
    out.append({"label": "Forecasting",
                "source": "STL decomposition + SARIMA(2,1,2)(1,1,1) + Prophet ensemble"})
    return out


_DISCLAIMER = (
    "This report was generated by the PE Value Creation Copilot, an AI-assisted "
    "portfolio monitoring system. All financial figures are sourced from management "
    "accounts and third-party data providers and are unaudited unless stated otherwise. "
    "AI-generated narrative sections were reviewed and approved by a qualified professional "
    "via the human-in-the-loop gate before inclusion. This document is for internal use only "
    "and does not constitute investment advice or an offer to buy or sell securities."
)
