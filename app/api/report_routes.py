"""
Report API routes — generate, retrieve, approve, and edit board packs and VCP status reports.

Generation pipeline (per request):
  1. Load milestones + KPI records from processed data
  2. Run VCP drift (live, same as company detail endpoint)
  3. Synthesize alert card (Alert & Synthesis Agent)
  4. Generate narrative prose (Report Narrative Agent)
  5. Run peer benchmarking (best-effort)
  6. Build KPI performance + risks/actions tables
  7. Assemble PDF (board_pack_generator or vcp_status_generator)
  8. Persist record + PDF bytes to ReportStore
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from app.reports.pptx_generator import generate_pptx
from app.store.report_store import ReportRecord, ReportStore
from app.workflows.hitl_decisions import load_audit_entries

# Staged generation progress (mirrors frontend PROGRESS_STEPS in spec §10)
PROGRESS_STEPS: List[Dict[str, Any]] = [
    {"key": "fetching_kpis",        "label": "Fetching KPI data",          "pct": 10},
    {"key": "running_forecast",     "label": "Running forward curve",       "pct": 25},
    {"key": "benchmarking",         "label": "Pulling sector benchmarks",   "pct": 40},
    {"key": "generating_narrative", "label": "Writing executive summary...", "pct": 60},
    {"key": "generating_questions", "label": "Generating board questions...", "pct": 75},
    {"key": "rendering_charts",     "label": "Rendering charts",            "pct": 85},
    {"key": "assembling_pptx",      "label": "Assembling deck",             "pct": 95},
    {"key": "complete",             "label": "Report ready",                "pct": 100},
]
_PROGRESS_LABEL = {s["key"]: s["label"] for s in PROGRESS_STEPS}

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROCESSED = PROJECT_ROOT / "data" / "processed"
HITL_AUDIT = PROCESSED / "hitl_audit_log.json"
HITL_QUEUE = PROCESSED / "hitl_review_queue.json"

router = APIRouter(prefix="/api/reports", tags=["reports"])
_store = ReportStore()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _build_kpi_performance(
    drift_results: List[Dict[str, Any]],
    kpi_series: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Build the KPI performance scorecard rows used on PDF page 3 and the in-app
    viewer Section 2. Joins drift targets against the two most recent KPI records
    to compute quarter-over-quarter delta.
    """
    STATUS_MAP = {"Red": "Behind", "Amber": "At Risk", "Green": "On Track",
                  "Not Evaluable": "No Data"}

    DISPLAY = {
        "annual_revenue":       ("Revenue",         "currency", False),
        "ebitda_margin":        ("EBITDA Margin",    "pct",      False),
        "gross_margin":         ("Gross Margin",     "pct",      False),
        "net_debt_to_ebitda":   ("Net Debt/EBITDA",  "multiple", True),
        "revenue_growth_yoy":   ("Revenue Growth",   "pct",      False),
    }

    def _fmt(v: Any, unit: str) -> str:
        if v is None:
            return "—"
        try:
            f = float(v)
        except (TypeError, ValueError):
            return str(v)
        if unit == "currency":
            if abs(f) >= 1e6:
                return f"£{f / 1e6:.1f}M"
            if abs(f) >= 1e3:
                return f"£{f / 1e3:.0f}k"
            return f"£{f:.0f}"
        if unit == "pct":
            return f"{f:.1%}"
        if unit == "multiple":
            return f"{f:.2f}x"
        return str(round(f, 2))

    # Index drift by metric
    drift_by_metric = {r["metric"]: r for r in drift_results}

    # Latest two KPI series points for QoQ delta
    sorted_series = sorted(kpi_series, key=lambda r: r.get("period_end", ""), reverse=True)
    latest = sorted_series[0] if sorted_series else {}
    prev   = sorted_series[1] if len(sorted_series) > 1 else {}

    rows: List[Dict[str, Any]] = []
    for metric_key, (label, unit, inverse) in DISPLAY.items():
        d = drift_by_metric.get(metric_key)
        if not d:
            continue

        actual    = d.get("actual_value")
        target    = d.get("target_value")
        gap_pct   = d.get("gap_pct")
        raw_status = d.get("status", "Not Evaluable")
        status    = STATUS_MAP.get(raw_status, raw_status)

        # QoQ delta from kpi_series (best-effort)
        series_key_map = {
            "annual_revenue": "revenue",
            "ebitda_margin": "ebitda_margin",
            "net_debt_to_ebitda": "net_debt_to_ebitda",
        }
        sk = series_key_map.get(metric_key)
        qoq_pct: Optional[float] = None
        qoq_up: Optional[bool] = None
        if sk and latest.get(sk) is not None and prev.get(sk) is not None:
            try:
                curr_v = float(latest[sk])
                prev_v = float(prev[sk])
                if prev_v != 0:
                    qoq_pct = (curr_v - prev_v) / abs(prev_v)
                    qoq_up = qoq_pct > 0
            except (TypeError, ValueError):
                pass

        rows.append({
            "metric_key":    metric_key,
            "metric":        label,
            "actual":        actual,
            "ic_target":     target,
            "delta_pct":     gap_pct,
            "qoq_pct":       qoq_pct,
            "qoq_up":        qoq_up,
            "inverse":       inverse,
            "status":        status,
            "raw_status":    raw_status,
            "unit":          unit,
            "fmt_actual":    _fmt(actual, unit),
            "fmt_target":    _fmt(target, unit),
            "fmt_delta":     f"{gap_pct:+.1%}" if gap_pct is not None else "—",
            "fmt_qoq":       f"{qoq_pct:+.1%}" if qoq_pct is not None else "—",
        })

    # Sort: Behind → At Risk → On Track
    order = {"Behind": 0, "At Risk": 1, "On Track": 2, "No Data": 3}
    rows.sort(key=lambda r: order.get(r["status"], 9))
    return rows


