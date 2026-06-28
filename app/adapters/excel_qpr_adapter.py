from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

from app.adapters.base import BaseKPIAdapter
from app.schemas.kpi_schema import (
    EvidenceRef,
    KPIExtractionConfig,
    KPIRecord,
    SourceQualityReport,
    clean_value,
)


class ExcelQPRAdapter(BaseKPIAdapter):
    """
    Excel/QPR adapter.

    Reads a controlled Excel QPR file and maps it into KPIRecord + EvidenceRef.

    Current assumption:
    - File: data/raw/qpr/demo_qpr.xlsx
    - Sheet: Financials
    - Columns: period_end, revenue, operating_income, net_income,
      ebitda_proxy, working_capital, net_debt

    Later this can be expanded into workbook profiling + sheet classification.
    """

    source_type = "excel"

    required_columns = [
        "period_end",
        "revenue",
        "ebitda_proxy",
        "net_debt",
    ]

    metric_map = {
        "revenue": "revenue",
        "operating_income": "operating_income",
        "net_income": "net_income",
        "ebitda_proxy": "ebitda_proxy",
        "working_capital": "working_capital",
        "net_debt": "net_debt",
    }

    def extract(self, config: KPIExtractionConfig) -> Dict[str, Any]:
        source_path = "data/raw/qpr/demo_qpr.xlsx"
        sheet_name = "Financials"

        if not Path(source_path).exists():
            raise FileNotFoundError(
                f"Excel QPR file not found: {source_path}. "
                "Create data/raw/qpr/demo_qpr.xlsx first."
            )

        df = pd.read_excel(
            source_path,
            sheet_name=sheet_name,
            engine="openpyxl",
        )

        if "period_end" not in df.columns:
            raise ValueError("Excel QPR must contain a 'period_end' column.")

        df["period_end"] = pd.to_datetime(df["period_end"]).dt.date.astype(str)

        missing_required = [
            col for col in self.required_columns if col not in df.columns
        ]
        required_fields_present = len(missing_required) == 0

        # Critical: write model feature matrix so existing Quant Agent remains unchanged.
        Path(config.model_feature_matrix_path).parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        df.to_csv(config.model_feature_matrix_path, index=False)

        evidence_refs: List[Dict[str, Any]] = []
        kpi_records: List[Dict[str, Any]] = []

        for row_number, row in df.iterrows():
            period_end = clean_value(row.get("period_end"))
            record_evidence: List[Dict[str, Any]] = []

            for metric, col in self.metric_map.items():
                if col not in df.columns:
                    continue

                value = clean_value(row.get(col))

                evidence = EvidenceRef(
                    metric=metric,
                    value=value,
                    source_type=config.source_type,
                    source_document="Synthetic Excel QPR financials",
                    source_path=source_path,
                    source_page_or_sheet=sheet_name,
                    source_section=f"{col} row {row_number + 2}",
                    period_end=period_end,
                    confidence=0.85,
                    extraction_method="excel_qpr_adapter",
                ).to_dict()

                evidence_refs.append(evidence)
                record_evidence.append(evidence)

            record = KPIRecord(
                company_id=config.company_id,
                company_name=config.company_name,
                ticker=config.ticker,
                cik=config.cik,
                source_type=config.source_type,
                source_path=source_path,
                period_end=period_end,
                period_type="quarter",
                currency="USD",
                revenue=clean_value(row.get("revenue")),
                operating_income=clean_value(row.get("operating_income")),
                net_income=clean_value(row.get("net_income")),
                ebitda_proxy=clean_value(row.get("ebitda_proxy")),
                working_capital=clean_value(row.get("working_capital")),
                net_debt=clean_value(row.get("net_debt")),
                source_confidence=0.85,
                evidence_refs=record_evidence,
            ).to_dict()

            kpi_records.append(record)

        null_counts = {
            col: int(df[col].isna().sum()) for col in df.columns
        }

        quality_report = SourceQualityReport(
            source_type=config.source_type,
            source_path=source_path,
            record_count=len(kpi_records),
            required_fields_present=required_fields_present,
            missing_required_fields=missing_required,
            null_counts=null_counts,
            status="pass"
            if required_fields_present and len(kpi_records) > 0
            else "review",
        ).to_dict()

        return {
            "raw_rows": len(df),
            "model_rows": len(df),
            "kpi_records": kpi_records,
            "evidence_refs": evidence_refs,
            "source_quality_report": quality_report,
        }