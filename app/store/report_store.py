"""
Report Store — JSON-backed persistence for generated board packs and VCP status reports.

Each report record holds: narrative content, analytics snapshots, approval state, and
pointers to the PDF. Inline edits from the viewer are stored in edited_sections, which
shadow the original AI-generated text without destroying it.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


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
    """Lightweight JSON-backed report store. One JSON file per report, plus an index."""

    def __init__(self, base_dir: str = DEFAULT_REPORTS_DIR):
        self.base_dir = Path(base_dir)
        self.index_path = self.base_dir / "index.json"
        self.base_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Core CRUD
    # ------------------------------------------------------------------

    def save(self, record: ReportRecord) -> None:
        path = self._record_path(record.id)
        path.write_text(record.model_dump_json(indent=2), encoding="utf-8")
        self._rebuild_index()

    def load(self, report_id: str) -> Optional[ReportRecord]:
        path = self._record_path(report_id)
        if not path.exists():
            return None
        try:
            return ReportRecord.model_validate_json(path.read_text(encoding="utf-8"))
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
        for p in self.base_dir.glob("*.json"):
            if p.name == "index.json":
                continue
            rec = self.load(p.stem)
            if rec:
                records.append(rec)
        records.sort(key=lambda r: r.generated_at, reverse=True)
        return records

    # ------------------------------------------------------------------
    # PDF storage
    # ------------------------------------------------------------------

    def pdf_path(self, report_id: str) -> Path:
        return self.base_dir / f"{report_id}.pdf"

    def save_pdf(self, report_id: str, pdf_bytes: bytes) -> None:
        self.pdf_path(report_id).write_bytes(pdf_bytes)

    def has_pdf(self, report_id: str) -> bool:
        return self.pdf_path(report_id).exists()

    def delete(self, report_id: str) -> None:
        self._record_path(report_id).unlink(missing_ok=True)
        self.pdf_path(report_id).unlink(missing_ok=True)
        self._rebuild_index()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _record_path(self, report_id: str) -> Path:
        return self.base_dir / f"{report_id}.json"

    def _rebuild_index(self) -> None:
        index = []
        for p in sorted(self.base_dir.glob("*.json")):
            if p.name == "index.json":
                continue
            rec = self.load(p.stem)
            if rec:
                index.append({
                    "id": rec.id,
                    "company_id": rec.company_id,
                    "company_name": rec.company_name,
                    "report_type": rec.report_type,
                    "period": rec.period,
                    "status": rec.status,
                    "generation_mode": rec.generation_mode,
                    "narrative_mode": rec.narrative_mode,
                    "generated_at": rec.generated_at,
                    "approved_by": rec.approved_by,
                    "alert_severity": rec.alert_severity,
                })
        index.sort(key=lambda e: e["generated_at"], reverse=True)
        self.index_path.write_text(json.dumps(index, indent=2), encoding="utf-8")
