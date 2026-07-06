from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

from app.graph.report_state import ReportGenerationState

# Progress reported after each node completes — read back via graph.get_state()
# by GET /api/reports/graph/{thread_id}/status (see report_routes.py).
NODE_PROGRESS: Dict[str, Dict[str, Any]] = {
    "load_milestones_and_kpis": {"step": "fetching_kpis", "label": "Fetching KPI data", "pct": 10},
    "compute_drift":            {"step": "running_forecast", "label": "Running VCP drift", "pct": 25},
    "alert_synthesis":          {"step": "synthesizing_alert", "label": "Synthesizing alert", "pct": 40},
    "peer_benchmark":           {"step": "benchmarking", "label": "Pulling sector benchmarks", "pct": 55},
    "narrative_synthesis":      {"step": "generating_narrative", "label": "Writing executive summary...", "pct": 75},
    "build_slides":             {"step": "rendering_charts", "label": "Rendering charts", "pct": 88},
    "render_pdf":               {"step": "assembling_pptx", "label": "Assembling deck", "pct": 96},
    "persist_report":           {"step": "complete", "label": "Report ready", "pct": 100},
}


def _mark(state: ReportGenerationState, node_name: str) -> None:
    progress = NODE_PROGRESS[node_name]
    state["progress_step"] = progress["step"]
    state["progress_pct"] = progress["pct"]
    state["status"] = "complete" if node_name == "persist_report" else "running"


PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROCESSED = PROJECT_ROOT / "data" / "processed"


def load_milestones_and_kpis_node(state: ReportGenerationState) -> ReportGenerationState:
    from app.store.vcp_store import VCPStore
    from app.workflows.vcp_confirmation import DEFAULT_STORE_PATH

    company_id = state["company_id"]

    vcp_store = VCPStore(DEFAULT_STORE_PATH)
    confirmed_milestones = (
        vcp_store.load_confirmed_for_company(company_id) if vcp_store.exists() else []
    )
    if not confirmed_milestones:
        raise ValueError(
            f"No confirmed VCP milestones for {company_id}. Complete Setup first."
        )
    milestones = [m.to_dict() for m in confirmed_milestones]
    company_name = confirmed_milestones[0].company_name or company_id

    from app.store.kpi_records_store import load_kpi_records

    kpi_path = PROCESSED / f"{company_id}_kpi_records.json"
    kpi_records_raw = load_kpi_records(str(kpi_path))
    if not kpi_records_raw:
        raise ValueError(f"No KPI records for {company_id}")

    kpi_series = []
    for r in kpi_records_raw:
        rev = r.get("revenue")
        ebitda = r.get("adjusted_ebitda") or r.get("ebitda_proxy")
        nd = r.get("net_debt")
        margin = (ebitda / rev) if (rev and ebitda is not None) else None
        lever = (nd / (ebitda * 12)) if (ebitda and nd is not None) else None
        kpi_series.append({
            "period_end": r.get("period_end"),
            "revenue": rev,
            "ebitda": ebitda,
            "ebitda_margin": margin,
            "net_debt": nd,
            "net_debt_to_ebitda": lever,
            "cash": r.get("cash"),
        })

    period = state.get("period") or ""
    if not period:
        latest_end = max((r.get("period_end", "") for r in kpi_records_raw), default="")
        period = latest_end[:7] if latest_end else "Latest"

    sector = kpi_records_raw[0].get("source_type", "") if kpi_records_raw else ""

    state["company_name"] = company_name
    state["milestones"] = milestones
    state["kpi_records_raw"] = kpi_records_raw
    state["kpi_series"] = kpi_series
    state["period"] = period
    state["sector"] = sector

    _mark(state, "load_milestones_and_kpis")
    return state


def compute_drift_node(state: ReportGenerationState) -> ReportGenerationState:
    from app.analytics.vcp_drift import run_vcp_drift_for_kpi_records
    from app.workflows.vcp_confirmation import DEFAULT_STORE_PATH

    company_id = state["company_id"]
    kpi_path = PROCESSED / f"{company_id}_kpi_records.json"

    drift = run_vcp_drift_for_kpi_records(
        company_id=company_id,
        kpi_records_path=str(kpi_path),
        vcp_store_path=DEFAULT_STORE_PATH,
    )
    state["drift_results"] = drift.get("results", [])

    _mark(state, "compute_drift")
    return state


