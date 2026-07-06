"""
VCP monitoring API.

Single source of truth: vcp_store.json (confirmed milestones) + {company_id}_kpi_records.json.
Everything is computed live — no pre-generated pipeline artifacts read by these endpoints.

Batch scripts (run_portfolio_vcp_monitoring.py etc.) still exist for exports/reports,
but the API never depends on their output files.
"""

from __future__ import annotations

import json
import re
import tempfile
from datetime import date
from pathlib import Path

import pandas as pd
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from app.agents.vcp_extraction_agent import extract_from_document, to_vcp_milestones
from app.analytics.action_items import build_action_item
from app.analytics.data_freshness import FreshnessStatus, compute_freshness
from app.analytics.sector import infer_sector_key
from app.data_sources.edgar import fetch_company_sic
from app.analytics.vcp_drift import run_vcp_drift_for_kpi_records
from app.ingestion.quarterly_resample import infer_periods_per_year
from app.llm import azure_openai
from app.quant.vcp_irr import build_vcp_irr
from app.store.company_store import load_company_meta, update_company_meta
from app.store.deal_store import DealStore
from app.store.kpi_records_store import load_kpi_records
from app.store.portfolio_memo_store import load_portfolio_memo, save_portfolio_memo
from app.store.vcp_store import VCPStore
from app.workflows.hitl_decisions import HITLDecisionError, apply_hitl_decision, load_audit_entries
from app.workflows.hitl_queue import (
    load_hitl_queue,
    refresh_hitl_review_queue_from_action_items,
    save_hitl_queue,
)
from app.workflows.vcp_confirmation import (
    DEFAULT_STORE_PATH,
    VCPConfirmationError,
    confirm_vcp_milestones,
    kpi_records_path,
)

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROCESSED = PROJECT_ROOT / "data" / "processed"
IC_MEMO_DIR = PROJECT_ROOT / "data" / "raw" / "ic_memos"
HITL_QUEUE = PROCESSED / "hitl_review_queue.json"
HITL_AUDIT = PROCESSED / "hitl_audit_log.json"

PROCESSED.mkdir(parents=True, exist_ok=True)

_MAX_UPLOAD_BYTES = 25 * 1024 * 1024

# Sentinel distinguishing "caller didn't pass a preloaded deal" from "caller
# passed deal=None because there truly is no deal record for this company."
_UNSET = object()

router = APIRouter(prefix="/api/vcp", tags=["vcp"])


# ── Utilities ────────────────────────────────────────────────────────────────

def _kpi_records_path(company_id: str) -> Path:
    return PROJECT_ROOT / kpi_records_path(company_id)


def _load_kpi(company_id: str) -> List[Dict]:
    return load_kpi_records(str(_kpi_records_path(company_id)))


def _load_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        if default is not None:
            return default
        raise HTTPException(status_code=404, detail=f"Not found: {path.name}")
    text = path.read_text(encoding="utf-8")
    if not text.strip():
        # Concurrent writers (multiple tabs polling the same endpoint) can briefly
        # observe a truncated file mid-write; treat that as "nothing here yet"
        # rather than a hard failure.
        if default is not None:
            return default
        raise HTTPException(status_code=404, detail=f"Not found: {path.name}")
    return json.loads(text)


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


SECTOR_BENCHMARKS = PROJECT_ROOT / "data" / "reference" / "sector_benchmarks.json"


def _infer_sector(
    company_id: str,
    company_name: str,
    deal: Optional[Any] = _UNSET,
) -> Optional[str]:
    """Resolve sector key. Resolution order:
    1. company_meta sidecar (written at ingestion/onboarding — canonical new path)
    2. DealStore (backward-compat for existing deal JSON files, e.g. qualtrics.json)
    3. infer_sector_key() from app.analytics.sector (SIC map → keyword inference)

    `deal` lets a caller that already loaded the company's DealMetadata pass it
    in, instead of this function re-fetching the same Postgres row.
    """
    meta = load_company_meta(company_id, base_dir=str(PROCESSED))
    if meta and meta.sector_key:
        return meta.sector_key
    if deal is _UNSET:
        deal = DealStore().load(company_id)
    if deal and deal.sector_key:
        return deal.sector_key
    return infer_sector_key(company_id, company_name, sic_code=meta.sic if meta else None)


