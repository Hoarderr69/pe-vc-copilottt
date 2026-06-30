# pe-value-creation-copilot

Implementation Plan
Part 1 — Sector mapping: full refactor (sector as a first-class company attribute)
Goal: sector is decided once at ingestion, stored with the company, and survives clearing processed//features/. sector_benchmarks.json becomes read-only (medians only). Benchmarking never hard-fails.

Step 1.1 — New shared sector resolver
New file app/analytics/sector.py:

infer_sector_key(company_id, company_name, sic_code=None, explicit=None) -> Optional[str] — resolution order: explicit → SIC-code map (for EDGAR filers) → keyword fallback (the current saas/industrial/health logic, moved out of vcp_routes.py) → None.
SIC_TO_SECTOR dict (e.g. 7372/7389 → b2b_saas, etc.).
Move \_infer_sector logic here; vcp_routes.\_infer_sector becomes a thin wrapper (or is deleted).
Step 1.2 — Persist sector on the company record
Add sector_key: Optional[str] = None to DealMetadata (deal_store.py:32).
For companies without a deal-metadata file, add a tiny data/processed/{company_id}\_company_meta.json sidecar (written at ingest) holding {company_id, company_name, sector_key, source_type, cik?, sic?}. Add load_company_meta()/save_company_meta() helpers (in deal_store.py or a small company_store.py).
Step 1.3 — Set sector at ingestion (the actual fix)
In ingest_routes.py ingest_financials_upload (~line 122–145): after resolved_id/resolved_name are known, call infer_sector_key(...) and persist via the meta helper. Same for the VCP extract-upload path in vcp_routes.py.
Step 1.4 — Benchmarking reads sector from the company, not the reference file
run_peer_benchmark_for_company (peer_benchmarking.py:141): add optional sector_key param. Resolution: explicit arg → company meta/deal store → (legacy) company_sector_map.
If still unknown: return a payload with sector_key=None and all metrics "Not Evaluable" + a clear reason, instead of raise ValueError. This fixes the silent peer_benchmark=None in report_routes.py:374.
Step 1.5 — Stop mutating reference data
Delete \_register_sector and the \_register_sector call in the /peers handler (vcp_routes.py:491-497). The handler instead resolves sector from company meta and passes it down.
Strip company_sector_map out of sector_benchmarks.json (kept only as legacy fallback during transition; remove in a follow-up).
Step 1.6 — Backfill + tests
One-off scripts/backfill_sector_keys.py: for every existing company in processed/, infer + write sector_key into its meta/deal file.
Unit test: ingest a fresh company_id with no prior map entry → assert sector resolved and peer benchmark returns evaluable results (regression test for the exact bug you hit).
Outcome: clear processed/+features/, re-ingest → sector set during ingest, peer benchmark works immediately, reports get real peer data.

Part 2 — Real EDGAR demo: Qualtrics (public→private)
Uses the existing EDGARFeatureMatrixAdapter + data_sources/edgar.py. Live XBRL pull.

Step 2.1 — Confirm the filer & tags
Resolve Qualtrics' real CIK; verify data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json returns the SaaS tags. Extend METRIC*TAGS in edgar.py:22 with subscription/SaaS tags (RevenueFromContractWithCustomerExcludingAssessedTax split by axis isn't trivial — start with total Revenues, OperatingIncomeLoss, and add RPO/deferred-revenue tags as ARR proxies where disclosed).
Step 2.2 — Deal metadata from the DEFM14C (your attached PDF)
Create data/raw/deal_metadata/qualtrics.json (DealMetadata): close date (Mar 2023), entry EV ≈ $12.5bn, $18.15/share, sponsors Silver Lake + CPP, plus sector_key="b2b_saas". I'll pull the exact Sources & Uses / per-share figures from the proxy (targeted page reads).
Step 2.3 — Seed + run the EDGAR pipeline
scripts/seed_qualtrics_demo.py: build a KPIExtractionConfig with the real CIK, company_id="qualtrics", source_type="edgar", output paths keyed to qualtrics*\*; run the adapter → writes the same processed//features/ artifacts the dashboard reads.
Step 2.4 — Real VCP plan from the public thesis
Encode the market-sceptical revenue-growth targets as VCP milestones (baseline at IPO → target), so VCP drift compares real EDGAR revenue vs the underwritten growth path — the quantified "thesis miss."
Step 2.5 — Frontend "Real data / EDGAR" badge + citations
Add a data_source flag (edgar vs synthetic) to the company payload; render a badge in PortfolioOverview/CompanyDetail. Wire SEC filing URLs into the existing citations builder (report_routes.py:234).
Step 2.6 — Generalize (light)
Factor the seed script into an "add public→private company by CIK" helper so future take-privates need only a CIK + deal-metadata JSON, no code changes.
Suggested PR sequencing
PR 1 — Part 1 sector refactor (Steps 1.1–1.6). Unblocks everything, fixes the bug.
PR 2 — Qualtrics data pipeline (2.1–2.4).
PR 3 — Frontend badge + citations + generalization (2.5–2.6).
