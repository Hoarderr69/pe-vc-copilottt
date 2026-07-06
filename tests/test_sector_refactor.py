"""
Regression tests for the Part 1 sector refactor.

The bug being pinned: a freshly ingested company with no entry in the legacy
``company_sector_map`` got ``peer_benchmark=None`` silently. After the refactor the
sector is inferred at ingestion, stored *with the company*, and benchmarking returns
evaluable results — and when a sector genuinely can't be resolved it degrades to a
Not-Evaluable payload instead of raising.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from app.analytics.peer_benchmarking import run_peer_benchmark_for_company  # noqa: E402
from app.analytics.sector import SIC_TO_SECTOR, infer_sector_key  # noqa: E402
from app.store.company_store import (  # noqa: E402
    load_company_meta,
    update_company_meta,
)
from app.store.kpi_records_store import save_kpi_records  # noqa: E402


# ── Fixtures / builders ──────────────────────────────────────────────────────

def _write_benchmarks(path: Path) -> None:
    """A minimal reference file with NO company_sector_map (the post-refactor shape)."""
    path.write_text(
        json.dumps(
            {
                "_metric_direction": {
                    "revenue_growth_yoy": "higher_is_better",
                    "ebitda_margin": "higher_is_better",
                    "gross_margin": "higher_is_better",
                    "net_debt_to_ebitda": "lower_is_better",
                },
                "sectors": {
                    "b2b_saas": {
                        "label": "B2B SaaS",
                        "peer_set_size": 25,
                        "medians": {
                            "revenue_growth_yoy": 0.20,
                            "ebitda_margin": 0.15,
                            "gross_margin": 0.70,
                            "net_debt_to_ebitda": 3.0,
                        },
                    }
                },
            }
        ),
        encoding="utf-8",
    )


def _write_kpi_records(path: Path, company_id: str, company_name: str) -> None:
    """14 monthly records so YoY growth (needs >=13) and all margins are evaluable.

    KPI records are Postgres-backed (app.store.kpi_records_store); ``path`` is
    just the identity key run_peer_benchmark_for_company reads back through,
    not a file on disk.
    """
    records = []
    for i in range(14):
        revenue = 1000.0 * (1.0 + 0.02 * i)  # grows ~ month over month
        records.append(
            {
                "company_id": company_id,
                "company_name": company_name,
                "period_end": f"2024-{i % 12 + 1:02d}-28" if i < 12 else f"2025-{i - 12 + 1:02d}-28",
                "currency": "USD",
                "revenue": revenue,
                "adjusted_ebitda": revenue * 0.18,
                "gross_profit": revenue * 0.75,
                "net_debt": revenue * 5.0,
            }
        )
    save_kpi_records(str(path), records)


# ── Step 1.1: resolver ───────────────────────────────────────────────────────

def test_infer_sector_keyword_fallback():
    assert infer_sector_key("acme_saas", "Acme SaaS Co") == "b2b_saas"
    assert infer_sector_key("forge_co", "Forge Manufacturing") == "industrial_manufacturing"
    assert infer_sector_key("clinic_co", "City Healthcare") == "healthcare_services"
    assert infer_sector_key("mystery", "Mystery Holdings") is None


def test_infer_sector_explicit_and_sic_precedence():
    # explicit wins over everything
    assert infer_sector_key("acme_saas", "Acme SaaS", explicit="healthcare_services") == "healthcare_services"
    # SIC beats keyword (name says nothing, SIC says SaaS)
    sic = next(iter(SIC_TO_SECTOR))
    assert infer_sector_key("co", "Generic Holdings", sic_code=sic) == SIC_TO_SECTOR[sic]
    # SIC tolerates ints
    assert infer_sector_key("co", "Generic Holdings", sic_code=int(sic)) == SIC_TO_SECTOR[sic]


# ── Step 1.2/1.3: sector persisted on the company at ingestion ───────────────

def test_company_meta_roundtrip(tmp_path):
    base = str(tmp_path)
    update_company_meta(
        "acme_saas", base_dir=base, company_name="Acme SaaS",
        sector_key=infer_sector_key("acme_saas", "Acme SaaS"), source_type="pdf_financials",
    )
    meta = load_company_meta("acme_saas", base_dir=base)
    assert meta is not None
    assert meta.sector_key == "b2b_saas"
    assert meta.source_type == "pdf_financials"

    # A later update must not clobber fields it doesn't supply.
    update_company_meta("acme_saas", base_dir=base, cik="0001234567")
    meta2 = load_company_meta("acme_saas", base_dir=base)
    assert meta2.sector_key == "b2b_saas"
    assert meta2.cik == "0001234567"


# ── Step 1.4: the core regression ────────────────────────────────────────────

def test_fresh_company_benchmarks_evaluably(tmp_path, monkeypatch):
    """A brand-new company (no legacy map entry) resolves its sector and benchmarks."""
    company_id = "newco_saas"
    company_name = "NewCo SaaS Inc"

    benchmarks = tmp_path / "sector_benchmarks.json"
    _write_benchmarks(benchmarks)

    # Simulate ingestion: chdir so the default 'data/processed' meta dir lives in tmp.
    monkeypatch.chdir(tmp_path)
    processed = tmp_path / "data" / "processed"
    processed.mkdir(parents=True)
    kpi_path = processed / f"{company_id}_kpi_records.json"
    _write_kpi_records(kpi_path, company_id, company_name)

    # No prior map entry anywhere; ingestion stores the inferred sector on the company.
    update_company_meta(
        company_id, company_name=company_name,
        sector_key=infer_sector_key(company_id, company_name),
    )

    # Benchmark WITHOUT passing sector_key — it must be resolved from company meta.
    payload = run_peer_benchmark_for_company(
        company_id=company_id,
        kpi_records_path=str(kpi_path),
        benchmarks_path=str(benchmarks),
    )

    assert payload["sector_key"] == "b2b_saas"
    evaluable = [r for r in payload["results"] if r["status"] != "Not Evaluable"]
    assert evaluable, "expected at least one evaluable metric"
    assert payload["composite_outperformance"] is not None


def test_unknown_sector_degrades_without_raising(tmp_path):
    """No resolvable sector → Not-Evaluable payload with a reason, never an exception."""
    company_id = "mystery_holdings"
    benchmarks = tmp_path / "sector_benchmarks.json"
    _write_benchmarks(benchmarks)
    kpi_path = tmp_path / f"{company_id}_kpi_records.json"
    _write_kpi_records(kpi_path, company_id, "Mystery Holdings")

    payload = run_peer_benchmark_for_company(
        company_id=company_id,
        kpi_records_path=str(kpi_path),
        benchmarks_path=str(benchmarks),
    )

    assert payload["sector_key"] is None
    assert payload["composite_outperformance"] is None
    assert payload.get("reason")
    assert all(r["status"] == "Not Evaluable" for r in payload["results"])


def test_explicit_sector_key_overrides_resolution(tmp_path):
    benchmarks = tmp_path / "sector_benchmarks.json"
    _write_benchmarks(benchmarks)
    kpi_path = tmp_path / "co_kpi_records.json"
    _write_kpi_records(kpi_path, "co", "Generic Co")

    payload = run_peer_benchmark_for_company(
        company_id="co",
        kpi_records_path=str(kpi_path),
        benchmarks_path=str(benchmarks),
        sector_key="b2b_saas",
    )
    assert payload["sector_key"] == "b2b_saas"
    assert payload["sector_label"] == "B2B SaaS"
