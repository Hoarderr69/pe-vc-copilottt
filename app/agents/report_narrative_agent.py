"""
Report Narrative Agent — third true AI agent in the monitoring pipeline.

Receives all structured signals (VCP drift, alert card, peer benchmarks, IRR)
and generates board-quality executive prose for the PDF board pack.

Two execution modes:
  - "azure_openai": live GPT-4o structured-output call.
  - "offline_rule_based": deterministic template-based prose derived from the
    structured data. Clearly labelled; never mistaken for the LLM path.

Why an LLM here: board-ready prose requires judgment — knowing which signal
is the most important to lead with, how to frame a miss without being
alarmist, and what context makes an operating partner act vs. defer.
The same data points can mean very different things depending on stage,
sector, and macro context. Rules produce formulaic output; this agent
produces something an operating partner would actually say in a meeting.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from app.llm import azure_openai


class NarrativeOutput(BaseModel):
    """Structured prose output from the Report Narrative Agent."""

    exec_summary: str = Field(
        description=(
            "2–3 sentence executive summary. Lead with the single most important "
            "takeaway. Include a specific number. Write for a board member who has "
            "30 seconds before the meeting starts. No jargon, no hedging."
        )
    )
    key_risks: List[str] = Field(
        description=(
            "Exactly 3 specific, numbered risk statements. Each must cite a metric "
            "and a number. Format: 'Revenue growth of X% is tracking Y% below the "
            "VCP target of Z%, ...' Not vague — tied to the actual data."
        ),
        min_length=3,
        max_length=3,
    )
    priority_action: str = Field(
        description=(
            "One specific action the deal team must take this quarter. "
            "Not a category — an actual step: who does what by when. "
            "E.g. 'Convene a commercial review with the CEO by end of July to "
            "diagnose the NRR compression and agree a pricing re-architecture plan.'"
        )
    )
    board_talking_points: List[str] = Field(
        description=(
            "2–3 bullet points for the operating partner to raise in the board meeting. "
            "These are questions or positions, not summaries. "
            "E.g. 'What is the current NRR by customer cohort and how has it trended "
            "since the ERP migration completed?'"
        ),
        min_length=2,
        max_length=3,
    )
    confidence_statement: str = Field(
        description=(
            "One sentence on data completeness and any caveats. "
            "E.g. 'All figures sourced from management accounts through May 2027; "
            "EBITDA margin is unaudited.' If data is complete and verified, say so."
        )
    )
    narrative_mode: str = "azure_openai"


_SHARED_RULES = """
VOICE:
- Direct, institutional, no passive voice
- Numbers in every key sentence (actual figures, not percentages alone)
- Frame problems as solvable, but be honest about severity
- Write for an IC-level reader who has seen hundreds of board packs

OUTPUT RULES:
- exec_summary: 2-3 sentences. Lead with the verdict (Red/Amber/Green + why).
  Include the most important specific number. End with the consequence if not addressed.
- key_risks: Exactly 3. Each one sentence. Must cite metric name, actual value,
  target value, and gap. Ordered worst-first.
- priority_action: One sentence. Specific actor, specific action, specific deadline.
- board_talking_points: 2-3 questions or positions to raise at the board.
  These must be diagnostic -- they should surface information the data cannot answer.
- confidence_statement: One sentence. Name the data source, the period covered,
  and any known gaps or caveats. Be honest about what is and is not verified.