def _build_risks_actions(
    alert_card: Any,
    drift_results: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Build the risks & recommended actions rows for PDF page 7 and the viewer.
    Derives IRR impact from irr_at_risk_bps distributed across at-risk milestones.
    """
    at_risk = [r for r in drift_results if r.get("status") in ("Red", "Amber")]

    irr_total = abs(alert_card.irr_at_risk_bps or 0)
    n = len(at_risk) or 1
    irr_per = irr_total // n

    rows = []
    for i, r in enumerate(at_risk[:5]):
        status_label = "RED" if r.get("status") == "Red" else "AMBER"
        rows.append({
            "priority":           i + 1,
            "status":             status_label,
            "risk":               f"{r.get('initiative', r.get('metric', '—'))}: {r.get('reason', '')}",
            "irr_at_risk_bps":    -irr_per if irr_per else None,
            "recommended_action": alert_card.recommended_action if i == 0 else "",
        })
    return rows


def _hitl_decision_for_company(company_id: str) -> Optional[Dict[str, Any]]:
    """Return this company's current HITL queue decision, if any."""
    queue = _load_json(HITL_QUEUE)
    if not queue:
        return None
    for q in queue.get("queue_items", []):
        if q.get("company_id") == company_id:
            return q
    return None


def _load_hitl_decisions() -> List[Dict[str, Any]]:
    return load_audit_entries(str(HITL_AUDIT), limit=5)


def _build_citations(
    company_id: str,
    peer_benchmark: Optional[Dict[str, Any]],
    kpi_records: Optional[List[Dict[str, Any]]] = None,
) -> List[str]:
    cits = [
        f"VCP Milestones: data/processed/vcp_store.json",
        f"KPI Records: data/processed/{company_id}_kpi_records.json",
    ]

    # For EDGAR-sourced companies, add the SEC filing URL as a verifiable citation.
    if kpi_records:
        first = kpi_records[0]
        if first.get("source_type") == "edgar":
            cik_raw = first.get("cik", "").strip()
            if cik_raw and cik_raw not in ("N/A", ""):
                cik_pad = cik_raw.zfill(10)
                cits.append(
                    f"Primary source: SEC EDGAR companyfacts API — "
                    f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik_pad}.json"
                )
                cits.append(
                    f"SEC filings index — "
                    f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik_pad}&type=10-K&dateb=&owner=include&count=10"
                )

    if peer_benchmark:
        n = peer_benchmark.get("peer_set_size", "?")
        sector = peer_benchmark.get("sector_label", "sector")
        cits.append(f"Peer Benchmarks: EDGAR XBRL · {n} peers · {sector}")
    cits.append("Macro data: FRED API (DFF, INDPRO, CPILFESL)")
    return cits


