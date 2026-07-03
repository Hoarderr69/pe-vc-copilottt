"""
Shared sector resolver — the single source of truth for "what sector is this company?".

Sector is decided once, at ingestion, and stored *with the company* (see
:mod:`app.store.company_store`). This module holds only the resolution *logic*:
given whatever identifiers we have at ingest time, pick a sector key.

Resolution order (first hit wins):
  1. explicit    — the caller already knows the sector (e.g. deal metadata).
  2. SIC code    — EDGAR filers carry a SIC code; map it deterministically.
  3. keyword     — fall back to keywords in the company id / name.
  4. None        — unknown; the caller decides what "unknown" means.

The sector keys here line up with the ``"sectors"`` block in
``data/reference/sector_benchmarks.json``: ``b2b_saas``,
``industrial_manufacturing``, ``healthcare_services``.
"""

from __future__ import annotations

from typing import Optional, Tuple

# Sector keys — must match the "sectors" block in sector_benchmarks.json.
SECTOR_B2B_SAAS = "b2b_saas"
SECTOR_INDUSTRIAL = "industrial_manufacturing"
SECTOR_HEALTHCARE = "healthcare_services"

# SIC code → sector key, for EDGAR filers.
# SEC SIC reference: https://www.sec.gov/info/edgar/siccodes.htm
SIC_TO_SECTOR = {
    # Prepackaged software / computer programming & services → B2B SaaS
    "7370": SECTOR_B2B_SAAS,
    "7371": SECTOR_B2B_SAAS,
    "7372": SECTOR_B2B_SAAS,
    "7373": SECTOR_B2B_SAAS,
    "7374": SECTOR_B2B_SAAS,
    "7375": SECTOR_B2B_SAAS,
    "7379": SECTOR_B2B_SAAS,
    "7389": SECTOR_B2B_SAAS,
    # Industrial / manufacturing (industrial machinery, metals, electrical equipment)
    "3400": SECTOR_INDUSTRIAL,
    "3500": SECTOR_INDUSTRIAL,
    "3510": SECTOR_INDUSTRIAL,
    "3530": SECTOR_INDUSTRIAL,
    "3550": SECTOR_INDUSTRIAL,
    "3559": SECTOR_INDUSTRIAL,
    "3560": SECTOR_INDUSTRIAL,
    "3600": SECTOR_INDUSTRIAL,
    "3674": SECTOR_INDUSTRIAL,
    "3700": SECTOR_INDUSTRIAL,
    # Healthcare services (hospitals, medical labs, health services, pharma)
    "2834": SECTOR_HEALTHCARE,
    "2836": SECTOR_HEALTHCARE,
    "8000": SECTOR_HEALTHCARE,
    "8011": SECTOR_HEALTHCARE,
    "8050": SECTOR_HEALTHCARE,
    "8060": SECTOR_HEALTHCARE,
    "8062": SECTOR_HEALTHCARE,
    "8090": SECTOR_HEALTHCARE,
    "8093": SECTOR_HEALTHCARE,
}

# Keyword fallback, evaluated in order. Mirrors the original vcp_routes._infer_sector.
_KEYWORDS: Tuple[Tuple[str, Tuple[str, ...]], ...] = (
    (SECTOR_B2B_SAAS, ("saas", "software", "tech")),
    (SECTOR_INDUSTRIAL, ("industrial", "manufacturing", "factory")),
    (SECTOR_HEALTHCARE, ("health", "care", "medical", "pharma")),
)


def _normalize_sic(sic_code: Optional[object]) -> Optional[str]:
    """SIC codes arrive as ints or strings ('7372', 7372, '07372'). Normalize to a key."""
    if sic_code is None:
        return None
    s = str(sic_code).strip()
    if not s or not s.isdigit():
        return None
    # SEC SIC codes are 4 digits; preserve as-is once digit-only.
    return s


def infer_sector_key(
    company_id: str,
    company_name: Optional[str] = None,
    sic_code: Optional[object] = None,
    explicit: Optional[str] = None,
) -> Optional[str]:
    """Resolve a company's sector key. Returns ``None`` when nothing matches.

    Resolution order: ``explicit`` → SIC-code map → keyword fallback → ``None``.
    """
    if explicit:
        return explicit

    sic = _normalize_sic(sic_code)
    if sic and sic in SIC_TO_SECTOR:
        return SIC_TO_SECTOR[sic]

    text = f"{company_id or ''} {company_name or ''}".lower()
    for sector_key, keywords in _KEYWORDS:
        if any(k in text for k in keywords):
            return sector_key

    return None
