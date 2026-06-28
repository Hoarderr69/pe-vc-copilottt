from __future__ import annotations

from typing import Any, Dict

from app.adapters.base import BaseKPIAdapter
from app.schemas.kpi_schema import KPIExtractionConfig


class PlaceholderKPIAdapter(BaseKPIAdapter):
    """
    Placeholder adapter for future source types.

    Use this for QPR PDFs, board packs, Excel models, and MCP until their real
    extraction logic is implemented.
    """

    def __init__(self, source_type: str):
        self.source_type = source_type

    def extract(self, config: KPIExtractionConfig) -> Dict[str, Any]:
        return {
            "raw_rows": 0,
            "model_rows": 0,
            "kpi_records": [],
            "evidence_refs": [],
            "source_quality_report": {
                "source_type": self.source_type,
                "source_path": "",
                "record_count": 0,
                "required_fields_present": False,
                "missing_required_fields": [],
                "null_counts": {},
                "status": "not_implemented",
            },
        }