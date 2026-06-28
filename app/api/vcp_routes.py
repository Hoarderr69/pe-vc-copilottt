"""
VCP monitoring API.

Single source of truth: vcp_store.json (confirmed milestones) + {company_id}_kpi_records.json.
Everything is computed live — no pre-generated pipeline artifacts read by these endpoints.

Batch scripts (run_portfolio_vcp_monitoring.py etc.) still exist for exports/reports,
but the API never depends on their output files.
"""

from __future__ import annotations

import json
import math
import re
import tempfile
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.agents.vcp_extraction_agent import extract_from_document, to_vcp_milestones
from app.analytics.vcp_drift import run_vcp_drift_for_kpi_records
from app.llm import azure_openai
from app.store.vcp_store import VCPStore
from app.workflows.hitl_decisions import HITLDecisionError, apply_hitl_decision
from app.workflows.vcp_confirmation import (
    DEFAULT_STORE_PATH,
    VCPConfirmationError,
    confirm_vcp_milestones,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROCESSED = PROJECT_ROOT / "data" / "processed"
IC_MEMO_DIR = PROJECT_ROOT / "data" / "raw" / "ic_memos"
HITL_QUEUE = PROCESSED / "hitl_review_queue.json"
HITL_AUDIT = PROCESSED / "hitl_audit_log.json"
PORTFOLIO_MEMO = PROCESSED / "portfolio_memo.md"
SECTOR_BENCHMARKS = PROJECT_ROOT / "data" / "reference" / "sector_benchmarks.json"

_MAX_UPLOAD_BYTES = 25 * 1024 * 1024

router = APIRouter(prefix="/api/vcp", tags=["vcp"])


# ── Utilities ────────────────────────────────────────────────────────────────

def _kpi_records_path(company_id: str) -> Path:
    return PROCESSED / f"{company_id}_kpi_records.json"


def _load_kpi(company_id: str) -> List[Dict]:
    path = _kpi_records_path(company_id)
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


def _load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        if default is not None:
            return default
        raise HTTPException(status_code=404, detail=f"Not found: {path.name}")
    return json.loads(path.read_text(encoding="utf-8"))


def _worst_status(counts: Dict[str, int]) -> str:
    for s in ("Red", "Amber", "Green"):
        if counts.get(s):
            return s
    return "Not Evaluable"


def _slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")
    return slug or "uploaded_company"


_FILENAME_NOISE = re.compile(r"[_\s]?ic[_\s]?memo$", re.IGNORECASE)


def _clean_name(stem: str) -> str:
    """'portco_b_industrial_ic_memo' → 'Portco B Industrial'"""
    cleaned = _FILENAME_NOISE.sub("", stem).strip("_- ")
    return " ".join(w.capitalize() for w in re.split(r"[_\-\s]+", cleaned) if w)


def _infer_sector(company_id: str, company_name: str) -> Optional[str]:
    """Return sector key from sector_benchmarks.json, auto-inferring from name if not mapped."""
    if not SECTOR_BENCHMARKS.exists():
        return None
    benchmarks = json.loads(SECTOR_BENCHMARKS.read_text(encoding="utf-8"))
    sector_map = benchmarks.get("company_sector_map", {})

    # Exact match first
    if company_id in sector_map:
        return sector_map[company_id]

    # Keyword inference from company name/id
    text = (company_id + " " + company_name).lower()
    if any(k in text for k in ("saas", "software", "tech")):
        return "b2b_saas"
    if any(k in text for k in ("industrial", "manufacturing", "factory")):
        return "industrial_manufacturing"
    if any(k in text for k in ("health", "care", "medical", "pharma")):
        return "healthcare_services"
    return None


def _register_sector(company_id: str, sector_key: str) -> None:
    """Persist a new company→sector mapping so future lookups are instant."""
    if not SECTOR_BENCHMARKS.exists():
        return
    benchmarks = json.loads(SECTOR_BENCHMARKS.read_text(encoding="utf-8"))
    if company_id not in benchmarks.get("company_sector_map", {}):
        benchmarks.setdefault("company_sector_map", {})[company_id] = sector_key
        SECTOR_BENCHMARKS.write_text(json.dumps(benchmarks, indent=2), encoding="utf-8")


# ── Plan-path generation ─────────────────────────────────────────────────────

def _plan_path(
    baseline: Optional[float],
    target: Optional[float],
    target_date_str: Optional[str],
    kpi_periods: List[str],
) -> List[Dict[str, Any]]:
    """Linear interpolation baseline→target across the KPI period dates."""
    if baseline is None or target is None or not target_date_str or not kpi_periods:
        return []
    try:
        t_end = date.fromisoformat(str(target_date_str)[:10])
        t_start = date.fromisoformat(str(kpi_periods[0])[:10])
    except ValueError:
        return []
    total_days = (t_end - t_start).days
    if total_days <= 0:
        return []
    result = []
    for p in kpi_periods:
        try:
            p_date = date.fromisoformat(str(p)[:10])
        except ValueError:
            continue
        if p_date > t_end:
            break
        frac = (p_date - t_start).days / total_days
        result.append({"period_end": str(p)[:10], "planned_value": baseline + frac * (target - baseline)})
    return result


def _enrich_milestones(milestones: List[Dict], kpi_periods: List[str]) -> List[Dict]:
    """Attach a generated plan_path to every milestone that doesn't already have one."""
    out = []
    for m in milestones:
        m = dict(m)
        meta = dict(m.get("metadata") or {})
        if not meta.get("plan_path"):
            meta["plan_path"] = _plan_path(
                m.get("baseline_value"), m.get("target_value"),
                m.get("target_date"), kpi_periods,
            )
            m["metadata"] = meta
        out.append(m)
    return out


# ── IRR (PE-style, derived from VCP milestones + KPI actuals) ────────────────

def _pe_irr(entry_equity: float, exit_equity: float, years: float) -> Optional[float]:
    if entry_equity <= 0 or exit_equity <= 0 or years <= 0:
        return None
    irr = ((exit_equity / entry_equity) ** (1.0 / years) - 1.0) * 100.0
    return None if math.isnan(irr) or math.isinf(irr) else irr


def _irr_matrix(company_id: str, kpi_records: List[Dict], milestones: List[Dict]) -> Dict[str, Any]:
    """Build an exit_multiple × hold_years IRR grid from VCP targets + KPI entry metrics."""
    if not kpi_records:
        raise HTTPException(status_code=404, detail=f"No KPI records for {company_id}")

    entry = kpi_records[0]
    entry_ebitda_m = entry.get("adjusted_ebitda") or entry.get("ebitda_proxy")
    if not entry_ebitda_m:
        raise HTTPException(status_code=422, detail="Entry EBITDA not available in KPI records.")
    entry_ebitda = entry_ebitda_m * 12
    entry_net_debt = entry.get("net_debt") or 0.0

    ms = {m["metric"]: m for m in milestones}
    rev_ms, margin_ms, lev_ms = ms.get("annual_revenue"), ms.get("ebitda_margin"), ms.get("net_debt_to_ebitda")

    # Exit EBITDA from VCP targets; fall back to last KPI period
    exit_ebitda: float
    if rev_ms and rev_ms.get("target_value") and margin_ms and margin_ms.get("target_value"):
        exit_ebitda = rev_ms["target_value"] * margin_ms["target_value"]
    elif margin_ms and margin_ms.get("target_value") and kpi_records[-1].get("revenue"):
        exit_ebitda = kpi_records[-1]["revenue"] * 12 * margin_ms["target_value"]
    else:
        exit_ebitda = entry_ebitda * 1.4  # assume 40 % growth if targets unavailable

    # Exit net debt from VCP leverage target
    if lev_ms and lev_ms.get("target_value") is not None:
        exit_net_debt = lev_ms["target_value"] * exit_ebitda
    else:
        exit_net_debt = entry_net_debt * 0.5

    # Entry equity: assume 10× entry multiple (typical PE mid-market)
    entry_multiple = 10.0
    entry_ev = entry_ebitda * entry_multiple
    entry_equity = max(entry_ev - entry_net_debt, entry_ev * 0.3)

    exit_multiples = [8.0, 10.0, 12.0, 14.0, 16.0]
    hold_years = [3.0, 4.0, 5.0, 6.0]

    rows = []
    for em in exit_multiples:
        for hy in hold_years:
            exit_equity = em * exit_ebitda - exit_net_debt
            irr = _pe_irr(entry_equity, exit_equity, hy)
            if irr is not None:
                rows.append({"exit_multiple": em, "hold_years": hy, "irr_percent": round(irr, 2)})

    return {
        "company_id": company_id,
        "exit_multiples": exit_multiples,
        "hold_years": hold_years,
        "scenarios": rows,
        "entry_ebitda_annual": round(entry_ebitda),
        "exit_ebitda_estimate": round(exit_ebitda),
        "entry_multiple_assumed": entry_multiple,
    }


# ── Action item scoring (inline — no pre-generated file needed) ───────────────

_METRIC_WEIGHTS = {"net_debt_to_ebitda": 5, "ebitda_margin": 4, "annual_revenue": 3}
_SEVERITY_WEIGHTS = {"Red": 10, "Amber": 5, "Green": 0}


def _action_item(company_id: str, company_name: str, drift: Dict) -> Optional[Dict]:
    # Build from drift results — each result is a metric-level assessment
    results = [r for r in drift.get("results", []) if r.get("status") in ("Red", "Amber", "Green")]
    if not results:
        return None
    red = [r for r in results if r.get("status") == "Red"]
    amber = [r for r in results if r.get("status") == "Amber"]
    if not red and not amber:
        return None  # all green — no action item needed
    metrics = sorted({r.get("metric") for r in results if r.get("metric") and r.get("status") in ("Red", "Amber")})
    score = sum(_SEVERITY_WEIGHTS.get(r.get("status", ""), 0) + _METRIC_WEIGHTS.get(r.get("metric", ""), 1) for r in red + amber)

    if len(red) >= 2 or score >= 25:
        priority = "P1"
    elif len(red) == 1 or score >= 12:
        priority = "P2"
    else:
        priority = "P3"

    metric_set = set(metrics)
    if "net_debt_to_ebitda" in metric_set and "ebitda_margin" in metric_set:
        action = "Review leverage headroom, cash generation, SG&A actions, and EBITDA recovery plan with CFO."
    elif "ebitda_margin" in metric_set and "annual_revenue" in metric_set:
        action = "Review revenue execution, pricing discipline, and cost base with CEO/CFO."
    elif "annual_revenue" in metric_set:
        action = "Review pipeline quality, sales execution, pricing, and customer retention plan."
    elif "ebitda_margin" in metric_set:
        action = "Review gross margin, SG&A run-rate, hiring pace, and discretionary spend."
    elif "net_debt_to_ebitda" in metric_set:
        action = "Review debt headroom, free cash flow, cash sweep assumptions, and liquidity risk."
    else:
        action = "Review underlying VCP milestone drift and assign owner follow-up."

    if len(red) >= 2:
        headline = f"{company_name} requires immediate attention: multiple VCP metrics are Red ({', '.join(metrics)})."
    elif len(red) == 1:
        headline = f"{company_name} has one Red VCP drift item requiring follow-up ({', '.join(metrics)})."
    elif amber:
        headline = f"{company_name} has Amber VCP drift requiring monitoring ({', '.join(metrics)})."
    else:
        headline = f"{company_name} is currently on track across evaluated VCP metrics."

    return {
        "company_id": company_id,
        "company_name": company_name,
        "priority_score": score,
        "priority": priority,
        "red_alert_count": len(red),
        "amber_alert_count": len(amber),
        "alert_count": len(red) + len(amber),
        "primary_risks": metrics,
        "headline": headline,
        "recommended_action": action,
    }


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("/portfolio")
def get_portfolio_overview() -> Dict[str, Any]:
    """Live portfolio roll-up from vcp_store + per-company drift."""
    store = VCPStore(DEFAULT_STORE_PATH)
    if not store.exists():
        return {"portfolio_company_count": 0, "total_alerts": 0, "severity_counts": {},
                "action_item_count": 0, "companies": [], "action_items": []}

    companies = []
    action_items = []

    for cid in store.company_ids():
        confirmed = store.load_confirmed_for_company(cid)
        if not confirmed:
            continue

        name = confirmed[0].company_name or cid
        kpi_records = _load_kpi(cid)

        if not kpi_records:
            # VCP locked but no financials yet
            companies.append({
                "company_id": cid, "company_name": name,
                "health": "Not Evaluable", "status_counts": {},
                "milestones_on_track": 0, "milestones_total": len(confirmed),
                "headline_metrics": {}, "alert_count": 0,
                "hitl_status": "vcp_confirmed", "priority": None, "priority_rank": None,
                "headline": f"VCP locked — {len(confirmed)} milestone(s). Upload financials to begin monitoring.",
                "recommended_action": None, "primary_risks": [],
            })
            continue

        drift = run_vcp_drift_for_kpi_records(
            company_id=cid,
            kpi_records_path=str(_kpi_records_path(cid)),
            vcp_store_path=DEFAULT_STORE_PATH,
        )
        counts = drift.get("status_counts", {})

        headline_metrics: Dict[str, Any] = {}
        for metric in ("annual_revenue", "ebitda_margin", "net_debt_to_ebitda"):
            r = next((x for x in drift.get("results", []) if x["metric"] == metric), None)
            if r:
                headline_metrics[metric] = {
                    "actual": r.get("actual_value"),
                    "target": r.get("target_value"),
                    "gap_pct": r.get("gap_pct"),
                    "status": r.get("status"),
                }

        item = _action_item(cid, name, drift)
        if item:
            action_items.append(item)

        companies.append({
            "company_id": cid, "company_name": name,
            "health": _worst_status(counts), "status_counts": counts,
            "milestones_on_track": counts.get("Green", 0),
            "milestones_total": sum(counts.values()),
            "headline_metrics": headline_metrics,
            "alert_count": sum(1 for r in drift.get("results", []) if r.get("status") in ("Red", "Amber")),
            "hitl_status": "monitoring",
            "priority": item["priority"] if item else None,
            "priority_rank": None,
            "headline": item["headline"] if item else f"{name} is on track.",
            "recommended_action": item["recommended_action"] if item else None,
            "primary_risks": item["primary_risks"] if item else [],
        })

    # Rank action items by score descending
    action_items.sort(key=lambda x: x["priority_score"], reverse=True)
    for i, item in enumerate(action_items, 1):
        item["priority_rank"] = i
        # Propagate rank back to the company card
        for c in companies:
            if c["company_id"] == item["company_id"]:
                c["priority_rank"] = i
                break

    companies.sort(key=lambda x: (x["priority_rank"] is None, x["priority_rank"] or 0, x["company_name"]))

    severity_counts: Dict[str, int] = {}
    for item in action_items:
        for a in ["Red"] * item["red_alert_count"] + ["Amber"] * item["amber_alert_count"]:
            severity_counts[a] = severity_counts.get(a, 0) + 1

    return {
        "portfolio_company_count": len(companies),
        "total_alerts": sum(c["alert_count"] for c in companies),
        "severity_counts": severity_counts,
        "action_item_count": len(action_items),
        "companies": companies,
        "action_items": action_items,
    }


@router.get("/company/{company_id}")
def get_company_detail(company_id: str) -> Dict[str, Any]:
    """Live company deep dive: VCP milestones with generated plan paths, drift, and KPI series."""
    store = VCPStore(DEFAULT_STORE_PATH)
    milestones = [m.to_dict() for m in store.load_confirmed_for_company(company_id)]
    if not milestones:
        raise HTTPException(status_code=404, detail=f"No confirmed VCP for {company_id}. Complete Setup first.")

    name = milestones[0].get("company_name") or company_id
    kpi_records = _load_kpi(company_id)

    if not kpi_records:
        return {
            "company_id": company_id, "company_name": name,
            "sector": None, "currency": "GBP",
            "health": "Not Evaluable", "status_counts": {},
            "latest_period_end": None,
            "milestones": milestones,
            "drift_results": [], "kpi_series": [],
        }

    kpi_periods = [r["period_end"] for r in kpi_records if r.get("period_end")]
    milestones = _enrich_milestones(milestones, kpi_periods)

    drift = run_vcp_drift_for_kpi_records(
        company_id=company_id,
        kpi_records_path=str(_kpi_records_path(company_id)),
        vcp_store_path=DEFAULT_STORE_PATH,
    )

    series = []
    for r in kpi_records:
        rev = r.get("revenue")
        ebitda = r.get("adjusted_ebitda") or r.get("ebitda_proxy")
        net_debt = r.get("net_debt")
        series.append({
            "period_end": r.get("period_end"),
            "revenue": rev,
            "ebitda": ebitda,
            "ebitda_margin": (ebitda / rev) if (rev and ebitda is not None) else None,
            "net_debt": net_debt,
            "net_debt_to_ebitda": (net_debt / (ebitda * 12)) if (ebitda and net_debt is not None) else None,
            "cash": r.get("cash"),
        })

    return {
        "company_id": company_id, "company_name": name,
        "sector": kpi_records[0].get("source_type"),
        "currency": kpi_records[0].get("currency", "GBP"),
        "health": _worst_status(drift.get("status_counts", {})),
        "status_counts": drift.get("status_counts", {}),
        "latest_period_end": drift.get("latest_period_end"),
        "milestones": milestones,
        "drift_results": drift.get("results", []),
        "kpi_series": series,
    }


@router.get("/company/{company_id}/irr")
def get_irr_scenarios(company_id: str) -> Dict[str, Any]:
    """PE IRR sensitivity matrix derived live from VCP targets and KPI entry metrics."""
    store = VCPStore(DEFAULT_STORE_PATH)
    milestones = [m.to_dict() for m in store.load_confirmed_for_company(company_id)]
    if not milestones:
        raise HTTPException(status_code=404, detail=f"No confirmed VCP for {company_id}.")
    return _irr_matrix(company_id, _load_kpi(company_id), milestones)


@router.get("/company/{company_id}/peers")
def get_peer_benchmark(company_id: str) -> Dict[str, Any]:
    """Peer benchmarking: company latest metrics vs sector medians."""
    from app.analytics.peer_benchmarking import run_peer_benchmark_for_company

    kpi_path = _kpi_records_path(company_id)
    if not kpi_path.exists():
        raise HTTPException(status_code=404, detail=f"No KPI records for {company_id}")

    # Auto-register sector mapping if not already present
    store = VCPStore(DEFAULT_STORE_PATH)
    confirmed = store.load_confirmed_for_company(company_id)
    name = confirmed[0].company_name if confirmed else company_id
    sector = _infer_sector(company_id, name)
    if sector:
        _register_sector(company_id, sector)

    try:
        return run_peer_benchmark_for_company(company_id=company_id, kpi_records_path=str(kpi_path))
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/hitl")
def get_hitl_queue() -> Dict[str, Any]:
    return _load_json(HITL_QUEUE, default={"queue_item_count": 0, "pending_review_count": 0, "queue_items": []})


class DecisionRequest(BaseModel):
    review_id: str
    decision: str
    reviewed_by: str
    reviewer_note: Optional[str] = None
    edited_recommended_action: Optional[str] = None


@router.post("/hitl/decision")
def post_hitl_decision(req: DecisionRequest) -> Dict[str, Any]:
    try:
        return apply_hitl_decision(
            review_id=req.review_id, decision=req.decision,
            reviewed_by=req.reviewed_by, reviewer_note=req.reviewer_note,
            edited_recommended_action=req.edited_recommended_action,
            queue_path=str(HITL_QUEUE), audit_log_path=str(HITL_AUDIT),
        )
    except HITLDecisionError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/audit-log")
def get_audit_log() -> Dict[str, Any]:
    if not HITL_AUDIT.exists():
        return {"entries": [], "entry_count": 0}
    return _load_json(HITL_AUDIT)


# ── VCP extraction & setup ────────────────────────────────────────────────────

@router.get("/extract/status")
def extract_status() -> Dict[str, Any]:
    return {
        "llm_configured": azure_openai.is_configured(),
        "mode": "azure_openai" if azure_openai.is_configured() else "offline_heuristic",
        "missing_vars": azure_openai.missing_vars(),
        "deployment": azure_openai.deployment_name(),
    }


@router.post("/extract/{company_id}")
def run_extraction(company_id: str) -> Dict[str, Any]:
    """Run VCP extraction over a pre-staged IC memo file."""
    pdf = IC_MEMO_DIR / f"{company_id}_ic_memo.pdf"
    md = IC_MEMO_DIR / f"{company_id}_ic_memo.md"
    memo_path = pdf if pdf.exists() else md if md.exists() else None
    if not memo_path:
        raise HTTPException(status_code=404, detail=f"No IC memo for {company_id}")

    store = VCPStore(DEFAULT_STORE_PATH)
    confirmed = store.load_confirmed_for_company(company_id)
    company_name = confirmed[0].company_name if confirmed else company_id

    result = extract_from_document(str(memo_path), company_id, company_name)
    milestones = to_vcp_milestones(result)
    (PROCESSED / f"{company_id}_extracted_milestones.json").write_text(
        json.dumps([m.to_dict() for m in milestones], indent=2, default=str), encoding="utf-8"
    )
    return {
        "company_id": company_id, "company_name": company_name,
        "extraction_mode": result.extraction_mode, "model": result.model,
        "source_document": result.source_document, "document_loader": result.document_loader,
        "milestone_count": len(milestones),
        "needs_review_count": sum(1 for m in milestones if m.confidence < 0.7),
        "milestones": [m.to_dict() for m in milestones],
    }


@router.post("/extract-upload")
async def run_extraction_from_upload(
    file: UploadFile = File(...),
    company_id: Optional[str] = Form(None),
    company_name: Optional[str] = Form(None),
) -> Dict[str, Any]:
    """VCP extraction from an uploaded IC memo (PDF/DOCX/MD)."""
    from app.ingestion.document_loader import _DOCLING_SUFFIXES, _PASSTHROUGH_SUFFIXES, _PDF_SUFFIXES

    filename = file.filename or "uploaded"
    suffix = Path(filename).suffix.lower()
    if suffix not in (_DOCLING_SUFFIXES | _PASSTHROUGH_SUFFIXES | _PDF_SUFFIXES):
        raise HTTPException(status_code=400, detail=f"Unsupported file type '{suffix}'.")

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    if len(raw) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 25 MB).")

    resolved_name = (company_name or "").strip() or _clean_name(Path(filename).stem)
    resolved_id = (company_id or "").strip() or _slugify(resolved_name)

    tmp_path: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(raw)
            tmp_path = Path(tmp.name)
        result = extract_from_document(str(tmp_path), resolved_id, resolved_name)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    finally:
        if tmp_path:
            tmp_path.unlink(missing_ok=True)

    result.source_document = filename
    milestones = to_vcp_milestones(result)
    if not milestones:
        raise HTTPException(status_code=422, detail="No commitments extracted — document may be image-only.")

    (PROCESSED / f"{resolved_id}_extracted_milestones.json").write_text(
        json.dumps([m.to_dict() for m in milestones], indent=2, default=str), encoding="utf-8"
    )
    return {
        "company_id": resolved_id, "company_name": resolved_name,
        "extraction_mode": result.extraction_mode, "model": result.model,
        "source_document": filename, "document_loader": result.document_loader,
        "milestone_count": len(milestones),
        "needs_review_count": sum(1 for m in milestones if m.confidence < 0.7),
        "milestones": [m.to_dict() for m in milestones],
    }


