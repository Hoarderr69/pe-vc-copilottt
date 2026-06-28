"""
Render the synthetic IC memo markdown files into real PDFs.

The VCP Extraction Agent's production input is a PDF (IC memo / investment thesis),
not markdown. These PDFs give the Docling ingestion path something real to parse so
the end-to-end flow (PDF -> Docling -> extraction -> HITL -> VCPStore) is exercised.

Usage:
  uv run python scripts/generate_ic_memo_pdfs.py
"""

import sys
from pathlib import Path

from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

IC_MEMO_DIR = PROJECT_ROOT / "data" / "raw" / "ic_memos"


def _styles():
    base = getSampleStyleSheet()
    return {
        "h1": ParagraphStyle("h1", parent=base["Heading1"], fontName="Helvetica-Bold",
                             fontSize=16, spaceAfter=12, textColor="#0f172a"),
        "h2": ParagraphStyle("h2", parent=base["Heading2"], fontName="Helvetica-Bold",
                             fontSize=12, spaceBefore=12, spaceAfter=6, textColor="#1e3a8a"),
        "body": ParagraphStyle("body", parent=base["BodyText"], fontName="Helvetica",
                               fontSize=10.5, leading=15, spaceAfter=8, alignment=TA_LEFT),
    }


def markdown_to_flowables(md_text: str, styles) -> list:
    """Minimal markdown -> reportlab flowables. Handles #, ##, and paragraphs."""
    flow = []
    for raw in md_text.splitlines():
        line = raw.rstrip()
        if not line:
            continue
        if line.startswith("## "):
            flow.append(Paragraph(line[3:].strip(), styles["h2"]))
        elif line.startswith("# "):
            flow.append(Paragraph(line[2:].strip(), styles["h1"]))
            flow.append(Spacer(1, 0.2 * cm))
        else:
            flow.append(Paragraph(line, styles["body"]))
    return flow


def render(md_path: Path, pdf_path: Path, styles) -> None:
    md_text = md_path.read_text(encoding="utf-8")
    doc = SimpleDocTemplate(
        str(pdf_path), pagesize=A4,
        leftMargin=2.2 * cm, rightMargin=2.2 * cm,
        topMargin=2 * cm, bottomMargin=2 * cm,
        title=md_path.stem,
    )
    doc.build(markdown_to_flowables(md_text, styles))


def main() -> None:
    styles = _styles()
    md_files = sorted(IC_MEMO_DIR.glob("*_ic_memo.md"))
    if not md_files:
        print(f"No IC memo markdown found in {IC_MEMO_DIR}")
        return
    for md_path in md_files:
        pdf_path = md_path.with_suffix(".pdf")
        render(md_path, pdf_path, styles)
        print(f"  wrote {pdf_path.relative_to(PROJECT_ROOT)}  ({pdf_path.stat().st_size // 1024} KB)")
    print(f"\nRendered {len(md_files)} IC memo PDF(s).")


if __name__ == "__main__":
    main()
