import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.workflows.hitl_queue import build_hitl_review_queue


def main():
    print("\n========== HITL REVIEW QUEUE BUILDER ==========")

    payload = build_hitl_review_queue(
        action_inbox_path="data/processed/portfolio_action_inbox.json",
        output_path="data/processed/hitl_review_queue.json",
    )

    print(f"Queue items: {payload.get('queue_item_count')}")
    print(f"Pending review: {payload.get('pending_review_count')}")

    print("\nReview queue:")
    for item in payload.get("queue_items", []):
        print(
            f"- {item['review_id']} | "
            f"[{item['priority']}] {item['company_name']} | "
            f"{item['review_action']}"
        )
        print(f"  {item['headline']}")

    print("\nSaved: data/processed/hitl_review_queue.json")


if __name__ == "__main__":
    main()