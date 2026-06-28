from __future__ import annotations

from app.adapters.base import BaseKPIAdapter
from app.adapters.edgar_adapter import EDGARFeatureMatrixAdapter
from app.adapters.excel_qpr_adapter import ExcelQPRAdapter
from app.adapters.pdf_financial_adapter import PdfFinancialAdapter
from app.adapters.placeholder_adapter import PlaceholderKPIAdapter
from app.adapters.private_portco_adapter import PrivatePortcoFinancialAdapter


# Document-based financial sources routed to the PDF/document adapter (PyMuPDF4LLM
# + Docling OCR fallback + LLM/offline table extraction).
_PDF_FINANCIAL_SOURCE_TYPES = {
    "qpr_pdf",
    "board_pack_pdf",
    "pdf_financials",
    "financials_pdf",
    "private_portco_pdf",
    "pdf",
    "docx_financials",
}

SUPPORTED_SOURCE_TYPES = {
    "edgar",
    "feature_matrix",
    "excel",
    "mcp",
    "private_portco_csv",
    "private_portco_excel",
} | _PDF_FINANCIAL_SOURCE_TYPES


def get_kpi_adapter(source_type: str) -> BaseKPIAdapter:
    """
    Return the right adapter for the requested source type.
    """

    normalized = (source_type or "edgar").lower().strip()

    if normalized in {"edgar", "feature_matrix"}:
        return EDGARFeatureMatrixAdapter()

    if normalized == "excel":
        return ExcelQPRAdapter()
    
    if normalized in {"private_portco_csv", "private_portco_excel"}:
        return PrivatePortcoFinancialAdapter()

    if normalized in _PDF_FINANCIAL_SOURCE_TYPES:
        return PdfFinancialAdapter(normalized)

    if normalized == "mcp":
        return PlaceholderKPIAdapter(normalized)

    raise ValueError(
        f"Unsupported KPI source_type: {source_type}. "
        f"Supported values: {sorted(SUPPORTED_SOURCE_TYPES)}"
    )