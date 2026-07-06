"""
VCP confirmation — the HITL gate of the Setup graph.

The VCP Extraction Agent produces *candidate* milestones (confirmed=False). They are
not ground truth until an operating partner reviews them: edit a target, fix a date,
delete a spurious one, add one the agent missed, then confirm. This module records that
human decision and writes the confirmed milestones into the VCPStore — the locked,
versioned ground truth every monitoring run reads.

No LLM here: this is deterministic write-back + an immutable audit trail.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.schemas.vcp_schema import VCPMilestone
from app.store.vcp_store import VCPStore

DEFAULT_STORE_PATH = "data/processed/vcp_store.json"
DEFAULT_CONFIRMATION_LOG = "data/processed/vcp_confirmation_log.json"
PROCESSED_DIR = "data/processed"


def kpi_records_path(company_id: str) -> str:
    """Canonical per-company KPI records path — the one convention every
    caller (routes, graph nodes) should derive from instead of hardcoding."""
    return f"{PROCESSED_DIR}/{company_id}_kpi_records.json"


class VCPConfirmationError(ValueError):
    """Raised when a VCP confirmation cannot be applied."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def confirm_vcp_milestones(
    company_id: str,
    company_name: str,
    milestones: List[Dict[str, Any]],
    reviewed_by: str,
    reviewer_note: Optional[str] = None,
    store_path: str = DEFAULT_STORE_PATH,
    confirmation_log_path: str = DEFAULT_CONFIRMATION_LOG,
) -> Dict[str, Any]:
    """Lock a company's reviewed milestones into the VCPStore as confirmed ground truth.

    `milestones` is the human-reviewed set (post edit/add/delete) as dicts. Each is
    stamped confirmed=True with a bumped version, replacing any prior entries for the
    company. The action is recorded in an append-only confirmation log.
    """
    if not milestones:
        raise VCPConfirmationError("Cannot confirm an empty milestone set.")

    store = VCPStore(store_path)
    existing = store.load_all() if store.exists() else []

    # Version is per-company: bump past whatever version is already stored.
    prior_for_company = [m for m in existing if m.company_id == company_id]
    next_version = max((m.version for m in prior_for_company), default=0) + 1

    confirmed: List[VCPMilestone] = []
    for raw in milestones:
        m = VCPMilestone.from_dict(raw)
        m.company_id = company_id
        m.company_name = company_name or m.company_name
        m.confirmed = True
        m.version = next_version
        metadata = dict(m.metadata or {})
        metadata.update({"confirmed_by": reviewed_by, "confirmed_at": _now()})
        m.metadata = metadata
        confirmed.append(m)

    # Replace this company's entries; keep every other company untouched.
    others = [m for m in existing if m.company_id != company_id]
    store.save_all(others + confirmed)

    _append_confirmation_log(
        {
            "logged_at": _now(),
            "company_id": company_id,
            "company_name": company_name,
            "reviewed_by": reviewed_by,
            "reviewer_note": reviewer_note,
            "version": next_version,
            "milestone_count": len(confirmed),
            "metrics": [m.metric for m in confirmed],
        },
        confirmation_log_path,
    )

    return {
        "company_id": company_id,
        "company_name": company_name,
        "version": next_version,
        "confirmed_count": len(confirmed),
        "store_path": store_path,
        "milestones": [m.to_dict() for m in confirmed],
    }


def _append_confirmation_log(entry: Dict[str, Any], log_path: str) -> None:
    path = Path(log_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists():
        log = json.loads(path.read_text(encoding="utf-8"))
    else:
        log = {"entries": []}

    log["entries"].append(entry)
    log["entry_count"] = len(log["entries"])
    log["updated_at"] = entry["logged_at"]

    path.write_text(json.dumps(log, indent=2, default=str), encoding="utf-8")
