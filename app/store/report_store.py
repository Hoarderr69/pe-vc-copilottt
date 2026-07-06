"""
Report Store — JSON-backed persistence for generated board packs and VCP status reports.

Each report record holds: narrative content, analytics snapshots, approval state, and
pointers to the PDF. Inline edits from the viewer are stored in edited_sections, which
shadow the original AI-generated text without destroying it.
"""
from __future__ import annotations

import base64
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.store.postgres_json_store import PostgresJsonStore


class ReportRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    company_id: str
    company_name: str
    report_type: str          # "board_pack" | "vcp_status_update"
    period: str
    sector: str = ""
    tone: str = "board_ready" # "board_ready" | "management_internal"
    status: str = "draft"     # "draft" | "pending_review" | "approved"
    generation_mode: str = "manual"  # "auto" | "manual"
    narrative_mode: str = "offline_rule_based"

    generated_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    approved_at: Optional[str] = None
    approved_by: Optional[str] = None
    approved_note: Optional[str] = None

    # Progress tracking (status-polling endpoint)
    progress_step: str = "complete"   # key from PROGRESS_STEPS, e.g. "generating_narrative"
    progress_pct: int = 100

    # Narrative content (from report_narrative_agent)
    exec_summary: str = ""
    key_risks: List[str] = Field(default_factory=list)
    priority_action: str = ""
    board_talking_points: List[str] = Field(default_factory=list)
    confidence_statement: str = ""
    board_questions: List[str] = Field(default_factory=list)
    risks_output: Optional[Dict[str, Any]] = None

    # Alert card fields
    alert_severity: str = "Amber"
    alert_headline: str = ""
    alert_root_cause: str = ""
    alert_recommended_action: str = ""
    lever_category: str = "other"
    irr_at_risk_bps: Optional[int] = None

    # Structured analytics (snapshots at generation time)
    drift_results: List[Dict[str, Any]] = Field(default_factory=list)
    milestones: List[Dict[str, Any]] = Field(default_factory=list)
    kpi_records: List[Dict[str, Any]] = Field(default_factory=list)
    kpi_performance: List[Dict[str, Any]] = Field(default_factory=list)
    risks_actions: List[Dict[str, Any]] = Field(default_factory=list)
    irr_scenarios: Optional[List[Dict[str, Any]]] = None
    peer_benchmark: Optional[Dict[str, Any]] = None
    ic_target_irr: Optional[float] = None
    ic_target_moic: Optional[float] = None
    entry_equity: Optional[float] = None
    holding_period: float = 5.0
    citations: List[str] = Field(default_factory=list)
    hitl_decisions: List[Dict[str, Any]] = Field(default_factory=list)

    # Fully-structured per-slide payload (10-slide Board Pack spec)
    slides: List[Dict[str, Any]] = Field(default_factory=list)

    # Inline edits from the in-app viewer (section_key → edited text)
    edited_sections: Dict[str, str] = Field(default_factory=dict)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REPORTS_DIR = str(PROJECT_ROOT / "data" / "processed" / "reports")


class ReportStore:
    """Report store, backed by Postgres (PostgresJsonStore) — one document per report,
    plus a companion collection for PDF bytes (base64-encoded, since JSONB holds text)."""

    def __init__(self, base_dir: str = DEFAULT_REPORTS_DIR):
        self.base_dir = Path(base_dir)
        self._store = PostgresJsonStore("reports")
        self._pdf_store = PostgresJsonStore("report_pdfs")

    # ------------------------------------------------------------------
    # Core CRUD
    # ------------------------------------------------------------------

    def save(self, record: ReportRecord) -> None:
        self._store.put(record.id, record.model_dump(mode="json"))

    def load(self, report_id: str) -> Optional[ReportRecord]:
        doc = self._store.get(report_id)
        if doc is None:
            return None
        try:
            return ReportRecord.model_validate(doc)
        except Exception:
            return None

    def update(self, report_id: str, **fields: Any) -> Optional[ReportRecord]:
        record = self.load(report_id)
        if record is None:
            return None
        updated = record.model_copy(update=fields)
        self.save(updated)
        return updated

    def list_all(self) -> List[ReportRecord]:
        records = []
        for doc in self._store.list():
            try:
                records.append(ReportRecord.model_validate(doc))
            except Exception:
                continue
        records.sort(key=lambda r: r.generated_at, reverse=True)
        return records

    # ------------------------------------------------------------------
    # PDF storage
    # ------------------------------------------------------------------

    def save_pdf(self, report_id: str, pdf_bytes: bytes) -> None:
        self._pdf_store.put(report_id, {"pdf_base64": base64.b64encode(pdf_bytes).decode("ascii")})

    def load_pdf(self, report_id: str) -> Optional[bytes]:
        doc = self._pdf_store.get(report_id)
        if doc is None:
            return None
        return base64.b64decode(doc["pdf_base64"])

    def has_pdf(self, report_id: str) -> bool:
        return self._pdf_store.get(report_id) is not None

    def pdf_ids(self) -> set:
        """All report ids that have a stored PDF, in one round trip — for a
        caller checking existence across many reports (e.g. the report list
        endpoint) instead of calling has_pdf() once per report."""
        return set(self._pdf_store.list_ids())

    def delete(self, report_id: str) -> None:
        self._store.delete(report_id)
        self._pdf_store.delete(report_id)
