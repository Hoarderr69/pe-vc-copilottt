from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, TypedDict

from langgraph.types import interrupt

from app.analytics.action_items import build_action_item
from app.analytics.vcp_drift import run_vcp_drift_for_kpi_records
from app.store.vcp_store import VCPStore
from app.workflows.hitl_queue import refresh_hitl_review_queue_from_action_items
from app.workflows.vcp_confirmation import DEFAULT_STORE_PATH, kpi_records_path


class VCPMonitoringState(TypedDict, total=False):
    """
    State for the VCP monitoring graph.

    This graph focuses only on:
    - VCP confirmation
    - VCP drift computation
    - Alert & Synthesis Agent output
    """

    company_id: str
    company_scope: str
    vcp_store_path: str
    kpi_records_path: str
    vcp_drift_scores_path: str

    vcp_confirmed: bool
    vcp_milestones_count: int
    vcp_company_count: int
    vcp_store_summary: Dict[str, Any]

    vcp_drift_result_count: int
    vcp_drift_status_counts: Dict[str, int]
    vcp_drift_scores: List[Dict[str, Any]]

    # Alert & Synthesis Agent outputs
    alert_card: Dict[str, Any]           # AlertCard.model_dump()
    alert_severity: str                  # "Red" | "Amber" | "Green"
    alert_synthesis_mode: str            # "azure_openai" | "offline_rule_based"

    # Optional context forwarded to the synthesis agent
    kpi_snapshot: Dict[str, Any]
    irr_scenarios: List[Dict[str, Any]]
    peer_composite: Dict[str, Any]

    alerts: List[Dict[str, Any]]
    hitl_status: str
    hitl_decision: Dict[str, Any]
    status: str
    errors: List[str]


def initialize_vcp_monitoring_state_node(
    state: VCPMonitoringState,
) -> VCPMonitoringState:
    """
    Initialize defaults for the VCP monitoring graph.

    Clean path:
    VCPStore + normalized KPI records -> VCP drift -> alerts.

    company_id is a required invoke-time input (no portfolio-wide default) —
    every path/store lookup below is derived from it via the same helpers the
    live routes use, so the graph and the HTTP API never disagree on where a
    company's data lives.
    """

    company_id = state.get("company_id")
    if not company_id:
        raise ValueError(
            "company_id is required to run the VCP monitoring graph."
        )

    state.setdefault("company_scope", company_id)
    state.setdefault("vcp_store_path", DEFAULT_STORE_PATH)
    state.setdefault("kpi_records_path", kpi_records_path(company_id))

    state.setdefault("alerts", [])
    state.setdefault("errors", [])
    state["status"] = "initialized"

    return state

def vcp_confirmation_check_node(
    state: VCPMonitoringState,
) -> VCPMonitoringState:
    """
    Check whether confirmed VCP milestones exist.

    For the synthetic prototype, all seed milestones are treated as confirmed.
    Later, this node will enforce HITL confirmation before monitoring runs.
    """

    store = VCPStore(state["vcp_store_path"])
    summary = store.summary()

    state["vcp_store_summary"] = summary
    state["vcp_milestones_count"] = summary.get("total_milestones", 0)
    state["vcp_company_count"] = summary.get("company_count", 0)

    if not store.exists():
        state["vcp_confirmed"] = False
        state["status"] = "vcp_store_missing"
        state.setdefault("errors", []).append(
            f"VCP store not found: {state['vcp_store_path']}"
        )
        return state

    milestones = store.load_all()

    if not milestones:
        state["vcp_confirmed"] = False
        state["status"] = "vcp_empty"
        state.setdefault("errors", []).append("No VCP milestones found.")
        return state

    company_id = state.get("company_id") or state.get("company_scope")

    if company_id and company_id != "ALL":
        state["vcp_confirmed"] = store.is_confirmed(company_id)
    else:
        state["vcp_confirmed"] = all(m.confirmed for m in milestones)

    state["status"] = (
        "vcp_confirmed" if state["vcp_confirmed"] else "vcp_not_confirmed"
    )

    return state


def route_after_vcp_confirmation(
    state: VCPMonitoringState,
) -> Literal["continue", "stop"]:
    """
    Conditional router.

    If VCP is not confirmed, stop the graph.
    If confirmed, continue to drift computation.
    """

    return "continue" if state.get("vcp_confirmed") else "stop"


# def vcp_drift_node(state: VCPMonitoringState) -> VCPMonitoringState:
#     """
#     Run deterministic VCP drift computation.

#     This compares latest synthetic financials against confirmed VCP milestones.
#     """

#     payload = run_vcp_drift_for_manifest(
#         manifest_path=state["source_manifest_path"],
#         vcp_store_path=state["vcp_store_path"],
#         output_path=state["vcp_drift_scores_path"],
#     )

#     state["vcp_drift_result_count"] = payload["result_count"]
#     state["vcp_drift_status_counts"] = payload["status_counts"]
#     state["vcp_drift_scores"] = payload["results"]
#     state["status"] = "vcp_drift_ready"

#     return state