def _register_sector(company_id: str, sector_key: str) -> None:
    """Persist to sector_benchmarks.json company_sector_map (legacy belt-and-suspenders)."""
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
    anchor_date_str: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Linear interpolation baseline→target from the plan anchor to the target date.

    The plan anchors at the deal close date when known — the underwriting plan
    starts at entry, not at the first period of (possibly pre-deal) KPI history.
    KPI period dates inside the plan window are kept as plan points so the chart
    can overlay plan vs actual; the path is then extended on a quarterly grid to
    the target date so the full plan renders even beyond reported actuals.
    """
    if baseline is None or target is None or not target_date_str:
        return []
    try:
        t_end = date.fromisoformat(str(target_date_str)[:10])
    except ValueError:
        return []

    t_start = None
    if anchor_date_str:
        try:
            t_start = date.fromisoformat(str(anchor_date_str)[:10])
        except ValueError:
            t_start = None
    if t_start is None:
        if not kpi_periods:
            return []
        try:
            t_start = date.fromisoformat(str(kpi_periods[0])[:10])
        except ValueError:
            return []

    total_days = (t_end - t_start).days
    if total_days <= 0:
        return []

    plan_dates = {t_start, t_end}
    for p in kpi_periods:
        try:
            p_date = date.fromisoformat(str(p)[:10])
        except ValueError:
            continue
        if t_start <= p_date <= t_end:
            plan_dates.add(p_date)
    # Quarterly grid so the plan line continues past the latest reported actual.
    grid = pd.date_range(start=t_start, end=t_end, freq="QE")
    plan_dates.update(d.date() for d in grid)

    result = []
    for p_date in sorted(plan_dates):
        frac = (p_date - t_start).days / total_days
        result.append({
            "period_end": p_date.isoformat(),
            "planned_value": baseline + frac * (target - baseline),
        })
    return result


def _enrich_milestones(
    milestones: List[Dict],
    kpi_periods: List[str],
    company_id: Optional[str] = None,
    deal: Optional[Any] = _UNSET,
) -> List[Dict]:
    """Attach a generated plan_path to every milestone that doesn't already have one.

    `deal` lets a caller that already loaded the company's DealMetadata pass it
    in, instead of this function re-fetching the same Postgres row.
    """
    anchor = None
    if company_id:
        if deal is _UNSET:
            deal = DealStore().load(company_id)
        if deal and deal.deal_close_date:
            anchor = deal.deal_close_date
    out = []
    for m in milestones:
        m = dict(m)
        meta = dict(m.get("metadata") or {})
        if not meta.get("plan_path"):
            meta["plan_path"] = _plan_path(
                m.get("baseline_value"), m.get("target_value"),
                m.get("target_date"), kpi_periods,
                anchor_date_str=anchor,
            )
            m["metadata"] = meta
        out.append(m)
    return out


# ── Equity-at-risk HITL alert injection ─────────────────────────────────────

def _inject_equity_at_risk_alert(
    company_id: str,
    kpi_records: List[Dict[str, Any]],
    nd_ebitda_str: str,
) -> None:
    """
    Push a P1 HITL alert into the review queue when the IRR endpoint detects
    that the base-case quant projection yields negative exit equity.

    Idempotent: if an equity-at-risk alert for this company already exists in
    the queue as pending, it is not duplicated.
    """
    from datetime import datetime, timezone

    queue_data = load_hitl_queue(str(HITL_QUEUE), default={"queue_items": []})
    existing = queue_data.get("queue_items", [])

    # Deduplicate: skip if there is already a pending equity-at-risk item for this company.
    for item in existing:
        if (
            item.get("company_id") == company_id
            and "equity" in item.get("headline", "").lower()
            and item.get("status") == "pending_review"
        ):
            return

    company_name = kpi_records[0].get("company_name", company_id) if kpi_records else company_id
    now = datetime.now(timezone.utc).isoformat()

    alert = {
        "review_id": f"review_equity_risk_{company_id}",
        "created_at": now,
        "status": "pending_review",
        "review_action": "immediate_review",
        "priority_rank": 1,
        "priority": "P1",
        "priority_score": 100,
        "company_id": company_id,
        "company_name": company_name,
        "headline": f"CRITICAL: Base-case DCF projects negative equity value at exit — {company_name}",
        "recommended_action": (
            "Urgent operating review required. Quant forecast projects that net debt "
            "exceeds exit EBITDA × entry multiple under the base case. "
            f"Current Net Debt / Trailing EBITDA: {nd_ebitda_str}. "
            "Assess refinancing options, covenant headroom, and downside recovery scenarios."
        ),
        "primary_risks": [
            "Equity value wiped at base-case exit",
            f"Net Debt / Trailing EBITDA: {nd_ebitda_str} — leverage expanding, not compressing",
            "EBITDA trajectory insufficient to service debt and return equity at entry multiple",
        ],
        "red_alert_count": 1,
        "amber_alert_count": 0,
        "evidence": [
            {
                "metric": "base_case_exit_equity",
                "signal": "negative",
                "source": "quant_forecast_irr",
            }
        ],
        "decision": {
            "decision_status": "not_reviewed",
            "reviewed_by": None,
            "reviewed_at": None,
            "reviewer_note": None,
            "edited_recommended_action": None,
        },
    }

    existing.insert(0, alert)
    queue_data["queue_items"] = existing
    queue_data["queue_item_count"] = len(existing)
    queue_data["pending_review_count"] = sum(
        1 for i in existing if i.get("status") == "pending_review"
    )

    save_hitl_queue(queue_data, str(HITL_QUEUE))


# ── HITL decision fold-back ──────────────────────────────────────────────────

# Queue item status → the review_status surfaced on live alerts.
_STATUS_TO_REVIEW = {
    "pending_review": "pending",
    "approved": "approved",
    "approved_with_edit": "edited",
    "rejected": "rejected",
}


def _hitl_decision_map() -> Dict[str, Dict[str, Any]]:
    """Map company_id → its current HITL decision, read from the review queue."""
    queue = load_hitl_queue(str(HITL_QUEUE), default={"queue_items": []})
    out: Dict[str, Dict[str, Any]] = {}
    for q in queue.get("queue_items", []):
        cid = q.get("company_id")
        if not cid:
            continue
        decision = q.get("decision", {})
        out[cid] = {
            "review_status": _STATUS_TO_REVIEW.get(q.get("status", ""), "pending"),
            "review_id": q.get("review_id"),
            "reviewed_by": decision.get("reviewed_by"),
            "reviewed_at": decision.get("reviewed_at"),
            "edited_recommended_action": decision.get("edited_recommended_action"),
        }
    return out


def _apply_review_to_action_item(item: Dict[str, Any], decision: Optional[Dict[str, Any]]) -> None:
    """Stamp an action item with its HITL review status; swap in edited action text."""
    if not decision:
        item["review_status"] = "none"
        return
    item["review_status"] = decision["review_status"]
    item["reviewed_by"] = decision.get("reviewed_by")
    item["reviewed_at"] = decision.get("reviewed_at")
    if decision["review_status"] == "edited" and decision.get("edited_recommended_action"):
        item["recommended_action"] = decision["edited_recommended_action"]


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
    deals_by_id = DealStore().load_all()

    for cid in store.company_ids():
        confirmed = store.load_confirmed_for_company(cid)
        if not confirmed:
            continue

        name = confirmed[0].company_name or cid
        kpi_records = _load_kpi(cid)
        deal = deals_by_id.get(cid)
        freshness = compute_freshness(cid, kpi_records, deal.deal_close_date if deal else None)

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
                "data_freshness": freshness.model_dump(),
            })
            continue

        # OVERDUE data is itself the signal: suppress drift/IRR analysis on stale
        # actuals (a false drift alert is worse than no alert) and route the late
        # submission to the GP as its own alert instead.
        if freshness.freshness_status == FreshnessStatus.OVERDUE:
            overdue_item = {
                "company_id": cid, "company_name": name,
                "priority_score": 20, "priority": "P2",
                "red_alert_count": 0, "amber_alert_count": 1, "alert_count": 1,
                "primary_risks": ["Data submission overdue"],
                "headline": f"{name}: {freshness.message}",
                "recommended_action": "Contact portco CFO — confirm data pack submission or escalate.",
                "evidence": [{
                    "metric": "reporting_schedule", "severity": "Amber",
                    "summary": freshness.message, "source_path": None, "source_column": None,
                }],
                "alert_type": "DATA_SUBMISSION_OVERDUE",
            }
            action_items.append(overdue_item)
            companies.append({
                "company_id": cid, "company_name": name,
                "health": "Amber", "status_counts": {},
                "milestones_on_track": 0, "milestones_total": len(confirmed),
                "headline_metrics": {}, "alert_count": 1,
                "hitl_status": "monitoring", "priority": "P2", "priority_rank": None,
                "headline": overdue_item["headline"],
                "recommended_action": overdue_item["recommended_action"],
                "primary_risks": overdue_item["primary_risks"],
                "data_source": kpi_records[0].get("source_type", "unknown"),
                "currency": kpi_records[0].get("currency", "GBP"),
                "data_freshness": freshness.model_dump(),
            })
            continue

        drift = run_vcp_drift_for_kpi_records(
            company_id=cid,
            kpi_records_path=str(_kpi_records_path(cid)),
            vcp_store_path=DEFAULT_STORE_PATH,
            milestones=confirmed,
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

        # HISTORICAL (structural cutoff, e.g. pre-take-private public data) is real,
        # already-known drift, not an open operational risk — show the actual
        # numbers (framed by the freshness badge) but don't raise a fresh GP alert
        # asking someone to act on it.
        is_historical = freshness.freshness_status == FreshnessStatus.HISTORICAL
        item = build_action_item(cid, name, drift)
        if item and not is_historical:
            action_items.append(item)

        companies.append({
            "company_id": cid, "company_name": name,
            "health": _worst_status(counts),
            "status_counts": counts,
            "milestones_on_track": counts.get("Green", 0),
            "milestones_total": sum(counts.values()),
            "headline_metrics": headline_metrics,
            "alert_count": sum(1 for r in drift.get("results", []) if r.get("status") in ("Red", "Amber")),
            "hitl_status": "monitoring",
            "priority": item["priority"] if (item and not is_historical) else None,
            "priority_rank": None,
            "headline": item["headline"] if item else f"{name} is on track.",
            "recommended_action": item["recommended_action"] if item else None,
            "primary_risks": item["primary_risks"] if item else [],
            "data_source": kpi_records[0].get("source_type", "unknown") if kpi_records else None,
            "currency": kpi_records[0].get("currency", "GBP") if kpi_records else "GBP",
            "data_freshness": freshness.model_dump(),
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

    # Keep the HITL review queue in sync with the live monitoring run: new alerts
    # become pending review items; existing items (and their decisions) are preserved.
    try:
        refresh_hitl_review_queue_from_action_items(action_items, output_path=str(HITL_QUEUE))
    except Exception:
        pass  # queue refresh is best-effort; never break the portfolio roll-up

    # Fold HITL decisions back into the live view — the gate from the plan: an alert
    # is only "board-ready" once a human approves it; a rejected alert is dismissed.
    decisions = _hitl_decision_map()
    for item in action_items:
        _apply_review_to_action_item(item, decisions.get(item["company_id"]))
    for c in companies:
        c["review_status"] = (decisions.get(c["company_id"]) or {}).get("review_status", "none")

    # Escalation counts exclude dismissed (rejected) alerts.
    severity_counts = {}
    for item in action_items:
        if item["review_status"] == "rejected":
            continue
        for a in ["Red"] * item["red_alert_count"] + ["Amber"] * item["amber_alert_count"]:
            severity_counts[a] = severity_counts.get(a, 0) + 1

    return {
        "portfolio_company_count": len(companies),
        "total_alerts": sum(c["alert_count"] for c in companies),
        "severity_counts": severity_counts,
        "action_item_count": sum(1 for i in action_items if i["review_status"] != "rejected"),
        "companies": companies,
        "action_items": action_items,
    }


@router.get("/company/{company_id}")
def get_company_detail(company_id: str) -> Dict[str, Any]:
    """Live company deep dive: VCP milestones with generated plan paths, drift, and KPI series."""
    store = VCPStore(DEFAULT_STORE_PATH)
    confirmed_milestones = store.load_confirmed_for_company(company_id)
    milestones = [m.to_dict() for m in confirmed_milestones]
    if not milestones:
        raise HTTPException(status_code=404, detail=f"No confirmed VCP for {company_id}. Complete Setup first.")

    name = milestones[0].get("company_name") or company_id
    kpi_records = _load_kpi(company_id)
    deal = DealStore().load(company_id)
    freshness = compute_freshness(company_id, kpi_records, deal.deal_close_date if deal else None)

    if not kpi_records:
        return {
            "company_id": company_id, "company_name": name,
            "sector": None, "currency": "GBP",
            "data_source": None, "basis_mismatch": False, "last_filing_date": None,
            "health": "Not Evaluable", "status_counts": {},
            "latest_period_end": None,
            "milestones": milestones,
            "drift_results": [], "kpi_series": [],
            "data_freshness": freshness.model_dump(),
        }

    kpi_periods = [r["period_end"] for r in kpi_records if r.get("period_end")]
    milestones = _enrich_milestones(milestones, kpi_periods, company_id=company_id, deal=deal)

    drift = run_vcp_drift_for_kpi_records(
        company_id=company_id,
        kpi_records_path=str(_kpi_records_path(company_id)),
        vcp_store_path=DEFAULT_STORE_PATH,
        milestones=confirmed_milestones,
    )

    periods_per_year = infer_periods_per_year(kpi_records)
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
            "net_debt_to_ebitda": (net_debt / (ebitda * periods_per_year)) if (ebitda and net_debt is not None) else None,
            "cash": r.get("cash"),
        })

    first_rec = kpi_records[0]
    data_source = first_rec.get("source_type", "unknown")
    # Basis guard (company-level counterpart of the IRR engine's check): an EDGAR
    # series with no adjusted EBITDA falls back to the GAAP operating-income proxy,
    # which is not comparable to the VCP's non-GAAP targets — flag it so the UI can
    # explain the gap instead of implying operational underperformance.
    basis_mismatch = data_source == "edgar" and not any(
        r.get("adjusted_ebitda") is not None for r in kpi_records
    )
    last_filing_date = max(kpi_periods) if data_source == "edgar" and kpi_periods else None
    # Only OVERDUE (unreliable, late-arriving actuals) gates the drift/IRR display —
    # HISTORICAL (e.g. Qualtrics pre-take-private) is real, finalized data and the
    # deep dive should still show it, just framed by the freshness badge.
    monitoring_paused = freshness.freshness_status == FreshnessStatus.OVERDUE
    return {
        "company_id": company_id, "company_name": name,
        "sector": _infer_sector(company_id, name, deal=deal),
        "data_source": data_source,
        "basis_mismatch": basis_mismatch,
        "last_filing_date": last_filing_date,
        "cik": first_rec.get("cik") or None,
        "currency": first_rec.get("currency", "GBP"),
        "periods_per_year": periods_per_year,
        "health": "Not Evaluable" if monitoring_paused else _worst_status(drift.get("status_counts", {})),
        "status_counts": {} if monitoring_paused else drift.get("status_counts", {}),
        "latest_period_end": drift.get("latest_period_end"),
        "milestones": milestones,
        "drift_results": [] if monitoring_paused else drift.get("results", []),
        "kpi_series": series,
        "data_freshness": freshness.model_dump(),
    }


@router.get("/company/{company_id}/irr")
def get_irr_scenarios(company_id: str) -> Dict[str, Any]:
    """
    IRR scenarios + sensitivity matrix.

    Projections come from the quant forecast engine (P10/P50/P90 exit EBITDA);
    entry equity and the IC-underwritten target come from the deal-metadata store.
    VCP milestones are NOT used here — they are ground truth for drift, not projection.
    """
    kpi_records = _load_kpi(company_id)
    if not kpi_records:
        raise HTTPException(status_code=404, detail=f"No KPI records for {company_id}.")
    try:
        result = build_vcp_irr(company_id, kpi_records)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # Equity-at-risk: inject a P1 HITL alert so the review queue surfaces this
    # automatically rather than waiting for the next monitoring run.
    if result.get("equity_at_risk"):
        detail = result["equity_at_risk_detail"] or {}
        nd_str = (
            f"{detail['nd_ebitda_trailing']}x"
            if detail.get("nd_ebitda_trailing") is not None
            else "n/a"
        )
        _inject_equity_at_risk_alert(company_id, kpi_records, nd_str)

    return result


@router.get("/company/{company_id}/peers")
def get_peer_benchmark(company_id: str) -> Dict[str, Any]:
    """Peer benchmarking: company latest metrics vs sector medians."""
    from app.analytics.peer_benchmarking import run_peer_benchmark_for_company

    kpi_path = _kpi_records_path(company_id)
    if not _load_kpi(company_id):
        raise HTTPException(status_code=404, detail=f"No KPI records for {company_id}")

    # Auto-register sector mapping if not already present
    store = VCPStore(DEFAULT_STORE_PATH)
    confirmed = store.load_confirmed_for_company(company_id)
    name = confirmed[0].company_name if confirmed else company_id
    sector = _infer_sector(company_id, name)
    if sector:
        _register_sector(company_id, sector)

    try:
        return run_peer_benchmark_for_company(
            company_id=company_id, kpi_records_path=str(kpi_path), sector_key=sector
        )
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/hitl")
def get_hitl_queue() -> Dict[str, Any]:
    return load_hitl_queue(
        str(HITL_QUEUE),
        default={"queue_item_count": 0, "pending_review_count": 0, "queue_items": []},
    )


class DecisionRequest(BaseModel):
    review_id: str
    decision: str
    reviewed_by: str
    reviewer_note: Optional[str] = None
    edited_recommended_action: Optional[str] = None


def _resume_graph_if_paused(company_id: Optional[str], req: DecisionRequest) -> None:
    """Best-effort: if `company_id` has a monitoring-graph run paused at a HITL
    interrupt (started via POST /api/vcp/graph/monitor/{company_id}), resume it
    with this decision. A no-op for decisions on alerts that only ever went
    through the synchronous /api/vcp/portfolio path, or when the Postgres
    checkpointer isn't configured — this never blocks the flat-file decision
    write above, which remains the source of truth for the HITL queue/audit log.
    """
    if not company_id:
        return

    from app.graph.checkpointer import is_configured

    if not is_configured():
        return

    from langgraph.types import Command
    from app.graph.vcp_monitoring_graph_builder import get_vcp_monitoring_graph

    graph = get_vcp_monitoring_graph()
    config = {"configurable": {"thread_id": company_id}}

    try:
        snapshot = graph.get_state(config)
    except Exception:
        return

    if not snapshot or not snapshot.next:
        return  # this thread isn't currently paused — nothing to resume

    graph.invoke(
        Command(resume={
            "decision": req.decision,
            "reviewed_by": req.reviewed_by,
            "reviewer_note": req.reviewer_note,
            "edited_recommended_action": req.edited_recommended_action,
        }),
        config=config,
    )


@router.post("/hitl/decision")
def post_hitl_decision(req: DecisionRequest) -> Dict[str, Any]:
    try:
        target = apply_hitl_decision(
            review_id=req.review_id, decision=req.decision,
            reviewed_by=req.reviewed_by, reviewer_note=req.reviewer_note,
            edited_recommended_action=req.edited_recommended_action,
            queue_path=str(HITL_QUEUE), audit_log_path=str(HITL_AUDIT),
        )
    except HITLDecisionError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc))

    _resume_graph_if_paused(target.get("company_id"), req)

    return target


@router.get("/audit-log")
def get_audit_log() -> Dict[str, Any]:
    entries = load_audit_entries(str(HITL_AUDIT))
    return {"entries": entries, "entry_count": len(entries)}


# ── LangGraph monitoring run (strangler-fig alongside /portfolio, /company) ──
# Same drift -> alert-synthesis -> HITL-routing logic as get_portfolio_overview/
# get_company_detail above, but run through the compiled StateGraph so a Red/
# Amber alert actually pauses (interrupt) on a durable Postgres checkpoint
# instead of completing inline within this request.

@router.post("/graph/monitor/{company_id}")
def run_monitoring_graph(company_id: str) -> Dict[str, Any]:
    from app.graph.vcp_monitoring_graph_builder import get_vcp_monitoring_graph

    graph = get_vcp_monitoring_graph()
    config = {"configurable": {"thread_id": company_id}}
    result = graph.invoke({"company_id": company_id}, config=config)

    interrupts = result.get("__interrupt__")
    if interrupts:
        return {
            "company_id": company_id,
            "thread_id": company_id,
            "status": "interrupted",
            "interrupt": interrupts[0].value,
        }

    return {
        "company_id": company_id,
        "thread_id": company_id,
        "status": result.get("status"),
        "alert_card": result.get("alert_card"),
        "alert_severity": result.get("alert_severity"),
        "hitl_status": result.get("hitl_status"),
        "errors": result.get("errors", []),
    }


# ── Company onboarding (deal metadata + optional EDGAR pull) ─────────────────

class SeedCompanyRequest(BaseModel):
    company_id: str
    company_name: str
    cik: Optional[str] = None
    ticker: Optional[str] = None
    sector_key: Optional[str] = None
    deal_close_date: Optional[str] = None
    entry_ebitda: Optional[float] = None
    entry_ev_multiple: Optional[float] = None
    entry_enterprise_value: Optional[float] = None
    entry_net_debt: Optional[float] = None
    entry_equity_value: Optional[float] = None
    holding_period_years: Optional[float] = None
    fund_vintage: Optional[int] = None
    ic_target_irr: Optional[float] = None
    ic_target_moic: Optional[float] = None
    currency: str = "USD"
    source_document: Optional[str] = None
    notes: Optional[str] = None


@router.post("/companies")
def seed_company(req: SeedCompanyRequest) -> Dict[str, Any]:
    """Onboard a new portfolio company.

    For private portcos: saves deal metadata only.
    For public take-privates: saves deal metadata + triggers EDGAR KPI ingestion by CIK.

    This is the backend counterpart to the Setup flow's EDGAR path — the frontend
    calls this after locking VCP milestones so both happen in one user action.
    """
    from app.agents.kpi_extraction_agent import run_kpi_extraction_agent
    from app.schemas.kpi_schema import KPIExtractionConfig
    from app.store.deal_store import DealMetadata  # DealMetadata only; DealStore is top-level

    out: Dict[str, Any] = {
        "company_id": req.company_id,
        "company_name": req.company_name,
        "deal_metadata_saved": False,
        "edgar_ingested": False,
        "kpi_periods": 0,
        "source_quality_status": None,
        "errors": [],
    }

    # 1. Persist deal metadata
    deal = DealMetadata(
        company_id=req.company_id,
        company_name=req.company_name,
        deal_close_date=req.deal_close_date,
        entry_ebitda=req.entry_ebitda,
        entry_ev_multiple=req.entry_ev_multiple,
        entry_enterprise_value=req.entry_enterprise_value,
        entry_net_debt=req.entry_net_debt,
        entry_equity_value=req.entry_equity_value,
        holding_period_years=req.holding_period_years,
        fund_vintage=req.fund_vintage,
        ic_target_irr=req.ic_target_irr,
        ic_target_moic=req.ic_target_moic,
        currency=req.currency,
        source_document=req.source_document,
        notes=req.notes,
        sector_key=req.sector_key,
    )
    DealStore().save(deal)
    out["deal_metadata_saved"] = True

    # 2. Write company_meta sidecar — canonical sector store read by _infer_sector()
    sic_code: Optional[str] = None
    if req.cik:
        try:
            sic_code = fetch_company_sic(req.cik.strip())
        except Exception:
            sic_code = None  # sector still resolves via keyword fallback
    resolved_sector = req.sector_key or infer_sector_key(
        req.company_id, req.company_name, sic_code=sic_code
    )
    update_company_meta(
        req.company_id,
        base_dir=str(PROCESSED),
        company_name=req.company_name,
        sector_key=resolved_sector,
        cik=req.cik,
        sic=sic_code,
        source_type="edgar" if req.cik else "private",
    )
    if resolved_sector:
        _register_sector(req.company_id, resolved_sector)

    # 3. EDGAR ingestion — only when a CIK is provided
    if req.cik:
        cid = req.company_id
        features_dir = PROJECT_ROOT / "data" / "features"
        features_dir.mkdir(parents=True, exist_ok=True)
        config = KPIExtractionConfig(
            company_id=cid,
            company_name=req.company_name,
            ticker=req.ticker or "PRIVATE",
            cik=req.cik.strip(),
            source_type="edgar",
            source_path="",
            base_currency=req.currency,
            raw_feature_matrix_path=str(features_dir / f"{cid}_raw_feature_matrix.csv"),
            model_feature_matrix_path=str(features_dir / f"{cid}_model_feature_matrix.csv"),
            kpi_records_path=str(PROCESSED / f"{cid}_kpi_records.json"),
            evidence_refs_path=str(PROCESSED / f"{cid}_evidence_refs.json"),
            source_quality_report_path=str(PROCESSED / f"{cid}_source_quality_report.json"),
        )
        try:
            agent_result = run_kpi_extraction_agent(config)
            out["edgar_ingested"] = True
            out["kpi_periods"] = agent_result.get("kpi_records_count", 0)
            out["source_quality_status"] = agent_result.get("source_quality_report", {}).get("status")
        except Exception as exc:
            out["errors"].append(f"EDGAR ingestion failed: {exc}")

    return out


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


# ── VCP extraction graph (Phase 3) ────────────────────────────────────────
# True agentic Setup Graph: extract_milestones -> hitl_review (interrupts) ->
# confirm_and_store, checkpointed via Postgres so the review pause survives
# across the extract-upload / confirm HTTP requests instead of relying on two
# stateless calls the way /extract-upload + /extract/{id}/confirm do today.

@router.post("/graph/extract-upload")
async def run_extraction_graph_from_upload(
    file: UploadFile = File(...),
    company_id: Optional[str] = Form(None),
    company_name: Optional[str] = Form(None),
) -> Dict[str, Any]:
    """Start the extraction graph from an uploaded IC memo (PDF/DOCX/MD).

    Runs extract_milestones synchronously, then pauses at hitl_review —
    candidates come back in the response body (from the interrupt payload)
    for the operating partner to edit before calling the /confirm endpoint.
    """
    from app.ingestion.document_loader import _DOCLING_SUFFIXES, _PASSTHROUGH_SUFFIXES, _PDF_SUFFIXES
    from app.graph.extraction_graph import get_vcp_extraction_graph

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

    update_company_meta(
        resolved_id,
        base_dir=str(PROCESSED),
        company_name=resolved_name,
        sector_key=infer_sector_key(resolved_id, resolved_name),
        source_type="ic_memo",
    )

    tmp_path: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(raw)
            tmp_path = Path(tmp.name)

        graph = get_vcp_extraction_graph()
        config = {"configurable": {"thread_id": resolved_id}}
        result = graph.invoke(
            {
                "company_id": resolved_id,
                "company_name": resolved_name,
                "tmp_path": str(tmp_path),
                "source_filename": filename,
            },
            config=config,
        )
    finally:
        if tmp_path:
            tmp_path.unlink(missing_ok=True)

    if result.get("status") == "extraction_empty":
        raise HTTPException(status_code=422, detail="No commitments extracted — document may be image-only.")

    interrupts = result.get("__interrupt__")
    if not interrupts:
        raise HTTPException(status_code=500, detail="Extraction graph did not pause for review as expected.")

    payload = interrupts[0].value
    return {
        "thread_id": resolved_id,
        "company_id": resolved_id,
        "company_name": resolved_name,
        "extraction_mode": result.get("extraction_mode"),
        "model": result.get("model"),
        "source_document": filename,
        "document_loader": result.get("document_loader"),
        "status": "pending_review",
        "milestone_count": len(payload.get("candidate_milestones", [])),
        "needs_review_count": payload.get("needs_review_count", 0),
        "milestones": payload.get("candidate_milestones", []),
    }


@router.post("/graph/{thread_id}/confirm")
def confirm_extraction_graph(thread_id: str, req: ConfirmRequest) -> Dict[str, Any]:
    """Resume a paused extraction graph run with the operating partner's
    reviewed (edited) milestone list, locking it into the VCPStore."""
    from langgraph.types import Command
    from app.graph.extraction_graph import get_vcp_extraction_graph

    graph = get_vcp_extraction_graph()
    config = {"configurable": {"thread_id": thread_id}}

    snapshot = graph.get_state(config)
    if not snapshot or not snapshot.next:
        raise HTTPException(status_code=404, detail=f"No pending extraction review for thread {thread_id}")

    result = graph.invoke(
        Command(resume={
            "milestones": req.milestones,
            "reviewed_by": req.reviewed_by,
            "reviewer_note": req.reviewer_note,
            "company_name": req.company_name,
        }),
        config=config,
    )

    return result.get("confirmation_result", {})


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
    markdown = load_portfolio_memo()
    if markdown is None:
        raise HTTPException(status_code=404, detail="Portfolio memo not generated yet.")
    return {"markdown": markdown}


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
            milestones=confirmed,
        )
        item = build_action_item(cid, name, drift)
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
    save_portfolio_memo(memo_text)

    return {"markdown": memo_text, "generated_at": generated_at, "action_item_count": len(action_items)}