class ConfirmRequest(BaseModel):
    company_name: Optional[str] = None
    reviewed_by: str
    reviewer_note: Optional[str] = None
    milestones: List[Dict[str, Any]]


@router.post("/extract/{company_id}/confirm")
def confirm_extraction(company_id: str, req: ConfirmRequest) -> Dict[str, Any]:
    """Lock reviewed milestones into the VCPStore as confirmed ground truth."""
    store = VCPStore(DEFAULT_STORE_PATH)
    confirmed = store.load_confirmed_for_company(company_id)
    company_name = req.company_name or (confirmed[0].company_name if confirmed else company_id)
    try:
        return confirm_vcp_milestones(
            company_id=company_id, company_name=company_name,
            milestones=req.milestones, reviewed_by=req.reviewed_by,
            reviewer_note=req.reviewer_note,
        )
    except VCPConfirmationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/store/{company_id}")
def get_confirmed_vcp(company_id: str) -> Dict[str, Any]:
    """Confirmed (locked) VCP for a company."""
    store = VCPStore(DEFAULT_STORE_PATH)
    milestones = store.load_for_company(company_id) if store.exists() else []
    return {
        "company_id": company_id,
        "confirmed": bool(milestones) and all(m.confirmed for m in milestones),
        "version": max((m.version for m in milestones), default=0),
        "milestone_count": len(milestones),
        "milestones": [m.to_dict() for m in milestones],
    }


