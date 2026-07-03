from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List


def _atomic_write_json(path: Path, data: Dict[str, Any]) -> None:
    """Write JSON via a temp file + rename so concurrent readers never see a
    truncated/empty file (multiple browser tabs can poll the same endpoint
    and trigger overlapping refreshes of this file)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(json.dumps(data, indent=2, default=str))
        os.replace(tmp_name, path)
    except BaseException:
        Path(tmp_name).unlink(missing_ok=True)
        raise


def default_review_action(priority: str) -> str:
    if priority == "P1":
        return "immediate_review"
    if priority == "P2":
        return "review_this_week"
    return "monitor"


def _queue_item_from_action_item(item: Dict[str, Any], now: str) -> Dict[str, Any]:
    """Shape one action-inbox item into a pending HITL queue item."""
    return {
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


def refresh_hitl_review_queue_from_action_items(
    action_items: List[Dict[str, Any]],
    output_path: str = "data/processed/hitl_review_queue.json",
) -> Dict[str, Any]:
    """Merge live action items into the HITL review queue, preserving decisions.

    Stateful, in-place refresh used by the live API monitoring run. Existing queue
    items are kept untouched (so reviewed decisions and history survive), and any
    company that does not yet have a queue item gets a new pending one appended.

    Identity is keyed by company_id — not review_id — because review_id embeds the
    priority_rank, which shifts between runs. Keying by company avoids duplicating a
    company's item when its rank changes.
    """
    path = Path(output_path)
    now = datetime.now(timezone.utc).isoformat()

    existing_text = path.read_text(encoding="utf-8").strip() if path.exists() else ""
    if existing_text:
        queue = json.loads(existing_text)
        items: List[Dict[str, Any]] = queue.get("queue_items", [])
    else:
        queue = {"created_at": now}
        items = []

    existing_company_ids = {item.get("company_id") for item in items}

    for action_item in action_items:
        if action_item.get("company_id") in existing_company_ids:
            continue  # keep the existing item (and any decision on it) untouched
        items.append(_queue_item_from_action_item(action_item, now))
        existing_company_ids.add(action_item.get("company_id"))

    queue["queue_items"] = items
    queue["queue_item_count"] = len(items)
    queue["pending_review_count"] = len(
        [item for item in items if item.get("status") == "pending_review"]
    )
    queue["refreshed_at"] = now

    _atomic_write_json(path, queue)

    return queue


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
        queue_items.append(_queue_item_from_action_item(item, now))

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