# ---------------------------------------------------------------------------
# Request/Response models
# ---------------------------------------------------------------------------

class GenerateRequest(BaseModel):
    company_id: str
    report_type: str = "board_pack"   # "board_pack" | "vcp_status_update"
    period: str = ""
    tone: str = "board_ready"
    generation_mode: str = "manual"
    sections_included: Optional[List[str]] = None  # reserved for future filtering


class ApproveRequest(BaseModel):
    approved_by: str
    note: Optional[str] = None


class EditSectionRequest(BaseModel):
    section_key: str   # "exec_summary" | "priority_action" | "key_risks" | etc.
    content: str


# ---------------------------------------------------------------------------
# GET /api/reports  —  list all reports (summary only)
# ---------------------------------------------------------------------------

@router.get("")
def list_reports() -> Dict[str, Any]:
    records = _store.list_all()
    pdf_ids = _store.pdf_ids()
    summaries = []
    for r in records:
        summaries.append({
            "id":               r.id,
            "company_id":       r.company_id,
            "company_name":     r.company_name,
            "report_type":      r.report_type,
            "period":           r.period,
            "status":           r.status,
            "generation_mode":  r.generation_mode,
            "narrative_mode":   r.narrative_mode,
            "alert_severity":   r.alert_severity,
            "generated_at":     r.generated_at,
            "approved_by":      r.approved_by,
            "has_pdf":          r.id in pdf_ids,
        })
    return {"count": len(summaries), "reports": summaries}


# ---------------------------------------------------------------------------
# POST /api/reports/graph/generate  —  run the full generation pipeline as a
# checkpointed LangGraph (see app/graph/report_nodes.py — same steps as the
# synchronous version this replaced, re-sequenced into nodes). Returns immediately;
# poll /graph/{thread_id}/status for real per-node progress, backed by
# graph.get_state() rather than the client-side GEN_STEPS timer.
# ---------------------------------------------------------------------------

@router.post("/graph/generate")
def generate_report_graph(req: GenerateRequest, background_tasks: BackgroundTasks) -> Dict[str, Any]:
    report_id = str(uuid.uuid4())
    thread_id = report_id

    def _run() -> None:
        from app.graph.report_graph import get_report_graph

        graph = get_report_graph()
        config = {"configurable": {"thread_id": thread_id}}
        try:
            graph.invoke(
                {
                    "report_id": report_id,
                    "company_id": req.company_id,
                    "report_type": req.report_type,
                    "period": req.period,
                    "tone": req.tone,
                    "generation_mode": req.generation_mode,
                },
                config=config,
            )
        except Exception as exc:
            print(f"[ReportGraph] generation failed for thread {thread_id}: {exc}")

    background_tasks.add_task(_run)

    return {"report_id": report_id, "thread_id": thread_id, "status": "started"}


@router.get("/graph/{thread_id}/status")
def report_graph_status(thread_id: str) -> Dict[str, Any]:
    from app.graph.report_graph import get_report_graph

    graph = get_report_graph()
    config = {"configurable": {"thread_id": thread_id}}
    snapshot = graph.get_state(config)

    if not snapshot or not snapshot.values:
        raise HTTPException(status_code=404, detail=f"No graph run found for thread {thread_id}")

    error = next((task.error for task in snapshot.tasks if task.error), None)
    values = snapshot.values

    # NOTE: snapshot.next is not a reliable "is this graph done" signal for a
    # plain (non-interrupted) linear graph like this one — it's only populated
    # by LangGraph's interrupt() primitive (which the monitoring graph in
    # vcp_routes.py uses, but this report graph does not). Completion is
    # instead derived from progress_step, which persist_report_node sets to
    # "complete" as its very last state mutation.
    status = "failed" if error else ("complete" if values.get("progress_step") == "complete" else "running")

    return {
        "thread_id":      thread_id,
        "report_id":      values.get("report_id", thread_id),
        "status":         status,
        "progress_step":  values.get("progress_step"),
        "progress_pct":   values.get("progress_pct"),
        "error":          error,
    }


