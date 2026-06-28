import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.analytics.vcp_drift import run_vcp_drift_for_kpi_records


def main():
    print("\n========== VCP DRIFT FROM NORMALIZED KPI RECORDS ==========")

    payload = run_vcp_drift_for_kpi_records(
        company_id="portco_a_saas",
        kpi_records_path="data/processed/portco_a_saas_kpi_records.json",
        vcp_store_path="data/processed/synthetic_vcp_milestones_seed.json",
        output_path="data/processed/portco_a_saas_vcp_drift_from_kpi_records.json",
    )

    print(f"Company: {payload.get('company_id')}")
    print(f"Company name: {payload.get('company_name')}")
    print(f"Latest period: {payload.get('latest_period_end')}")
    print(f"Result count: {payload.get('result_count')}")
    print("Status counts:")
    print(json.dumps(payload.get("status_counts"), indent=2))

    print("\nResults:")
    for item in payload.get("results", []):
        print(
            f"- [{item['status']}] {item['metric']} | "
            f"actual={item['actual_value']} | "
            f"target={item['target_value']} | "
            f"reason={item['reason']}"
        )

    print(
        "\nSaved: "
        "data/processed/portco_a_saas_vcp_drift_from_kpi_records.json"
    )


if __name__ == "__main__":
    main()