@router.get("/memo")
def get_memo() -> Dict[str, Any]:
    if not PORTFOLIO_MEMO.exists():
        raise HTTPException(status_code=404, detail="Portfolio memo not generated yet.")
    return {"markdown": PORTFOLIO_MEMO.read_text(encoding="utf-8")}


@router.post("/memo/generate")
def generate_memo() -> Dict[str, Any]:
    """Generate portfolio memo from live portfolio data (no pre-run pipeline needed)."""
    from datetime import datetime, timezone

    store = VCPStore(DEFAULT_STORE_PATH)
    if not store.exists():
        raise HTTPException(status_code=404, detail="No VCP data found. Complete Setup first.")

    # Build action items from live drift (same logic as portfolio endpoint)
    action_items: List[Dict[str, Any]] = []
    for cid in store.company_ids():
        confirmed = store.load_confirmed_for_company(cid)
        if not confirmed:
            continue
        name = confirmed[0].company_name or cid
        kpi_records = _load_kpi(cid)
        if not kpi_records:
            continue
        drift = run_vcp_drift_for_kpi_records(
            company_id=cid,
            kpi_records_path=str(_kpi_records_path(cid)),
            vcp_store_path=DEFAULT_STORE_PATH,
        )
        item = _action_item(cid, name, drift)
        if item:
            action_items.append(item)

    action_items.sort(key=lambda x: x["priority_score"], reverse=True)
    for i, item in enumerate(action_items, 1):
        item["priority_rank"] = i

    generated_at = datetime.now(timezone.utc).isoformat()
    severity_counts: Dict[str, int] = {}
    for item in action_items:
        for _ in range(item["red_alert_count"]):
            severity_counts["Red"] = severity_counts.get("Red", 0) + 1
        for _ in range(item["amber_alert_count"]):
            severity_counts["Amber"] = severity_counts.get("Amber", 0) + 1

    company_count = len(store.company_ids())
    total_alerts = sum(i["alert_count"] for i in action_items)
    red = severity_counts.get("Red", 0)
    amber = severity_counts.get("Amber", 0)
    p1 = sum(1 for i in action_items if i.get("priority") == "P1")

    lines: List[str] = []
    lines.append("# Portfolio Value Creation Memo")
    lines.append("")
    lines.append(f"_Generated: {generated_at}_")
    lines.append("")
    lines.append("## Executive Summary")
    lines.append("")
    lines.append(
        f"Across **{company_count} portfolio companies**, monitoring produced "
        f"**{total_alerts} VCP drift alerts** ({red} Red, {amber} Amber). "
        f"**{p1} company(ies)** are flagged P1 for immediate operating-partner attention."
    )
    lines.append("")
    if action_items:
        top = action_items[0]
        lines.append(f"Highest priority: **{top['company_name']}** — {top['headline']}")
        lines.append("")

    lines.append("## Portfolio Alert Overview")
    lines.append("")
    lines.append("| Rank | Company | Priority | Red | Amber | Primary risks |")
    lines.append("|---|---|---|---|---|---|")
    for item in action_items:
        lines.append(
            f"| {item['priority_rank']} | {item['company_name']} | {item['priority']} "
            f"| {item['red_alert_count']} | {item['amber_alert_count']} "
            f"| {', '.join(item['primary_risks'])} |"
        )
    lines.append("")

    lines.append("## Company-Level Action Items")
    lines.append("")
    for item in action_items:
        lines.append(f"### {item['priority_rank']}. {item['company_name']} [{item['priority']}]")
        lines.append("")
        lines.append(f"- **Headline:** {item['headline']}")
        lines.append(f"- **Recommended action:** {item['recommended_action']}")
        lines.append(
            f"- **Priority score:** {item['priority_score']} "
            f"({item['red_alert_count']} Red, {item['amber_alert_count']} Amber)"
        )
        lines.append("")

    memo_text = "\n".join(lines)
    PORTFOLIO_MEMO.parent.mkdir(parents=True, exist_ok=True)
    PORTFOLIO_MEMO.write_text(memo_text, encoding="utf-8")

    return {"markdown": memo_text, "generated_at": generated_at, "action_item_count": len(action_items)}
