"""
Deal-metadata store — the deal's founding economics, captured once at deal close.

Mirrors :class:`app.store.vcp_store.VCPStore`: a lightweight JSON-backed store for
the prototype (Postgres in production). One file per company under
``data/raw/deal_metadata/{company_id}.json``.

This holds the entry side of the IRR — entry equity (the fixed IRR denominator),
entry EV/leverage, holding period, and the IC-underwritten return targets. These
come from the IC memo's "Sources & Uses" / "Transaction Structure" table, NOT from
the VCP milestones (which are the value-creation *commitments* we monitor against).

Field names are aligned with what :func:`app.quant.irr_engine.build_irr_scenarios`
already consumes in ``pe_deal`` mode (``entry_equity_value``,
``entry_enterprise_value``, ``holding_period_years``, ``ic_target_irr``,
``ic_target_moic``) so the same metadata drives both engines.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

DEFAULT_DEAL_DIR = "data/raw/deal_metadata"


class DealMetadata(BaseModel):
    """Deal economics fixed at close — the entry side of every IRR calculation.

    All monetary fields are absolute currency units (e.g. 219000000.0 for
    $219mm), the same scale as KPI records and forecasts. Never millions.
    """

    company_id: str
    company_name: Optional[str] = None
    deal_close_date: str = Field(description="ISO date the deal closed.")

    # Sector is a first-class company attribute, decided once at ingestion and stored
    # with the company (see app.store.company_store). Kept here too so a deal file alone
    # is enough to benchmark a company that has no separate meta sidecar.
    sector_key: Optional[str] = Field(
        default=None,
        description="Resolved sector key (e.g. 'b2b_saas'); aligns with sector_benchmarks.json.",
    )

    # Entry economics (from the IC memo Sources & Uses / Transaction Structure table).
    entry_ebitda: float = Field(description="Entry annual EBITDA at close.")
    entry_ev_multiple: float = Field(description="Entry EV / EBITDA multiple, e.g. 12.0.")
    entry_enterprise_value: float = Field(description="Purchase enterprise value at close.")
    entry_net_debt: float = Field(description="Entry net debt (leverage drawn at close).")
    entry_equity_value: float = Field(
        description="Sponsor equity at close — the fixed IRR denominator."
    )

    # Hold + underwritten return targets (the IC-underwritten case).
    holding_period_years: float = 5.0
    fund_vintage: Optional[int] = None
    ic_target_irr: Optional[float] = Field(
        default=None, description="Underwritten gross IRR as a ratio, e.g. 0.25."
    )
    ic_target_moic: Optional[float] = Field(
        default=None, description="Underwritten money multiple, e.g. 2.5."
    )

    currency: str = "GBP"
    source_document: Optional[str] = None
    notes: Optional[str] = None
    sector_key: Optional[str] = Field(
        default=None,
        description="Sector benchmark key (data/reference/sector_benchmarks.json) set at deal entry.",
    )


class DealStore:
    """JSON-backed deal-metadata store, one file per company."""

    def __init__(self, base_dir: str = DEFAULT_DEAL_DIR):
        self.base_dir = Path(base_dir)

    def _path(self, company_id: str) -> Path:
        return self.base_dir / f"{company_id}.json"

    def exists(self, company_id: str) -> bool:
        return self._path(company_id).exists()

    def load(self, company_id: str) -> Optional[DealMetadata]:
        path = self._path(company_id)
        if not path.exists():
            return None
        return DealMetadata.model_validate_json(path.read_text(encoding="utf-8"))

    def save(self, deal: DealMetadata) -> str:
        self.base_dir.mkdir(parents=True, exist_ok=True)
        path = self._path(deal.company_id)
        path.write_text(deal.model_dump_json(indent=2), encoding="utf-8")
        return str(path)
