"""
Financial / data-room ingestion API — Path 2 (recurring per-period data).

This is the upload counterpart to the VCP Setup flow. Where ``/api/vcp/extract-upload``
takes the IC memo and produces *milestones* (the plan), this route takes a portfolio
company's actual financial documents — a management-accounts PDF, a QPR board pack, an
Excel/CSV export from the data room — and produces the normalized ``KPIRecord`` time
series the monitoring core runs on.

Design notes mirroring the rest of the system:
  - Source-agnostic: the route just dispatches on file type to the right adapter
    (PDF/DOCX/HTML -> PdfFinancialAdapter; CSV/XLSX -> PrivatePortcoFinancialAdapter).
    Every adapter emits the same KPIRecord + EvidenceRef + SourceQualityReport triple.
  - Currency + scale are normalized deterministically inside the adapter to one base
    reporting currency at full absolute units (see financial_normalization). The route
    surfaces that report so the transform is visible (the "show your work" rule).
  - Output lands in the same processed/features artifacts the dashboard reads, keyed by
    company_id — re-ingesting a company refreshes its KPI series.
"""

from __future__ import annotations

import re
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from app.agents.kpi_extraction_agent import run_kpi_extraction_agent
from app.analytics.sector import infer_sector_key
from app.llm import azure_openai
from app.schemas.kpi_schema import KPIExtractionConfig
from app.store.company_store import update_company_meta

PROJECT_ROOT = Path(__file__).resolve().parents[2]
PROCESSED = PROJECT_ROOT / "data" / "processed"
FEATURES = PROJECT_ROOT / "data" / "features"

router = APIRouter(prefix="/api/ingest", tags=["ingest"])

# File type -> the source_type the adapter registry routes on.
_TABULAR_SUFFIXES = {".csv": "private_portco_csv", ".xlsx": "private_portco_excel", ".xls": "private_portco_excel"}
_DOCUMENT_SUFFIXES = {".pdf", ".docx", ".pptx", ".html", ".xhtml", ".md", ".markdown", ".txt"}

_SUPPORTED = set(_TABULAR_SUFFIXES) | _DOCUMENT_SUFFIXES

# Data-room financials can be larger than IC memos (full workbooks, multi-year packs).
_MAX_UPLOAD_BYTES = 40 * 1024 * 1024


