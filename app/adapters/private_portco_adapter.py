from __future__ import annotations
import pandas as pd

from pathlib import Path
from typing import Any, Dict, List
from app.adapters.base import BaseKPIAdapter
from app.schemas.kpi_schema import (
    EvidenceRef,
    KPIExtractionConfig,
    KPIRecord,
    SourceQualityReport,
    clean_value,
)


class PrivatePortcoFinancialAdapter(BaseKPIAdapter):
    """
    Adapter for private portfolio company monthly financial data.

    Supports:
    - CSV synthetic financials
    - Excel synthetic financials with sheet 'Financials'

    Normalizes private portco financials into KPIRecord + EvidenceRef.
    """

    source_type = "private_portco"

    required_columns = [
        "period_end",
        "revenue",
        "ebitda",
        "net_debt",
    ]

    metric_map = {
        "revenue": "revenue",
        "gross_profit": "gross_profit",
        "adjusted_ebitda": "ebitda",
        "ebitda_proxy": "ebitda",
        "ebitda_margin": "ebitda_margin",
        "cash": "cash",
        "net_debt": "net_debt",
        "free_cash_flow": "free_cash_flow",
        "working_capital": "working_capital",
    }

    def _load_source(self, source_path: str) -> pd.DataFrame:
        path = Path(source_path)

        if not path.exists():
            raise FileNotFoundError(f"Private portco source file not found: {source_path}")

        if path.suffix.lower() == ".csv":
            return pd.read_csv(path)

        if path.suffix.lower() in {".xlsx", ".xls"}:
            return pd.read_excel(path, sheet_name="Financials", engine="openpyxl")

        raise ValueError(f"Unsupported private portco source file type: {path.suffix}")

    def extract(self, config: KPIExtractionConfig) -> Dict[str, Any]:
        if not config.source_path:
            raise ValueError(
                "PrivatePortcoFinancialAdapter requires config.source_path."
            )

        df = self._load_source(config.source_path)

        if "period_end" not in df.columns:
            raise ValueError("Private portco financials must contain period_end column.")

        df["period_end"] = pd.to_datetime(df["period_end"]).dt.date.astype(str)

        # Compute working capital if AR / inventory / AP are available.
        if "working_capital" not in df.columns:
            if {"ar", "inventory", "ap"}.issubset(set(df.columns)):
                df["working_capital"] = df["ar"] + df["inventory"] - df["ap"]

        # Normalize EBITDA naming for downstream Quant Agent.
        if "ebitda_proxy" not in df.columns and "ebitda" in df.columns:
            df["ebitda_proxy"] = df["ebitda"]

        if "adjusted_ebitda" not in df.columns and "ebitda" in df.columns:
            df["adjusted_ebitda"] = df["ebitda"]

        # Use EBITDA as operating income proxy for synthetic private data.
        if "operating_income" not in df.columns and "ebitda" in df.columns:
            df["operating_income"] = df["ebitda"]

        missing_required = [
            col for col in self.required_columns if col not in df.columns
        ]
        required_fields_present = len(missing_required) == 0

        Path(config.raw_feature_matrix_path).parent.mkdir(parents=True, exist_ok=True)
        Path(config.model_feature_matrix_path).parent.mkdir(parents=True, exist_ok=True)

        df.to_csv(config.raw_feature_matrix_path, index=False)

        model_cols = [
            "period_end",
            "revenue",
            "gross_profit",
            "operating_income",
            "adjusted_ebitda",
            "ebitda_proxy",
            "ebitda_margin",
            "working_capital",
            "cash",
            "net_debt",
            "free_cash_flow",
        ]
        model_cols = [col for col in model_cols if col in df.columns]

        model_df = df[model_cols].copy()
        model_df.to_csv(config.model_feature_matrix_path, index=False)

        path = Path(config.source_path)
        source_page_or_sheet = "Financials" if path.suffix.lower() in {".xlsx", ".xls"} else "csv"

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
                    source_document=path.name,
                    source_path=config.source_path,
                    source_page_or_sheet=source_page_or_sheet,
                    source_section=f"{col} row {row_number + 2}",
                    period_end=period_end,
                    confidence=0.9,
                    extraction_method="private_portco_financial_adapter",
                ).to_dict()

                evidence_refs.append(evidence)
                record_evidence.append(evidence)

            record = KPIRecord(
                company_id=config.company_id,
                company_name=config.company_name,
                ticker=config.ticker,
                cik=config.cik,
                source_type=config.source_type,
                source_path=config.source_path,
                period_end=period_end,
                period_type="month",
                currency=clean_value(row.get("currency")) or "GBP",
                revenue=clean_value(row.get("revenue")),
                gross_profit=clean_value(row.get("gross_profit")),
                operating_income=clean_value(row.get("operating_income")),
                adjusted_ebitda=clean_value(row.get("adjusted_ebitda")),
                ebitda_proxy=clean_value(row.get("ebitda_proxy")),
                working_capital=clean_value(row.get("working_capital")),
                cash=clean_value(row.get("cash")),
                net_debt=clean_value(row.get("net_debt")),
                free_cash_flow=clean_value(row.get("free_cash_flow")),
                source_confidence=0.9,
                evidence_refs=record_evidence,
            ).to_dict()

            kpi_records.append(record)

        null_counts = {
            col: int(df[col].isna().sum()) for col in df.columns
        }

        quality_report = SourceQualityReport(
            source_type=config.source_type,
            source_path=config.source_path,
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
            "model_rows": len(model_df),
            "kpi_records": kpi_records,
            "evidence_refs": evidence_refs,
            "source_quality_report": quality_report,
        }



