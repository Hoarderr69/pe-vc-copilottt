import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.agents.kpi_extraction_agent import run_kpi_extraction_agent
from app.schemas.kpi_schema import KPIExtractionConfig


def main():
    print("\n========== PRIVATE PORTCO KPI NORMALIZATION CHECK ==========")

    source_path = (
        "data/raw/synthetic_portcos/portco_a_saas/"
        "portco_a_saas_monthly_financials.csv"
    )

    config = KPIExtractionConfig(
        company_id="portco_a_saas",
        company_name="Company A — B2B SaaS",
        ticker="PRIVATE",
        cik="N/A",
        source_type="private_portco_csv",
        source_path=source_path,
        raw_feature_matrix_path="data/features/portco_a_saas_raw_feature_matrix.csv",
        model_feature_matrix_path="data/features/portco_a_saas_model_feature_matrix.csv",
        kpi_records_path="data/processed/portco_a_saas_kpi_records.json",
        evidence_refs_path="data/processed/portco_a_saas_evidence_refs.json",
        source_quality_report_path="data/processed/portco_a_saas_source_quality_report.json",
        include_macro=False,
    )

    result = run_kpi_extraction_agent(config)

    print("\nResult:")
    print(json.dumps(result, indent=2, default=str))

    print("\nGenerated artifacts:")
    print("- data/features/portco_a_saas_raw_feature_matrix.csv")
    print("- data/features/portco_a_saas_model_feature_matrix.csv")
    print("- data/processed/portco_a_saas_kpi_records.json")
    print("- data/processed/portco_a_saas_evidence_refs.json")
    print("- data/processed/portco_a_saas_source_quality_report.json")


if __name__ == "__main__":
    main()