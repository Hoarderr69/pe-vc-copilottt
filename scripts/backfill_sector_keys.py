"""
One-off backfill: give every already-ingested company a stored sector_key.

Before the sector refactor, sector lived only in data/reference/sector_benchmarks.json
(and was lazily mutated by the /peers endpoint). This walks every company in
data/processed/ (one per ``{company_id}_kpi_records.json``), infers its sector with the
shared resolver, and persists it onto the company — into its deal-metadata file if one
exists, and always into the ``{company_id}_company_meta.json`` sidecar.

Usage:
  uv run python scripts/backfill_sector_keys.py            # write changes
  uv run python scripts/backfill_sector_keys.py --dry-run  # report only
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.analytics.sector import infer_sector_key  # noqa: E402
from app.store.company_store import (  # noqa: E402
    CompanyMeta,
    load_company_meta,
    save_company_meta,
)
from app.store.deal_store import DealStore  # noqa: E402

PROCESSED = PROJECT_ROOT / "data" / "processed"
_KPI_SUFFIX = "_kpi_records.json"


def _company_name(kpi_path: Path, company_id: str) -> str:
    try:
        records = json.loads(kpi_path.read_text(encoding="utf-8"))
        if records:
            return records[-1].get("company_name") or company_id
    except (json.JSONDecodeError, OSError):
        pass
    return company_id


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Report without writing.")
    args = parser.parse_args()

    if not PROCESSED.exists():
        print(f"No processed dir at {PROCESSED}; nothing to backfill.")
        return

    kpi_files = sorted(PROCESSED.glob(f"*{_KPI_SUFFIX}"))
    if not kpi_files:
        print(f"No '*{_KPI_SUFFIX}' files in {PROCESSED}; nothing to backfill.")
        return

    deal_store = DealStore()
    print(f"\n===== BACKFILL SECTOR KEYS ({'dry-run' if args.dry_run else 'write'}) =====")

    for kpi_path in kpi_files:
        company_id = kpi_path.name[: -len(_KPI_SUFFIX)]
        company_name = _company_name(kpi_path, company_id)

        # Prefer an already-stored sector so we don't override curated values.
        meta = load_company_meta(company_id, base_dir=str(PROCESSED))
        deal = deal_store.load(company_id)
        existing = (meta.sector_key if meta else None) or (deal.sector_key if deal else None)
        sector_key = existing or infer_sector_key(company_id, company_name)

        status = "kept" if existing else ("inferred" if sector_key else "unknown")
        print(f"  {company_id:30} {company_name:28} → {sector_key or '—'}  [{status}]")

        if args.dry_run or not sector_key:
            continue

        if deal is not None and deal.sector_key != sector_key:
            deal.sector_key = sector_key
            deal_store.save(deal)

        new_meta = meta or CompanyMeta(company_id=company_id)
        new_meta.company_name = new_meta.company_name or company_name
        new_meta.sector_key = sector_key
        save_company_meta(new_meta, base_dir=str(PROCESSED))

    print("\nDone." + ("  (dry-run — nothing written)" if args.dry_run else ""))


if __name__ == "__main__":
    main()