def _slugify_company(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", name.strip().lower()).strip("_")
    return slug or "uploaded_company"


def _source_type_for(suffix: str) -> str:
    if suffix in _TABULAR_SUFFIXES:
        return _TABULAR_SUFFIXES[suffix]
    return "pdf_financials"


def _period_preview(records: List[Dict[str, Any]], limit: int = 12) -> List[Dict[str, Any]]:
    """A compact, dashboard-friendly view of the normalized periods."""
    out: List[Dict[str, Any]] = []
    for r in records[-limit:]:
        rev = r.get("revenue")
        ebitda = r.get("adjusted_ebitda") or r.get("ebitda_proxy")
        out.append(
            {
                "period_end": r.get("period_end"),
                "currency": r.get("currency"),
                "revenue": rev,
                "ebitda": ebitda,
                "ebitda_margin": (ebitda / rev) if (rev and ebitda is not None) else None,
                "net_debt": r.get("net_debt"),
                "cash": r.get("cash"),
            }
        )
    return out


@router.get("/status")
def ingest_status() -> Dict[str, Any]:
    """Whether the live LLM table-reader is configured, else the offline parser is used."""
    configured = azure_openai.is_configured()
    return {
        "llm_configured": configured,
        "mode": "azure_openai" if configured else "offline_heuristic",
        "missing_vars": azure_openai.missing_vars(),
        "deployment": azure_openai.deployment_name(),
        "supported_types": sorted(_SUPPORTED),
    }


@router.post("/financials-upload")
async def ingest_financials_upload(
    file: UploadFile = File(...),
    company_id: Optional[str] = Form(None),
    company_name: Optional[str] = Form(None),
    base_currency: str = Form("USD"),
) -> Dict[str, Any]:
    """Ingest an uploaded financial document into normalized KPI records.

    The operating partner / portco CFO drops a management-accounts PDF, QPR board pack,
    or Excel/CSV export. The matching adapter normalizes it (currency + scale included)
    into the company's KPI time series, written to the same artifacts the dashboard reads.
    """
    filename = file.filename or "uploaded"
    suffix = Path(filename).suffix.lower()
    if suffix not in _SUPPORTED:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type '{suffix or '(none)'}'. Supported: {sorted(_SUPPORTED)}",
        )

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
    if len(raw) > _MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="File too large (max 40 MB).")

    resolved_name = (company_name or "").strip() or Path(filename).stem
    resolved_id = (company_id or "").strip() or _slugify_company(resolved_name)
    source_type = _source_type_for(suffix)

    PROCESSED.mkdir(parents=True, exist_ok=True)
    FEATURES.mkdir(parents=True, exist_ok=True)

    # Sector is decided once, here at ingestion, and stored with the company so it
    # survives a wipe of processed/ + features/ and benchmarking never has to guess.
    sector_key = infer_sector_key(resolved_id, resolved_name)
    update_company_meta(
        resolved_id,
        base_dir=str(PROCESSED),
        company_name=resolved_name,
        sector_key=sector_key,
        source_type=source_type,
    )

    # Adapters/loaders dispatch on suffix, so preserve it on the temp file.
    tmp_path: Optional[Path] = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            tmp.write(raw)
            tmp_path = Path(tmp.name)

        config = KPIExtractionConfig(
            company_id=resolved_id,
            company_name=resolved_name,
            ticker="PRIVATE",
            cik="N/A",
            source_type=source_type,
            source_path=str(tmp_path),
            base_currency=(base_currency or "USD").strip().upper(),
            raw_feature_matrix_path=str(FEATURES / f"{resolved_id}_raw_feature_matrix.csv"),
            model_feature_matrix_path=str(FEATURES / f"{resolved_id}_model_feature_matrix.csv"),
            kpi_records_path=str(PROCESSED / f"{resolved_id}_kpi_records.json"),
            evidence_refs_path=str(PROCESSED / f"{resolved_id}_evidence_refs.json"),
            source_quality_report_path=str(PROCESSED / f"{resolved_id}_source_quality_report.json"),
        )

        result = run_kpi_extraction_agent(config)
    except (ValueError, FileNotFoundError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    finally:
        if tmp_path is not None:
            tmp_path.unlink(missing_ok=True)

    quality = result.get("source_quality_report", {})
    if result.get("kpi_records_count", 0) == 0:
        raise HTTPException(
            status_code=422,
            detail=(
                "No financial periods could be extracted from this document. It may be "
                "scanned (image-only), have no recognisable financial table, or use an "
                "unsupported layout."
            ),
        )

    # Read back the records we just wrote for the period preview (kept out of the
    # adapter return to stay light; the file is the source of truth either way).
    import json

    records = json.loads(Path(config.kpi_records_path).read_text(encoding="utf-8"))

    # Report the currency the records actually carry. The document path normalizes to the
    # requested base (USD); the tabular path passes a source currency column through
    # unchanged, so echoing config.base_currency there would mislabel the preview.
    actual_currency = (records[0].get("currency") if records else None) or config.base_currency

    return {
        "company_id": resolved_id,
        "company_name": resolved_name,
        "source_document": filename,
        "source_type": source_type,
        "base_currency": actual_currency,
        "extraction_mode": quality.get("extraction_mode", source_type),
        "model": quality.get("model"),
        "document_loader": quality.get("document_loader"),
        "period_count": result.get("kpi_records_count", 0),
        "evidence_count": result.get("evidence_refs_count", 0),
        "quality_status": quality.get("status"),
        "missing_required_fields": quality.get("missing_required_fields", []),
        "currency_normalization": quality.get("currency_normalization"),
        "kpi_records_path": result.get("kpi_records_path"),
        "periods": _period_preview(records),
    }
