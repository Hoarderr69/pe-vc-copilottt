"""
PDF / document financials adapter.

Turns an unstructured data-room financial document (QPR PDF, board-pack PDF, a
monthly management-accounts PDF, or any DOCX/HTML financial statement) into the
same normalized ``KPIRecord`` + ``EvidenceRef`` + ``SourceQualityReport`` triple
every other adapter produces. This is the missing bridge between the data-room
ingestion stack and the deterministic monitoring core.

Reuses the *exact* VCP ingestion stack:
  - ``document_loader.load_document_text`` -> PyMuPDF4LLM fast path for native-text
    PDFs (text + native tables to markdown, milliseconds, fully local), with a
    per-page Docling OCR + TableFormer fallback for scanned / image-only pages.

Two extraction modes over that markdown (same pattern as the VCP Extraction Agent):
  - "azure_openai": GPT structured-output call maps the document's financial tables
    onto the canonical KPI fields. This is where language understanding earns its
    place -- real statements label the same line item a dozen ways ("Revenue" /
    "Total turnover" / "Net sales"; "Adj. EBITDA" / "Normalised EBITDA") and lay
    periods out in either orientation. Rules break on that; the LLM does not.
  - "offline_heuristic": a deterministic markdown pipe-table parser with a metric
    alias map, so the pipeline runs without credentials and handles clean tables.

Architectural rule preserved: the LLM is used only for *parsing / label
understanding* (a language task). Every financial figure flows into KPIRecord and
all downstream math (margins, drift, IRR) stays deterministic Python.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from app.adapters.base import BaseKPIAdapter
from app.ingestion.document_loader import load_document_text
from app.ingestion.financial_normalization import normalize_periods
from app.llm import azure_openai
from app.schemas.kpi_schema import (
    EvidenceRef,
    KPIExtractionConfig,
    KPIRecord,
    SourceQualityReport,
    clean_value,
)

# Canonical KPIRecord financial fields this adapter populates (period_end +
# currency are handled separately). Order matters for the model feature matrix.
FINANCIAL_FIELDS = [
    "revenue",
    "gross_profit",
    "operating_income",
    "reported_ebitda",
    "adjusted_ebitda",
    "net_income",
    "capex",
    "working_capital",
    "cash",
    "debt",
    "net_debt",
    "interest_expense",
    "free_cash_flow",
]

# Line-item label synonyms -> canonical field. Keys are normalized (lowercased,
# alphanumeric only) so "Adj. EBITDA", "adjusted_ebitda" and "AdjustedEBITDA" all
# collapse to the same lookup. Used by the offline parser; the LLM does this in prose.
_METRIC_ALIASES: Dict[str, str] = {
    # revenue
    "revenue": "revenue",
    "revenues": "revenue",
    "totalrevenue": "revenue",
    "netrevenue": "revenue",
    "turnover": "revenue",
    "totalturnover": "revenue",
    "netsales": "revenue",
    "sales": "revenue",
    "totalsales": "revenue",
    # gross profit
    "grossprofit": "gross_profit",
    "gp": "gross_profit",
    # operating income / EBIT
    "operatingincome": "operating_income",
    "operatingprofit": "operating_income",
    "operatingresult": "operating_income",
    "ebit": "operating_income",
    # EBITDA
    "ebitda": "reported_ebitda",
    "reportedebitda": "reported_ebitda",
    "adjustedebitda": "adjusted_ebitda",
    "adjebitda": "adjusted_ebitda",
    "normalisedebitda": "adjusted_ebitda",
    "normalizedebitda": "adjusted_ebitda",
    "underlyingebitda": "adjusted_ebitda",
    # net income
    "netincome": "net_income",
    "netprofit": "net_income",
    "netearnings": "net_income",
    "profitfortheperiod": "net_income",
    "profitfortheyear": "net_income",
    # capex
    "capex": "capex",
    "capitalexpenditure": "capex",
    "capitalexpenditures": "capex",
    # working capital
    "workingcapital": "working_capital",
    "networkingcapital": "working_capital",
    "nwc": "working_capital",
    # cash
    "cash": "cash",
    "cashequivalents": "cash",
    "cashandequivalents": "cash",
    "cashandcashequivalents": "cash",
    "cashatbank": "cash",
    # debt
    "debt": "debt",
    "totaldebt": "debt",
    "grossdebt": "debt",
    "netdebt": "net_debt",
    # interest
    "interestexpense": "interest_expense",
    "interest": "interest_expense",
    "financecosts": "interest_expense",
    "financeexpense": "interest_expense",
    # free cash flow
    "freecashflow": "free_cash_flow",
    "fcf": "free_cash_flow",
}

# Header labels that denote the period/date column in a period-per-row table.
_PERIOD_HEADER_ALIASES = {"periodend", "period", "date", "month", "monthend", "quarter", "asat", "asof"}


def _norm(text: Any) -> str:
    """Lowercase + strip to alphanumerics, for robust label matching."""
    return re.sub(r"[^a-z0-9]", "", str(text).lower())


# ---------------------------------------------------------------------------
# LLM structured-output schema (Azure OpenAI) -- mirrors the VCP agent pattern
# ---------------------------------------------------------------------------

class ExtractedFinancialPeriod(BaseModel):
    """Financials for a single reporting period, normalized to full absolute units."""

    period_end: str = Field(description="Period end as ISO date YYYY-MM-DD (end of the month/quarter/year).")
    period_type: str = Field(default="month", description="One of: month, quarter, year.")
    currency: Optional[str] = Field(default=None, description="ISO currency code, e.g. GBP, USD, EUR.")
    revenue: Optional[float] = None
    gross_profit: Optional[float] = None
    operating_income: Optional[float] = None
    reported_ebitda: Optional[float] = None
    adjusted_ebitda: Optional[float] = None
    net_income: Optional[float] = None
    capex: Optional[float] = None
    working_capital: Optional[float] = None
    cash: Optional[float] = None
    debt: Optional[float] = None
    net_debt: Optional[float] = None
    interest_expense: Optional[float] = None
    free_cash_flow: Optional[float] = None
    confidence: float = Field(default=0.85, description="0..1 confidence this period was read correctly.")


class FinancialExtraction(BaseModel):
    currency: Optional[str] = Field(default=None, description="Dominant currency of the statements.")
    units_note: Optional[str] = Field(default=None, description="Any scale note, e.g. 'figures in GBP thousands'.")
    periods: List[ExtractedFinancialPeriod]


_SYSTEM_PROMPT = """You are a private-equity financial analyst. You read portfolio-company \
financial documents (monthly management accounts, quarterly performance reports, board packs) \
and extract the financial line items for every reporting period into a structured table.

