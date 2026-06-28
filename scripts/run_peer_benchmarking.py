"""
Run the Peer Benchmarking Node over the synthetic portfolio companies.

Usage:
  uv run python scripts/run_peer_benchmarking.py
  uv run python scripts/run_peer_benchmarking.py --company portco_a_saas
"""

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.analytics.peer_benchmarking import run_peer_benchmark_for_company  # noqa: E402

PROCESSED = PROJECT_ROOT / "data" / "processed"
COMPANIES = ["portco_a_saas", "portco_b_industrial", "portco_c_healthcare"]


def _fmt(metric: str, v):
    if v is None:
        return "—"
    if metric == "net_debt_to_ebitda":
        return f"{v:.2f}x"
    return f"{v * 100:.1f}%"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--company", choices=COMPANIES, default=None)
    args = parser.parse_args()

    targets = [args.company] if args.company else COMPANIES

    print("\n========== PEER BENCHMARKING NODE ==========")
    for cid in targets:
        kpi_path = PROCESSED / f"{cid}_kpi_records.json"
        if not kpi_path.exists():
            print(f"\n[skip] no KPI records for {cid}")
            continue

        out_path = PROCESSED / f"{cid}_peer_benchmark.json"
        payload = run_peer_benchmark_for_company(
            company_id=cid,
            kpi_records_path=str(kpi_path),
            output_path=str(out_path),
        )

        comp = payload["composite_outperformance"]
        comp_str = f"{comp * 100:.0f}% of metrics beat sector" if comp is not None else "n/a"
        print(f"\n── {payload['company_name']} ──  sector: {payload['sector_label']} "
              f"(n={payload['peer_set_size']})  ·  {comp_str}")
        for r in payload["results"]:
            arrow = {"Outperform": "▲", "Underperform": "▼", "In-line": "≈", "Not Evaluable": "·"}[r["status"]]
            print(f"  {arrow} {r['metric']:22} company={_fmt(r['metric'], r['company_value']):>8}"
                  f"  sector={_fmt(r['metric'], r['sector_median']):>8}  → {r['status']}")
        print(f"  saved: {out_path.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
