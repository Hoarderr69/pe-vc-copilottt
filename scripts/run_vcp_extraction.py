"""
Run the VCP Extraction Agent over the IC memos and evaluate it against the seed
ground truth.

Usage:
  uv run python scripts/run_vcp_extraction.py                 # all companies
  uv run python scripts/run_vcp_extraction.py --company portco_a_saas
  uv run python scripts/run_vcp_extraction.py --no-llm        # force offline mode
"""

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
load_dotenv()

from app.agents.vcp_extraction_agent import extract, to_vcp_milestones  # noqa: E402
from app.llm import azure_openai  # noqa: E402

IC_MEMO_DIR = PROJECT_ROOT / "data" / "raw" / "ic_memos"
PROCESSED = PROJECT_ROOT / "data" / "processed"
SEED = PROCESSED / "synthetic_vcp_milestones_seed.json"

COMPANIES = {
    "portco_a_saas": "Company A — B2B SaaS",
    "portco_b_industrial": "Company B — Industrial Manufacturing",
    "portco_c_healthcare": "Company C — Healthcare Services",
}

FINANCIAL = {"annual_revenue", "ebitda_margin", "net_debt_to_ebitda"}


def load_seed_by_company():
    if not SEED.exists():
        return {}
    seed = json.loads(SEED.read_text(encoding="utf-8"))
    by = {}
    for m in seed:
        by.setdefault(m["company_id"], {})[m["metric"]] = m
    return by


def evaluate(company_id, milestones, seed_for_company):
    """Recall over the known seed metrics + value accuracy on financial targets."""
    extracted = {m.metric: m for m in milestones}
    seed_metrics = set(seed_for_company.keys())
    found = seed_metrics & set(extracted.keys())
    extras = set(extracted.keys()) - seed_metrics

    value_hits, value_total = 0, 0
    for metric in FINANCIAL & found:
        value_total += 1
        ev = extracted[metric].target_value
        sv = seed_for_company[metric].get("target_value")
        if ev is not None and sv:
            if abs(ev - sv) / abs(sv) <= 0.02:
                value_hits += 1

    # The reporting-upgrade milestone is the deliberately ambiguous one.
    amb = extracted.get("reporting_cadence_upgrade_complete")
    ambiguity_ok = bool(amb and amb.confidence < 0.7)

    return {
        "recall": len(found) / len(seed_metrics) if seed_metrics else None,
        "found": sorted(found),
        "missed": sorted(seed_metrics - found),
        "extras": sorted(extras),
        "value_accuracy": (value_hits / value_total) if value_total else None,
        "ambiguity_flagged": ambiguity_ok,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--company", choices=list(COMPANIES), default=None)
    parser.add_argument("--no-llm", action="store_true", help="Force the offline heuristic extractor.")
    args = parser.parse_args()

    targets = [args.company] if args.company else list(COMPANIES)
    seed_by_company = load_seed_by_company()

    mode = "azure_openai" if (not args.no_llm and azure_openai.is_configured()) else "offline_heuristic"
    print("\n========== VCP EXTRACTION AGENT ==========")
    print(f"Mode: {mode}" + ("" if mode == "azure_openai" else f"  (Azure not configured: {', '.join(azure_openai.missing_vars()) or 'forced --no-llm'})"))

    agg_recall, agg_value, n = 0.0, 0.0, 0

    for cid in targets:
        memo_path = IC_MEMO_DIR / f"{cid}_ic_memo.md"
        if not memo_path.exists():
            print(f"\n[skip] memo not found: {memo_path}")
            continue

        memo = memo_path.read_text(encoding="utf-8")
        result = extract(memo, cid, COMPANIES[cid], prefer_llm=not args.no_llm)
        milestones = to_vcp_milestones(result)

        out_path = PROCESSED / f"{cid}_extracted_milestones.json"
        out_path.write_text(json.dumps([m.to_dict() for m in milestones], indent=2, default=str), encoding="utf-8")

        print(f"\n── {COMPANIES[cid]} ──  ({result.extraction_mode}{', ' + result.model if result.model else ''})")
        for m in milestones:
            conf_flag = "  ⚠ review" if m.confidence < 0.7 else ""
            tv = m.target_value
            print(f"  • {m.initiative:30} metric={m.metric:32} target={tv}  conf={m.confidence:.2f}{conf_flag}")

        ev = evaluate(cid, milestones, seed_by_company.get(cid, {}))
        if ev["recall"] is not None:
            n += 1
            agg_recall += ev["recall"]
            agg_value += ev["value_accuracy"] or 0
            print(f"  eval: recall={ev['recall']:.0%}  value_accuracy={ev['value_accuracy']:.0%}  "
                  f"ambiguity_flagged={ev['ambiguity_flagged']}")
            if ev["missed"]:
                print(f"        missed: {ev['missed']}")
            if ev["extras"]:
                print(f"        extra (in memo, not in seed): {ev['extras']}")
        print(f"  saved: {out_path.relative_to(PROJECT_ROOT)}")

    if n:
        print(f"\n========== EVAL SUMMARY ({n} companies) ==========")
        print(f"Mean recall:         {agg_recall / n:.0%}")
        print(f"Mean value accuracy: {agg_value / n:.0%}")
        print("Each extracted milestone is unconfirmed (confirmed=false) — it must pass HITL before becoming ground truth.")


if __name__ == "__main__":
    main()
