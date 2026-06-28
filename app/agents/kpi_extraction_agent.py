from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from app.adapters.registry import get_kpi_adapter
from app.schemas.kpi_schema import KPIExtractionConfig


def _write_json(path: str, payload: Any) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, default=str)


def run_kpi_extraction_agent(config: KPIExtractionConfig) -> Dict[str, Any]:
    """
    Source-agnostic KPI Extraction Agent.

    The agent itself does not know source-specific parsing details. It delegates
    extraction to the adapter registry, saves standardized artifacts, and returns
    a concise summary to LangGraph state.
    """

    adapter = get_kpi_adapter(config.source_type)
    result = adapter.extract(config)

    _write_json(config.kpi_records_path, result["kpi_records"])
    _write_json(config.evidence_refs_path, result["evidence_refs"])
    _write_json(
        config.source_quality_report_path,
        result["source_quality_report"],
    )

    return {
        "raw_rows": result["raw_rows"],
        "model_rows": result["model_rows"],
        "kpi_records_path": config.kpi_records_path,
        "kpi_records_count": len(result["kpi_records"]),
        "evidence_refs_path": config.evidence_refs_path,
        "evidence_refs_count": len(result["evidence_refs"]),
        "source_quality_report_path": config.source_quality_report_path,
        "source_quality_report": result["source_quality_report"],
    }