def alert_synthesis_node(state: ReportGenerationState) -> ReportGenerationState:
    from app.agents import alert_synthesis_agent
    from app.api.report_routes import _hitl_decision_for_company

    company_id = state["company_id"]
    kpi_records_raw = state["kpi_records_raw"]
    latest_kpi = max(kpi_records_raw, key=lambda r: r.get("period_end", ""), default={})

    alert_card = alert_synthesis_agent.synthesize(
        company_id=company_id,
        company_name=state["company_name"],
        drift_scores=state["drift_results"],
        kpi_snapshot=latest_kpi,
    )

    # HITL gate: honor the operating-partner decision before the alert reaches
    # the board pack — same override the synchronous /generate endpoint applies.
    hitl_item = _hitl_decision_for_company(company_id)
    if hitl_item and hitl_item.get("status") == "approved_with_edit":
        edited = (hitl_item.get("decision") or {}).get("edited_recommended_action")
        if edited:
            alert_card.recommended_action = edited

    state["alert_card"] = alert_card.model_dump()

    _mark(state, "alert_synthesis")
    return state


def peer_benchmark_node(state: ReportGenerationState) -> ReportGenerationState:
    from app.analytics.peer_benchmarking import run_peer_benchmark_for_company
    from app.store.deal_store import DealStore

    company_id = state["company_id"]
    kpi_path = PROCESSED / f"{company_id}_kpi_records.json"

    peer_benchmark = None
    try:
        deal = DealStore().load(company_id)
        sector_key = deal.sector_key if deal else None
        peer_benchmark = run_peer_benchmark_for_company(
            company_id=company_id,
            kpi_records_path=str(kpi_path),
            sector_key=sector_key,
        )
    except Exception:
        peer_benchmark = None

    state["peer_benchmark"] = peer_benchmark

    _mark(state, "peer_benchmark")
    return state


def narrative_synthesis_node(state: ReportGenerationState) -> ReportGenerationState:
    from app.agents import report_narrative_agent

    alert_card = state["alert_card"]

    narrative = report_narrative_agent.generate(
        company_name=state["company_name"],
        period=state["period"],
        alert_severity=alert_card["severity"],
        alert_headline=alert_card["headline"],
        alert_root_cause=alert_card["root_cause"],
        alert_recommended_action=alert_card["recommended_action"],
        lever_category=alert_card["lever_category"],
        drift_results=state["drift_results"],
        milestones=state["milestones"],
        peer_benchmark=state.get("peer_benchmark"),
        irr_at_risk_bps=alert_card.get("irr_at_risk_bps"),
        tone=state.get("tone", "board_ready"),
    )
    board_questions = report_narrative_agent.generate_board_questions(
        company_name=state["company_name"],
        period=state["period"],
        drift_results=state["drift_results"],
    )
    risks_output = report_narrative_agent.generate_risks(
        company_name=state["company_name"],
        period=state["period"],
        drift_results=state["drift_results"],
        alert_recommended_action=alert_card["recommended_action"],
        irr_at_risk_bps=alert_card.get("irr_at_risk_bps"),
    )

    state["narrative"] = narrative.model_dump()
    state["board_questions"] = board_questions
    state["risks_output"] = risks_output.model_dump()

    _mark(state, "narrative_synthesis")
    return state


def build_slides_node(state: ReportGenerationState) -> ReportGenerationState:
    from app.agents.alert_synthesis_agent import AlertCard
    from app.api.report_routes import (
        _build_citations,
        _build_kpi_performance,
        _build_risks_actions,
        _load_hitl_decisions,
    )
    from app.quant.vcp_irr import build_vcp_irr
    from app.reports import slide_data_builder

    company_id = state["company_id"]
    kpi_records_raw = state["kpi_records_raw"]
    drift_results = state["drift_results"]
    peer_benchmark = state.get("peer_benchmark")

    kpi_performance = _build_kpi_performance(drift_results, state["kpi_series"])

    alert_card_obj = AlertCard.model_validate(state["alert_card"])
    risks_actions = _build_risks_actions(alert_card_obj, drift_results)

    citations = _build_citations(company_id, peer_benchmark, kpi_records=kpi_records_raw)
    hitl_decisions = _load_hitl_decisions()

    irr_data = None
    try:
        irr_data = build_vcp_irr(company_id, kpi_records_raw)
    except Exception:
        irr_data = None
    irr_scenarios = irr_data["scenario_detail"] if irr_data else None

    generated_at = datetime.now(timezone.utc).isoformat()

    slides = slide_data_builder.build_slides(
        company_id=company_id,
        company_name=state["company_name"],
        period=state["period"],
        sector=state["sector"],
        milestones=state["milestones"],
        drift_results=drift_results,
        kpi_series=state["kpi_series"],
        alert_card=state["alert_card"],
        narrative=state["narrative"],
        peer_benchmark=peer_benchmark,
        irr_data=irr_data,
        board_questions=state["board_questions"],
        risks_output=state["risks_output"],
        citations=citations,
        hitl_decisions=hitl_decisions,
        generated_at=generated_at,
    )

    state["kpi_performance"] = kpi_performance
    state["risks_actions"] = risks_actions
    state["citations"] = citations
    state["hitl_decisions"] = hitl_decisions
    state["irr_data"] = irr_data
    state["irr_scenarios"] = irr_scenarios
    state["slides"] = slides
    state["generated_at"] = generated_at

    _mark(state, "build_slides")
    return state


