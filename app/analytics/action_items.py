"""
Turn a VCP drift result into a HITL action item.

Shared between the live portfolio roll-up (app/api/vcp_routes.py) and the
monitoring graph (app/graph/vcp_nodes.py) so both produce identically-shaped
queue items for app.workflows.hitl_queue.refresh_hitl_review_queue_from_action_items.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

_METRIC_WEIGHTS = {"net_debt_to_ebitda": 5, "ebitda_margin": 4, "annual_revenue": 3}
_SEVERITY_WEIGHTS = {"Red": 10, "Amber": 5, "Green": 0}


def build_action_item(company_id: str, company_name: str, drift: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    # Build from drift results — each result is a metric-level assessment
    results = [r for r in drift.get("results", []) if r.get("status") in ("Red", "Amber", "Green")]
    if not results:
        return None
    red = [r for r in results if r.get("status") == "Red"]
    amber = [r for r in results if r.get("status") == "Amber"]
    if not red and not amber:
        return None  # all green — no action item needed
    metrics = sorted({r.get("metric") for r in results if r.get("metric") and r.get("status") in ("Red", "Amber")})
    score = sum(_SEVERITY_WEIGHTS.get(r.get("status", ""), 0) + _METRIC_WEIGHTS.get(r.get("metric", ""), 1) for r in red + amber)

    if len(red) >= 2 or score >= 25:
        priority = "P1"
    elif len(red) == 1 or score >= 12:
        priority = "P2"
    else:
        priority = "P3"

    metric_set = set(metrics)
    if "net_debt_to_ebitda" in metric_set and "ebitda_margin" in metric_set:
        action = "Review leverage headroom, cash generation, SG&A actions, and EBITDA recovery plan with CFO."
    elif "ebitda_margin" in metric_set and "annual_revenue" in metric_set:
        action = "Review revenue execution, pricing discipline, and cost base with CEO/CFO."
    elif "annual_revenue" in metric_set:
        action = "Review pipeline quality, sales execution, pricing, and customer retention plan."
    elif "ebitda_margin" in metric_set:
        action = "Review gross margin, SG&A run-rate, hiring pace, and discretionary spend."
    elif "net_debt_to_ebitda" in metric_set:
        action = "Review debt headroom, free cash flow, cash sweep assumptions, and liquidity risk."
    else:
        action = "Review underlying VCP milestone drift and assign owner follow-up."

    if len(red) >= 2:
        headline = f"{company_name} requires immediate attention: multiple VCP metrics are Red ({', '.join(metrics)})."
    elif len(red) == 1:
        headline = f"{company_name} has one Red VCP drift item requiring follow-up ({', '.join(metrics)})."
    elif amber:
        headline = f"{company_name} has Amber VCP drift requiring monitoring ({', '.join(metrics)})."
    else:
        headline = f"{company_name} is currently on track across evaluated VCP metrics."

    # Cite the underlying Red/Amber drift results as evidence (metric + source).
    evidence = [
        {
            "metric": r.get("metric"),
            "severity": r.get("status"),
            "summary": r.get("reason"),
            "source_path": r.get("source_path"),
            "source_column": r.get("source_column"),
        }
        for r in sorted(red + amber, key=lambda r: 0 if r.get("status") == "Red" else 1)
    ]

    return {
        "company_id": company_id,
        "company_name": company_name,
        "priority_score": score,
        "priority": priority,
        "red_alert_count": len(red),
        "amber_alert_count": len(amber),
        "alert_count": len(red) + len(amber),
        "primary_risks": metrics,
        "headline": headline,
        "recommended_action": action,
        "evidence": evidence,
    }
