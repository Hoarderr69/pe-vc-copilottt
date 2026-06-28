from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


def _load(path: str) -> Optional[Dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def _fmt_currency(value: Any) -> str:
    try:
        return f"${float(value):,.0f}"
    except (TypeError, ValueError):
        return str(value)


def build_portfolio_memo(
    action_inbox_path: str = "data/processed/portfolio_action_inbox.json",
    monitoring_summary_path: str = "data/processed/portfolio_vcp_monitoring_summary.json",
    hitl_queue_path: str = "data/processed/hitl_review_queue.json",
    output_path: str = "data/processed/portfolio_memo.md",
) -> Dict[str, Any]:
    """
    Build a deterministic, board-ready markdown memo skeleton from the existing
    monitoring artifacts. This is the decision artifact the rebased plan calls
    for (memo before dashboard polish). It is templated, not LLM-generated; the
    Report Narrative Agent will later replace the executive-summary prose.
    """

    inbox = _load(action_inbox_path)
    if inbox is None:
        raise FileNotFoundError(f"Action inbox not found: {action_inbox_path}")

    summary = _load(monitoring_summary_path) or {}
    hitl = _load(hitl_queue_path) or {}

    generated_at = datetime.now(timezone.utc).isoformat()
    action_items: List[Dict[str, Any]] = inbox.get("action_items", [])
    severity_counts = inbox.get("severity_counts", {})

    lines: List[str] = []

    # --- Header ---
    lines.append("# Portfolio Value Creation Memo")
    lines.append("")
    lines.append(f"_Generated: {generated_at}_")
    lines.append("")

    # --- Executive summary ---
    lines.append("## Executive Summary")
    lines.append("")
    company_count = inbox.get("portfolio_company_count", "?")
    total_alerts = inbox.get("total_alerts", 0)
    red = severity_counts.get("Red", 0)
    amber = severity_counts.get("Amber", 0)
    p1 = sum(1 for i in action_items if i.get("priority") == "P1")
    lines.append(
        f"Across **{company_count} portfolio companies**, monitoring produced "
        f"**{total_alerts} VCP drift alerts** ({red} Red, {amber} Amber). "
        f"**{p1} company(ies)** are flagged P1 for immediate operating-partner attention."
    )
    lines.append("")
    if action_items:
        top = action_items[0]
        lines.append(
            f"Highest priority: **{top.get('company_name')}** — {top.get('headline')}"
        )
        lines.append("")

    # --- Portfolio alert overview ---
    lines.append("## Portfolio Alert Overview")
    lines.append("")
    lines.append("| Rank | Company | Priority | Red | Amber | Primary risks |")
    lines.append("|---|---|---|---|---|---|")
    for item in action_items:
        lines.append(
            f"| {item.get('priority_rank')} "
            f"| {item.get('company_name')} "
            f"| {item.get('priority')} "
            f"| {item.get('red_alert_count', 0)} "
            f"| {item.get('amber_alert_count', 0)} "
            f"| {', '.join(item.get('primary_risks', []))} |"
        )
    lines.append("")

    # --- Company-level action items ---
    lines.append("## Company-Level Action Items")
    lines.append("")
    for item in action_items:
        lines.append(
            f"### {item.get('priority_rank')}. {item.get('company_name')} "
            f"[{item.get('priority')}]"
        )
        lines.append("")
        lines.append(f"- **Headline:** {item.get('headline')}")
        lines.append(f"- **Recommended action:** {item.get('recommended_action')}")
        lines.append(
            f"- **Priority score:** {item.get('priority_score')} "
            f"({item.get('red_alert_count', 0)} Red, "
            f"{item.get('amber_alert_count', 0)} Amber)"
        )
        lines.append("")

    # --- Evidence citations ---
    lines.append("## Evidence Citations")
    lines.append("")
    for item in action_items:
        lines.append(f"**{item.get('company_name')}**")
        lines.append("")
        for ev in item.get("evidence", []):
            metric = ev.get("metric")
            severity = ev.get("severity")
            source = ev.get("source_path")
            column = ev.get("source_column")
            lines.append(
                f"- [{severity}] `{metric}` — {ev.get('summary')} "
                f"(source: `{source}`, column: `{column}`)"
            )
        lines.append("")

    # --- Pending review items ---
    lines.append("## Pending Review Items (HITL)")
    lines.append("")
    queue_items: List[Dict[str, Any]] = hitl.get("queue_items", [])
    if not queue_items:
        lines.append("_No HITL review queue available._")
        lines.append("")
    else:
        pending = [q for q in queue_items if q.get("status") == "pending_review"]
        reviewed = [q for q in queue_items if q.get("status") != "pending_review"]
        lines.append(
            f"{len(pending)} pending, {len(reviewed)} reviewed of "
            f"{len(queue_items)} total."
        )
        lines.append("")
        lines.append("| Review ID | Company | Status | Reviewed by | Note |")
        lines.append("|---|---|---|---|---|")
        for q in queue_items:
            decision = q.get("decision", {})
            lines.append(
                f"| {q.get('review_id')} "
                f"| {q.get('company_name')} "
                f"| {q.get('status')} "
                f"| {decision.get('reviewed_by') or '—'} "
                f"| {decision.get('reviewer_note') or '—'} |"
            )
        lines.append("")

    memo_text = "\n".join(lines)

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(memo_text, encoding="utf-8")

    return {
        "generated_at": generated_at,
        "output_path": output_path,
        "company_count": company_count,
        "action_item_count": len(action_items),
        "pending_review_count": hitl.get("pending_review_count", 0),
        "memo_text": memo_text,
    }