Rules:
- Produce one entry per reporting period (month, quarter, or year) shown in the document.
- Map each line item onto the canonical fields, recognising synonyms: revenue (turnover, \
net sales), gross_profit, operating_income (operating profit, EBIT), reported_ebitda (EBITDA), \
adjusted_ebitda (adj./normalised/underlying EBITDA), net_income (net profit), capex, \
working_capital (net working capital), cash, debt (total/gross debt), net_debt, \
interest_expense (finance costs), free_cash_flow.
- Set a field to null if it is not present for that period. Do NOT guess or derive values that \
are not stated (downstream math will derive margins and ratios deterministically).
- Normalize every figure to its FULL absolute value in the stated currency. If the statement \
says "in thousands"/"£'000" or "in millions", multiply accordingly so 1,234 (£'000) -> 1234000. \
Record the scale you applied in units_note.
- Parentheses or a leading minus mean a negative number.
- period_end must be the ISO date of the END of the period (e.g. "March 2025" -> 2025-03-31, \
"Q3 2025" calendar -> 2025-09-30).
- Detect the currency (ISO code).

Return every period you can read, with an honest per-period confidence."""


def _build_user_prompt(doc_text: str, company_name: str) -> str:
    return (
        f"Company: {company_name}\n\n"
        f"FINANCIAL DOCUMENT (markdown):\n\"\"\"\n{doc_text}\n\"\"\"\n\n"
        "Extract the financial line items for every reporting period as a structured table."
    )


def _extract_llm(
    doc_text: str, company_name: str
) -> Tuple[List[Dict[str, Any]], str, Optional[str], Optional[str], Optional[str]]:
    """Live Azure OpenAI structured extraction. Returns (rows, mode, model, currency, units_note)."""
    client = azure_openai.get_client()
    model = azure_openai.deployment_name()

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": _build_user_prompt(doc_text, company_name)},
    ]

    parse_fn = getattr(client.chat.completions, "parse", None) or client.beta.chat.completions.parse
    completion = parse_fn(model=model, messages=messages, response_format=FinancialExtraction, temperature=0)
    parsed: Optional[FinancialExtraction] = completion.choices[0].message.parsed

    rows: List[Dict[str, Any]] = []
    if parsed:
        for p in parsed.periods:
            row = p.model_dump()
            if not row.get("currency"):
                row["currency"] = parsed.currency
            rows.append(row)
    return rows, "azure_openai", model, (parsed.currency if parsed else None), (parsed.units_note if parsed else None)


# ---------------------------------------------------------------------------
# Offline deterministic markdown-table parser (no credentials needed)
# ---------------------------------------------------------------------------

def _parse_number(cell: str) -> Optional[float]:
    s = str(cell).strip()
    if not s or s.lower() in {"n/a", "na", "-", "--", "nil", "none"}:
        return None
    neg = s.startswith("(") and s.endswith(")")
    s = s.strip("()")
    s = re.sub(r"[£$€,%\s]", "", s)
    if not re.search(r"\d", s):
        return None
    try:
        val = float(s)
    except ValueError:
        return None
    return -val if neg else val


def _parse_period(cell: str) -> Optional[str]:
    """Parse a header/value into an ISO period-end date, or None."""
    import pandas as pd

    s = str(cell).strip()
    if not s:
        return None

    # Q3 2025 / Q3-25 -> end of that calendar quarter.
    qm = re.search(r"q([1-4])[\s\-/]*'?(\d{2,4})", s, re.I)
    if qm:
        q = int(qm.group(1))
        yr = int(qm.group(2))
        yr += 2000 if yr < 100 else 0
        end_month = q * 3
        return str(pd.Timestamp(year=yr, month=end_month, day=1) + pd.offsets.MonthEnd(0))[:10]

    # FY2024 / FY24 -> calendar year end.
    fy = re.search(r"fy[\s\-]?'?(\d{2,4})", s, re.I)
    if fy:
        yr = int(fy.group(1))
        yr += 2000 if yr < 100 else 0
        return f"{yr}-12-31"

    ts = pd.to_datetime(s, errors="coerce", dayfirst=False)
    if pd.isna(ts):
        ts = pd.to_datetime(s, errors="coerce", dayfirst=True)
    if pd.isna(ts):
        return None
    # Snap to month end so monthly statements line up with the rest of the pipeline.
    return str(ts + pd.offsets.MonthEnd(0))[:10] if ts.day == 1 else str(ts.date())


def _markdown_grids(md: str) -> List[List[List[str]]]:
    """Extract GitHub-style pipe tables from markdown as grids of string cells."""
    grids: List[List[List[str]]] = []
    current: List[List[str]] = []
    for line in md.splitlines():
        if line.strip().startswith("|") and line.count("|") >= 2:
            cells = [c.strip() for c in line.strip().strip("|").split("|")]
            # Skip markdown separator rows (|---|:--:|).
            if all(re.fullmatch(r":?-{2,}:?", c) or c == "" for c in cells):
                continue
            current.append(cells)
        else:
            if len(current) >= 2:
                grids.append(current)
            current = []
    if len(current) >= 2:
        grids.append(current)
    return grids


def _grid_to_rows(grid: List[List[str]]) -> List[Dict[str, Any]]:
    """Interpret one table grid into period rows, trying both orientations."""
    header = grid[0]
    body = grid[1:]

    # Orientation A: periods across the header (metric per row). Detected when most
    # header cells (after the first) parse as dates.
    date_headers = [(_parse_period(h) is not None) for h in header[1:]]
    if header[1:] and sum(date_headers) >= max(1, len(date_headers) // 2):
        periods_by_col: Dict[int, Dict[str, Any]] = {}
        for col_idx, h in enumerate(header[1:], start=1):
            pe = _parse_period(h)
            if pe:
                periods_by_col[col_idx] = {"period_end": pe}
        for row in body:
            if not row:
                continue
            field = _METRIC_ALIASES.get(_norm(row[0]))
            if not field:
                continue
            for col_idx, rec in periods_by_col.items():
                if col_idx < len(row):
                    val = _parse_number(row[col_idx])
                    if val is not None:
                        rec[field] = val
        return [r for r in periods_by_col.values() if len(r) > 1]

    # Orientation B: one period per row (metric per column, like a CSV).
    col_field: Dict[int, str] = {}
    period_col: Optional[int] = None
    for idx, h in enumerate(header):
        nh = _norm(h)
        if period_col is None and nh in _PERIOD_HEADER_ALIASES:
            period_col = idx
            continue
        if nh in _METRIC_ALIASES:
            col_field[idx] = _METRIC_ALIASES[nh]

    rows: List[Dict[str, Any]] = []
    for row in body:
        if not row:
            continue
        pe = None
        if period_col is not None and period_col < len(row):
            pe = _parse_period(row[period_col])
        if pe is None:  # fall back to first column that looks like a date
            for idx, cell in enumerate(row):
                if idx not in col_field:
                    pe = _parse_period(cell)
                    if pe:
                        break
        if pe is None:
            continue
        rec: Dict[str, Any] = {"period_end": pe}
        for idx, field in col_field.items():
            if idx < len(row):
                val = _parse_number(row[idx])
                if val is not None:
                    rec[field] = val
        if len(rec) > 1:
            rows.append(rec)
    return rows


def _detect_currency(md: str) -> Optional[str]:
    for code in ("GBP", "USD", "EUR"):
        if re.search(rf"\b{code}\b", md):
            return code
    if "£" in md:
        return "GBP"
    if "€" in md:
        return "EUR"
    if "$" in md:
        return "USD"
    return None


def _extract_offline(
    doc_text: str,
) -> Tuple[List[Dict[str, Any]], str, Optional[str], Optional[str], Optional[str]]:
    rows: List[Dict[str, Any]] = []
    for grid in _markdown_grids(doc_text):
        rows.extend(_grid_to_rows(grid))

    # Merge rows that share a period_end (e.g. P&L table + balance-sheet table).
    merged: Dict[str, Dict[str, Any]] = {}
    for r in rows:
        pe = r["period_end"]
        merged.setdefault(pe, {"period_end": pe}).update({k: v for k, v in r.items() if k != "period_end"})

    out = sorted(merged.values(), key=lambda r: r["period_end"])
    return out, "offline_heuristic", None, _detect_currency(doc_text), None


# ---------------------------------------------------------------------------
# Adapter
# ---------------------------------------------------------------------------

class PdfFinancialAdapter(BaseKPIAdapter):
    """Normalizes a PDF/DOCX/HTML financial document into KPIRecord + EvidenceRef."""

    source_type = "pdf_financials"

    required_columns = ["period_end", "revenue"]

    # Class-level switch so callers/tests can force the offline path.
    prefer_llm = True

    def __init__(self, source_type: Optional[str] = None):
        if source_type:
            self.source_type = source_type

    def extract(self, config: KPIExtractionConfig) -> Dict[str, Any]:
        if not config.source_path:
            raise ValueError("PdfFinancialAdapter requires config.source_path (the document to ingest).")

        loaded = load_document_text(config.source_path)

        if self.prefer_llm and azure_openai.is_configured():
            rows, mode, model, doc_currency, units_note = _extract_llm(loaded.text, config.company_name)
            llm_full_units = True  # the LLM prompt mandates full absolute units
        else:
            rows, mode, model, doc_currency, units_note = _extract_offline(loaded.text)
            llm_full_units = False  # offline parser reads numbers as printed

        # Deterministic currency + scale normalization: convert every period to the
        # pipeline's base currency at full absolute units. Runs before _postprocess so
        # the derived proxies (ebitda_proxy, operating_income) inherit normalized values.
        base_currency = getattr(config, "base_currency", None) or "USD"
        rows, norm_report = normalize_periods(
            rows,
            base_currency=base_currency,
            document_currency=doc_currency,
            units_note=units_note,
            document_text=loaded.text,
            figures_are_full_units=llm_full_units,
        )

        rows = self._postprocess(rows)

        currency = base_currency
        path = Path(config.source_path)
        extraction_method = f"pdf_financial_adapter_{mode}"

        kpi_records: List[Dict[str, Any]] = []
        evidence_refs: List[Dict[str, Any]] = []

        for row in rows:
            period_end = row.get("period_end")
            record_evidence: List[Dict[str, Any]] = []

            for field in FINANCIAL_FIELDS + ["ebitda_proxy"]:
                value = row.get(field)
                if value is None:
                    continue
                evidence = EvidenceRef(
                    metric=field,
                    value=value,
                    source_type=self.source_type,
                    source_document=path.name,
                    source_path=config.source_path,
                    source_page_or_sheet=loaded.loader,
                    source_section=f"{field} @ {period_end}",
                    period_end=period_end,
                    confidence=float(row.get("confidence", 0.85) or 0.85),
                    extraction_method=extraction_method,
                ).to_dict()
                evidence_refs.append(evidence)
                record_evidence.append(evidence)

            record = KPIRecord(
                company_id=config.company_id,
                company_name=config.company_name,
                ticker=config.ticker,
                cik=config.cik,
                source_type=self.source_type,
                source_path=config.source_path,
                period_end=period_end,
                period_type=row.get("period_type") or "month",
                currency=row.get("currency") or currency,
                revenue=row.get("revenue"),
                gross_profit=row.get("gross_profit"),
                operating_income=row.get("operating_income"),
                reported_ebitda=row.get("reported_ebitda"),
                adjusted_ebitda=row.get("adjusted_ebitda"),
                ebitda_proxy=row.get("ebitda_proxy"),
                net_income=row.get("net_income"),
                capex=row.get("capex"),
                working_capital=row.get("working_capital"),
                cash=row.get("cash"),
                debt=row.get("debt"),
                net_debt=row.get("net_debt"),
                interest_expense=row.get("interest_expense"),
                free_cash_flow=row.get("free_cash_flow"),
                source_confidence=float(row.get("confidence", 0.85) or 0.85),
                evidence_refs=record_evidence,
            ).to_dict()
            kpi_records.append(record)

        self._write_feature_matrices(config, rows)
        quality_report = self._quality_report(
            config, rows, kpi_records, mode, model, units_note, loaded.loader, norm_report
        )

        return {
            "raw_rows": len(rows),
            "model_rows": len(rows),
            "kpi_records": kpi_records,
            "evidence_refs": evidence_refs,
            "source_quality_report": quality_report,
        }

    @staticmethod
    def _postprocess(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Derive the proxy fields downstream nodes rely on, mirroring the CSV adapter."""
        out: List[Dict[str, Any]] = []
        for row in rows:
            r = dict(row)
            ebitda = r.get("adjusted_ebitda")
            if ebitda is None:
                ebitda = r.get("reported_ebitda")
            if ebitda is not None:
                r.setdefault("ebitda_proxy", ebitda)
                if r.get("adjusted_ebitda") is None:
                    r["adjusted_ebitda"] = ebitda
                if r.get("operating_income") is None:
                    r["operating_income"] = ebitda
            if r.get("period_end"):
                out.append(r)
        return sorted(out, key=lambda r: r["period_end"])

    @staticmethod
    def _write_feature_matrices(config: KPIExtractionConfig, rows: List[Dict[str, Any]]) -> None:
        import pandas as pd

        Path(config.raw_feature_matrix_path).parent.mkdir(parents=True, exist_ok=True)
        Path(config.model_feature_matrix_path).parent.mkdir(parents=True, exist_ok=True)

        df = pd.DataFrame(rows)
        df.to_csv(config.raw_feature_matrix_path, index=False)

        model_cols = ["period_end", "revenue", "gross_profit", "operating_income",
                      "adjusted_ebitda", "ebitda_proxy", "working_capital", "cash",
                      "net_debt", "free_cash_flow"]
        model_cols = [c for c in model_cols if c in df.columns]
        (df[model_cols] if model_cols else df).to_csv(config.model_feature_matrix_path, index=False)

    def _quality_report(self, config, rows, kpi_records, mode, model, units_note, loader, norm_report=None) -> Dict[str, Any]:
        present_fields = {k for r in rows for k, v in r.items() if v is not None}
        missing_required = [c for c in self.required_columns if c not in present_fields]
        required_present = len(missing_required) == 0 and len(rows) > 0

        null_counts = {
            field: sum(1 for r in rows if r.get(field) is None)
            for field in FINANCIAL_FIELDS
        }

        report = SourceQualityReport(
            source_type=self.source_type,
            source_path=config.source_path,
            record_count=len(kpi_records),
            required_fields_present=required_present,
            missing_required_fields=missing_required,
            null_counts=null_counts,
            status="pass" if required_present else "review",
        ).to_dict()
        report["extraction_mode"] = mode
        report["model"] = model
        report["document_loader"] = loader
        report["units_note"] = units_note
        if norm_report is not None:
            report["currency_normalization"] = norm_report.to_dict()
            report["currency"] = norm_report.base_currency
        return report
