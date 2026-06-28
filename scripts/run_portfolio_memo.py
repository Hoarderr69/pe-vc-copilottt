import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.workflows.portfolio_memo import build_portfolio_memo


def main():
    print("\n========== PORTFOLIO MEMO BUILDER ==========")

    payload = build_portfolio_memo(
        action_inbox_path="data/processed/portfolio_action_inbox.json",
        monitoring_summary_path="data/processed/portfolio_vcp_monitoring_summary.json",
        hitl_queue_path="data/processed/hitl_review_queue.json",
        output_path="data/processed/portfolio_memo.md",
    )

    print(f"Companies:        {payload['company_count']}")
    print(f"Action items:     {payload['action_item_count']}")
    print(f"Pending reviews:  {payload['pending_review_count']}")
    print(f"\nSaved: {payload['output_path']}")


if __name__ == "__main__":
    main()