def render_pdf_node(state: ReportGenerationState) -> ReportGenerationState:
    from app.reports.board_pack_generator import generate_board_pack
    from app.reports.vcp_status_generator import generate_vcp_status_pdf

    narrative = state["narrative"]
    alert_card = state["alert_card"]
    pdf_bytes = None

    try:
        if state["report_type"] == "vcp_status_update":
            pdf_bytes = generate_vcp_status_pdf(
                company_name=state["company_name"],
                period=state["period"],
                milestones=state["milestones"],
                drift_results=state["drift_results"],
                priority_action=narrative["priority_action"],
                confidence_statement=narrative["confidence_statement"],
            )
        else:
            pdf_bytes = generate_board_pack(
                company_name=state["company_name"],
                company_id=state["company_id"],
                period=state["period"],
                sector=state["sector"],
                alert_severity=alert_card["severity"],
                alert_headline=alert_card["headline"],
                alert_root_cause=alert_card["root_cause"],
                alert_recommended_action=alert_card["recommended_action"],
                lever_category=alert_card["lever_category"],
                irr_at_risk_bps=alert_card.get("irr_at_risk_bps"),
                exec_summary=narrative["exec_summary"],
                key_risks=narrative["key_risks"],
                priority_action=narrative["priority_action"],
                board_talking_points=narrative["board_talking_points"],
                confidence_statement=narrative["confidence_statement"],
                narrative_mode=narrative["narrative_mode"],
                synthesis_mode="azure_openai" if alert_card["severity"] else "offline_rule_based",
                milestones=state["milestones"],
                drift_results=state["drift_results"],
                kpi_performance=state["kpi_performance"],
                risks_actions=state["risks_actions"],
                irr_scenarios=state.get("irr_scenarios"),
                peer_benchmark=state.get("peer_benchmark"),
                kpi_records=state["kpi_records_raw"],
                citations=state["citations"],
                hitl_decisions=state["hitl_decisions"],
            )
    except Exception as exc:
        print(f"[ReportGraph] PDF generation failed: {exc}")
        pdf_bytes = None

    state["pdf_bytes_b64"] = base64.b64encode(pdf_bytes).decode() if pdf_bytes else None

    _mark(state, "render_pdf")
    return state


def persist_report_node(state: ReportGenerationState) -> ReportGenerationState:
    from app.store.report_store import ReportRecord, ReportStore

    narrative = state["narrative"]
    alert_card = state["alert_card"]

    record = ReportRecord(
        id=state["report_id"],
        company_id=state["company_id"],
        company_name=state["company_name"],
        report_type=state["report_type"],
        period=state["period"],
        sector=state["sector"],
        tone=state.get("tone", "board_ready"),
        status="pending_review",
        generation_mode=state.get("generation_mode", "manual"),
        narrative_mode=narrative["narrative_mode"],
        alert_severity=alert_card["severity"],
        alert_headline=alert_card["headline"],
        alert_root_cause=alert_card["root_cause"],
        alert_recommended_action=alert_card["recommended_action"],
        lever_category=alert_card["lever_category"],
        irr_at_risk_bps=alert_card.get("irr_at_risk_bps"),
        exec_summary=narrative["exec_summary"],
        key_risks=narrative["key_risks"],
        priority_action=narrative["priority_action"],
        board_talking_points=narrative["board_talking_points"],
        confidence_statement=narrative["confidence_statement"],
        board_questions=state["board_questions"],
        risks_output=state["risks_output"],
        slides=state["slides"],
        progress_step="complete",
        progress_pct=100,
        generated_at=state["generated_at"],
        drift_results=state["drift_results"],
        milestones=state["milestones"],
        kpi_records=state["kpi_records_raw"],
        kpi_performance=state["kpi_performance"],
        risks_actions=state["risks_actions"],
        irr_scenarios=state.get("irr_scenarios"),
        peer_benchmark=state.get("peer_benchmark"),
        citations=state["citations"],
        hitl_decisions=state["hitl_decisions"],
    )

    store = ReportStore()
    if state.get("pdf_bytes_b64"):
        store.save_pdf(record.id, base64.b64decode(state["pdf_bytes_b64"]))
    store.save(record)

    _mark(state, "persist_report")
    return state
