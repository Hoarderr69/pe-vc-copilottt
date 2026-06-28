"""
Alert & Synthesis Agent — second true AI agent in the monitoring pipeline.

Takes VCP drift scores (actual vs target gaps, per milestone) plus whatever
context is available (KPI snapshot, IRR scenarios, peer gaps) and synthesizes
them into a single structured alert card per company per monitoring run.

Two execution modes:
  - "azure_openai": live GPT-4o structured-output call (requires Azure config).
  - "offline_rule_based": deterministic fallback that derives the same output
    schema from the drift scores without any LLM. Clearly labelled so it is
    never mistaken for the LLM path.

Why an LLM here: the agent reasons across multiple signals simultaneously —
a revenue miss + a cost overrun + a delayed hire might together point to a
single root cause (wrong go-to-market motion) that no rule would catch.
Deterministic drift scoring tells you *what* drifted. The synthesis agent
tells you *why* and *what to do*.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from app.llm import azure_openai


LeverCategory = Literal[
    "pricing_and_revenue_growth",
    "cost_reduction",
    "working_capital_optimization",
    "operational_excellence",
    "talent_and_leadership",
    "strategic_m_and_a",
    "commercial_excellence",
    "other",
]

Severity = Literal["Red", "Amber", "Green"]


class MilestoneAtRisk(BaseModel):
    initiative: str
    metric: str
    gap_pct: Optional[float] = Field(
        default=None,
        description="Signed gap as decimal. Negative = below target.",
    )
    status: str


class AlertCard(BaseModel):
    """Structured output from the Alert & Synthesis Agent — one per company per run."""

    severity: Severity = Field(
        description="Overall severity across all milestones: Red / Amber / Green."
    )
    headline: str = Field(
        description=(
            "One punchy sentence capturing the most critical issue. "
            "E.g. 'EBITDA margin 340bps below plan as headcount growth outpaces revenue.'"
        )
    )
    irr_at_risk_bps: Optional[int] = Field(
        default=None,
        description=(
            "Estimated IRR delta vs underwritten case in basis points (negative = loss). "
            "Null if insufficient data to estimate."
        ),
    )
    milestones_at_risk: List[MilestoneAtRisk] = Field(
        default_factory=list,
        description="Milestones that are Red or Amber.",
    )
    root_cause: str = Field(
        description=(
            "2-3 sentences explaining what is happening and why. "
            "Cite specific metrics and periods."
        )
    )
    recommended_action: str = Field(
        description=(
            "The specific operating lever the deal team should pull. "
            "One clear action, not a list."
        )
    )
    lever_category: LeverCategory
    citations: List[str] = Field(
        default_factory=list,
        description=(
            "Source references supporting each claim: "
            "financial file path, VCP milestone name, period, EDGAR filing, etc."
        ),
    )
    synthesis_mode: str = "azure_openai"


SYSTEM_PROMPT = """\
You are a private-equity operating partner analyst. You receive a VCP \
(Value Creation Plan) drift report for a single portfolio company and synthesize \
it into a clear, actionable alert card that will be reviewed by the deal team.

