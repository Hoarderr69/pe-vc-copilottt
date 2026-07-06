from __future__ import annotations

from typing import Any, Dict, List, Optional, TypedDict


class VCPExtractionState(TypedDict, total=False):
    """State for the setup/extraction graph — the IC-memo extraction + confirm
    flow from the original brief's "Setup Graph". Distinct from the superseded
    demo pipeline in app/graph/nodes.py (see Phase 3 note in the migration plan).
    """

    # Invoke-time input (set by POST /api/vcp/graph/extract-upload)
    company_id: str
    company_name: str
    tmp_path: str
    source_filename: str

    # extract_milestones
    extraction_mode: str
    model: Optional[str]
    document_loader: Optional[str]
    candidate_milestones: List[Dict[str, Any]]
    needs_review_count: int

    # hitl_review (populated on resume via POST /api/vcp/graph/{thread_id}/confirm)
    edited_milestones: List[Dict[str, Any]]
    reviewed_by: str
    reviewer_note: Optional[str]

    # confirm_and_store
    confirmation_result: Dict[str, Any]

    status: str
    errors: List[str]