NEVER:
- Use phrases like "it is important to note", "it should be mentioned", "going forward"
- Write more than the specified length for any field
- Invent numbers not present in the input
- Round VCP targets without noting they are rounded"""

SYSTEM_PROMPT_BOARD_READY = (
    "You are a senior private equity operating partner preparing board materials for a "
    "portfolio company review. You write with authority, precision, and economy. "
    "Every sentence must contain a specific fact or judgment -- never generic filler. "
    "Audience: independent board directors and limited partners. Tone is institutional, "
    "objective, and polished -- suitable for external distribution. Approved actions only; "
    "no speculative open questions."
    + _SHARED_RULES
)

SYSTEM_PROMPT_MANAGEMENT_INTERNAL = (
    "You are a senior private equity operating partner preparing an INTERNAL working document "
    "for the deal team. Write candidly and diagnostically -- this document is NOT for LP or board "
    "distribution. Surface the uncomfortable truths, flag root-cause ambiguities, and include "
    "open diagnostic questions the deal team must answer before the next board meeting. "
    "Do not sanitise the language. Every sentence must contain a specific fact, judgment, or "
    "open question that forces accountability. Preferred style: direct, blunt, diagnostic."
    + _SHARED_RULES
)

# Default (board-ready) kept as the original name for backwards compatibility
SYSTEM_PROMPT = SYSTEM_PROMPT_BOARD_READY


def _build_user_prompt(
    company_name: str,
    period: str,
    alert_severity: str,
    alert_headline: str,
    alert_root_cause: str,
    alert_recommended_action: str,
    lever_category: str,
    irr_at_risk_bps: Optional[int],
    drift_results: List[Dict[str, Any]],
    milestones: List[Dict[str, Any]],
    peer_benchmark: Optional[Dict[str, Any]],
    irr_scenarios: Optional[List[Dict[str, Any]]],
) -> str:
    lines = [
        f"COMPANY: {company_name}",
        f"MONITORING PERIOD: {period}",
        f"OVERALL SEVERITY: {alert_severity}",
        f"ALERT HEADLINE: {alert_headline}",
        f"ROOT CAUSE: {alert_root_cause}",
        f"RECOMMENDED LEVER: {lever_category.replace('_', ' ')}",
    ]

    if irr_at_risk_bps is not None:
        lines.append(f"IRR AT RISK: {irr_at_risk_bps:+d} bps vs underwritten case")

    lines.append("\nVCP MILESTONE DRIFT:")
    for r in drift_results:
        gap_str = f"{r['gap_pct']:.1%}" if r.get("gap_pct") is not None else "n/a"
        actual_str = (
            f"£{r['actual_value'] / 1e6:.1f}M"
            if isinstance(r.get("actual_value"), (int, float)) and r["actual_value"] > 1e4
            else str(r.get("actual_value", "n/a"))
        )
        target_str = (
            f"£{r['target_value'] / 1e6:.1f}M"
            if isinstance(r.get("target_value"), (int, float)) and r["target_value"] > 1e4
            else str(r.get("target_value", "n/a"))
        )
        lines.append(
            f"  [{r['status']}] {r['initiative']} | {r['metric']}"
            f" | actual={actual_str} vs target={target_str} | gap={gap_str}"
        )

    if peer_benchmark and peer_benchmark.get("results"):
        lines.append(f"\nSECTOR BENCHMARKING ({peer_benchmark.get('sector_label', 'sector')}, "
                     f"N={peer_benchmark.get('peer_set_size', '?')} peers):")
        for b in peer_benchmark["results"]:
            gap_pct = b.get("gap_pct", 0)
            lines.append(
                f"  [{b['status']}] {b['metric']}"
                f" | company={b['company_value']:.1%} vs median={b['sector_median']:.1%}"
                f" | gap={gap_pct:+.1%}"
            )

    if irr_scenarios:
        lines.append("\nIRR SCENARIOS:")
        for s in irr_scenarios:
            irr_str = f"{s.get('irr_percent', 0):.1f}%" if s.get("irr_percent") is not None else "n/a"
            moic_str = f"{s.get('moic', 0):.2f}x" if s.get("moic") is not None else "n/a"
            lines.append(
                f"  [{s.get('scenario_status', '?')}] {s.get('scenario', '?').upper()}"
                f" | IRR={irr_str} | MOIC={moic_str}"
                f" | IRR gap vs IC={s.get('irr_gap_vs_ic_bps', 'n/a')} bps"
            )

    lines.append(f"\nPRIORITY ACTION FROM ALERT AGENT: {alert_recommended_action}")
    lines.append(
        "\nGenerate board-quality narrative prose for this monitoring report."
    )
    return "\n".join(lines)


def generate_llm(
    company_name: str,
    period: str,
    alert_severity: str,
    alert_headline: str,
    alert_root_cause: str,
    alert_recommended_action: str,
    lever_category: str,
    drift_results: List[Dict[str, Any]],
    milestones: Optional[List[Dict[str, Any]]] = None,
    peer_benchmark: Optional[Dict[str, Any]] = None,
    irr_scenarios: Optional[List[Dict[str, Any]]] = None,
    irr_at_risk_bps: Optional[int] = None,
    tone: str = "board_ready",
) -> NarrativeOutput:
    client = azure_openai.get_client()
    model = azure_openai.deployment_name()

    system_prompt = (
        SYSTEM_PROMPT_MANAGEMENT_INTERNAL
        if tone == "management_internal"
        else SYSTEM_PROMPT_BOARD_READY
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {
            "role": "user",
            "content": _build_user_prompt(
                company_name=company_name,
                period=period,
                alert_severity=alert_severity,
                alert_headline=alert_headline,
                alert_root_cause=alert_root_cause,
                alert_recommended_action=alert_recommended_action,
                lever_category=lever_category,
                irr_at_risk_bps=irr_at_risk_bps,
                drift_results=drift_results,
                milestones=milestones or [],
                peer_benchmark=peer_benchmark,
                irr_scenarios=irr_scenarios,
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
        response_format=NarrativeOutput,
        temperature=0,
        max_completion_tokens=1500,
        timeout=60,
    )

    result: NarrativeOutput = completion.choices[0].message.parsed
    result.narrative_mode = "azure_openai"
    return result


def generate_offline(
    company_name: str,
    period: str,
    alert_severity: str,
    alert_headline: str,
    alert_root_cause: str,
    alert_recommended_action: str,
    lever_category: str,
    drift_results: List[Dict[str, Any]],
    milestones: Optional[List[Dict[str, Any]]] = None,
    peer_benchmark: Optional[Dict[str, Any]] = None,
    irr_scenarios: Optional[List[Dict[str, Any]]] = None,
    irr_at_risk_bps: Optional[int] = None,
    tone: str = "board_ready",
) -> NarrativeOutput:
    """Deterministic narrative from structured data — no LLM required."""

    red = [r for r in drift_results if r.get("status") == "Red"]
    amber = [r for r in drift_results if r.get("status") == "Amber"]
    at_risk = red + amber
    on_track = [r for r in drift_results if r.get("status") == "Green"]
    total = len(drift_results)

    def fmt_val(v: Any) -> str:
        if isinstance(v, float) and v < 1:
            return f"{v:.1%}"
        if isinstance(v, (int, float)) and v > 1e4:
            return f"£{v / 1e6:.1f}M"
        return str(v)

    # Executive summary
    at_risk_count = len(at_risk)
    on_track_count = len(on_track)
    irr_clause = (
        f" IRR is tracking {irr_at_risk_bps:+d} bps vs the underwritten case."
        if irr_at_risk_bps is not None
        else ""
    )
    if tone == "management_internal":
        exec_summary = (
            f"[INTERNAL — NOT FOR DISTRIBUTION] {company_name} is {alert_severity} for {period}. "
            f"{at_risk_count}/{total} VCP milestones off-track; {on_track_count} on-track.{irr_clause} "
            f"Root cause flagged: {alert_root_cause} — deal team must confirm this diagnosis before the next board. "
            f"Do not present this framing externally without sign-off."
        )
    else:
        exec_summary = (
            f"{company_name} is rated {alert_severity} for {period}: "
            f"{at_risk_count} of {total} VCP milestones are off-track, with {on_track_count} on-track.{irr_clause} "
            f"{alert_root_cause}"
        )

    # Key risks
    key_risks: List[str] = []
    for r in at_risk[:3]:
        gap_str = f"{r['gap_pct']:.1%}" if r.get("gap_pct") is not None else "below target"
        actual_str = fmt_val(r.get("actual_value", "n/a"))
        target_str = fmt_val(r.get("target_value", "n/a"))
        key_risks.append(
            f"{r['initiative']}: actual {actual_str} vs VCP target {target_str} "
            f"({gap_str} gap) — status {r['status']}."
        )
    while len(key_risks) < 3:
        key_risks.append(
            "No additional off-track milestones identified in the current monitoring period."
        )

    # Priority action
    priority_action = alert_recommended_action or (
        f"Convene operating review on {lever_category.replace('_', ' ')} "
        f"levers for {company_name} before next board meeting."
    )

    # Talking points — board-ready = polished questions; management-internal = candid diagnostics
    if tone == "management_internal":
        talking_points: List[str] = [
            f"UNRESOLVED: Is the {lever_category.replace('_', ' ')} miss a management execution failure "
            f"or a flawed VCP assumption? Deal team must clarify before the board meeting.",
            f"ROOT CAUSE CHECK: Are the {at_risk_count} off-track milestones driven by the same "
            f"underlying bottleneck, or are they independent failures? Answer before the next IC update.",
        ]
    else:
        talking_points = [
            f"What specific actions has management taken since the last board meeting "
            f"to address the {lever_category.replace('_', ' ')} shortfall?",
            f"Are the {at_risk_count} off-track milestones linked to a common root cause "
            f"(e.g. a single go-to-market motion, a delayed hire, or a process bottleneck)?",
        ]
    if peer_benchmark:
        status_counts = {}
        for b in peer_benchmark.get("results", []):
            s = b.get("status", "Unknown")
            status_counts[s] = status_counts.get(s, 0) + 1
        underperform_count = status_counts.get("Underperform", 0)
        if underperform_count > 0:
            sector = peer_benchmark.get("sector_label", "sector")
            talking_points.append(
                f"The company is underperforming {sector} peers on {underperform_count} of "
                f"{len(peer_benchmark.get('results', []))} benchmark metrics — "
                f"is this a company-specific execution issue or a sector-wide headwind?"
            )

    board_talking_points = talking_points[:3]

    # Confidence statement
    if peer_benchmark:
        sector = peer_benchmark.get("sector_label", "sector")
        n = peer_benchmark.get("peer_set_size", "?")
        confidence_statement = (
            f"Financial figures sourced from management accounts for {period}; "
            f"peer benchmarks based on {n} {sector} companies from EDGAR public filings. "
            "EBITDA figures are unaudited."
        )
    else:
        confidence_statement = (
            f"Financial figures sourced from management accounts for {period}; "
            "all EBITDA and revenue figures are unaudited management estimates."
        )

    return NarrativeOutput(
        exec_summary=exec_summary,
        key_risks=key_risks,
        priority_action=priority_action,
        board_talking_points=board_talking_points[:3],
        confidence_statement=confidence_statement,
        narrative_mode="offline_rule_based",
    )


def generate(
    company_name: str,
    period: str,
    alert_severity: str,
    alert_headline: str,
    alert_root_cause: str,
    alert_recommended_action: str,
    lever_category: str,
    drift_results: List[Dict[str, Any]],
    milestones: Optional[List[Dict[str, Any]]] = None,
    peer_benchmark: Optional[Dict[str, Any]] = None,
    irr_scenarios: Optional[List[Dict[str, Any]]] = None,
    irr_at_risk_bps: Optional[int] = None,
    prefer_llm: bool = True,
    tone: str = "board_ready",
) -> NarrativeOutput:
    """Generate narrative using GPT-4o when configured; fall back to offline."""
    kwargs = dict(
        company_name=company_name,
        period=period,
        alert_severity=alert_severity,
        alert_headline=alert_headline,
        alert_root_cause=alert_root_cause,
        alert_recommended_action=alert_recommended_action,
        lever_category=lever_category,
        drift_results=drift_results,
        milestones=milestones,
        peer_benchmark=peer_benchmark,
        irr_scenarios=irr_scenarios,
        irr_at_risk_bps=irr_at_risk_bps,
        tone=tone,
    )
    if prefer_llm and azure_openai.is_configured():
        try:
            return generate_llm(**kwargs)
        except Exception as exc:  # noqa: BLE001
            # Any LLM failure (timeout, length-limit/parse error, auth) must not
            # 500 the report — degrade gracefully to the deterministic narrative.
            print(f"[NarrativeAgent] narrative LLM failed, falling back: {exc}")
    return generate_offline(**kwargs)


# ===========================================================================
# Spec prompts (Report_Module_Spec.md §8) + Board Questions + Structured Risks
# ===========================================================================

EXEC_SUMMARY_PROMPT = """
You are writing the executive summary for a Private Equity board pack.
The audience is a board of directors and the GP operating partner team.
Write formally, concisely, and without hedging language.

