"""
Seed a public-to-private portfolio company from real SEC EDGAR data.

General-purpose: any take-private just needs a CIK plus two JSON files (deal
metadata + VCP milestones) — no code changes. This is the "Real data / EDGAR"
onboarding path, as opposed to the synthetic-seed / upload paths.

Usage:
    python scripts/seed_public_to_private_company.py \\
        --company-id qualtrics \\
        --company-name "Qualtrics International Inc." \\
        --cik 1747748 \\
        --ticker XM \\
        --deal-metadata-json data/raw/deal_metadata/qualtrics.json \\
        --milestones-json data/raw/vcp_milestones/qualtrics_milestones.json \\
        --reviewed-by "demo-seed-script"

What it does, in order:
  1. Pulls live XBRL data for the CIK via the EDGAR adapter (source_type="edgar"),
     writing the same processed/ + features/ artifacts the dashboard reads for any
     other company (KPI records, evidence refs, source-quality report).
  2. Loads + validates the deal-metadata JSON (DealMetadata) and saves it via
     DealStore — this is the entry-side IRR economics and, via `sector_key`, what
     makes peer benchmarking work without a code change (see vcp_routes._infer_sector).
  3. Loads the VCP milestones JSON and locks them in as confirmed ground truth via
     the same HITL confirmation workflow the UI uses (confirm_vcp_milestones), so
     drift/IRR/portfolio endpoints treat this company identically to any other.

Re-running is safe: KPI records are overwritten with a fresh EDGAR pull, deal
metadata is overwritten, and VCP milestones get a bumped version (prior versions
are replaced for this company_id only).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.agents.kpi_extraction_agent import run_kpi_extraction_agent  # noqa: E402
from app.schemas.kpi_schema import KPIExtractionConfig  # noqa: E402
from app.store.deal_store import DealMetadata, DealStore  # noqa: E402
from app.workflows.vcp_confirmation import confirm_vcp_milestones  # noqa: E402

PROCESSED = PROJECT_ROOT / "data" / "processed"
FEATURES = PROJECT_ROOT / "data" / "features"


def _load_json(path: str) -> Any:
    p = Path(path)
    if not p.is_absolute():
        p = PROJECT_ROOT / p
    if not p.exists():
        raise FileNotFoundError(f"File not found: {p}")
    return json.loads(p.read_text(encoding="utf-8"))


def seed_kpi_records(company_id: str, company_name: str, cik: str, ticker: str) -> Dict[str, Any]:
    """Step 1: pull live EDGAR XBRL data into the standard KPI artifacts."""
    PROCESSED.mkdir(parents=True, exist_ok=True)
    FEATURES.mkdir(parents=True, exist_ok=True)

    config = KPIExtractionConfig(
        company_id=company_id,
        company_name=company_name,
        ticker=ticker,
        cik=cik,
        source_type="edgar",
        base_currency="USD",
        raw_feature_matrix_path=str(FEATURES / f"{company_id}_raw_feature_matrix.csv"),
        model_feature_matrix_path=str(FEATURES / f"{company_id}_model_feature_matrix.csv"),
        kpi_records_path=str(PROCESSED / f"{company_id}_kpi_records.json"),
        evidence_refs_path=str(PROCESSED / f"{company_id}_evidence_refs.json"),
        source_quality_report_path=str(PROCESSED / f"{company_id}_source_quality_report.json"),
        include_macro=False,
    )

    return run_kpi_extraction_agent(config)


def seed_deal_metadata(company_id: str, deal_metadata_json: str) -> str:
    """Step 2: validate + persist the deal-metadata JSON via DealStore."""
    raw = _load_json(deal_metadata_json)
    raw["company_id"] = company_id  # the deal file's company_id must match this seed run
    deal = DealMetadata.model_validate(raw)
    return DealStore().save(deal)


def seed_vcp_milestones(
    company_id: str, company_name: str, milestones_json: str, reviewed_by: str
) -> Dict[str, Any]:
    """Step 3: lock the public-thesis VCP plan in as confirmed ground truth."""
    milestones: List[Dict[str, Any]] = _load_json(milestones_json)
    return confirm_vcp_milestones(
        company_id=company_id,
        company_name=company_name,
        milestones=milestones,
        reviewed_by=reviewed_by,
        reviewer_note=f"Seeded from public-to-private EDGAR demo script for {company_id}.",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--company-id", required=True, help="Slug used as the company_id everywhere downstream.")
    parser.add_argument("--company-name", required=True)
    parser.add_argument("--cik", required=True, help="SEC EDGAR CIK (with or without leading zeros).")
    parser.add_argument("--ticker", default="N/A")
    parser.add_argument("--deal-metadata-json", required=True, help="Path to a DealMetadata JSON file.")
    parser.add_argument("--milestones-json", required=True, help="Path to a list[VCPMilestone-dict] JSON file.")
    parser.add_argument("--reviewed-by", default="seed-script", help="Attributed reviewer for the HITL confirmation log.")
    parser.add_argument("--skip-edgar", action="store_true", help="Skip the live EDGAR pull (reuse existing KPI records).")
    args = parser.parse_args()

    print(f"== Seeding public-to-private company: {args.company_id} ({args.company_name}) ==")

    if not args.skip_edgar:
        print(f"[1/3] Pulling EDGAR XBRL data for CIK {args.cik}...")
        kpi_result = seed_kpi_records(args.company_id, args.company_name, args.cik, args.ticker)
        print(
            f"      -> {kpi_result['kpi_records_count']} KPI periods, "
            f"{kpi_result['evidence_refs_count']} evidence refs written to "
            f"{kpi_result['kpi_records_path']}"
        )
        quality = kpi_result.get("source_quality_report", {})
        if quality.get("status") != "pass":
            print(f"      [WARN] source quality status='{quality.get('status')}', "
                  f"missing_required_fields={quality.get('missing_required_fields')}")
    else:
        print("[1/3] Skipped EDGAR pull (--skip-edgar).")

    print(f"[2/3] Saving deal metadata from {args.deal_metadata_json}...")
    deal_path = seed_deal_metadata(args.company_id, args.deal_metadata_json)
    print(f"      -> {deal_path}")

    print(f"[3/3] Confirming VCP milestones from {args.milestones_json}...")
    vcp_result = seed_vcp_milestones(
        args.company_id, args.company_name, args.milestones_json, args.reviewed_by
    )
    print(
        f"      -> {vcp_result['confirmed_count']} milestones confirmed "
        f"(version {vcp_result['version']}) in {vcp_result['store_path']}"
    )

    print(f"== Done. '{args.company_id}' will now appear in /api/vcp/portfolio. ==")


if __name__ == "__main__":
    main()
