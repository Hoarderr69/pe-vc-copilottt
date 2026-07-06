"""
Company-meta store — lightweight, per-company attributes decided at ingestion.

Where :mod:`app.store.deal_store` holds the *deal's* founding economics, this store
holds the *company's* identity attributes that the rest of the system resolves against
— most importantly the **sector key**, which is decided once at ingestion and must
survive a wipe of ``data/processed`` / ``data/features``.

One JSON sidecar per company under ``data/processed/{company_id}_company_meta.json``.
Companies that have a full :class:`~app.store.deal_store.DealMetadata` file can carry
``sector_key`` there too; this sidecar covers the (common) case of a company ingested
from a financials upload with no deal file.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from pydantic import BaseModel

from app.store.postgres_json_store import PostgresJsonStore

DEFAULT_PROCESSED_DIR = "data/processed"

_store = PostgresJsonStore("company_meta")


class CompanyMeta(BaseModel):
    """Per-company attributes resolved at ingestion."""

    company_id: str
    company_name: Optional[str] = None
    sector_key: Optional[str] = None
    source_type: Optional[str] = None
    cik: Optional[str] = None
    sic: Optional[str] = None


def _key(company_id: str, base_dir: str) -> str:
    """base_dir is folded into the Postgres key (not just company_id) so callers
    that pass an isolated base_dir — e.g. tests using tmp_path — don't collide
    with the shared production company_meta collection. Resolved to an absolute
    path first so "data/processed" (the default) and an equivalent absolute
    PROCESSED path (as vcp_routes.py passes) land on the same key."""
    return f"{Path(base_dir).resolve()}/{company_id}_company_meta.json"


def load_company_meta(
    company_id: str, base_dir: str = DEFAULT_PROCESSED_DIR
) -> Optional[CompanyMeta]:
    """Load a company's meta document, or ``None`` if it doesn't exist."""
    doc = _store.get(_key(company_id, base_dir))
    if doc is None:
        return None
    return CompanyMeta.model_validate(doc)


def save_company_meta(meta: CompanyMeta, base_dir: str = DEFAULT_PROCESSED_DIR) -> str:
    """Write (overwrite) a company's meta document. Returns its store key."""
    key = _key(meta.company_id, base_dir)
    _store.put(key, meta.model_dump(mode="json"))
    return key


def update_company_meta(
    company_id: str,
    base_dir: str = DEFAULT_PROCESSED_DIR,
    **fields: object,
) -> CompanyMeta:
    """Merge non-``None`` fields into a company's meta sidecar, creating it if absent.

    Existing values are preserved unless a non-``None`` replacement is supplied, so an
    IC-memo upload won't clobber a ``cik``/``sic`` learned from an earlier EDGAR ingest.
    """
    meta = load_company_meta(company_id, base_dir) or CompanyMeta(company_id=company_id)
    for key, value in fields.items():
        if value is not None and hasattr(meta, key):
            setattr(meta, key, value)
    save_company_meta(meta, base_dir)
    return meta
