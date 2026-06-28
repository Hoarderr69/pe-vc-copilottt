from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


def default_review_action(priority: str) -> str:
    if priority == "P1":
        return "immediate_review"
    if priority == "P2":
        return "review_this_week"
    return "monitor"


def build_hitl_review_queue(
    action_inbox_path: str = "data/processed/portfolio_action_inbox.json",
    output_path: str = "data/processed/hitl_review_queue.json",
) -> Dict[str, Any]:
    """
    Convert deterministic portfolio action inbox into HITL review queue.

    This is a JSON-first workflow artifact.
    Later Streamlit will read this file and show Approve/Edit/Reject controls.
    """

    path = Path(action_inbox_path)

    if not path.exists():
        raise FileNotFoundError(f"Action inbox not found: {action_inbox_path}")

    inbox = json.loads(path.read_text(encoding="utf-8"))

    queue_items: List[Dict[str, Any]] = []

    now = datetime.now(timezone.utc).isoformat()

    for item in inbox.get("action_items", []):
        queue_item = {
            "review_id": f"review_{item['priority_rank']:03d}_{item['company_id']}",
            "created_at": now,
            "status": "pending_review",
            "review_action": default_review_action(item.get("priority", "P3")),
            "priority_rank": item.get("priority_rank"),
            "priority": item.get("priority"),
            "priority_score": item.get("priority_score"),
            "company_id": item.get("company_id"),
            "company_name": item.get("company_name"),
            "headline": item.get("headline"),
            "recommended_action": item.get("recommended_action"),
            "primary_risks": item.get("primary_risks", []),
            "red_alert_count": item.get("red_alert_count", 0),
            "amber_alert_count": item.get("amber_alert_count", 0),
            "evidence": item.get("evidence", []),
            "decision": {
                "decision_status": "not_reviewed",
                "reviewed_by": None,
                "reviewed_at": None,
                "reviewer_note": None,
                "edited_recommended_action": None,
            },
        }

        queue_items.append(queue_item)

    payload = {
        "created_at": now,
        "source_action_inbox_path": action_inbox_path,
        "queue_item_count": len(queue_items),
        "pending_review_count": len(
            [item for item in queue_items if item["status"] == "pending_review"]
        ),
        "queue_items": queue_items,
    }

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")

    return payload