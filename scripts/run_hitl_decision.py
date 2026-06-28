import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.workflows.hitl_decisions import HITLDecisionError, apply_hitl_decision


def main():
    parser = argparse.ArgumentParser(
        description="Record an operating-partner HITL decision on a review item."
    )
    parser.add_argument("review_id", help="e.g. review_001_portco_a_saas")
    parser.add_argument(
        "decision",
        choices=["approve", "edit", "reject"],
        help="Decision to record.",
    )
    parser.add_argument("--by", required=True, help="Reviewer identity (name or email).")
    parser.add_argument("--note", default=None, help="Optional reviewer note.")
    parser.add_argument(
        "--edited-action",
        default=None,
        help="Required for 'edit': the revised recommended action.",
    )
    args = parser.parse_args()

    print("\n========== HITL DECISION ==========")

    try:
        item = apply_hitl_decision(
            review_id=args.review_id,
            decision=args.decision,
            reviewed_by=args.by,
            reviewer_note=args.note,
            edited_recommended_action=args.edited_action,
        )
    except (HITLDecisionError, FileNotFoundError) as exc:
        print(f"ERROR: {exc}")
        sys.exit(1)

    decision = item["decision"]
    print(f"Review:    {item['review_id']} ({item['company_name']})")
    print(f"Decision:  {args.decision} -> status '{item['status']}'")
    print(f"Reviewer:  {decision['reviewed_by']} at {decision['reviewed_at']}")
    if decision.get("reviewer_note"):
        print(f"Note:      {decision['reviewer_note']}")
    if decision.get("edited_recommended_action"):
        print(f"Edited:    {decision['edited_recommended_action']}")

    print("\nUpdated: data/processed/hitl_review_queue.json")
    print("Logged:  data/processed/hitl_audit_log.json")


if __name__ == "__main__":
    main()
