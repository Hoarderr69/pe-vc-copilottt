import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.analytics.portfolio_action_inbox import build_portfolio_action_inbox


def main():
    print("\n========== PORTFOLIO ACTION INBOX ==========")

    payload = build_portfolio_action_inbox(
        portfolio_summary_path="data/processed/portfolio_vcp_monitoring_summary.json",
        output_path="data/processed/portfolio_action_inbox.json",
    )

    print(f"Portfolio companies: {payload.get('portfolio_company_count')}")
    print(f"Total alerts: {payload.get('total_alerts')}")
    print(f"Action items: {payload.get('action_item_count')}")
    print(f"Severity counts: {payload.get('severity_counts')}")

    print("\nRanked action items:")
    for item in payload.get("action_items", []):
        print(
            f"{item['priority_rank']}. [{item['priority']}] "
            f"{item['company_name']} | score={item['priority_score']}"
        )
        print(f"   {item['headline']}")
        print(f"   Recommended action: {item['recommended_action']}")

    print("\nSaved: data/processed/portfolio_action_inbox.json")


if __name__ == "__main__":
    main()