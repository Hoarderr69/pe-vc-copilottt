"""
Deterministic currency + scale normalization for ingested financials.

Where this sits in the pipeline: every financial adapter extracts period rows in
*whatever* currency and unit scale the source document happens to use — a UK
management-accounts PDF in "£'000", a US data-room workbook in full USD, a European
board pack in EUR millions. Downstream nodes (forecasting, IRR, peer benchmarking)
assume one reporting currency at full absolute units. This module is the bridge: it
converts every period to a single base currency at full units and emits a
``NormalizationReport`` so the transformation is auditable (the product's "show your
work" rule).

Architectural rule preserved: this is an *analytical* (deterministic Python) step,
never an LLM call. The LLM's job is label/parse understanding; turning 12.3 (£'m)
into 12_300_000 and applying an FX rate is arithmetic and must be reproducible.

Two transforms, applied in order:
  1. Unit scaling  — "£'000" / "in millions" -> multiply monetary fields so the value
     is full absolute units. The LLM extraction path is *instructed* to already emit
     full units, so scaling there is a no-op (we only record the note); the offline
     markdown-table parser reads numbers as printed, so it needs the multiplier.
  2. FX conversion — convert monetary fields from the period's source currency into the
     base reporting currency using a static rate table (a clearly-marked stand-in for a
     live ECB/FRED feed in production). Ratios computed downstream (margins, leverage)
     are currency-invariant, but absolute comparisons, IRR and cross-portfolio roll-ups
     are not — so we normalize the absolutes.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Tuple

# Monetary KPIRecord fields that scaling and FX conversion apply to. Anything not in
# this set (dates, ratios, counts, confidences) is left untouched.
MONETARY_FIELDS = (
    "revenue",
    "gross_profit",
    "operating_income",
    "reported_ebitda",
    "adjusted_ebitda",
    "ebitda_proxy",
    "net_income",
    "capex",
    "working_capital",
    "cash",
    "debt",
    "net_debt",
    "interest_expense",
    "free_cash_flow",
)

DEFAULT_BASE_CURRENCY = "USD"

# Static FX pivot table: "value of 1 unit of currency in GBP". Conversion between any two
# currencies is a ratio (_PIVOT[src] / _PIVOT[base]), so the pivot unit is arbitrary and
# the table works for any base — the pipeline's base is USD (see DEFAULT_BASE_CURRENCY).
# This is a deliberate stand-in: in production it's a dated lookup against an ECB/FRED
# series, and the rate's date flows into the report instead of "static_table".
_PIVOT: Dict[str, float] = {
    "GBP": 1.0,
    "USD": 0.79,
    "EUR": 0.86,
    "CAD": 0.58,
    "AUD": 0.52,
    "CHF": 0.88,
    "JPY": 0.0052,
}

_CURRENCY_SYMBOLS = {"£": "GBP", "$": "USD", "€": "EUR", "¥": "JPY"}

# Scale cue -> multiplier. Ordered most-specific first so "£'000" wins over a bare
# "000". Matched case-insensitively. These are the *strict* patterns used when scanning
# raw document text, where a bare "millions" could be prose ("millions of customers").
_SCALE_PATTERNS: List[Tuple[str, float, str]] = [
    (r"in\s+billions|figures?\s+in\s+\w*\s*billions|[£$€]\s?'?bn\b|\(\s*billions?\s*\)", 1_000_000_000.0, "billions"),
    (r"in\s+millions|figures?\s+in\s+\w*\s*millions|[£$€]\s?'?m(?:n|m)?\b|[£$€]\s?millions|\(\s*millions?\s*\)", 1_000_000.0, "millions"),
    (r"in\s+thousands|figures?\s+in\s+\w*\s*thousands|[£$€]\s?'?000s?\b|'000\b|\(\s*thousands?\s*\)|[£$€]\s?000s\b", 1_000.0, "thousands"),
]

# Looser keyword patterns, applied ONLY to a short explicit units note (e.g. the LLM's
# "figures in GBP thousands"), where a bare scale word is unambiguously the scale.
_SCALE_KEYWORDS: List[Tuple[str, float, str]] = [
    (r"\bbillions?\b", 1_000_000_000.0, "billions"),
    (r"\bmillions?\b", 1_000_000.0, "millions"),
    (r"\bthousands?\b", 1_000.0, "thousands"),
]


@dataclass
class NormalizationReport:
    """Auditable record of the currency/scale transform applied to a source document."""

    base_currency: str
    source_currency: Optional[str]
    fx_rate_to_base: float
    fx_rate_source: str  # e.g. "static_table" | "ecb:2025-03-31"
    scale_multiplier: float
    scale_detected: Optional[str]  # "thousands" | "millions" | None
    scale_source: str  # "units_note" | "document_text" | "none" | "llm_full_units"
    periods_normalized: int
    monetary_fields_present: List[str] = field(default_factory=list)
    note: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def _norm_currency(value: Any) -> Optional[str]:
    """Coerce a currency hint (ISO code or symbol) to a known ISO code, or None."""
    if not value:
        return None
    s = str(value).strip().upper()
    if s in _PIVOT:
        return s
    # Symbol form, possibly embedded.
    for sym, code in _CURRENCY_SYMBOLS.items():
        if sym in str(value):
            return code
    # Common words.
    if "POUND" in s or "STERLING" in s:
        return "GBP"
    if "DOLLAR" in s:
        return "USD"
    if "EURO" in s:
        return "EUR"
    return None


def fx_rate_to_base(source_currency: Optional[str], base_currency: str) -> Tuple[float, str]:
    """Return (rate, source) to multiply a ``source_currency`` value into ``base_currency``.

    Unknown or missing currencies fall back to 1.0 (treated as already-in-base) rather
    than raising — ingestion should degrade gracefully and surface the assumption in the
    report instead of failing the whole upload.
    """
    base = (base_currency or DEFAULT_BASE_CURRENCY).upper()
    src = _norm_currency(source_currency)
    if src is None or base not in _PIVOT:
        return 1.0, "assumed_base (currency not recognised)"
    if src == base:
        return 1.0, "static_table"
    rate = _PIVOT[src] / _PIVOT[base]
    return rate, "static_table"


def detect_scale(units_note: Optional[str], document_text: Optional[str]) -> Tuple[float, Optional[str], str]:
    """Detect the unit scale of printed figures.

    Prefers an explicit ``units_note`` (e.g. the LLM's "figures in GBP thousands") over a
    scan of the raw document text. Returns (multiplier, label, source).
    """
    # A short explicit units note: a bare scale keyword is unambiguous here.
    if units_note:
        low = str(units_note).lower()
        for pattern, mult, label in _SCALE_KEYWORDS:
            if re.search(pattern, low):
                return mult, label, "units_note"

    # Raw document text: require the stricter contextual patterns.
    if document_text:
        low = str(document_text).lower()
        for pattern, mult, label in _SCALE_PATTERNS:
            if re.search(pattern, low):
                return mult, label, "document_text"
    return 1.0, None, "none"


def normalize_periods(
    rows: List[Dict[str, Any]],
    *,
    base_currency: str = DEFAULT_BASE_CURRENCY,
    document_currency: Optional[str] = None,
    units_note: Optional[str] = None,
    document_text: Optional[str] = None,
    figures_are_full_units: bool = False,
) -> Tuple[List[Dict[str, Any]], NormalizationReport]:
    """Normalize extracted period rows to ``base_currency`` at full absolute units.

    Args:
        rows: period dicts with monetary fields (mutated copies are returned, inputs
            are left untouched).
        base_currency: the single reporting currency the whole pipeline runs in.
        document_currency: document-level currency hint, used when a row omits its own.
        units_note: an explicit scale note (e.g. from the LLM extractor) — preferred
            over scanning ``document_text``.
        document_text: raw markdown of the source, scanned for a scale cue when no
            ``units_note`` is given (the offline-parser case).
        figures_are_full_units: True when the extractor already produced full absolute
            units (the LLM path). Scaling is then suppressed — only the note is recorded
            — so values are never multiplied twice.

    Returns:
        (normalized_rows, NormalizationReport). Each normalized row's ``currency`` is set
        to ``base_currency`` since its monetary values are now expressed in it.
    """
    base = (base_currency or DEFAULT_BASE_CURRENCY).upper()

    if figures_are_full_units:
        # LLM already scaled to absolute units; record the note but do not re-multiply.
        _, scale_label, _ = detect_scale(units_note, None)
        multiplier, scale_source = 1.0, "llm_full_units"
    else:
        multiplier, scale_label, scale_source = detect_scale(units_note, document_text)

    # Document-level FX (used for the report headline + any row lacking its own currency).
    doc_ccy = _norm_currency(document_currency)

    out: List[Dict[str, Any]] = []
    fields_present: set[str] = set()
    converted = 0
    seen_source_ccy: Optional[str] = doc_ccy

    for row in rows:
        r = dict(row)
        row_ccy = _norm_currency(r.get("currency")) or doc_ccy
        if row_ccy and seen_source_ccy is None:
            seen_source_ccy = row_ccy
        rate, _ = fx_rate_to_base(row_ccy, base)

        for f in MONETARY_FIELDS:
            v = r.get(f)
            if v is None:
                continue
            fields_present.add(f)
            r[f] = round(float(v) * multiplier * rate, 2)
        # Values now live in the base currency.
        r["currency"] = base
        if rate != 1.0 or multiplier != 1.0:
            converted += 1
        out.append(r)

    headline_rate, rate_source = fx_rate_to_base(seen_source_ccy, base)
    report = NormalizationReport(
        base_currency=base,
        source_currency=seen_source_ccy,
        fx_rate_to_base=round(headline_rate, 6),
        fx_rate_source=rate_source if seen_source_ccy else "none",
        scale_multiplier=multiplier,
        scale_detected=scale_label,
        scale_source=scale_source,
        periods_normalized=len(out),
        monetary_fields_present=sorted(fields_present),
        note=_build_note(base, seen_source_ccy, headline_rate, multiplier, scale_label, figures_are_full_units),
    )
    return out, report


def _build_note(
    base: str,
    src: Optional[str],
    rate: float,
    multiplier: float,
    scale_label: Optional[str],
    full_units: bool,
) -> str:
    parts: List[str] = []
    if scale_label and not full_units:
        parts.append(f"scaled from {scale_label} (×{multiplier:,.0f})")
    elif full_units and scale_label:
        parts.append(f"extractor reported {scale_label}; emitted as full units")
    if src and src != base and rate != 1.0:
        parts.append(f"converted {src}→{base} @ {rate:.4f}")
    elif src and src == base:
        parts.append(f"already in {base}")
    elif not src:
        parts.append(f"no currency detected; assumed {base}")
    return "; ".join(parts) if parts else f"no transform needed (already {base}, full units)"
