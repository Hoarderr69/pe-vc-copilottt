from __future__ import annotations

from typing import Literal

from langgraph.types import interrupt

from app.graph.extraction_state import VCPExtractionState


def extract_milestones_node(state: VCPExtractionState) -> VCPExtractionState:
    """VCP Extraction Agent node — wraps vcp_extraction_agent.extract_from_document
    over the IC memo saved at tmp_path by POST /api/vcp/graph/extract-upload."""
    from app.agents.vcp_extraction_agent import extract_from_document, to_vcp_milestones

    company_id = state["company_id"]
    company_name = state["company_name"]

    result = extract_from_document(state["tmp_path"], company_id, company_name)
    result.source_document = state.get("source_filename") or result.source_document
    milestones = to_vcp_milestones(result)

    state["extraction_mode"] = result.extraction_mode
    state["model"] = result.model
    state["document_loader"] = result.document_loader

    if not milestones:
        state.setdefault("errors", []).append(
            "No commitments extracted — document may be image-only."
        )
        state["candidate_milestones"] = []
        state["needs_review_count"] = 0
        state["status"] = "extraction_empty"
        return state

    state["candidate_milestones"] = [m.to_dict() for m in milestones]
    state["needs_review_count"] = sum(1 for m in milestones if m.confidence < 0.7)
    state["status"] = "extracted"
    return state


def route_after_extraction(state: VCPExtractionState) -> Literal["review", "stop"]:
    """Conditional router — skip straight to END if extraction yielded nothing,
    matching the 422 the synchronous /extract-upload endpoint returns today."""
    return "stop" if not state.get("candidate_milestones") else "review"


def hitl_review_node(state: VCPExtractionState) -> VCPExtractionState:
    """Pause for operating-partner review/edit of the extraction candidates.

    Blocks here via interrupt() until POST /api/vcp/graph/{thread_id}/confirm
    resumes this thread with the reviewed milestone list (see vcp_routes.py).
    """
    decision = interrupt({
        "company_id": state.get("company_id"),
        "company_name": state.get("company_name"),
        "candidate_milestones": state.get("candidate_milestones", []),
        "needs_review_count": state.get("needs_review_count", 0),
    })

    state["edited_milestones"] = decision["milestones"]
    state["reviewed_by"] = decision["reviewed_by"]
    state["reviewer_note"] = decision.get("reviewer_note")
    if decision.get("company_name"):
        state["company_name"] = decision["company_name"]
    state["status"] = "reviewed"
    return state


def confirm_and_store_node(state: VCPExtractionState) -> VCPExtractionState:
    """Lock the human-reviewed milestones into the VCPStore — wraps the same
    confirm_vcp_milestones() the synchronous /extract/{id}/confirm endpoint uses."""
    from app.workflows.vcp_confirmation import confirm_vcp_milestones

    result = confirm_vcp_milestones(
        company_id=state["company_id"],
        company_name=state["company_name"],
        milestones=state["edited_milestones"],
        reviewed_by=state["reviewed_by"],
        reviewer_note=state.get("reviewer_note"),
    )
    state["confirmation_result"] = result
    state["status"] = "confirmed"
    return state