Your job:
1. Assess the OVERALL severity (Red/Amber/Green) across ALL milestones — the worst \
single signal drives severity.
2. Write a concise headline capturing the most critical issue.
3. Identify the root cause in 2-3 sentences — what is actually happening and why. \
Cite specific metrics and periods.
4. Recommend ONE specific operating lever — be direct, not comprehensive.
5. Estimate IRR at risk in basis points where gap percentages make it inferable \
(rough order-of-magnitude is fine; null if you can't support the number).
6. List each milestone that is Red or Amber.
7. Cite the specific sources (financial file, VCP milestone name, period) that \
support your claims.

SEVERITY RULES:
- Red:   any financial milestone >10% below target, OR two or more Amber milestones
- Amber: a financial milestone 5–10% below target, OR a key operational/org milestone at risk
- Green: all milestones within 5% of target (±5%) or better

LEVER CATEGORIES — pick exactly one:
  pricing_and_revenue_growth  : revenue shortfall, pricing weakness, new logo gaps
  cost_reduction              : EBITDA margin compression from SG&A/COGS overruns
  working_capital_optimization: AR/AP/inventory issues, cash conversion cycle
  operational_excellence      : ERP, process, efficiency, reporting
  talent_and_leadership       : key hire delays, org design gaps
  strategic_m_and_a           : add-on acquisition thesis elements
  commercial_excellence       : go-to-market, retention, cross-sell
  other                       : catch-all

Be precise and direct. Operating partners read dozens of these. \
One clear insight beats a comprehensive summary every time.\
"""


def _build_user_prompt(
    company_name: str,
    drift_scores: List[Dict[str, Any]],
    kpi_snapshot: Optional[Dict[str, Any]],
    irr_scenarios: Optional[List[Dict[str, Any]]],
    peer_composite: Optional[Dict[str, Any]],
) -> str:
    lines = [f"COMPANY: {company_name}\n"]

    lines.append("VCP DRIFT SCORES:")
    for r in drift_scores:
        gap_str = (
            f"{r['gap_pct']:.1%}" if r.get("gap_pct") is not None else "n/a"
        )
        lines.append(
            f"  [{r['status']}] {r['initiative']} | metric={r['metric']} "
            f"| actual={r['actual_value']} vs target={r['target_value']} "
            f"| gap={gap_str} | {r['reason']}"
        )

    if kpi_snapshot:
        lines.append("\nLATEST KPI SNAPSHOT:")
        for k, v in kpi_snapshot.items():
            if k not in {"company_id", "company_name", "source_path"}:
                lines.append(f"  {k}: {v}")

    if irr_scenarios:
        lines.append("\nIRR SCENARIOS:")
        for s in irr_scenarios[:3]:
            lines.append(f"  {s}")

    if peer_composite:
        lines.append("\nPEER BENCHMARKS:")
        for k, v in peer_composite.items():
            lines.append(f"  {k}: {v}")

    lines.append(
        "\nSynthesize the above into a structured alert card for the deal team."
    )
    return "\n".join(lines)


def synthesize_llm(
    company_id: str,
    company_name: str,
    drift_scores: List[Dict[str, Any]],
    kpi_snapshot: Optional[Dict[str, Any]] = None,
    irr_scenarios: Optional[List[Dict[str, Any]]] = None,
    peer_composite: Optional[Dict[str, Any]] = None,
) -> AlertCard:
    """Live Azure OpenAI GPT-4o structured-output synthesis."""
    client = azure_openai.get_client()
    model = azure_openai.deployment_name()

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": _build_user_prompt(
                company_name, drift_scores, kpi_snapshot, irr_scenarios, peer_composite
            ),
        },
    ]

    parse_fn = (
        getattr(client.chat.completions, "parse", None)
        or client.beta.chat.completions.parse
    )
    completion = parse_fn(
        model=model,
        messages=messages,
        response_format=AlertCard,
        temperature=0,
    )

    parsed: AlertCard = completion.choices[0].message.parsed
    parsed.synthesis_mode = "azure_openai"
    return parsed


# ---------------------------------------------------------------------------
# Offline rule-based fallback — no credentials needed.
# Derives the same AlertCard schema purely from drift score arithmetic.
# ---------------------------------------------------------------------------

_METRIC_TO_LEVER: Dict[str, LeverCategory] = {
    "annual_revenue": "pricing_and_revenue_growth",
    "ebitda_margin": "cost_reduction",
    "net_debt_to_ebitda": "working_capital_optimization",
    "sga_ratio": "cost_reduction",
    "cro_hired": "talent_and_leadership",
    "reporting_cadence_upgrade_complete": "operational_excellence",
}


def _overall_severity(drift_scores: List[Dict[str, Any]]) -> Severity:
    red = any(r["status"] == "Red" for r in drift_scores)
    amber_count = sum(1 for r in drift_scores if r["status"] == "Amber")

    if red or amber_count >= 2:
        return "Red"
    if amber_count == 1:
        return "Amber"
    return "Green"


def synthesize_offline(
    company_id: str,
    company_name: str,
    drift_scores: List[Dict[str, Any]],
    kpi_snapshot: Optional[Dict[str, Any]] = None,
    irr_scenarios: Optional[List[Dict[str, Any]]] = None,
    peer_composite: Optional[Dict[str, Any]] = None,
) -> AlertCard:
    """Deterministic offline synthesis from drift scores only."""

    at_risk = [
        r for r in drift_scores if r["status"] in {"Red", "Amber"}
    ]

    severity = _overall_severity(drift_scores)

    # Determine primary lever from the worst metric
    primary_metric = None
    worst_gap = 0.0
    for r in at_risk:
        gap = r.get("gap_pct")
        if gap is not None and abs(gap) > abs(worst_gap):
            worst_gap = gap
            primary_metric = r.get("metric")

    lever: LeverCategory = _METRIC_TO_LEVER.get(primary_metric or "", "other")

    # Build headline
    if at_risk:
        worst = min(at_risk, key=lambda r: r.get("gap_pct") or 0)
        metric_label = worst["metric"].replace("_", " ")
        gap_pct = worst.get("gap_pct")
        gap_str = f"{gap_pct:.1%}" if gap_pct is not None else "unknown gap"
        headline = (
            f"{company_name}: {metric_label} is {gap_str} below VCP target "
            f"as of {worst.get('latest_period_end', 'latest period')}."
        )
    else:
        headline = f"{company_name}: all VCP milestones on track."

    # Root cause (deterministic)
    if at_risk:
        parts = []
        for r in at_risk[:2]:
            gap_pct = r.get("gap_pct")
            gap_str = f"{gap_pct:.1%}" if gap_pct is not None else "below target"
            parts.append(
                f"{r['initiative']} is {gap_str} vs the VCP target "
                f"(actual={r['actual_value']}, target={r['target_value']})"
            )
        root_cause = "; ".join(parts) + ". Review underlying drivers and operating levers."
    else:
        root_cause = "No milestones are drifting materially at this time."

    recommended_action = (
        f"Convene operating review on {lever.replace('_', ' ')} levers."
        if at_risk
        else "Maintain current trajectory; no action required."
    )

    milestones_at_risk = [
        MilestoneAtRisk(
            initiative=r["initiative"],
            metric=r["metric"],
            gap_pct=r.get("gap_pct"),
            status=r["status"],
        )
        for r in at_risk
    ]

    citations = list(
        {r["source_path"] for r in at_risk if r.get("source_path")}
    ) + [
        f"VCP milestone: {r['initiative']}" for r in at_risk
    ]

    return AlertCard(
        severity=severity,
        headline=headline,
        irr_at_risk_bps=None,
        milestones_at_risk=milestones_at_risk,
        root_cause=root_cause,
        recommended_action=recommended_action,
        lever_category=lever,
        citations=citations,
        synthesis_mode="offline_rule_based",
    )


def synthesize(
    company_id: str,
    company_name: str,
    drift_scores: List[Dict[str, Any]],
    kpi_snapshot: Optional[Dict[str, Any]] = None,
    irr_scenarios: Optional[List[Dict[str, Any]]] = None,
    peer_composite: Optional[Dict[str, Any]] = None,
    prefer_llm: bool = True,
) -> AlertCard:
    """Synthesize using GPT-4o when configured, else the offline rule-based fallback."""
    if prefer_llm and azure_openai.is_configured():
        return synthesize_llm(
            company_id,
            company_name,
            drift_scores,
            kpi_snapshot,
            irr_scenarios,
            peer_composite,
        )
    return synthesize_offline(
        company_id,
        company_name,
        drift_scores,
        kpi_snapshot,
        irr_scenarios,
        peer_composite,
    )
