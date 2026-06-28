from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


def clean_value(value: Any) -> Any:
    """Convert pandas/numpy missing values into JSON-safe values."""
    try:
        import numpy as np
        import pandas as pd

        if value is None:
            return None
        if pd.isna(value):
            return None
        if isinstance(value, (np.integer,)):
            return int(value)
        if isinstance(value, (np.floating,)):
            return float(value)
    except Exception:
        pass

    return value


@dataclass
class EvidenceRef:
    metric: str
    value: Any
    source_type: str
    source_document: str
    source_path: str
    period_end: Optional[str] = None
    source_page_or_sheet: Optional[str] = None
    source_section: Optional[str] = None
    confidence: float = 0.9
    extraction_method: str = "structured_pipeline"

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        return {k: clean_value(v) for k, v in data.items()}


@dataclass
class KPIRecord:
    company_id: str
    company_name: str
    ticker: str
    cik: str
    source_type: str
    source_path: str
    period_end: str
    period_type: str = "quarter"
    currency: str = "USD"

    revenue: Optional[float] = None
    gross_profit: Optional[float] = None
    operating_income: Optional[float] = None
    reported_ebitda: Optional[float] = None
    adjusted_ebitda: Optional[float] = None
    ebitda_proxy: Optional[float] = None
    net_income: Optional[float] = None
    capex: Optional[float] = None
    working_capital: Optional[float] = None
    cash: Optional[float] = None
    debt: Optional[float] = None
    net_debt: Optional[float] = None
    interest_expense: Optional[float] = None
    free_cash_flow: Optional[float] = None

    source_confidence: float = 0.9
    evidence_refs: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        data = asdict(self)
        return {k: clean_value(v) for k, v in data.items()}


@dataclass
class SourceQualityReport:
    source_type: str
    source_path: str
    record_count: int
    required_fields_present: bool
    missing_required_fields: List[str]
    null_counts: Dict[str, int]
    status: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class KPIExtractionConfig:
    company_id: str = "demo_aapl_proxy_001"
    company_name: str = "DemoCo / Apple proxy"
    ticker: str = "AAPL"
    cik: str = "0000320193"
    source_type: str = "edgar"
    source_path: str = ""

    # Single reporting currency the whole pipeline runs in. Adapters normalize every
    # source's monetary figures (and unit scale) to this before records are built.
    base_currency: str = "USD"

    raw_feature_matrix_path: str = "data/features/demo_feature_matrix.csv"
    model_feature_matrix_path: str = "data/features/demo_model_feature_matrix.csv"

    kpi_records_path: str = "data/processed/kpi_records.json"
    evidence_refs_path: str = "data/processed/evidence_refs.json"
    source_quality_report_path: str = "data/processed/source_quality_report.json"

    include_macro: bool = False