# ---------------------------------------------------------------------------
# GET /api/reports/{id}  —  full report data for the viewer
# ---------------------------------------------------------------------------

@router.get("/{report_id}")
def get_report(report_id: str) -> Dict[str, Any]:
    record = _store.load(report_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Report {report_id} not found")

    def _section_content(key: str, default: Any) -> Any:
        return record.edited_sections.get(key, default)

    return {
        "id":                   record.id,
        "company_id":           record.company_id,
        "company_name":         record.company_name,
        "report_type":          record.report_type,
        "period":               record.period,
        "sector":               record.sector,
        "status":               record.status,
        "generation_mode":      record.generation_mode,
        "narrative_mode":       record.narrative_mode,
        "generated_at":         record.generated_at,
        "approved_at":          record.approved_at,
        "approved_by":          record.approved_by,
        "has_pdf":              _store.has_pdf(record.id),
        # Alert header
        "alert_severity":       record.alert_severity,
        "alert_headline":       record.alert_headline,
        "irr_at_risk_bps":      record.irr_at_risk_bps,
        # Section content (edited overrides original if present)
        "exec_summary":         _section_content("exec_summary", record.exec_summary),
        "exec_summary_ai":      record.exec_summary,
        "exec_summary_edited":  "exec_summary" in record.edited_sections,
        "key_risks":            record.key_risks,
        "priority_action":      _section_content("priority_action", record.priority_action),
        "board_talking_points": record.board_talking_points,
        "confidence_statement": record.confidence_statement,
        # Structured data for each section
        "kpi_performance":      record.kpi_performance,
        "drift_results":        record.drift_results,
        "milestones":           record.milestones,
        "risks_actions":        record.risks_actions,
        "irr_scenarios":        record.irr_scenarios,
        "peer_benchmark":       record.peer_benchmark,
        "citations":            record.citations,
        "hitl_decisions":       record.hitl_decisions,
        "edited_sections":      record.edited_sections,
        # Fully-structured per-slide payload (10-slide Board Pack spec)
        "board_questions":      record.board_questions,
        "risks_output":         record.risks_output,
        "slides":               record.slides,
    }


# ---------------------------------------------------------------------------
# GET /api/reports/{id}/status  —  generation progress polling
# ---------------------------------------------------------------------------

@router.get("/{report_id}/status")
def report_status(report_id: str) -> Dict[str, Any]:
    record = _store.load(report_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Report {report_id} not found")
    return {
        "id":            record.id,
        "status":        record.status,
        "progress_step": record.progress_step,
        "progress_label": _PROGRESS_LABEL.get(record.progress_step, record.progress_step),
        "progress_pct":  record.progress_pct,
        "slide_count":   len(record.slides),
        "has_pdf":       _store.has_pdf(record.id),
    }


# ---------------------------------------------------------------------------
# GET /api/reports/{id}/pdf  —  stream the PDF bytes
# ---------------------------------------------------------------------------

@router.get("/{report_id}/pdf")
def download_pdf(report_id: str) -> Response:
    record = _store.load(report_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Report {report_id} not found")
    if not _store.has_pdf(report_id):
        raise HTTPException(status_code=404, detail="PDF not yet generated for this report")
    pdf_bytes = _store.load_pdf(report_id)
    filename = (
        f"{record.company_name}_{record.report_type}_{record.period}.pdf"
        .replace(" ", "_").replace("/", "-")
    )
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------------------------------------------------------------------------
# Export helpers (PPTX + PDF-from-PPTX)
# ---------------------------------------------------------------------------

def _export_filename(record: ReportRecord, ext: str) -> str:
    """Spec §9 naming: [Company]_BoardPack_[Period]_[APPROVED_]?[Date].ext"""
    type_label = "BoardPack" if record.report_type == "board_pack" else "VCPStatus"
    date = (record.approved_at or record.generated_at or "")[:10] or datetime.now(
        timezone.utc).date().isoformat()
    parts = [record.company_name, type_label, record.period]
    if record.status == "approved":
        parts.append("APPROVED")
    parts.append(date)
    name = "_".join(p for p in parts if p)
    return f"{name}.{ext}".replace(" ", "_").replace("/", "-")


def _build_pptx_bytes(record: ReportRecord) -> bytes:
    if not record.slides:
        raise HTTPException(status_code=409,
                            detail="Report has no slide payload — regenerate to enable export.")
    return generate_pptx(
        company_name=record.company_name,
        period=record.period,
        slides=record.slides,
        is_approved=record.status == "approved",
    )


def _pptx_to_pdf(pptx_bytes: bytes) -> Optional[bytes]:
    """Convert PPTX → PDF via headless LibreOffice. Returns None if unavailable."""
    soffice = shutil.which("soffice") or shutil.which("libreoffice")
    if not soffice:
        return None
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "deck.pptx"
        src.write_bytes(pptx_bytes)
        try:
            subprocess.run(
                [soffice, "--headless", "--convert-to", "pdf", "--outdir", tmp, str(src)],
                check=True, capture_output=True, timeout=120,
            )
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired):
            return None
        out = Path(tmp) / "deck.pdf"
        return out.read_bytes() if out.exists() else None


# ---------------------------------------------------------------------------
# GET /api/reports/{id}/export/pptx  —  editable PowerPoint deck
# ---------------------------------------------------------------------------

@router.get("/{report_id}/export/pptx")
def export_pptx(report_id: str) -> Response:
    record = _store.load(report_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Report {report_id} not found")
    pptx_bytes = _build_pptx_bytes(record)
    return Response(
        content=pptx_bytes,
        media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation",
        headers={"Content-Disposition": f'attachment; filename="{_export_filename(record, "pptx")}"'},
    )


# ---------------------------------------------------------------------------
# GET /api/reports/{id}/export/pdf  —  PDF rendered from the PPTX deck
# ---------------------------------------------------------------------------

@router.get("/{report_id}/export/pdf")
def export_pdf(report_id: str) -> Response:
    record = _store.load(report_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Report {report_id} not found")

    # Preferred path: render the editable deck to PDF via LibreOffice so the
    # PPTX and PDF are pixel-identical.
    pdf_bytes = _pptx_to_pdf(_build_pptx_bytes(record))

    # Fallback: serve the pre-built reportlab board pack when LibreOffice is absent.
    if pdf_bytes is None and _store.has_pdf(report_id):
        pdf_bytes = _store.load_pdf(report_id)

    if pdf_bytes is None:
        raise HTTPException(
            status_code=503,
            detail="PDF export needs LibreOffice (soffice) on the server, or a pre-generated PDF.",
        )

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{_export_filename(record, "pdf")}"'},
    )


# ---------------------------------------------------------------------------
# PATCH /api/reports/{id}/approve  —  operating partner approval
# ---------------------------------------------------------------------------

@router.patch("/{report_id}/approve")
def approve_report(report_id: str, req: ApproveRequest) -> Dict[str, Any]:
    record = _store.load(report_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Report {report_id} not found")
    record = _store.update(
        report_id,
        status="approved",
        approved_by=req.approved_by,
        approved_at=datetime.now(timezone.utc).isoformat(),
        approved_note=req.note,
    )
    return {
        "id":          record.id,
        "status":      record.status,
        "approved_by": record.approved_by,
        "approved_at": record.approved_at,
    }


# ---------------------------------------------------------------------------
# PATCH /api/reports/{id}/section  —  save inline edit from viewer
# ---------------------------------------------------------------------------

@router.delete("/{report_id}")
def delete_report(report_id: str) -> Dict[str, Any]:
    record = _store.load(report_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Report {report_id} not found")
    _store.delete(report_id)
    return {"deleted": True, "id": report_id}


@router.patch("/{report_id}/section")
def edit_section(report_id: str, req: EditSectionRequest) -> Dict[str, Any]:
    record = _store.load(report_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Report {report_id} not found")
    edited = dict(record.edited_sections)
    edited[req.section_key] = req.content
    _store.update(report_id, edited_sections=edited)
    return {"section_key": req.section_key, "saved": True}