COMPANY: {company_name} ({sector})
PERIOD: {period}
REPORT DATE: {report_date}

FINANCIAL PERFORMANCE:
{kpi_table_json}

VCP MILESTONE STATUS:
{vcp_summary_json}

IRR SCENARIOS:
Bear: {irr_bear}%  Base: {irr_base}%  Bull: {irr_bull}%  IC: {irr_ic}%

SECTOR BENCHMARK POSITION:
{benchmark_json}

TOP RISKS (from alert agent):
{risks_json}

Write exactly 4 sections in this order:
1. SITUATION (2-3 sentences): Revenue and EBITDA performance vs IC targets. State numbers.
2. KEY RISKS (3 bullet points): One sentence each. Name specific metrics and gaps.
3. PRIORITY ACTION (1 sentence): Name the person responsible (CFO/CEO/COO), the action, and the deadline.
4. Do not include a heading for section 4 — instead write one sentence on the IRR outlook.

Rules:
- Use past tense for performance ("achieved", "delivered", "exceeded")
- Use future tense for actions ("must implement", "will review")
- Never use "may", "might", "could" or other hedging language
- Every number cited must appear in the data provided above
- Maximum 180 words total
- Tone: Board-ready (formal, direct, no jargon)
"""

BOARD_QUESTIONS_PROMPT = """
You are preparing three questions for an operating partner to ask at a PE board meeting.