def vcp_drift_from_kpi_records_node(
    state: VCPMonitoringState,
) -> VCPMonitoringState:
    """
    Run deterministic VCP drift using normalized KPIRecord JSON.

    Preferred path:
    raw source -> adapter -> KPI records -> VCP drift.
    """

    company_id = state.get("company_id") or state.get("company_scope")

    if not company_id or company_id == "ALL":
        state["status"] = "vcp_drift_kpi_records_missing_company"
        state.setdefault("errors", []).append(
            "company_id is required for KPI-record-based VCP drift."
        )
        return state

    kpi_records_path = state.get("kpi_records_path")

    if not kpi_records_path:
        state["status"] = "vcp_drift_kpi_records_missing_path"
        state.setdefault("errors", []).append(
            "kpi_records_path is required for KPI-record-based VCP drift."
        )
        return state

    payload = run_vcp_drift_for_kpi_records(
        company_id=company_id,
        kpi_records_path=kpi_records_path,
        vcp_store_path=state["vcp_store_path"],
        output_path=state.get("vcp_drift_scores_path"),
    )

    state["vcp_drift_result_count"] = payload["result_count"]
    state["vcp_drift_status_counts"] = payload["status_counts"]
    state["vcp_drift_scores"] = payload["results"]
    state["status"] = "vcp_drift_from_kpi_records_ready"

    return state

def alert_synthesis_node(state: VCPMonitoringState) -> VCPMonitoringState:
    """
    Alert & Synthesis Agent — second true AI agent in the monitoring pipeline.

    Calls GPT-4o (or the offline fallback) to synthesize VCP drift scores into a
    structured alert card with severity, root cause, recommended lever, and citations.
    """
    from app.agents import alert_synthesis_agent

    company_id = state.get("company_id") or state.get("company_scope", "unknown")
    company_name = (
        state.get("vcp_store_summary", {}).get("companies", [company_id])[0]
        if state.get("vcp_store_summary")
        else company_id
    )

    drift_scores: List[Dict[str, Any]] = state.get("vcp_drift_scores", [])

    if not drift_scores:
        state["alert_card"] = {
            "severity": "Green",
            "headline": "No VCP drift scores available — monitoring did not run.",
            "milestones_at_risk": [],
            "root_cause": "No data.",
            "recommended_action": "Ensure KPI records are ingested correctly.",
            "lever_category": "other",
            "citations": [],
            "synthesis_mode": "no_data",
        }
        state["alert_severity"] = "Green"
        state["alert_synthesis_mode"] = "no_data"
        state["alerts"] = []
        state["hitl_status"] = "no_review_required"
        state["status"] = "alert_synthesis_skipped_no_data"
        return state

    card = alert_synthesis_agent.synthesize(
        company_id=company_id,
        company_name=company_name,
        drift_scores=drift_scores,
        kpi_snapshot=state.get("kpi_snapshot"),
        irr_scenarios=state.get("irr_scenarios"),
        peer_composite=state.get("peer_composite"),
    )

    card_dict = card.model_dump()
    state["alert_card"] = card_dict
    state["alert_severity"] = card.severity
    state["alert_synthesis_mode"] = card.synthesis_mode

    # Keep the alerts list populated for backward-compatibility with other consumers
    state["alerts"] = [card_dict]

    state["status"] = "alert_synthesis_ready"
    return state


def route_after_alert_synthesis(
    state: VCPMonitoringState,
) -> Literal["red_hitl", "amber_hitl", "green_skip"]:
    """
    Severity router — determines HITL urgency from the synthesized alert card.

    Red   → immediate HITL push (blocking review)
    Amber → batch end-of-day HITL digest
    Green → dashboard update only, no HITL
    """
    severity = state.get("alert_severity", "Green")
    if severity == "Red":
        return "red_hitl"
    if severity == "Amber":
        return "amber_hitl"
    return "green_skip"


def _sync_hitl_review_queue(state: VCPMonitoringState) -> None:
    """Push this run's alert into the same review queue the live app reads
    (data/processed/hitl_review_queue.json), via the identical build_action_item
    -> refresh_hitl_review_queue_from_action_items path the portfolio roll-up
    uses — so a paused graph run shows up in GET /api/vcp/hitl exactly like a
    synchronous /api/vcp/portfolio alert does today.
    """
    company_id = state.get("company_id") or state.get("company_scope")
    store = VCPStore(state["vcp_store_path"])
    confirmed = store.load_confirmed_for_company(company_id) if store.exists() else []
    company_name = confirmed[0].company_name if confirmed else company_id

    drift = {"results": state.get("vcp_drift_scores", [])}
    action_item = build_action_item(company_id, company_name, drift)
    if action_item:
        refresh_hitl_review_queue_from_action_items([action_item])


def hitl_immediate_node(state: VCPMonitoringState) -> VCPMonitoringState:
    """Red path: pause for immediate operating partner review.

    Blocks here via interrupt() until POST /api/vcp/hitl/decision resumes this
    thread with the reviewer's decision (see app/api/vcp_routes.py).
    """
    _sync_hitl_review_queue(state)
    state["hitl_status"] = "immediate_review_required"

    decision = interrupt({
        "alert_card": state.get("alert_card"),
        "severity": state.get("alert_severity"),
        "company_id": state.get("company_id"),
    })

    state["hitl_decision"] = decision
    state["status"] = "hitl_immediate_resolved"
    return state


def hitl_digest_node(state: VCPMonitoringState) -> VCPMonitoringState:
    """Amber path: pause for the end-of-day HITL digest review.

    Same interrupt/resume mechanics as hitl_immediate_node — only the queue
    framing (severity) differs; the review UI treats both as pending items.
    """
    _sync_hitl_review_queue(state)
    state["hitl_status"] = "digest_review_required"

    decision = interrupt({
        "alert_card": state.get("alert_card"),
        "severity": state.get("alert_severity"),
        "company_id": state.get("company_id"),
    })

    state["hitl_decision"] = decision
    state["status"] = "hitl_digest_resolved"
    return state


def hitl_skip_node(state: VCPMonitoringState) -> VCPMonitoringState:
    """Green path: dashboard update only, no human review needed."""
    state["hitl_status"] = "no_review_required"
    state["status"] = "dashboard_update_only"
    return state