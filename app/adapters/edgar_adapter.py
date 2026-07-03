from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

from app.adapters.base import BaseKPIAdapter
from app.ingestion.build_feature_matrix import (
    build_feature_matrix,
    build_model_feature_matrix,
)
from app.schemas.kpi_schema import (
    EvidenceRef,
    KPIExtractionConfig,
    KPIRecord,
    SourceQualityReport,
    clean_value,
)


class EDGARFeatureMatrixAdapter(BaseKPIAdapter):
    """
    EDGAR/FRED adapter for the prototype.

    Keeps the Week 1 EDGAR/FRED pipeline intact, then normalizes the generated
    model feature matrix into KPIRecord + EvidenceRef objects.
    """

    source_type = "edgar"

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
        "gross_profit": "gross_profit",
        "ebitda_proxy": "ebitda_proxy",
        "working_capital": "working_capital",
        "net_debt": "net_debt",
        # ARR proxy (RPO/deferred revenue) has no dedicated KPIRecord field — it still
        # flows into evidence_refs below so SaaS filers' subscription backlog is
        # citable evidence even though it isn't a first-class monitored metric yet.
        "arr_proxy": "arr_proxy",
    }

    def extract(self, config: KPIExtractionConfig) -> Dict[str, Any]:
        Path(config.raw_feature_matrix_path).parent.mkdir(
            parents=True,
            exist_ok=True,
        )
        Path(config.model_feature_matrix_path).parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        raw_df = build_feature_matrix(
            cik=config.cik,
            include_macro=config.include_macro,
            output_path=config.raw_feature_matrix_path,
        )

        model_df = build_model_feature_matrix(
            cik=config.cik,
            include_macro=config.include_macro,
            output_path=config.model_feature_matrix_path,
        )

        model_df["period_end"] = (
            pd.to_datetime(model_df["period_end"]).dt.date.astype(str)
        )

        missing_required = [
            col for col in self.required_columns if col not in model_df.columns
        ]
        required_fields_present = len(missing_required) == 0

        evidence_refs: List[Dict[str, Any]] = []
        kpi_records: List[Dict[str, Any]] = []

        for _, row in model_df.iterrows():
            period_end = clean_value(row.get("period_end"))
            record_evidence: List[Dict[str, Any]] = []

            for metric, col in self.metric_map.items():
                if col not in model_df.columns:
                    continue

                value = clean_value(row.get(col))

                evidence = EvidenceRef(
                    metric=metric,
                    value=value,
                    source_type=config.source_type,
                    source_document="SEC EDGAR companyfacts normalized feature matrix",
                    source_path=config.model_feature_matrix_path,
                    source_section=col,
                    period_end=period_end,
                    confidence=0.9,
                    extraction_method="structured_edgar_pipeline",
                ).to_dict()

                evidence_refs.append(evidence)
                record_evidence.append(evidence)

            record = KPIRecord(
                company_id=config.company_id,
                company_name=config.company_name,
                ticker=config.ticker,
                cik=config.cik,
                source_type=config.source_type,
                source_path=config.model_feature_matrix_path,
                period_end=period_end,
                period_type="quarter",
                currency="USD",
                revenue=clean_value(row.get("revenue")),
                gross_profit=clean_value(row.get("gross_profit")),
                operating_income=clean_value(row.get("operating_income")),
                net_income=clean_value(row.get("net_income")),
                ebitda_proxy=clean_value(row.get("ebitda_proxy")),
                working_capital=clean_value(row.get("working_capital")),
                net_debt=clean_value(row.get("net_debt")),
                source_confidence=0.9,
                evidence_refs=record_evidence,
            ).to_dict()

            kpi_records.append(record)

        null_counts = {
            col: int(model_df[col].isna().sum()) for col in model_df.columns
        }

        quality_report = SourceQualityReport(
            source_type=config.source_type,
            source_path=config.model_feature_matrix_path,
            record_count=len(kpi_records),
            required_fields_present=required_fields_present,
            missing_required_fields=missing_required,
            null_counts=null_counts,
            status="pass"
            if required_fields_present and len(kpi_records) > 0
            else "review",
        ).to_dict()

        return {
            "raw_rows": len(raw_df),
            "model_rows": len(model_df),
            "kpi_records": kpi_records,
            "evidence_refs": evidence_refs,
            "source_quality_report": quality_report,
        }
