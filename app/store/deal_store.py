"""
Deal-metadata store — the deal's founding economics, captured once at deal close.

Mirrors :class:`app.store.vcp_store.VCPStore`: a lightweight JSON-backed store for
the prototype (Postgres in production). One file per company under
``data/raw/deal_metadata/{company_id}.json``.

This holds the entry side of the IRR — entry equity (the fixed IRR denominator),
entry EV/leverage, holding period, and the IC-underwritten return targets. These
come from the IC memo's "Sources & Uses" / "Transaction Structure" table, NOT from
the VCP milestones (which are the value-creation *commitments* we monitor against).

Field names are aligned with what :func:`app.quant.vcp_irr.build_vcp_irr`
already consumes (``entry_equity_value``, ``entry_enterprise_value``,
``holding_period_years``, ``ic_target_irr``, ``ic_target_moic``) so the same
metadata drives both engines.
"""

from __future__ import annotations

from pathlib import Path
from typing import Dict, Optional

from pydantic import BaseModel, Field

from app.store.postgres_json_store import PostgresJsonStore

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
    """Deal-metadata store, backed by Postgres (PostgresJsonStore), one document per company."""

    def __init__(self, base_dir: str = DEFAULT_DEAL_DIR):
        self.base_dir = Path(base_dir)
        self._store = PostgresJsonStore("deals")

    def exists(self, company_id: str) -> bool:
        return self._store.get(company_id) is not None

    def load(self, company_id: str) -> Optional[DealMetadata]:
        doc = self._store.get(company_id)
        if doc is None:
            return None
        return DealMetadata.model_validate(doc)

    def load_all(self) -> Dict[str, DealMetadata]:
        """Fetch every deal in one Postgres round trip, keyed by company_id.

        Callers that need one company at a time in a loop (e.g. the portfolio
        overview iterating every company) should use this instead of calling
        `load(cid)` per company — each `get()` is its own network round trip to
        Azure Postgres, so N calls costs N round trips instead of one.
        """
        return {
            doc["company_id"]: DealMetadata.model_validate(doc)
            for doc in self._store.list()
        }

    def save(self, deal: DealMetadata) -> str:
        self._store.put(deal.company_id, deal.model_dump(mode="json"))
        return f"postgres:deals/{deal.company_id}"
