from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List


METRIC_WEIGHTS = {
    "net_debt_to_ebitda": 5,
    "ebitda_margin": 4,
    "annual_revenue": 3,
}


SEVERITY_WEIGHTS = {
    "Red": 10,
    "Amber": 5,
    "Green": 0,
}


def score_alert(alert: Dict[str, Any]) -> int:
    severity = alert.get("severity", "Green")
    metric = alert.get("metric", "")

    return SEVERITY_WEIGHTS.get(severity, 0) + METRIC_WEIGHTS.get(metric, 1)


def determine_priority(score: int, red_count: int) -> str:
    if red_count >= 2 or score >= 25:
        return "P1"
    if red_count == 1 or score >= 12:
        return "P2"
    return "P3"


def recommended_action_for_metrics(metrics: List[str]) -> str:
    metric_set = set(metrics)

    if "net_debt_to_ebitda" in metric_set and "ebitda_margin" in metric_set:
        return (
            "Review leverage headroom, cash generation, SG&A actions, and EBITDA recovery plan with CFO."
        )

    if "ebitda_margin" in metric_set and "annual_revenue" in metric_set:
        return (
            "Review revenue execution, pricing discipline, and cost base with CEO/CFO."
        )

    if "annual_revenue" in metric_set:
        return (
            "Review pipeline quality, sales execution, pricing, and customer retention plan."
        )

    if "ebitda_margin" in metric_set:
        return (
            "Review gross margin, SG&A run-rate, hiring pace, and discretionary spend."
        )

    if "net_debt_to_ebitda" in metric_set:
        return (
            "Review debt headroom, free cash flow, cash sweep assumptions, and liquidity risk."
        )

    return "Review underlying VCP milestone drift and assign owner follow-up."


def build_headline(company_name: str, red_count: int, amber_count: int, metrics: List[str]) -> str:
    metric_text = ", ".join(metrics)

    if red_count >= 2:
        return (
            f"{company_name} requires immediate attention: multiple VCP metrics are Red "
            f"({metric_text})."
        )

    if red_count == 1:
        return (
            f"{company_name} has one Red VCP drift item requiring follow-up "
            f"({metric_text})."
        )

    if amber_count > 0:
        return (
            f"{company_name} has Amber VCP drift requiring monitoring "
            f"({metric_text})."
        )

    return f"{company_name} is currently on track across evaluated VCP metrics."


def build_portfolio_action_inbox(
    portfolio_summary_path: str = "data/processed/portfolio_vcp_monitoring_summary.json",
    output_path: str = "data/processed/portfolio_action_inbox.json",
) -> Dict[str, Any]:
    path = Path(portfolio_summary_path)

    if not path.exists():
        raise FileNotFoundError(f"Portfolio summary not found: {portfolio_summary_path}")

    portfolio = json.loads(path.read_text(encoding="utf-8"))

    companies = portfolio.get("companies", [])

    action_items: List[Dict[str, Any]] = []

    for company in companies:
        alerts = company.get("alerts", [])

        if not alerts:
            continue

        red_alerts = [a for a in alerts if a.get("severity") == "Red"]
        amber_alerts = [a for a in alerts if a.get("severity") == "Amber"]

        total_score = sum(score_alert(alert) for alert in alerts)
        metrics = sorted({alert.get("metric") for alert in alerts if alert.get("metric")})

        action_items.append(
            {
                "company_id": company.get("company_id"),
                "company_name": company.get("company_name"),
                "priority_score": total_score,
                "priority": determine_priority(total_score, len(red_alerts)),
                "red_alert_count": len(red_alerts),
                "amber_alert_count": len(amber_alerts),
                "alert_count": len(alerts),
                "primary_risks": metrics,
                "headline": build_headline(
                    company_name=company.get("company_name"),
                    red_count=len(red_alerts),
                    amber_count=len(amber_alerts),
                    metrics=metrics,
                ),
                "recommended_action": recommended_action_for_metrics(metrics),
                "evidence": [
                    {
                        "metric": alert.get("metric"),
                        "severity": alert.get("severity"),
                        "summary": alert.get("summary"),
                        "source_path": alert.get("source_path"),
                        "source_column": alert.get("source_column"),
                    }
                    for alert in alerts
                ],
            }
        )

    action_items = sorted(
        action_items,
        key=lambda item: item["priority_score"],
        reverse=True,
    )

    for idx, item in enumerate(action_items, start=1):
        item["priority_rank"] = idx

    payload = {
        "portfolio_company_count": portfolio.get("portfolio_company_count"),
        "total_alerts": portfolio.get("total_alerts"),
        "severity_counts": portfolio.get("severity_counts"),
        "action_item_count": len(action_items),
        "action_items": action_items,
    }

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    return payload