Context:
- Company: {company_name}
- Period: {period}
- The operating partner has already read the board pack
- These questions should be ones management cannot easily deflect
- They should probe the gaps identified in the data

Risks and gaps identified:
{risks_and_gaps_json}

VCP milestones at risk or missing data:
{vcp_issues_json}

Write exactly 3 questions.
Rules:
- Each question names a specific metric, milestone, or decision point
- Questions cannot be answered with "yes" or "no"
- Questions should reveal whether management has a real plan, not just awareness of the problem
- Do not use "How do you plan to..." — use "What is..." or "When will..." or "What specifically..."
- Maximum 30 words per question
"""


class _BoardQuestionsOutput(BaseModel):
    questions: List[str] = Field(min_length=3, max_length=3)


class RiskRow(BaseModel):
    """Single row of the Risks & Recommended Actions table (spec §8)."""
    priority: int
    severity: Literal["red", "amber", "green"]
    risk_statement: str            # max 15 words
    category: str                  # Cost efficiency / Operational / Commercial / etc.
    irr_at_risk_bps: Optional[int] = None  # None if not quantifiable
    recommended_action: str        # max 20 words
    owner: str                     # CFO / CEO / COO / Board
    deadline: str                  # "Q2-28" format


class RisksOutput(BaseModel):
    risks: List[RiskRow] = Field(default_factory=list)
    total_irr_at_risk_bps: int = 0
    all_recoverable: bool = True
    no_risk_statement: Optional[str] = None


def _risks_and_gaps_json(drift_results: List[Dict[str, Any]]) -> str:
    import json
    payload = [
        {
            "initiative": r.get("initiative"),
            "metric": r.get("metric"),
            "status": r.get("status"),
            "actual": r.get("actual_value"),
            "target": r.get("target_value"),
            "gap_pct": r.get("gap_pct"),
            "reason": r.get("reason"),
        }
        for r in drift_results
    ]
    return json.dumps(payload, default=str, indent=2)


# ---------------------------------------------------------------------------
# Board questions
# ---------------------------------------------------------------------------

def generate_board_questions_llm(
    company_name: str,
    period: str,
    drift_results: List[Dict[str, Any]],
    vcp_issues: Optional[List[Dict[str, Any]]] = None,
) -> List[str]:
    import json
    client = azure_openai.get_client()
    model = azure_openai.deployment_name()
    prompt = BOARD_QUESTIONS_PROMPT.format(
        company_name=company_name,
        period=period,
        risks_and_gaps_json=_risks_and_gaps_json(drift_results),
        vcp_issues_json=json.dumps(vcp_issues or [], default=str),
    )
    parse_fn = (
        getattr(client.chat.completions, "parse", None)
        or client.beta.chat.completions.parse
    )
    completion = parse_fn(
        model=model,
        messages=[
            {"role": "system", "content": "You prepare sharp, specific board meeting questions."},
            {"role": "user", "content": prompt},
        ],
        response_format=_BoardQuestionsOutput,
        temperature=0,
        max_completion_tokens=800,
        timeout=60,
    )
    return completion.choices[0].message.parsed.questions[:3]


def generate_board_questions_offline(
    company_name: str,
    period: str,
    drift_results: List[Dict[str, Any]],
    vcp_issues: Optional[List[Dict[str, Any]]] = None,
) -> List[str]:
    at_risk = [r for r in drift_results if r.get("status") in ("Red", "Amber")]
    questions: List[str] = []
    for r in at_risk[:3]:
        metric = (r.get("initiative") or r.get("metric") or "this metric")
        gap = f"{r['gap_pct']:.1%}" if r.get("gap_pct") is not None else "the current gap"
        questions.append(
            f"What is the revised timeline and benchmark for {metric} to close {gap} versus the IC target?"
        )
    while len(questions) < 3:
        questions.append(
            f"What specifically will change in the next quarter to move {company_name}'s "
            f"off-track milestones back within plan?"
        )
    return questions[:3]


def generate_board_questions(
    company_name: str,
    period: str,
    drift_results: List[Dict[str, Any]],
    vcp_issues: Optional[List[Dict[str, Any]]] = None,
    prefer_llm: bool = True,
) -> List[str]:
    if prefer_llm and azure_openai.is_configured():
        try:
            return generate_board_questions_llm(company_name, period, drift_results, vcp_issues)
        except Exception as exc:  # noqa: BLE001
            print(f"[NarrativeAgent] board questions LLM failed, falling back: {exc}")
    return generate_board_questions_offline(company_name, period, drift_results, vcp_issues)


# ---------------------------------------------------------------------------
# Structured risks (RisksOutput)
# ---------------------------------------------------------------------------

_RISKS_SYSTEM_PROMPT = (
    "You are a senior PE operating partner. Produce the Risks & Recommended Actions table "
    "for a board pack as structured JSON. Each risk statement is <=15 words; each recommended "
    "action <=20 words and names an owner (CFO/CEO/COO/Board) and a deadline in 'Q2-28' format. "
    "Quantify IRR at risk in basis points where possible (negative integers). If there are no "
    "material risks, return an empty risks list and a no_risk_statement."
)


def generate_risks_llm(
    company_name: str,
    period: str,
    drift_results: List[Dict[str, Any]],
    alert_recommended_action: str = "",
    irr_at_risk_bps: Optional[int] = None,
) -> RisksOutput:
    client = azure_openai.get_client()
    model = azure_openai.deployment_name()
    user = (
        f"COMPANY: {company_name}\nPERIOD: {period}\n"
        f"TOTAL IRR AT RISK (bps): {irr_at_risk_bps}\n"
        f"ALERT RECOMMENDED ACTION: {alert_recommended_action}\n\n"
        f"VCP DRIFT / GAPS:\n{_risks_and_gaps_json(drift_results)}"
    )
    parse_fn = (
        getattr(client.chat.completions, "parse", None)
        or client.beta.chat.completions.parse
    )
    completion = parse_fn(
        model=model,
        messages=[
            {"role": "system", "content": _RISKS_SYSTEM_PROMPT},
            {"role": "user", "content": user},
        ],
        response_format=RisksOutput,
        temperature=0,
        max_completion_tokens=1200,
        timeout=60,
    )
    return completion.choices[0].message.parsed


def generate_risks_offline(
    company_name: str,
    period: str,
    drift_results: List[Dict[str, Any]],
    alert_recommended_action: str = "",
    irr_at_risk_bps: Optional[int] = None,
) -> RisksOutput:
    at_risk = [r for r in drift_results if r.get("status") in ("Red", "Amber")]
    if not at_risk:
        return RisksOutput(
            risks=[],
            total_irr_at_risk_bps=0,
            all_recoverable=True,
            no_risk_statement="No material risks identified this period. "
                              "All VCP milestones within ±5% of IC target.",
        )

    irr_total = abs(int(irr_at_risk_bps or 0))
    per = irr_total // (len(at_risk) or 1)
    rows: List[RiskRow] = []
    running = 0
    for i, r in enumerate(at_risk[:5]):
        sev = "red" if r.get("status") == "Red" else "amber"
        bps = -(per) if per else None
        if bps:
            running += abs(bps)
        statement = (r.get("initiative") or r.get("metric") or "Risk")
        gap = f"{r['gap_pct']:.0%}" if r.get("gap_pct") is not None else "below plan"
        rows.append(RiskRow(
            priority=i + 1,
            severity=sev,
            risk_statement=f"{statement} {gap} vs IC target",
            category=(r.get("category") or "Operational").title(),
            irr_at_risk_bps=bps,
            recommended_action=(alert_recommended_action[:80] if i == 0 and alert_recommended_action
                                else f"Operating review on {statement}"),
            owner="CFO" if i == 0 else "Operating Partner",
            deadline="Q2-28",
        ))
    return RisksOutput(
        risks=rows,
        total_irr_at_risk_bps=-running if running else 0,
        all_recoverable=True,
        no_risk_statement=None,
    )


def generate_risks(
    company_name: str,
    period: str,
    drift_results: List[Dict[str, Any]],
    alert_recommended_action: str = "",
    irr_at_risk_bps: Optional[int] = None,
    prefer_llm: bool = True,
) -> RisksOutput:
    if prefer_llm and azure_openai.is_configured():
        try:
            return generate_risks_llm(
                company_name, period, drift_results, alert_recommended_action, irr_at_risk_bps
            )
        except Exception as exc:  # noqa: BLE001
            print(f"[NarrativeAgent] risks LLM failed, falling back: {exc}")
    return generate_risks_offline(
        company_name, period, drift_results, alert_recommended_action, irr_at_risk_bps
    )
