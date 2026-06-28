import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.analytics.vcp_drift import run_vcp_drift_for_manifest


def main():
    payload = run_vcp_drift_for_manifest(
        manifest_path="data/processed/synthetic_source_manifest.json",
        vcp_store_path="data/processed/synthetic_vcp_milestones_seed.json",
        output_path="data/processed/vcp_drift_scores.json",
    )

    print("\n========== VCP DRIFT CHECK ==========")
    print(f"Result count: {payload['result_count']}")
    print("Status counts:")
    print(json.dumps(payload["status_counts"], indent=2))

    print("\nTop drift results:")
    sorted_results = sorted(
        payload["results"],
        key=lambda item: item.get("severity_score", 0),
        reverse=True,
    )

    for item in sorted_results[:10]:
        print(
            f"- [{item['status']}] {item['company_id']} | "
            f"{item['metric']} | actual={item['actual_value']} | "
            f"target={item['target_value']} | reason={item['reason']}"
        )

    print("\nSaved: data/processed/vcp_drift_scores.json")


if __name__ == "__main__":
    main()