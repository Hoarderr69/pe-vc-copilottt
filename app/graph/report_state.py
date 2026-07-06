from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict


class ReportGenerationState(TypedDict, total=False):
    """State for the report-generation graph — mirrors the body of
    generate_report() in app/api/report_routes.py, re-sequenced into nodes so
    each stage checkpoints (Postgres) instead of running inline in one request.
    """

    # Invoke-time input (set by POST /api/reports/graph/generate)
    report_id: str
    company_id: str
    report_type: str
    period: str
    tone: str
    generation_mode: str

    # load_milestones_and_kpis
    company_name: str
    milestones: List[Dict[str, Any]]
    kpi_records_raw: List[Dict[str, Any]]
    kpi_series: List[Dict[str, Any]]
    sector: str

    # compute_drift
    drift_results: List[Dict[str, Any]]

    # alert_synthesis
    alert_card: Dict[str, Any]  # AlertCard.model_dump()

    # peer_benchmark
    peer_benchmark: Optional[Dict[str, Any]]

    # narrative_synthesis
    narrative: Dict[str, Any]  # NarrativeOutput.model_dump()
    board_questions: List[str]
    risks_output: Dict[str, Any]  # RisksOutput.model_dump()

    # build_slides
    irr_data: Optional[Dict[str, Any]]
    irr_scenarios: Optional[List[Dict[str, Any]]]
    kpi_performance: List[Dict[str, Any]]
    risks_actions: List[Dict[str, Any]]
    citations: List[str]
    hitl_decisions: List[Dict[str, Any]]
    slides: List[Dict[str, Any]]
    generated_at: str

    # render_pdf
    pdf_bytes_b64: Optional[str]

    # progress / status, updated by every node (read via graph.get_state())
    progress_step: str
    progress_pct: int
    status: str
    errors: List[str]
