from __future__ import annotations

from typing import Any, Dict, List, TypedDict


class PortfolioMonitorState(TypedDict, total=False):
    """
    Shared graph state for PE Value Creation Copilot.

    Flow:
    source-aware KPI extraction -> Quant forecast -> IRR/MOIC scenarios
    -> thesis/peer/agreement-risk/alerts -> HITL/memo.
    """

    # Identity / config
    company_name: str
    ticker: str
    cik: str
    valuation_mode: str
    company_id: str

    # Deal / thesis context
    deal_metadata_path: str
    deal_metadata: Dict[str, Any]
    thesis_milestones: List[Dict[str, Any]]

    # Source registry / source-aware KPI extraction
    source_type: str
    source_registry: List[Dict[str, Any]]
    kpi_records_path: str
    kpi_records_count: int
    evidence_refs_path: str
    evidence_refs_count: int
    source_quality_report_path: str
    source_quality_report: Dict[str, Any]

    # Data outputs used by downstream Quant Agent
    raw_feature_matrix_path: str
    model_feature_matrix_path: str
    stl_components_path: str
    forecast_path: str
    irr_scenarios_path: str

    # Runtime summaries
    raw_rows: int
    model_rows: int
    forecast_rows: int
    irr_rows: int

    # IRR / scenario outputs
    irr_scenarios: List[Dict[str, Any]]

    # Future Week 2/3 agent outputs
    peer_composite: Dict[str, Any]
    covenant_results: Dict[str, Any]
    alerts: List[Dict[str, Any]]
    evidence_refs: List[Dict[str, Any]]
    hitl_status: str

    # Errors / diagnostics
    status: str
    errors: List[str]
