import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.agents.kpi_extraction_agent import run_kpi_extraction_agent
from app.schemas.kpi_schema import KPIExtractionConfig


def safe_slug(value: str) -> str:
    return value.lower().replace(" ", "_").replace("—", "").replace("-", "_")


def main():
    print("\n========== BATCH PRIVATE PORTCO KPI NORMALIZATION ==========")

    manifest_path = Path("data/processed/synthetic_source_manifest.json")

    if not manifest_path.exists():
        raise FileNotFoundError(
            "Missing data/processed/synthetic_source_manifest.json. "
            "Run scripts/generate_synthetic_portco_data.py first."
        )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

    financial_sources = [
        item
        for item in manifest
        if item.get("doc_type") == "financials_monthly"
        and item.get("source_type") == "csv"
    ]

    results = []

    for source in financial_sources:
        company_id = source["company_id"]
        company_name = source["company_name"]
        source_path = source["path"]

        print(f"\nNormalizing: {company_id} from {source_path}")

        config = KPIExtractionConfig(
            company_id=company_id,
            company_name=company_name,
            ticker="PRIVATE",
            cik="N/A",
            source_type="private_portco_csv",
            source_path=source_path,
            raw_feature_matrix_path=f"data/features/{company_id}_raw_feature_matrix.csv",
            model_feature_matrix_path=f"data/features/{company_id}_model_feature_matrix.csv",
            kpi_records_path=f"data/processed/{company_id}_kpi_records.json",
            evidence_refs_path=f"data/processed/{company_id}_evidence_refs.json",
            source_quality_report_path=f"data/processed/{company_id}_source_quality_report.json",
            include_macro=False,
        )

        result = run_kpi_extraction_agent(config)

        results.append(
            {
                "company_id": company_id,
                "company_name": company_name,
                "source_path": source_path,
                **result,
            }
        )

        print(
            f"  -> KPI records: {result['kpi_records_count']}, "
            f"Evidence refs: {result['evidence_refs_count']}, "
            f"Quality: {result['source_quality_report']['status']}"
        )

    output_path = Path("data/processed/private_portco_kpi_batch_summary.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")

    print("\n========== BATCH SUMMARY ==========")
    print(f"Companies processed: {len(results)}")
    print(f"Saved: {output_path}")


if __name__ == "__main__":
    main()