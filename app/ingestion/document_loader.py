"""
Document loader for the VCP Extraction Agent.

The agent reads IC memos / investment theses / SHAs that arrive as PDFs (sometimes
DOCX). This module turns any such document into clean text (markdown) the agent can
reason over.

Why a router, not a single parser. VCP source documents are overwhelmingly
*native-text* PDFs (exported from Word/InDesign), and they mix prose with the
occasional table — cap tables, earn-out schedules, funding waterfalls. For that case
PyMuPDF4LLM is the right tool: it extracts text *and* native tables to markdown in
milliseconds, fully local, no model download. It only struggles on *scanned* pages
(image-only, no text layer), which native legal/IC documents rarely contain.

So the rule is text-layer-vs-scanned, decided per page:
  - page has an extractable text layer  -> PyMuPDF4LLM (fast path)
  - page is image-only (scanned)         -> Docling with OCR + TableFormer

Docling is slow precisely *because* of OCR + the TableFormer model; we pay that cost
only on the pages that genuinely need it, never on a clean text memo. Everything runs
on-premise — no document bytes leave the machine (important for confidential PE data).

Plain-text formats (.md, .txt) are passed through directly. DOCX/PPTX/HTML are native
structured formats with no "scanned page" notion, so they go straight to Docling.

Design note: this is an *infrastructure* concern (ingestion), kept separate from the
agent's language reasoning. Raw bytes stop here; the agent only ever sees text.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

# PDFs route through the PyMuPDF4LLM fast path with a per-page Docling fallback.
_PDF_SUFFIXES = {".pdf"}
# Native structured formats: no text-layer/scanned distinction, handled by Docling.
_DOCLING_SUFFIXES = {".docx", ".pptx", ".html", ".xhtml"}
# Plain-text formats are read directly.
_PASSTHROUGH_SUFFIXES = {".md", ".markdown", ".txt"}

# A page with fewer than this many non-whitespace characters in its text layer is
# treated as scanned (image-only) and routed to Docling's OCR pipeline.
_MIN_TEXT_LAYER_CHARS = 12


@dataclass
class LoadedDocument:
    """The result of ingesting a source document."""

    text: str
    source_path: str
    source_name: str
    # "pymupdf4llm" | "docling" | "pymupdf4llm+docling" | "plaintext"
    loader: str
    page_count: Optional[int] = None


def _load_plaintext(path: Path) -> LoadedDocument:
    return LoadedDocument(
        text=path.read_text(encoding="utf-8"),
        source_path=str(path),
        source_name=path.name,
        loader="plaintext",
    )


# ---------------------------------------------------------------------------
# Docling — OCR fallback (scanned PDF pages) and native structured formats
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def _ocr_converter():
    """Docling converter with OCR + table structure ON, for scanned pages.

    This is the heavy path: it loads an OCR engine and the TableFormer model. We build
    it once (lru_cache) and only ever invoke it on pages that lack a text layer.
    """
    try:
        from docling.document_converter import DocumentConverter, PdfFormatOption
        from docling.datamodel.base_models import InputFormat
        from docling.datamodel.pipeline_options import PdfPipelineOptions
    except ModuleNotFoundError as e:
        raise RuntimeError(
            "This document has scanned (image) pages that need OCR, but docling "
            "isn't installed in this deployment. Upload a native-text PDF instead, "
            "or add docling back to pyproject.toml and rebuild the image."
        ) from e

    pipeline_options = PdfPipelineOptions()
    pipeline_options.do_ocr = True
    pipeline_options.do_table_structure = True

    return DocumentConverter(
        format_options={
            InputFormat.PDF: PdfFormatOption(pipeline_options=pipeline_options),
        }
    )


def _docling_markdown(path: Path, page_range: Optional[tuple[int, int]] = None) -> str:
    """Run Docling (OCR on) over a file, optionally restricted to a 1-based page range."""
    converter = _ocr_converter()
    if page_range is not None:
        result = converter.convert(str(path), page_range=page_range)
    else:
        result = converter.convert(str(path))
    return result.document.export_to_markdown()


def _load_native_with_docling(path: Path) -> LoadedDocument:
    """DOCX/PPTX/HTML: native structured formats, parsed by Docling directly."""
    text = _docling_markdown(path)
    return LoadedDocument(
        text=text,
        source_path=str(path),
        source_name=path.name,
        loader="docling",
    )


# ---------------------------------------------------------------------------
# PDF — PyMuPDF4LLM fast path with per-page Docling fallback for scanned pages
# ---------------------------------------------------------------------------

def _scanned_page_indices(path: Path) -> tuple[list[int], int]:
    """Return (0-based indices of scanned pages, total page count).

    A page is "scanned" if its text layer holds almost no characters — i.e. it is an
    image and needs OCR. Native IC memos / SHAs return an empty list here.
    """
    import pymupdf  # PyMuPDF; ships as the `pymupdf` package

    scanned: list[int] = []
    with pymupdf.open(str(path)) as doc:
        total = doc.page_count
        for i in range(total):
            text = doc[i].get_text("text").strip()
            if len(text) < _MIN_TEXT_LAYER_CHARS:
                scanned.append(i)
    return scanned, total


def _pymupdf4llm_markdown(path: Path, pages: Optional[list[int]] = None) -> str:
    """Extract markdown (text + native tables) via PyMuPDF4LLM, optionally per page."""
    import pymupdf4llm

    if pages is not None:
        return pymupdf4llm.to_markdown(str(path), pages=pages)
    return pymupdf4llm.to_markdown(str(path))


def _load_pdf(path: Path) -> LoadedDocument:
    """Load a PDF, routing each page to the engine that fits it.

    Fast path (the common case): no scanned pages -> one PyMuPDF4LLM pass.
    Mixed doc: assemble in page order, OCR'ing only the scanned pages via Docling.
    """
    scanned, total = _scanned_page_indices(path)

    # Fast path: fully native-text document.
    if not scanned:
        text = _pymupdf4llm_markdown(path)
        return LoadedDocument(
            text=text,
            source_path=str(path),
            source_name=path.name,
            loader="pymupdf4llm",
            page_count=total,
        )

    # Mixed document: stitch page-by-page so output stays in reading order. Text pages
    # go through PyMuPDF4LLM, scanned pages through Docling's OCR pipeline.
    scanned_set = set(scanned)
    used_pymupdf = False
    parts: list[str] = []
    for i in range(total):
        if i in scanned_set:
            # Docling page_range is 1-based and inclusive.
            parts.append(_docling_markdown(path, page_range=(i + 1, i + 1)))
        else:
            parts.append(_pymupdf4llm_markdown(path, pages=[i]))
            used_pymupdf = True

    loader = "pymupdf4llm+docling" if used_pymupdf else "docling"
    return LoadedDocument(
        text="\n\n".join(p for p in parts if p.strip()),
        source_path=str(path),
        source_name=path.name,
        loader=loader,
        page_count=total,
    )


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------

def load_document_text(document_path: str) -> LoadedDocument:
    """Load a source document into text.

    - .pdf            -> PyMuPDF4LLM (fast), Docling OCR fallback for scanned pages
    - .docx/.pptx/... -> Docling (native structured formats)
    - .md/.txt        -> read directly

    Raises FileNotFoundError if the path does not exist, ValueError for unsupported types.
    """
    path = Path(document_path)
    if not path.exists():
        raise FileNotFoundError(f"Document not found: {document_path}")

    suffix = path.suffix.lower()
    if suffix in _PASSTHROUGH_SUFFIXES:
        return _load_plaintext(path)
    if suffix in _PDF_SUFFIXES:
        return _load_pdf(path)
    if suffix in _DOCLING_SUFFIXES:
        return _load_native_with_docling(path)

    supported = sorted(_PASSTHROUGH_SUFFIXES | _PDF_SUFFIXES | _DOCLING_SUFFIXES)
    raise ValueError(f"Unsupported document type '{suffix}'. Supported: {supported}")
