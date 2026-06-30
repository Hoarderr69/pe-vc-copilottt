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

DEFAULT_PROCESSED_DIR = "data/processed"


class CompanyMeta(BaseModel):
    """Per-company attributes resolved at ingestion."""

    company_id: str
    company_name: Optional[str] = None
    sector_key: Optional[str] = None
    source_type: Optional[str] = None
    cik: Optional[str] = None
    sic: Optional[str] = None


def _meta_path(company_id: str, base_dir: str = DEFAULT_PROCESSED_DIR) -> Path:
    return Path(base_dir) / f"{company_id}_company_meta.json"


def load_company_meta(
    company_id: str, base_dir: str = DEFAULT_PROCESSED_DIR
) -> Optional[CompanyMeta]:
    """Load a company's meta sidecar, or ``None`` if it doesn't exist."""
    path = _meta_path(company_id, base_dir)
    if not path.exists():
        return None
    return CompanyMeta.model_validate_json(path.read_text(encoding="utf-8"))


def save_company_meta(meta: CompanyMeta, base_dir: str = DEFAULT_PROCESSED_DIR) -> str:
    """Write (overwrite) a company's meta sidecar. Returns the path written."""
    path = _meta_path(meta.company_id, base_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(meta.model_dump_json(indent=2), encoding="utf-8")
    return str(path)


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
