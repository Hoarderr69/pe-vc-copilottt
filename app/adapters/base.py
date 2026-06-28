from __future__ import annotations

from typing import Any, Dict

from app.schemas.kpi_schema import KPIExtractionConfig


class BaseKPIAdapter:
    """
    Base interface for source adapters.

    Every adapter must normalize its source into:
    - KPI records
    - evidence references
    - source quality report
    """

    source_type: str = "base"

    def extract(self, config: KPIExtractionConfig) -> Dict[str, Any]:
        raise NotImplementedError("Adapters must implement extract().")