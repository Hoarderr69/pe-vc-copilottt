import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.store.vcp_store import VCPStore


def main():
    store = VCPStore("data/processed/synthetic_vcp_milestones_seed.json")

    summary = store.summary()

    print("\n========== VCP STORE CHECK ==========")
    print(json.dumps(summary, indent=2))

    print("\nCompanies:")
    for company_id in store.company_ids():
        milestones = store.load_confirmed_for_company(company_id)
        print(f"\n- {company_id}: {len(milestones)} confirmed milestones")

        for milestone in milestones:
            print(
                f"  • {milestone.metric}: target={milestone.target_value}, "
                f"date={milestone.target_date}, confidence={milestone.confidence}"
            )


if __name__ == "__main__":
    main()