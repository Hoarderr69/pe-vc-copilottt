from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional


# Allowed reviewer decisions and how each maps to the queue item status.
DECISION_TO_STATUS = {
    "approve": "approved",
    "edit": "approved_with_edit",
    "reject": "rejected",
}


class HITLDecisionError(ValueError):
    """Raised when a HITL decision cannot be applied."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def apply_hitl_decision(
    review_id: str,
    decision: str,
    reviewed_by: str,
    reviewer_note: Optional[str] = None,
    edited_recommended_action: Optional[str] = None,
    queue_path: str = "data/processed/hitl_review_queue.json",
    audit_log_path: str = "data/processed/hitl_audit_log.json",
) -> Dict[str, Any]:
    """
    Record an operating-partner decision (approve / edit / reject) on one HITL
    review item.

    This is the deterministic write-back companion to build_hitl_review_queue:
    the builder produces pending items, this applies a human decision and logs
    it. It updates the item's `decision` block and top-level `status`, refreshes
    the queue-level pending count, and appends an immutable entry to the audit
    log. No LLM involved.
    """

    decision = decision.lower().strip()

    if decision not in DECISION_TO_STATUS:
        raise HITLDecisionError(
            f"Unknown decision '{decision}'. Expected one of: "
            f"{', '.join(sorted(DECISION_TO_STATUS))}."
        )

    if decision == "edit" and not edited_recommended_action:
        raise HITLDecisionError(
            "An 'edit' decision requires edited_recommended_action."
        )

    path = Path(queue_path)

    if not path.exists():
        raise FileNotFoundError(f"HITL review queue not found: {queue_path}")

    queue = json.loads(path.read_text(encoding="utf-8"))
    items: List[Dict[str, Any]] = queue.get("queue_items", [])

    target = next(
        (item for item in items if item.get("review_id") == review_id),
        None,
    )

    if target is None:
        available = ", ".join(item.get("review_id", "?") for item in items) or "(none)"
        raise HITLDecisionError(
            f"review_id '{review_id}' not found in queue. Available: {available}."
        )

    reviewed_at = _now()
    new_status = DECISION_TO_STATUS[decision]

    target["status"] = new_status
    target["decision"] = {
        "decision_status": new_status,
        "reviewed_by": reviewed_by,
        "reviewed_at": reviewed_at,
        "reviewer_note": reviewer_note,
        "edited_recommended_action": edited_recommended_action,
    }

    # Refresh queue-level counts so downstream readers stay consistent.
    queue["pending_review_count"] = len(
        [item for item in items if item.get("status") == "pending_review"]
    )
    queue["last_decision_at"] = reviewed_at

    path.write_text(json.dumps(queue, indent=2, default=str), encoding="utf-8")

    audit_entry = {
        "logged_at": reviewed_at,
        "review_id": review_id,
        "company_id": target.get("company_id"),
        "company_name": target.get("company_name"),
        "decision": decision,
        "resulting_status": new_status,
        "reviewed_by": reviewed_by,
        "reviewer_note": reviewer_note,
        "edited_recommended_action": edited_recommended_action,
        "original_recommended_action": target.get("recommended_action"),
        "priority": target.get("priority"),
    }

    _append_audit_entry(audit_entry, audit_log_path)

    return target


def _append_audit_entry(entry: Dict[str, Any], audit_log_path: str) -> None:
    """Append one decision entry to the append-only audit log."""

    log_path = Path(audit_log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    if log_path.exists():
        log = json.loads(log_path.read_text(encoding="utf-8"))
    else:
        log = {"entries": []}

    log["entries"].append(entry)
    log["entry_count"] = len(log["entries"])
    log["updated_at"] = entry["logged_at"]

    log_path.write_text(json.dumps(log, indent=2, default=str), encoding="utf-8")
