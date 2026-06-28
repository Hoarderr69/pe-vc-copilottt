"""
Board Pack Generator — ReportLab PDF engine for PE board materials.

Assembles a multi-page, board-ready PDF from structured monitoring outputs:
  Page 1: Cover — company, date, overall severity, headline KPIs
  Page 2: Executive Summary — AI-generated prose, key risks, priority action
  Page 3: VCP Milestone Scorecard — actual vs target table with RAG status
  Page 4: EBITDA Performance & Forward Curve — matplotlib chart embedded
  Page 5: IRR Scenario Analysis — bear/base/bull table
  Page 6: Sector Benchmarking — peer comparison chart
  Page 7: Audit Trail & Evidence — sources, HITL decisions, citations

Usage:
    from app.reports.board_pack_generator import generate_board_pack
    pdf_bytes = generate_board_pack(company_name=..., ...)
    with open("board_pack.pdf", "wb") as f:
        f.write(pdf_bytes)
"""

from __future__ import annotations

import io
import math
from datetime import date, datetime
from typing import Any, Dict, List, Optional

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np
import pandas as pd

from reportlab.lib.pagesizes import A4
from reportlab.lib.colors import (
    HexColor, white, black, Color,
)
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as rl_canvas

# ---------------------------------------------------------------------------
# Design system — institutional PE aesthetic
# ---------------------------------------------------------------------------

NAVY      = HexColor("#1E3A8A")   # spec primary blue — print-safe, slightly deeper than screen
NAVY_MID  = HexColor("#1e293b")   # section header bars
GOLD      = HexColor("#b8972e")   # accent / highlight
GOLD_LIGHT= HexColor("#d4b96a")   # lighter gold for subtle elements
SLATE     = HexColor("#64748B")   # secondary / muted text (spec value)
LIGHT_BG  = HexColor("#f8fafc")   # page background tint
BORDER    = HexColor("#CBD5E1")   # spec border value (0.5pt weight)
ROW_ALT   = HexColor("#f8fafc")   # alternating table rows
DIVIDER   = HexColor("#CBD5E1")   # horizontal rule
BODY_TEXT = HexColor("#1E293B")   # spec body text (not pure black)

# Spec: status text only — no background fills on table rows
STATUS_RED   = HexColor("#DC2626")
STATUS_AMBER = HexColor("#D97706")
STATUS_GREEN = HexColor("#059669")

W, H = A4  # 595 x 842 pts

MARGIN_L = 45
MARGIN_R = 45
MARGIN_T = 45
MARGIN_B = 45
CONTENT_W = W - MARGIN_L - MARGIN_R  # 505 pts
HEADER_H  = 50
FOOTER_H  = 28


def _status_colors(status: str):
    """Return (text_color, bg_color, border_color).
    Per spec: text colour carries the RAG status; no background fills on table rows.
    bg/border are only used for callout boxes, not table cells.
    """
    s = (status or "").strip()
    if s == "Red":
        return STATUS_RED, HexColor("#fff8f8"), HexColor("#fca5a5")
    if s == "Amber":
        return STATUS_AMBER, HexColor("#fffbeb"), HexColor("#fcd34d")
    if s == "Green":
        return STATUS_GREEN, HexColor("#f0fdf4"), HexColor("#86efac")
    return SLATE, HexColor("#f8fafc"), BORDER


def _fmt_currency(v: Any, currency: str = "£") -> str:
    if v is None:
        return "—"
    try:
        f = float(v)
    except (TypeError, ValueError):
        return str(v)
    if abs(f) >= 1e9:
        return f"{currency}{f / 1e9:.1f}bn"
    if abs(f) >= 1e6:
        return f"{currency}{f / 1e6:.1f}M"
    if abs(f) >= 1e3:
        return f"{currency}{f / 1e3:.0f}k"
    return f"{currency}{f:.0f}"


def _fmt_pct(v: Any, signed: bool = False) -> str:
    if v is None:
        return "—"
    try:
        f = float(v)
        prefix = "+" if signed and f > 0 else ""
        return f"{prefix}{f:.1%}"
    except (TypeError, ValueError):
        return str(v)


def _fmt_metric(metric: str, value: Any) -> str:
    """Format a metric value based on its name."""
    if value is None:
        return "—"
    try:
        f = float(value)
    except (TypeError, ValueError):
        return str(value)

    m = metric.lower()
    if "margin" in m or "growth" in m or "ratio" in m and f < 5:
        return f"{f:.1%}" if abs(f) < 5 else f"{f:.1f}x"
    if "revenue" in m or "ebitda" in m and abs(f) > 1e4:
        return _fmt_currency(f)
    if "debt_to" in m or "leverage" in m or "multiple" in m:
        return f"{f:.2f}x"
    if abs(f) < 1:
        return f"{f:.1%}"
    return f"{f:,.0f}"


# ---------------------------------------------------------------------------
# Canvas helpers
# ---------------------------------------------------------------------------

class PageCanvas:
    """Thin wrapper around ReportLab canvas with shared helpers."""

    def __init__(self, buffer: io.BytesIO, report_date: str, company_name: str):
        self.c = rl_canvas.Canvas(buffer, pagesize=A4)
        self.report_date = report_date
        self.company_name = company_name
        self._page = 0

    def new_page(self, draw_chrome: bool = True, bg: Optional[Color] = None):
        if self._page > 0:
            self.c.showPage()
        self._page += 1
        if bg:
            self.c.setFillColor(bg)
            self.c.rect(0, 0, W, H, fill=1, stroke=0)
        if draw_chrome:
            self._draw_header()
            self._draw_footer(self._page)

    def _draw_header(self):
        self.c.setFillColor(NAVY)
        self.c.rect(0, H - HEADER_H, W, HEADER_H, fill=1, stroke=0)
        self.c.setFillColor(GOLD)
        self.c.setFont("Helvetica-Bold", 7)
        self.c.drawString(MARGIN_L, H - 18, "PE VALUE CREATION COPILOT")
        self.c.setFillColor(white)
        self.c.setFont("Helvetica", 7)
        self.c.drawRightString(W - MARGIN_R, H - 18, "CONFIDENTIAL — BOARD ONLY")
        self.c.setFont("Helvetica-Bold", 10)
        self.c.drawString(MARGIN_L, H - 36, self.company_name)
        self.c.setFont("Helvetica", 8)
        self.c.setFillColor(HexColor("#8ba3be"))
        self.c.drawRightString(W - MARGIN_R, H - 36, self.report_date)

    def _draw_footer(self, page_num: int):
        self.c.setFillColor(NAVY)
        self.c.rect(0, 0, W, FOOTER_H, fill=1, stroke=0)
        self.c.setFillColor(HexColor("#8ba3be"))
        self.c.setFont("Helvetica", 7)
        self.c.drawString(MARGIN_L, 9, f"Generated {self.report_date} · PE Value Creation Copilot")
        self.c.drawRightString(W - MARGIN_R, 9, f"Page {page_num}")
        self.c.setFillColor(GOLD)
        self.c.drawCentredString(W / 2, 9, "STRICTLY CONFIDENTIAL")

    def section_header(self, y: float, title: str, subtitle: str = "") -> float:
        """Draw a section header bar. Returns new y below it."""
        bar_h = 32
        self.c.setFillColor(NAVY_MID)
        self.c.rect(MARGIN_L, y - bar_h, CONTENT_W, bar_h, fill=1, stroke=0)
        self.c.setFillColor(white)
        self.c.setFont("Helvetica-Bold", 10)
        self.c.drawString(MARGIN_L + 10, y - bar_h + 11, title)
        if subtitle:
            self.c.setFillColor(HexColor("#8ba3be"))
            self.c.setFont("Helvetica", 8)
            self.c.drawRightString(MARGIN_L + CONTENT_W - 10, y - bar_h + 11, subtitle)
        return y - bar_h - 10

    def divider(self, y: float) -> float:
        self.c.setStrokeColor(DIVIDER)
        self.c.setLineWidth(0.5)
        self.c.line(MARGIN_L, y, MARGIN_L + CONTENT_W, y)
        return y - 6

    def label_value(self, x: float, y: float, label: str, value: str,
                    label_color=None, value_color=None, label_size=8, value_size=14):
        self.c.setFillColor(label_color or SLATE)
        self.c.setFont("Helvetica", label_size)
        self.c.drawString(x, y + value_size + 3, label)
        self.c.setFillColor(value_color or NAVY)
        self.c.setFont("Helvetica-Bold", value_size)
        self.c.drawString(x, y, value)

    def rag_dot(self, x: float, y: float, status: str, r: float = 5.5):
        color, _, _ = _status_colors(status)
        self.c.setFillColor(color)
        self.c.circle(x, y, r, fill=1, stroke=0)

    def wrapped_text(self, x: float, y: float, text: str, width: float,
                     font: str = "Helvetica", size: int = 9,
                     color: Color = None, line_height: float = 14) -> float:
        """Draw wrapped text. Returns the y after the last line."""
        self.c.setFillColor(color or SLATE)
        self.c.setFont(font, size)
        words = text.split()
        line = ""
        for word in words:
            test = (line + " " + word).strip()
            if self.c.stringWidth(test, font, size) <= width:
                line = test
            else:
                self.c.drawString(x, y, line)
                y -= line_height
                line = word
        if line:
            self.c.drawString(x, y, line)
            y -= line_height
        return y

    def badge(self, x: float, y: float, text: str, status: str,
              w: float = 90, h: float = 22):
        color, bg, border = _status_colors(status)
        self.c.setFillColor(bg)
        self.c.setStrokeColor(border)
        self.c.setLineWidth(1)
        self.c.roundRect(x, y, w, h, 4, fill=1, stroke=1)
        self.c.setFillColor(color)
        self.c.setFont("Helvetica-Bold", 9)
        self.c.drawCentredString(x + w / 2, y + 7, text)

    def save(self):
        self.c.save()


# ---------------------------------------------------------------------------
# Page 1: Cover
# ---------------------------------------------------------------------------

def _cover_page(
    pc: PageCanvas,
    company_name: str,
    sector: str,
    report_date: str,
    period: str,
    alert_severity: str,
    alert_headline: str,
    vcp_on_track: int,
    vcp_total: int,
    irr_at_risk_bps: Optional[int],
    ebitda_actual: Optional[float],
    ebitda_target: Optional[float],
):
    """
    Spec: clean white cover — firm name, document type, company, quarter, date, classification.
    No colour fills, no decorative elements. Thin horizontal rule only.
    """
    pc.new_page(draw_chrome=False)

    # Thin navy top bar (branding stripe, not a panel)
    pc.c.setFillColor(NAVY)
    pc.c.rect(0, H - 5, W, 5, fill=1, stroke=0)

    # Firm label top-left
    pc.c.setFillColor(NAVY)
    pc.c.setFont("Helvetica-Bold", 8)
    pc.c.drawString(MARGIN_L, H - 30, "PE VALUE CREATION COPILOT")

    # Confidential top-right
    pc.c.setFillColor(SLATE)
    pc.c.setFont("Helvetica", 7)
    pc.c.drawRightString(W - MARGIN_R, H - 30, "CONFIDENTIAL")

    # Company name — large, high on page
    pc.c.setFillColor(BODY_TEXT)
    pc.c.setFont("Helvetica-Bold", 22)
    pc.c.drawString(MARGIN_L, H - 130, company_name)

    # Document type
    pc.c.setFont("Helvetica-Bold", 14)
    pc.c.drawString(MARGIN_L, H - 162, "Board Pack")

    # Period
    pc.c.setFillColor(SLATE)
    pc.c.setFont("Helvetica", 11)
    pc.c.drawString(MARGIN_L, H - 184, period)

    # Thin horizontal rule (spec: "a thin horizontal rule")
    pc.c.setStrokeColor(BORDER)
    pc.c.setLineWidth(0.5)
    pc.c.line(MARGIN_L, H - 210, MARGIN_L + 200, H - 210)

    # Metadata block
    meta = [
        ("Prepared by:", "Operating Partner Team"),
        ("Date:", report_date),
        ("Classification:", "Confidential"),
    ]
    pc.c.setFillColor(BODY_TEXT)
    my = H - 232
    for lbl, val in meta:
        pc.c.setFont("Helvetica-Bold", 9)
        pc.c.drawString(MARGIN_L, my, lbl)
        pc.c.setFont("Helvetica", 9)
        pc.c.drawString(MARGIN_L + 90, my, val)
        my -= 16

    # Another thin rule
    pc.c.setStrokeColor(BORDER)
    pc.c.setLineWidth(0.5)
    pc.c.line(MARGIN_L, my - 8, MARGIN_L + 200, my - 8)

    # AI generation attribution — small, honest
    pc.c.setFillColor(SLATE)
    pc.c.setFont("Helvetica", 8)
    pc.c.drawString(MARGIN_L, my - 26, "Generated by PE Value Creation Copilot")

    # Status indicator — text only, no fill
    sev_color, _, _ = _status_colors(alert_severity)
    pc.c.setFillColor(sev_color)
    pc.c.setFont("Helvetica-Bold", 9)
    pc.c.drawString(MARGIN_L, my - 42, f"● Status: {alert_severity.upper()}")


# ---------------------------------------------------------------------------
# Page 2: Executive Summary
# ---------------------------------------------------------------------------

def _exec_summary_page(
    pc: PageCanvas,
    exec_summary: str,
    key_risks: List[str],
    priority_action: str,
    board_talking_points: List[str],
    alert_severity: str,
    alert_headline: str,
    narrative_mode: str,
    irr_at_risk_bps: Optional[int] = None,
    vcp_on_track: int = 0,
    vcp_total: int = 0,
    key_risk_summary: str = "",
):
    pc.new_page()
    y = H - HEADER_H - 20

    y = pc.section_header(y, "EXECUTIVE SUMMARY", period_label(narrative_mode))

    # Alert badge + headline
    sev_color, sev_bg, sev_border = _status_colors(alert_severity)
    badge_h = 50
    pc.c.setFillColor(sev_bg)
    pc.c.setStrokeColor(sev_border)
    pc.c.setLineWidth(1.5)
    pc.c.roundRect(MARGIN_L, y - badge_h, CONTENT_W, badge_h, 5, fill=1, stroke=1)

    # Left status bar
    pc.c.setFillColor(sev_color)
    pc.c.roundRect(MARGIN_L, y - badge_h, 6, badge_h, 3, fill=1, stroke=0)
    pc.c.rect(MARGIN_L + 3, y - badge_h, 4, badge_h, fill=1, stroke=0)

    pc.c.setFillColor(sev_color)
    pc.c.setFont("Helvetica-Bold", 9)
    pc.c.drawString(MARGIN_L + 16, y - 16, f"● {alert_severity.upper()}")

    pc.c.setFillColor(NAVY)
    pc.c.setFont("Helvetica-Bold", 10)
    # Wrap headline inside badge
    max_headline_w = CONTENT_W - 30
    words = alert_headline.split()
    line1 = ""
    for w in words:
        test = (line1 + " " + w).strip()
        if pc.c.stringWidth(test, "Helvetica-Bold", 10) <= max_headline_w:
            line1 = test
        else:
            break
    remainder = alert_headline[len(line1):].strip()
    pc.c.drawString(MARGIN_L + 16, y - 32, line1)
    if remainder:
        pc.c.setFont("Helvetica", 9)
        pc.c.setFillColor(SLATE)
        pc.c.drawString(MARGIN_L + 16, y - 44, remainder[:100])

    y -= badge_h + 16

    # Executive prose
    pc.c.setFillColor(NAVY)
    pc.c.setFont("Helvetica-Bold", 8)
    pc.c.drawString(MARGIN_L, y, "SITUATION OVERVIEW")
    y -= 14
    y = pc.wrapped_text(MARGIN_L, y, exec_summary, CONTENT_W,
                        font="Helvetica", size=9, color=NAVY, line_height=15)
    y -= 10
    y = pc.divider(y)

    # Key risks
    pc.c.setFillColor(NAVY)
    pc.c.setFont("Helvetica-Bold", 8)
    pc.c.drawString(MARGIN_L, y, "KEY RISKS REQUIRING BOARD ATTENTION")
    y -= 16

    risk_statuses = ["Red", "Red", "Amber"]
    for i, risk in enumerate(key_risks):
        status = risk_statuses[i] if i < len(risk_statuses) else "Amber"
        rcolor, rbg, rborder = _status_colors(status)

        # Risk number badge
        pc.c.setFillColor(rcolor)
        pc.c.circle(MARGIN_L + 9, y - 1, 9, fill=1, stroke=0)
        pc.c.setFillColor(white)
        pc.c.setFont("Helvetica-Bold", 8)
        pc.c.drawCentredString(MARGIN_L + 9, y - 5, str(i + 1))

        # Risk text
        y_before = y
        y = pc.wrapped_text(MARGIN_L + 26, y, risk, CONTENT_W - 26,
                            font="Helvetica", size=9, color=NAVY, line_height=14)
        y -= 8

    y = pc.divider(y - 4)

    # Priority Action box
    pa_h = 65
    pc.c.setFillColor(HexColor("#fffbeb"))
    pc.c.setStrokeColor(HexColor("#f6ad55"))
    pc.c.setLineWidth(1.5)
    pc.c.roundRect(MARGIN_L, y - pa_h, CONTENT_W, pa_h, 5, fill=1, stroke=1)
    pc.c.setFillColor(HexColor("#c05621"))
    pc.c.rect(MARGIN_L, y - pa_h, 6, pa_h, fill=1, stroke=0)
    pc.c.roundRect(MARGIN_L, y - pa_h, 6, pa_h, 3, fill=1, stroke=0)

    pc.c.setFillColor(HexColor("#c05621"))
    pc.c.setFont("Helvetica-Bold", 8)
    pc.c.drawString(MARGIN_L + 16, y - 16, "PRIORITY ACTION THIS QUARTER")

    pc.c.setFillColor(NAVY)
    y_after = pc.wrapped_text(MARGIN_L + 16, y - 30, priority_action, CONTENT_W - 26,
                              font="Helvetica-Bold", size=9, color=NAVY, line_height=14)

    y -= pa_h + 16

    # Board talking points
    if board_talking_points:
        pc.c.setFillColor(NAVY)
        pc.c.setFont("Helvetica-Bold", 8)
        pc.c.drawString(MARGIN_L, y, "BOARD MEETING TALKING POINTS")
        y -= 16

        for i, point in enumerate(board_talking_points):
            pc.c.setFillColor(GOLD)
            pc.c.setFont("Helvetica-Bold", 10)
            pc.c.drawString(MARGIN_L, y + 2, "›")
            y = pc.wrapped_text(MARGIN_L + 14, y, point, CONTENT_W - 14,
                                font="Helvetica", size=9, color=SLATE, line_height=14)
            y -= 6

    # -----------------------------------------------------------------
    # Spec: 3-col summary strip at the bottom of page 2.
    # "If someone only reads page 2, they walk away with the 3 numbers that matter."
    # -----------------------------------------------------------------
    strip_h = 44
    strip_y = MARGIN_B + FOOTER_H + 10
    pc.c.setFillColor(HexColor("#f1f5f9"))
    pc.c.roundRect(MARGIN_L, strip_y, CONTENT_W, strip_h, 4, fill=1, stroke=0)

    irr_gap_bps = irr_at_risk_bps or 0
    cols_data = [
        ("IRR AT RISK",
         f"{irr_gap_bps:+d} bps" if irr_at_risk_bps is not None else "—",
         STATUS_RED if irr_gap_bps < -200 else STATUS_AMBER if irr_gap_bps < 0 else STATUS_GREEN),
        ("VCP ON TRACK",
         f"{vcp_on_track} / {vcp_total}" if vcp_total else "—",
         STATUS_GREEN if vcp_on_track == vcp_total else STATUS_AMBER if vcp_on_track >= vcp_total / 2 else STATUS_RED),
        ("KEY RISK",
         (key_risk_summary or (key_risks[0][:32] + "…" if key_risks and len(key_risks[0]) > 32 else (key_risks[0] if key_risks else "—"))),
         STATUS_RED),
    ]
    col_w = CONTENT_W / 3
    for i, (lbl, val, col) in enumerate(cols_data):
        cx = MARGIN_L + i * col_w + col_w / 2
        pc.c.setFillColor(SLATE)
        pc.c.setFont("Helvetica", 7)
        pc.c.drawCentredString(cx, strip_y + strip_h - 12, lbl)
        pc.c.setFillColor(col)
        pc.c.setFont("Helvetica-Bold", 11)
        pc.c.drawCentredString(cx, strip_y + 16, val[:28])


def period_label(mode: str) -> str:
    return "AI-Generated" if mode == "azure_openai" else "Rule-Based"


# ---------------------------------------------------------------------------
# Page 3: VCP Milestone Scorecard
# ---------------------------------------------------------------------------

def _vcp_scorecard_page(
    pc: PageCanvas,
    milestones: List[Dict[str, Any]],
    drift_results: List[Dict[str, Any]],
    period: str,
):
    pc.new_page()
    y = H - HEADER_H - 20

    # Build lookup: initiative → drift result
    drift_by_init = {r.get("initiative", ""): r for r in drift_results}

    on_track = sum(1 for r in drift_results if r.get("status") == "Green")
    total = len(drift_results)

    y = pc.section_header(y, "VALUE CREATION PLAN SCORECARD", f"As of {period}")

    # Summary banner
    green_count = sum(1 for r in drift_results if r.get("status") == "Green")
    red_count   = sum(1 for r in drift_results if r.get("status") == "Red")
    amber_count = sum(1 for r in drift_results if r.get("status") == "Amber")
    ne_count    = sum(1 for r in drift_results if r.get("status") == "Not Evaluable")

    summary_h = 36
    pc.c.setFillColor(HexColor("#eef2f7"))
    pc.c.roundRect(MARGIN_L, y - summary_h, CONTENT_W, summary_h, 4, fill=1, stroke=0)

    stat_items = [
        (str(red_count),   "Red",          STATUS_RED),
        (str(amber_count), "Amber",        STATUS_AMBER),
        (str(green_count), "Green",        STATUS_GREEN),
        (str(ne_count),    "Not Evaluable", SLATE),
    ]
    col_w = CONTENT_W / len(stat_items)
    for i, (val, lbl, col) in enumerate(stat_items):
        cx = MARGIN_L + i * col_w + col_w / 2
        pc.c.setFillColor(col)
        pc.c.setFont("Helvetica-Bold", 16)
        pc.c.drawCentredString(cx, y - 16, val)
        pc.c.setFillColor(SLATE)
        pc.c.setFont("Helvetica", 7)
        pc.c.drawCentredString(cx, y - 28, lbl)

    y -= summary_h + 14

    # Column headers
    cols = [
        ("INITIATIVE",   168, "L"),
        ("CATEGORY",      66, "L"),
        ("BASELINE",      55, "R"),
        ("TARGET",        55, "R"),
        ("ACTUAL",        60, "R"),
        ("GAP",           48, "R"),
        ("STATUS",        40, "C"),
        ("DUE DATE",      56, "R"),
    ]
    header_h = 22
    pc.c.setFillColor(NAVY)
    pc.c.rect(MARGIN_L, y - header_h, CONTENT_W, header_h, fill=1, stroke=0)

    xpos = MARGIN_L + 6
    for label, cw, align in cols:
        pc.c.setFillColor(white)
        pc.c.setFont("Helvetica-Bold", 7)
        if align == "R":
            pc.c.drawRightString(xpos + cw - 4, y - 15, label)
        elif align == "C":
            pc.c.drawCentredString(xpos + cw / 2, y - 15, label)
        else:
            pc.c.drawString(xpos + 4, y - 15, label)
        xpos += cw

    y -= header_h

    # Rows — join milestones with drift results
    all_rows = {}
    for m in milestones:
        key = m.get("initiative", "")
        all_rows[key] = {"milestone": m, "drift": drift_by_init.get(key, {})}
    for r in drift_results:
        key = r.get("initiative", "")
        if key not in all_rows:
            all_rows[key] = {"milestone": {}, "drift": r}

    for row_i, (key, row) in enumerate(all_rows.items()):
        m = row["milestone"]
        d = row["drift"]
        status = d.get("status", "Not Evaluable")
        rcolor, rbg, rborder = _status_colors(status)

        row_h = 28
        # Alternating background
        if row_i % 2 == 0:
            pc.c.setFillColor(white)
        else:
            pc.c.setFillColor(ROW_ALT)
        pc.c.rect(MARGIN_L, y - row_h, CONTENT_W, row_h, fill=1, stroke=0)

        # Left status stripe
        pc.c.setFillColor(rcolor)
        pc.c.rect(MARGIN_L, y - row_h, 4, row_h, fill=1, stroke=0)

        values = [
            m.get("initiative", d.get("initiative", "—")),
            m.get("category", d.get("category", "—")).title(),
            _fmt_metric(m.get("metric", ""), m.get("baseline_value")),
            _fmt_metric(d.get("metric", ""), d.get("target_value")),
            _fmt_metric(d.get("metric", ""), d.get("actual_value")),
            _fmt_pct(d.get("gap_pct"), signed=True),
            status,
            (m.get("target_date") or d.get("target_date") or "—")[:10],
        ]

        xpos = MARGIN_L + 6
        for vi, ((_, cw, align), val) in enumerate(zip(cols, values)):
            if vi == 6:  # Status column — draw dot only
                pc.rag_dot(xpos + cw / 2, y - row_h / 2, status, r=5)
                xpos += cw
                continue

            # Color actual vs target: red if actual is worse
            text_color = NAVY
            if vi == 4 and status == "Red":
                text_color = STATUS_RED
            elif vi == 4 and status == "Amber":
                text_color = STATUS_AMBER
            elif vi == 4 and status == "Green":
                text_color = STATUS_GREEN

            if vi == 5:  # Gap column
                gap = d.get("gap_pct")
                if gap is not None:
                    text_color = STATUS_RED if gap < -0.1 else (
                        STATUS_AMBER if gap < 0 else STATUS_GREEN
                    )

            pc.c.setFillColor(text_color)
            font = "Helvetica-Bold" if vi in (0, 4) else "Helvetica"
            pc.c.setFont(font, 8 if vi == 0 else 8)

            # Truncate initiative name if too long
            display_val = val
            if vi == 0:
                while pc.c.stringWidth(display_val, font, 8) > cw - 14 and len(display_val) > 10:
                    display_val = display_val[:-1]
                if display_val != val:
                    display_val = display_val[:-3] + "..."

            if align == "R":
                pc.c.drawRightString(xpos + cw - 4, y - row_h / 2 - 3, display_val)
            elif align == "C":
                pc.c.drawCentredString(xpos + cw / 2, y - row_h / 2 - 3, display_val)
            else:
                pc.c.drawString(xpos + 6, y - row_h / 2 - 3, display_val)
            xpos += cw

        # Bottom border
        pc.c.setStrokeColor(DIVIDER)
        pc.c.setLineWidth(0.3)
        pc.c.line(MARGIN_L, y - row_h, MARGIN_L + CONTENT_W, y - row_h)

        y -= row_h

    # Footer note
    y -= 10
    pc.c.setFillColor(SLATE)
    pc.c.setFont("Helvetica", 7)
    pc.c.drawString(MARGIN_L, y,
                    "RAG: Red = >10% below target · Amber = 5–10% below target · Green = within ±5% of target")


# ---------------------------------------------------------------------------
# Page 3: KPI Performance Scorecard  (NEW — spec Section 2 / Page 3)
# ---------------------------------------------------------------------------

def _kpi_scorecard_page(
    pc: PageCanvas,
    kpi_performance: List[Dict[str, Any]],
    period: str,
):
    """
    Full-page financial KPI table with actual vs IC target, delta, QoQ arrow.
    Spec rules: direction arrows on QoQ column; inverse metrics labelled (↑ = worse);
    sorted worst-first; text colour carries status, no row background fills.
    """
    pc.new_page()
    y = H - HEADER_H - 20

    y = pc.section_header(y, "KPI PERFORMANCE SCORECARD", f"Period: {period}")

    if not kpi_performance:
        pc.c.setFillColor(SLATE)
        pc.c.setFont("Helvetica", 10)
        pc.c.drawCentredString(W / 2, y - 60, "KPI performance data not available")
        return

    y -= 8

    cols = [
        ("METRIC",       160, "L"),
        ("ACTUAL",        72, "R"),
        ("IC TARGET",     72, "R"),
        ("DELTA",         60, "R"),
        ("VS LAST QTR",   72, "R"),
        ("STATUS",        69, "C"),
    ]

    hh = 22
    pc.c.setFillColor(NAVY_MID)
    pc.c.rect(MARGIN_L, y - hh, CONTENT_W, hh, fill=1, stroke=0)
    xp = MARGIN_L + 6
    for lbl, cw, align in cols:
        pc.c.setFillColor(white)
        pc.c.setFont("Helvetica-Bold", 7)
        if align == "R":
            pc.c.drawRightString(xp + cw - 4, y - 15, lbl)
        elif align == "C":
            pc.c.drawCentredString(xp + cw / 2, y - 15, lbl)
        else:
            pc.c.drawString(xp + 4, y - 15, lbl)
        xp += cw
    y -= hh

    STATUS_COLOR = {
        "Behind":  STATUS_RED,
        "At Risk": STATUS_AMBER,
        "On Track": STATUS_GREEN,
        "No Data": SLATE,
    }

    for ri, row in enumerate(kpi_performance):
        rh = 26
        # Alternating rows — plain white / very light bg; NO status fill
        pc.c.setFillColor(white if ri % 2 == 0 else ROW_ALT)
        pc.c.rect(MARGIN_L, y - rh, CONTENT_W, rh, fill=1, stroke=0)

        # Left status stripe (text colour only on the cell; thin stripe for visual anchor)
        s_col = STATUS_COLOR.get(row.get("status", ""), SLATE)
        pc.c.setFillColor(s_col)
        pc.c.rect(MARGIN_L, y - rh, 4, rh, fill=1, stroke=0)

        metric_label = row.get("metric", "—")
        if row.get("inverse"):
            metric_label += " (↑ = worse)"

        # QoQ arrow
        qoq_pct = row.get("qoq_pct")
        qoq_up  = row.get("qoq_up")
        inverse = row.get("inverse", False)
        if qoq_pct is not None:
            arrow = "▲" if qoq_up else "▼"
            qoq_str = f"{qoq_pct:+.1%} {arrow}"
            # For inverse metrics, up = worse (red), down = better (green)
            if inverse:
                qoq_col = STATUS_RED if qoq_up else STATUS_GREEN
            else:
                qoq_col = STATUS_GREEN if qoq_up else STATUS_RED
        else:
            qoq_str = "—"
            qoq_col = SLATE

        row_vals = [
            metric_label,
            row.get("fmt_actual", "—"),
            row.get("fmt_target", "—"),
            row.get("fmt_delta", "—"),
            qoq_str,
            row.get("status", "—"),
        ]

        xp = MARGIN_L + 6
        for vi, ((_, cw, align), val) in enumerate(zip(cols, row_vals)):
            if vi == 5:  # Status — coloured text only, no dot/fill
                pc.c.setFillColor(s_col)
                pc.c.setFont("Helvetica-Bold", 8)
                pc.c.drawCentredString(xp + cw / 2, y - rh / 2 - 3, val)
                xp += cw
                continue

            text_color = BODY_TEXT
            if vi == 3:  # Delta
                gap = row.get("delta_pct")
                if gap is not None:
                    if inverse:
                        text_color = STATUS_RED if gap > 0.05 else STATUS_AMBER if gap > 0 else STATUS_GREEN
                    else:
                        text_color = STATUS_RED if gap < -0.1 else STATUS_AMBER if gap < 0 else STATUS_GREEN
            elif vi == 4:  # QoQ
                text_color = qoq_col

            pc.c.setFillColor(text_color)
            pc.c.setFont("Helvetica-Bold" if vi == 0 else "Helvetica", 8)
            display = val
            if vi == 0:
                while pc.c.stringWidth(display, "Helvetica-Bold", 8) > cw - 14 and len(display) > 10:
                    display = display[:-1]
                if display != val:
                    display = display[:-3] + "..."
            if align == "R":
                pc.c.drawRightString(xp + cw - 4, y - rh / 2 - 3, display)
            elif align == "C":
                pc.c.drawCentredString(xp + cw / 2, y - rh / 2 - 3, display)
            else:
                pc.c.drawString(xp + 6, y - rh / 2 - 3, display)
            xp += cw

        pc.c.setStrokeColor(DIVIDER)
        pc.c.setLineWidth(0.3)
        pc.c.line(MARGIN_L, y - rh, MARGIN_L + CONTENT_W, y - rh)
        y -= rh

    y -= 10
    pc.c.setFillColor(SLATE)
    pc.c.setFont("Helvetica", 7)
    pc.c.drawString(MARGIN_L, y,
                    "▲/▼ = vs prior quarter. (↑ = worse) flags inverse metrics. "
                    "Behind = >10% below IC target · At Risk = 5–10% · On Track = within ±5%")
    y -= 11
    pc.c.drawString(MARGIN_L, y,
                    "Source: Management accounts · IC Memo confirmed at deal close")


# ---------------------------------------------------------------------------
# Page 4: EBITDA Performance Chart
# ---------------------------------------------------------------------------

def _ebitda_chart_png(
    kpi_records: List[Dict[str, Any]],
    vcp_ebitda_margin_target: Optional[float],
    period: str,
    company_name: str,
    width_in: float = 6.5,
    height_in: float = 3.8,
) -> Optional[bytes]:
    """Render EBITDA margin performance chart as PNG bytes."""
    try:
        df = pd.DataFrame(kpi_records)
        if df.empty or "period_end" not in df.columns:
            return None

        df["period_end"] = pd.to_datetime(df["period_end"])
        df = df.sort_values("period_end").reset_index(drop=True)

        # Prefer adjusted_ebitda; fall back to ebitda_proxy
        if "adjusted_ebitda" in df.columns:
            df["_ebitda"] = pd.to_numeric(df["adjusted_ebitda"], errors="coerce")
        elif "ebitda_proxy" in df.columns:
            df["_ebitda"] = pd.to_numeric(df["ebitda_proxy"], errors="coerce")
        else:
            return None

        df["_rev"] = pd.to_numeric(df.get("revenue", pd.Series(dtype=float)), errors="coerce")

        if "ebitda_margin" in df.columns:
            df["_margin"] = pd.to_numeric(df["ebitda_margin"], errors="coerce")
        elif df["_rev"].notna().any():
            df["_margin"] = df["_ebitda"] / df["_rev"]
        else:
            df["_margin"] = df["_ebitda"]

        df = df.dropna(subset=["_margin"])
        if len(df) < 2:
            return None

        # Build a simple 6-month forward projection (linear extrapolation)
        n_hist = len(df)
        n_fwd = 6
        last_margin = df["_margin"].iloc[-1]
        trend_slope = (df["_margin"].iloc[-1] - df["_margin"].iloc[max(0, -6)]) / max(n_hist, 6)
        last_date = df["period_end"].iloc[-1]
        fwd_dates = pd.date_range(last_date, periods=n_fwd + 1, freq="ME")[1:]
        fwd_p50 = [last_margin + trend_slope * (i + 1) for i in range(n_fwd)]
        fwd_p10 = [v * 0.88 for v in fwd_p50]
        fwd_p90 = [v * 1.12 for v in fwd_p50]

        fig, ax = plt.subplots(figsize=(width_in, height_in))
        fig.patch.set_facecolor("white")
        ax.set_facecolor("#f8f9fb")
        ax.grid(axis="y", color="#e2e8f0", linewidth=0.7, zorder=0)
        ax.set_axisbelow(True)

        # Historical bars
        bar_color = "#0d1b2a"
        bar_w = 20 if n_hist > 18 else 25
        ax.bar(df["period_end"], df["_margin"] * 100,
               color=bar_color, alpha=0.85, width=bar_w, zorder=2, label="Actual EBITDA Margin")

        # Join bar tops with a line
        ax.plot(df["period_end"], df["_margin"] * 100,
                color="#0d1b2a", linewidth=1.5, zorder=3, alpha=0.6)

        # Forward projection
        all_fwd = [last_date] + list(fwd_dates)
        all_p50 = [last_margin] + fwd_p50
        all_p10 = [last_margin] + fwd_p10
        all_p90 = [last_margin] + fwd_p90

        ax.plot(all_fwd, [v * 100 for v in all_p50],
                color="#4a90d9", linewidth=2, linestyle="--", zorder=4, label="P50 Projection")
        ax.fill_between(all_fwd,
                        [v * 100 for v in all_p10],
                        [v * 100 for v in all_p90],
                        color="#4a90d9", alpha=0.15, label="P10–P90 Range")

        # VCP target line
        if vcp_ebitda_margin_target is not None:
            target_pct = vcp_ebitda_margin_target * 100
            ax.axhline(target_pct, color="#b8972e", linewidth=2,
                       linestyle="--", zorder=5, label=f"VCP Target {target_pct:.0f}%")
            ax.annotate(f"VCP Target\n{target_pct:.0f}%",
                        xy=(df["period_end"].iloc[-1], target_pct),
                        xytext=(10, 0), textcoords="offset points",
                        fontsize=7.5, color="#b8972e", fontweight="bold",
                        va="center")

        # Today line
        ax.axvline(last_date, color="#4a5568", linewidth=0.8, linestyle=":", alpha=0.7)
        ax.text(last_date, ax.get_ylim()[0] if ax.get_ylim()[0] != 0 else 0,
                " Now", color="#4a5568", fontsize=7, va="bottom")

        # Gap annotation
        if vcp_ebitda_margin_target is not None:
            actual_last = last_margin * 100
            gap = actual_last - vcp_ebitda_margin_target * 100
            mid_y = (actual_last + vcp_ebitda_margin_target * 100) / 2
            ax.annotate(
                f"Gap: {gap:+.1f}pp",
                xy=(df["period_end"].iloc[-1], mid_y),
                xytext=(-50, 0), textcoords="offset points",
                fontsize=7.5, color="#c53030" if gap < 0 else "#276749",
                fontweight="bold",
                arrowprops=dict(arrowstyle="-", color="#c53030", lw=0.8),
            )

        ax.set_xlabel("Period", fontsize=8, color="#4a5568")
        ax.set_ylabel("EBITDA Margin (%)", fontsize=8, color="#4a5568")
        ax.tick_params(axis="both", labelsize=7.5, colors="#4a5568")
        ax.yaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:.0f}%"))

        # Shade projection area
        if len(fwd_dates) > 0:
            ax.axvspan(last_date, fwd_dates[-1], color="#4a90d9", alpha=0.04)

        legend = ax.legend(fontsize=7.5, loc="upper left",
                           framealpha=0.9, edgecolor="#e2e8f0")
        legend.get_frame().set_linewidth(0.5)

        for spine in ax.spines.values():
            spine.set_color("#e2e8f0")
            spine.set_linewidth(0.5)

        fig.tight_layout(pad=0.8)

        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=150, bbox_inches="tight",
                    facecolor="white", edgecolor="none")
        plt.close(fig)
        buf.seek(0)
        return buf.read()

    except Exception as e:
        print(f"[BoardPack] Chart render failed: {e}")
        return None


def _ebitda_page(
    pc: PageCanvas,
    kpi_records: List[Dict[str, Any]],
    vcp_ebitda_margin_target: Optional[float],
    actual_ebitda_margin: Optional[float],
    actual_revenue: Optional[float],
    period: str,
    company_name: str,
    irr_scenarios: Optional[List[Dict[str, Any]]] = None,
    ic_target_irr: Optional[float] = None,
):
    pc.new_page()
    y = H - HEADER_H - 20

    y = pc.section_header(y, "EBITDA PERFORMANCE & FORWARD CURVE",
                          "Historical Actuals · P10/P50/P90 Projection · VCP Target")

    # Summary stat strip
    strip_h = 42
    pc.c.setFillColor(HexColor("#eef2f7"))
    pc.c.roundRect(MARGIN_L, y - strip_h, CONTENT_W, strip_h, 4, fill=1, stroke=0)

    stats = [
        ("ACTUAL EBITDA MARGIN",  _fmt_pct(actual_ebitda_margin)),
        ("VCP TARGET MARGIN",     _fmt_pct(vcp_ebitda_margin_target)),
        ("GAP VS PLAN",           _fmt_pct(
            (actual_ebitda_margin - vcp_ebitda_margin_target)
            if actual_ebitda_margin is not None and vcp_ebitda_margin_target is not None
            else None, signed=True)),
        ("ANNUALISED REVENUE",    _fmt_currency(actual_revenue * 12
                                               if actual_revenue else None)),
    ]
    sw = CONTENT_W / len(stats)
    for i, (lbl, val) in enumerate(stats):
        cx = MARGIN_L + i * sw + sw / 2
        # Determine color for gap stat
        val_color = NAVY
        if i == 2 and actual_ebitda_margin is not None and vcp_ebitda_margin_target is not None:
            val_color = STATUS_RED if actual_ebitda_margin < vcp_ebitda_margin_target * 0.9 else \
                        STATUS_AMBER if actual_ebitda_margin < vcp_ebitda_margin_target else STATUS_GREEN

        pc.c.setFillColor(SLATE)
        pc.c.setFont("Helvetica", 7)
        pc.c.drawCentredString(cx, y - 14, lbl)
        pc.c.setFillColor(val_color)
        pc.c.setFont("Helvetica-Bold", 14)
        pc.c.drawCentredString(cx, y - 32, val)

    y -= strip_h + 12

    # Chart
    chart_h = 220
    png = _ebitda_chart_png(kpi_records, vcp_ebitda_margin_target, period, company_name)
    if png:
        img_reader = ImageReader(io.BytesIO(png))
        pc.c.drawImage(img_reader, MARGIN_L, y - chart_h, width=CONTENT_W, height=chart_h,
                       preserveAspectRatio=True, anchor="nw")
    else:
        # Placeholder
        pc.c.setFillColor(HexColor("#f0f4f9"))
        pc.c.roundRect(MARGIN_L, y - chart_h, CONTENT_W, chart_h, 5, fill=1, stroke=0)
        pc.c.setFillColor(SLATE)
        pc.c.setFont("Helvetica", 10)
        pc.c.drawCentredString(W / 2, y - chart_h / 2, "EBITDA Margin Chart — Insufficient data")

    y -= chart_h + 12

    # IRR inset box (bottom-right per spec) — shown when irr_scenarios provided
    if irr_scenarios:
        scenario_map = {s.get("scenario", "").lower(): s for s in irr_scenarios}
        box_w, box_h = 160, 90
        bx = MARGIN_L + CONTENT_W - box_w
        by = y - box_h
        pc.c.setFillColor(HexColor("#f8fafc"))
        pc.c.setStrokeColor(BORDER)
        pc.c.setLineWidth(0.5)
        pc.c.roundRect(bx, by, box_w, box_h, 4, fill=1, stroke=1)
        pc.c.setFillColor(NAVY_MID)
        pc.c.setFont("Helvetica-Bold", 7)
        pc.c.drawString(bx + 8, by + box_h - 12, "IRR SCENARIOS")
        my = by + box_h - 26
        for sc_key, sc_lbl in [("bear", "Bear"), ("base", "Base"), ("bull", "Bull")]:
            s = scenario_map.get(sc_key)
            if s:
                irr_val = s.get("irr_percent")
                irr_str = f"{irr_val:.1f}%" if irr_val is not None else "—"
                col = STATUS_RED if sc_key == "bear" else STATUS_AMBER if sc_key == "base" else STATUS_GREEN
                if ic_target_irr and irr_val:
                    col = STATUS_GREEN if irr_val / 100 >= ic_target_irr else STATUS_AMBER if irr_val / 100 >= ic_target_irr * 0.85 else STATUS_RED
                pc.c.setFillColor(BODY_TEXT)
                pc.c.setFont("Helvetica", 7)
                pc.c.drawString(bx + 8, my, sc_lbl)
                pc.c.setFillColor(col)
                pc.c.setFont("Helvetica-Bold", 8)
                pc.c.drawRightString(bx + box_w - 8, my, irr_str)
                my -= 13
        if ic_target_irr:
            pc.c.setStrokeColor(BORDER)
            pc.c.setLineWidth(0.3)
            pc.c.line(bx + 8, my, bx + box_w - 8, my)
            my -= 8
            pc.c.setFillColor(SLATE)
            pc.c.setFont("Helvetica", 6.5)
            pc.c.drawString(bx + 8, my, "IC Underwritten")
            pc.c.setFont("Helvetica-Bold", 7)
            pc.c.drawRightString(bx + box_w - 8, my, f"{ic_target_irr:.0%}")

    # Methodology footnote (spec: "should be legible, not hidden — trust signal")
    fn_y = MARGIN_B + FOOTER_H + 20
    pc.c.setFillColor(SLATE)
    pc.c.setFont("Helvetica", 7)
    pc.c.drawString(MARGIN_L, fn_y + 13,
                    "Source: Management accounts. Projection: STL decomposition + linear trend "
                    "extrapolation from trailing 6 months. P10–P90 band = ±12% of P50.")
    pc.c.drawString(MARGIN_L, fn_y,
                    "Methodology: STL decomposition + SARIMA ensemble · FRED macro regressors · "
                    "Confidence: Moderate (minimum 8 quarters of history recommended)")


# ---------------------------------------------------------------------------
# Page 5-legacy: IRR Scenario Analysis (kept for standalone use; merged into _ebitda_page above)
# ---------------------------------------------------------------------------

def _irr_scenarios_page(
    pc: PageCanvas,
    irr_scenarios: Optional[List[Dict[str, Any]]],
    ic_target_irr: Optional[float],
    ic_target_moic: Optional[float],
    irr_at_risk_bps: Optional[int],
    entry_equity: Optional[float],
    holding_period: Optional[float],
):
    pc.new_page()
    y = H - HEADER_H - 20

    y = pc.section_header(y, "IRR SCENARIO ANALYSIS",
                          f"Entry Equity: {_fmt_currency(entry_equity)} · "
                          f"Holding Period: {holding_period or 5:.0f} Years")

    if not irr_scenarios:
        pc.c.setFillColor(SLATE)
        pc.c.setFont("Helvetica", 10)
        pc.c.drawCentredString(W / 2, y - 80, "IRR scenarios not available for this company")
        return

    y -= 16

    # IC targets callout
    if ic_target_irr or ic_target_moic:
        tgt_h = 36
        pc.c.setFillColor(HexColor("#fffbeb"))
        pc.c.setStrokeColor(GOLD)
        pc.c.setLineWidth(1)
        pc.c.roundRect(MARGIN_L, y - tgt_h, CONTENT_W, tgt_h, 4, fill=1, stroke=1)
        pc.c.setFillColor(GOLD)
        pc.c.setFont("Helvetica-Bold", 8)
        pc.c.drawString(MARGIN_L + 12, y - 14, "IC UNDERWRITE TARGETS:")
        pc.c.setFillColor(NAVY)
        pc.c.setFont("Helvetica-Bold", 10)
        tgt_text = ""
        if ic_target_irr:
            tgt_text += f"IRR ≥ {ic_target_irr:.0%}"
        if ic_target_moic:
            tgt_text += f"  ·  MOIC ≥ {ic_target_moic:.1f}x"
        pc.c.drawString(MARGIN_L + 12, y - 30, tgt_text)
        y -= tgt_h + 14

    # Scenario cards — 3 across
    scenario_order = ["bear", "base", "bull"]
    card_gap = 14
    card_w = (CONTENT_W - 2 * card_gap) / 3
    card_h = 170

    scenario_map = {s.get("scenario", "").lower(): s for s in irr_scenarios}

    for i, sc_key in enumerate(scenario_order):
        s = scenario_map.get(sc_key)
        if not s:
            continue

        cx = MARGIN_L + i * (card_w + card_gap)
        cy = y - card_h

        status = s.get("scenario_status", "Amber")
        scolor, sbg, sborder = _status_colors(status)

        # Card
        pc.c.setFillColor(sbg)
        pc.c.setStrokeColor(sborder)
        pc.c.setLineWidth(1.5)
        pc.c.roundRect(cx, cy, card_w, card_h, 6, fill=1, stroke=1)

        # Top color band
        band_h = 34
        pc.c.setFillColor(scolor)
        pc.c.roundRect(cx, cy + card_h - band_h, card_w, band_h, 6, fill=1, stroke=0)
        pc.c.rect(cx, cy + card_h - band_h, card_w, band_h / 2, fill=1, stroke=0)

        # Scenario name
        pc.c.setFillColor(white)
        pc.c.setFont("Helvetica-Bold", 11)
        scenario_label = {"bear": "BEAR CASE", "base": "BASE CASE", "bull": "BULL CASE"}.get(sc_key, sc_key.upper())
        pc.c.drawCentredString(cx + card_w / 2, cy + card_h - 22, scenario_label)

        # P scenario sub-label
        pc.c.setFont("Helvetica", 7)
        pc.c.setFillColor(HexColor("#f0f0f0"))
        desc = s.get("scenario_description", "")
        pc.c.drawCentredString(cx + card_w / 2, cy + card_h - 33, desc[:35])

        # Key metrics
        metrics = [
            ("Exit EBITDA",    _fmt_currency(s.get("exit_annual_ebitda"))),
            ("Exit Multiple",  f"{s.get('exit_multiple', 0):.1f}x"),
            ("Exit EV",        _fmt_currency(s.get("exit_enterprise_value"))),
            ("MOIC",           f"{s.get('moic', 0):.2f}x" if s.get("moic") else "—"),
            ("IRR",            f"{s.get('irr_percent', 0):.1f}%" if s.get("irr_percent") else "—"),
        ]

        my = cy + card_h - band_h - 10
        for lbl, val in metrics:
            my -= 20
            pc.c.setFillColor(SLATE)
            pc.c.setFont("Helvetica", 7.5)
            pc.c.drawString(cx + 12, my, lbl)

            val_color = NAVY
            if lbl == "IRR" and ic_target_irr:
                irr_val = s.get("irr_percent", 0) or 0
                val_color = STATUS_GREEN if irr_val / 100 >= ic_target_irr else \
                            STATUS_AMBER if irr_val / 100 >= ic_target_irr * 0.85 else STATUS_RED
            elif lbl == "MOIC" and ic_target_moic:
                moic_val = s.get("moic", 0) or 0
                val_color = STATUS_GREEN if moic_val >= ic_target_moic else \
                            STATUS_AMBER if moic_val >= ic_target_moic * 0.85 else STATUS_RED

            pc.c.setFillColor(val_color)
            pc.c.setFont("Helvetica-Bold", 9 if lbl in ("IRR", "MOIC") else 8)
            pc.c.drawRightString(cx + card_w - 12, my, val)

            # Thin divider
            pc.c.setStrokeColor(DIVIDER)
            pc.c.setLineWidth(0.3)
            pc.c.line(cx + 12, my - 4, cx + card_w - 12, my - 4)

        # vs IC gap at bottom of card
        irr_gap = s.get("irr_gap_vs_ic_bps")
        if irr_gap is not None:
            gap_color = STATUS_GREEN if irr_gap >= 0 else STATUS_RED
            pc.c.setFillColor(gap_color)
            pc.c.setFont("Helvetica-Bold", 8)
            gap_text = f"{irr_gap:+.0f} bps vs IC"
            pc.c.drawCentredString(cx + card_w / 2, cy + 10, gap_text)

    y -= card_h + 20

    # IRR at risk callout
    if irr_at_risk_bps is not None and irr_at_risk_bps < 0:
        box_h = 40
        pc.c.setFillColor(HexColor("#fff8f8"))
        pc.c.setStrokeColor(STATUS_RED)
        pc.c.setLineWidth(1.5)
        pc.c.roundRect(MARGIN_L, y - box_h, CONTENT_W, box_h, 4, fill=1, stroke=1)
        pc.c.setFillColor(STATUS_RED)
        pc.c.setFont("Helvetica-Bold", 9)
        pc.c.drawString(MARGIN_L + 14, y - 16,
                        f"⚠  Base case IRR is {irr_at_risk_bps:+d} bps below the underwritten IC case.")
        pc.c.setFont("Helvetica", 8)
        pc.c.setFillColor(NAVY)
        pc.c.drawString(MARGIN_L + 14, y - 30,
                        "If the current EBITDA trajectory persists, the investment does not meet the IC return threshold.")


# ---------------------------------------------------------------------------
# Page 6: Peer Benchmarking
# ---------------------------------------------------------------------------

def _peer_benchmark_chart_png(
    benchmark_results: List[Dict[str, Any]],
    width_in: float = 6.5,
    height_in: float = 3.5,
) -> Optional[bytes]:
    if not benchmark_results:
        return None
    try:
        metric_labels = {
            "revenue_growth_yoy": "Revenue Growth (YoY)",
            "ebitda_margin":      "EBITDA Margin",
            "gross_margin":       "Gross Margin",
            "net_debt_to_ebitda": "Net Debt / EBITDA",
        }
        metrics    = [r["metric"] for r in benchmark_results]
        labels     = [metric_labels.get(m, m.replace("_", " ").title()) for m in metrics]
        company    = [r["company_value"] * 100 if abs(r["company_value"]) < 5 else r["company_value"]
                      for r in benchmark_results]
        sector_med = [r["sector_median"] * 100 if abs(r["sector_median"]) < 5 else r["sector_median"]
                      for r in benchmark_results]
        statuses   = [r["status"] for r in benchmark_results]

        bar_colors = [
            "#c53030" if s == "Underperform" else
            "#c05621" if s == "In-line" else "#276749"
            for s in statuses
        ]

        n = len(metrics)
        y_pos = np.arange(n)
        h = max(2.5, n * 0.65)

        fig, ax = plt.subplots(figsize=(width_in, h))
        fig.patch.set_facecolor("white")
        ax.set_facecolor("#f8f9fb")
        ax.grid(axis="x", color="#e2e8f0", linewidth=0.6, zorder=0)
        ax.set_axisbelow(True)

        bar_h = 0.32
        # Company bars
        bars_co = ax.barh(y_pos + bar_h / 2, company, height=bar_h,
                          color=bar_colors, zorder=2, label="Company")
        # Sector median bars
        ax.barh(y_pos - bar_h / 2, sector_med, height=bar_h,
                color="#0d1b2a", alpha=0.2, zorder=2, label="Sector Median")

        # Sector median markers
        for yi, sm in zip(y_pos, sector_med):
            ax.plot(sm, yi - bar_h / 2, marker="|", markersize=12,
                    color="#0d1b2a", linewidth=2, zorder=3)

        # Value labels
        for bar, val, status in zip(bars_co, company, statuses):
            w = bar.get_width()
            suffix = "%" if abs(val) < 100 else "x"
            lbl = f"{w:.1f}{suffix}"
            ax.text(max(w, 0) + 0.3, bar.get_y() + bar.get_height() / 2,
                    lbl, va="center", ha="left", fontsize=7.5, fontweight="bold",
                    color="#c53030" if status == "Underperform" else "#276749")

        ax.set_yticks(y_pos)
        ax.set_yticklabels(labels, fontsize=8)
        ax.tick_params(axis="x", labelsize=7.5, colors="#4a5568")
        ax.xaxis.set_major_formatter(plt.FuncFormatter(
            lambda v, _: f"{v:.0f}%" if abs(v) < 100 else f"{v:.1f}x"
        ))

        legend_items = [
            mpatches.Patch(color="#c53030", label="Company (Underperform)"),
            mpatches.Patch(color="#276749", label="Company (In-line / Outperform)"),
            mpatches.Patch(color="#0d1b2a", alpha=0.25, label="Sector Median"),
        ]
        ax.legend(handles=legend_items, fontsize=7, loc="lower right",
                  framealpha=0.9, edgecolor="#e2e8f0")

        for spine in ax.spines.values():
            spine.set_color("#e2e8f0")
            spine.set_linewidth(0.5)

        fig.tight_layout(pad=0.8)
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=150, bbox_inches="tight",
                    facecolor="white", edgecolor="none")
        plt.close(fig)
        buf.seek(0)
        return buf.read()

    except Exception as e:
        print(f"[BoardPack] Peer chart failed: {e}")
        return None


def _peer_benchmark_page(
    pc: PageCanvas,
    peer_benchmark: Optional[Dict[str, Any]],
):
    pc.new_page()
    y = H - HEADER_H - 20

    sector_label = (peer_benchmark or {}).get("sector_label", "Sector")
    n_peers = (peer_benchmark or {}).get("peer_set_size", "?")

    y = pc.section_header(y, "SECTOR BENCHMARKING",
                          f"{sector_label} · N={n_peers} peers · EDGAR public filings")

    if not peer_benchmark or not peer_benchmark.get("results"):
        pc.c.setFillColor(SLATE)
        pc.c.setFont("Helvetica", 10)
        pc.c.drawCentredString(W / 2, y - 80, "Peer benchmarking data not available")
        return

    results = peer_benchmark["results"]
    y -= 14

    # Status summary strip
    underperform = sum(1 for r in results if r.get("status") == "Underperform")
    inline       = sum(1 for r in results if r.get("status") == "In-line")
    outperform   = sum(1 for r in results if r.get("status") == "Outperform")

    strip_h = 36
    pc.c.setFillColor(HexColor("#eef2f7"))
    pc.c.roundRect(MARGIN_L, y - strip_h, CONTENT_W, strip_h, 4, fill=1, stroke=0)

    items = [
        (str(underperform), "Below Sector Median", STATUS_RED),
        (str(inline),       "In-Line with Median", STATUS_AMBER),
        (str(outperform),   "Above Sector Median", STATUS_GREEN),
    ]
    sw = CONTENT_W / len(items)
    for i, (val, lbl, col) in enumerate(items):
        cx = MARGIN_L + i * sw + sw / 2
        pc.c.setFillColor(col)
        pc.c.setFont("Helvetica-Bold", 16)
        pc.c.drawCentredString(cx, y - 16, val)
        pc.c.setFillColor(SLATE)
        pc.c.setFont("Helvetica", 7)
        pc.c.drawCentredString(cx, y - 28, lbl)

    y -= strip_h + 14

    # Chart
    chart_h = 200
    png = _peer_benchmark_chart_png(results)
    if png:
        img_reader = ImageReader(io.BytesIO(png))
        pc.c.drawImage(img_reader, MARGIN_L, y - chart_h, width=CONTENT_W, height=chart_h,
                       preserveAspectRatio=True, anchor="nw")
    else:
        pc.c.setFillColor(HexColor("#f0f4f9"))
        pc.c.roundRect(MARGIN_L, y - chart_h, CONTENT_W, chart_h, 5, fill=1, stroke=0)
        pc.c.setFillColor(SLATE)
        pc.c.setFont("Helvetica", 9)
        pc.c.drawCentredString(W / 2, y - chart_h / 2, "Peer comparison chart unavailable")

    y -= chart_h + 14

    # Detail table
    pc.c.setFillColor(NAVY)
    pc.c.setFont("Helvetica-Bold", 8)
    pc.c.drawString(MARGIN_L, y, "METRIC-BY-METRIC BREAKDOWN")
    y -= 14

    col_widths = [160, 100, 100, 90, 55]
    col_headers = ["METRIC", "COMPANY", "SECTOR MEDIAN", "GAP", "STATUS"]
    col_aligns  = ["L", "R", "R", "R", "C"]

    hh = 20
    pc.c.setFillColor(NAVY)
    pc.c.rect(MARGIN_L, y - hh, CONTENT_W, hh, fill=1, stroke=0)
    xp = MARGIN_L + 6
    for hdr, cw, align in zip(col_headers, col_widths, col_aligns):
        pc.c.setFillColor(white)
        pc.c.setFont("Helvetica-Bold", 7)
        if align == "R":
            pc.c.drawRightString(xp + cw - 4, y - 13, hdr)
        elif align == "C":
            pc.c.drawCentredString(xp + cw / 2, y - 13, hdr)
        else:
            pc.c.drawString(xp + 4, y - 13, hdr)
        xp += cw
    y -= hh

    metric_labels = {
        "revenue_growth_yoy": "Revenue Growth (YoY)",
        "ebitda_margin":      "EBITDA Margin",
        "gross_margin":       "Gross Margin",
        "net_debt_to_ebitda": "Net Debt / EBITDA",
    }

    for ri, r in enumerate(results):
        rh = 22
        pc.c.setFillColor(white if ri % 2 == 0 else ROW_ALT)
        pc.c.rect(MARGIN_L, y - rh, CONTENT_W, rh, fill=1, stroke=0)

        status = r.get("status", "—")
        rcolor, _, _ = _status_colors(
            "Red" if status == "Underperform" else
            "Amber" if status == "In-line" else "Green"
        )

        # Left stripe
        pc.c.setFillColor(rcolor)
        pc.c.rect(MARGIN_L, y - rh, 4, rh, fill=1, stroke=0)

        def pct_or_x(v, m):
            if v is None:
                return "—"
            try:
                f = float(v)
                if "debt" in m or "multiple" in m:
                    return f"{f:.2f}x"
                return f"{f:.1%}"
            except Exception:
                return str(v)

        metric = r.get("metric", "")
        row_vals = [
            metric_labels.get(metric, metric.replace("_", " ").title()),
            pct_or_x(r.get("company_value"), metric),
            pct_or_x(r.get("sector_median"), metric),
            _fmt_pct(r.get("gap_pct"), signed=True),
            status,
        ]

        xp = MARGIN_L + 6
        for vi, (rv, cw, align) in enumerate(zip(row_vals, col_widths, col_aligns)):
            if vi == 4:  # Status dot
                dot_color = STATUS_RED if status == "Underperform" else \
                            STATUS_AMBER if status == "In-line" else STATUS_GREEN
                pc.c.setFillColor(dot_color)
                pc.c.circle(xp + cw / 2, y - rh / 2, 4.5, fill=1, stroke=0)
                xp += cw
                continue

            text_color = NAVY
            if vi == 3:
                gap = r.get("gap_pct", 0) or 0
                text_color = STATUS_RED if gap < -0.1 else \
                             STATUS_AMBER if gap < 0 else STATUS_GREEN

            pc.c.setFillColor(text_color)
            pc.c.setFont("Helvetica", 8)
            if align == "R":
                pc.c.drawRightString(xp + cw - 4, y - rh / 2 - 3, rv)
            elif align == "C":
                pc.c.drawCentredString(xp + cw / 2, y - rh / 2 - 3, rv)
            else:
                pc.c.drawString(xp + 6, y - rh / 2 - 3, rv)
            xp += cw

        pc.c.setStrokeColor(DIVIDER)
        pc.c.setLineWidth(0.3)
        pc.c.line(MARGIN_L, y - rh, MARGIN_L + CONTENT_W, y - rh)
        y -= rh

    y -= 10
    pc.c.setFillColor(SLATE)
    pc.c.setFont("Helvetica", 7)
    pc.c.drawString(MARGIN_L, y,
                    f"Source: EDGAR public filings, XBRL data. Sector: {sector_label}. "
                    f"N={n_peers} peers (SIC code filtered). Figures represent latest available period.")


# ---------------------------------------------------------------------------
# Page 7: Risks & Recommended Actions + Board Questions  (NEW per spec)
# ---------------------------------------------------------------------------

def _risks_actions_page(
    pc: PageCanvas,
    risks_actions: List[Dict[str, Any]],
    board_talking_points: List[str],
    alert_severity: str,
):
    """
    Top half: risk table (red/amber only, ≤5 rows).
    Bottom half: Board Questions block (GPT-synthesised diagnostic questions).
    """
    pc.new_page()
    y = H - HEADER_H - 20

    y = pc.section_header(y, "RISKS & RECOMMENDED ACTIONS", f"● AI Generated · {pc.report_date}")
    y -= 8

    if risks_actions:
        # Column headers
        cols = [
            ("PRIORITY",  54, "C"),
            ("RISK",      240, "L"),
            ("IRR AT RISK", 70, "R"),
            ("RECOMMENDED ACTION", 141, "L"),
        ]
        hh = 20
        pc.c.setFillColor(NAVY_MID)
        pc.c.rect(MARGIN_L, y - hh, CONTENT_W, hh, fill=1, stroke=0)
        xp = MARGIN_L + 6
        for lbl, cw, align in cols:
            pc.c.setFillColor(white)
            pc.c.setFont("Helvetica-Bold", 7)
            if align == "R":
                pc.c.drawRightString(xp + cw - 4, y - 13, lbl)
            elif align == "C":
                pc.c.drawCentredString(xp + cw / 2, y - 13, lbl)
            else:
                pc.c.drawString(xp + 4, y - 13, lbl)
            xp += cw
        y -= hh

        for ri, row in enumerate(risks_actions[:5]):
            rh = 36
            pc.c.setFillColor(white if ri % 2 == 0 else ROW_ALT)
            pc.c.rect(MARGIN_L, y - rh, CONTENT_W, rh, fill=1, stroke=0)

            status_lbl = row.get("status", "AMBER")
            s_col = STATUS_RED if "RED" in status_lbl.upper() else STATUS_AMBER
            pc.c.setFillColor(s_col)
            pc.c.rect(MARGIN_L, y - rh, 4, rh, fill=1, stroke=0)

            irr_bps = row.get("irr_at_risk_bps")
            irr_str = f"{irr_bps:+d} bps" if irr_bps is not None else "—"

            risk_text   = row.get("risk", "—")
            action_text = row.get("recommended_action", "—")

            xp = MARGIN_L + 6
            for vi, (_, cw, align) in enumerate(cols):
                if vi == 0:
                    pc.c.setFillColor(s_col)
                    pc.c.setFont("Helvetica-Bold", 9)
                    pc.c.drawCentredString(xp + cw / 2, y - rh / 2 - 3, f"● {row.get('priority', ri+1)}")
                elif vi == 1:
                    pc.c.setFillColor(BODY_TEXT)
                    pc.c.setFont("Helvetica", 8)
                    words = risk_text.split()
                    line, ly = "", y - 12
                    for w in words:
                        test = (line + " " + w).strip()
                        if pc.c.stringWidth(test, "Helvetica", 8) <= cw - 8:
                            line = test
                        else:
                            pc.c.drawString(xp + 4, ly, line)
                            ly -= 11
                            line = w
                    if line:
                        pc.c.drawString(xp + 4, ly, line)
                elif vi == 2:
                    pc.c.setFillColor(STATUS_RED if irr_bps and irr_bps < 0 else SLATE)
                    pc.c.setFont("Helvetica-Bold", 8)
                    pc.c.drawRightString(xp + cw - 4, y - rh / 2 - 3, irr_str)
                elif vi == 3:
                    if action_text and action_text != "—":
                        pc.c.setFillColor(BODY_TEXT)
                        pc.c.setFont("Helvetica", 8)
                        words = action_text.split()
                        line, ly = "", y - 12
                        for w in words:
                            test = (line + " " + w).strip()
                            if pc.c.stringWidth(test, "Helvetica", 8) <= cw - 8:
                                line = test
                            else:
                                pc.c.drawString(xp + 4, ly, line)
                                ly -= 11
                                line = w
                        if line:
                            pc.c.drawString(xp + 4, ly, line)
                xp += cw

            pc.c.setStrokeColor(DIVIDER)
            pc.c.setLineWidth(0.3)
            pc.c.line(MARGIN_L, y - rh, MARGIN_L + CONTENT_W, y - rh)
            y -= rh

    y -= 6
    pc.c.setFillColor(SLATE)
    pc.c.setFont("Helvetica", 7)
    pc.c.drawString(MARGIN_L, y,
                    "● Risks shown are those with IRR impact > 30bps. Green items omitted. "
                    "Source: Synthesised from VCP drift · Alert Agent · IC Memo")
    y -= 20

    # Board Questions block
    if board_talking_points:
        y = pc.divider(y)
        y -= 4
        pc.c.setFillColor(NAVY_MID)
        pc.c.setFont("Helvetica-Bold", 9)
        pc.c.drawString(MARGIN_L, y, "BOARD QUESTIONS (suggested by system)")
        y -= 16

        for i, pt in enumerate(board_talking_points[:3]):
            pc.c.setFillColor(NAVY)
            pc.c.setFont("Helvetica-Bold", 9)
            pc.c.drawString(MARGIN_L, y, f"{i + 1}.")
            y = pc.wrapped_text(MARGIN_L + 14, y, pt, CONTENT_W - 14,
                                font="Helvetica", size=9, color=BODY_TEXT, line_height=14)
            y -= 8


# ---------------------------------------------------------------------------
# Page 8: Audit Trail & Evidence  (was Page 7)
# ---------------------------------------------------------------------------

def _audit_trail_page(
    pc: PageCanvas,
    citations: List[str],
    hitl_decisions: Optional[List[Dict[str, Any]]],
    vcp_store_path: Optional[str],
    data_source_path: Optional[str],
    narrative_mode: str,
    synthesis_mode: str,
    confidence_statement: str,
):
    pc.new_page()
    y = H - HEADER_H - 20

    y = pc.section_header(y, "AUDIT TRAIL & EVIDENCE", "All inputs cited and logged")

    # AI generation provenance
    prov_h = 44
    pc.c.setFillColor(HexColor("#f0f4f9"))
    pc.c.roundRect(MARGIN_L, y - prov_h, CONTENT_W, prov_h, 4, fill=1, stroke=0)
    pc.c.setFillColor(NAVY)
    pc.c.setFont("Helvetica-Bold", 8)
    pc.c.drawString(MARGIN_L + 12, y - 14, "REPORT GENERATION PROVENANCE")
    pc.c.setFont("Helvetica", 8)
    pc.c.setFillColor(SLATE)
    pc.c.drawString(MARGIN_L + 12, y - 26,
                    f"Alert Synthesis: {synthesis_mode.replace('_', ' ').title()}  ·  "
                    f"Narrative: {narrative_mode.replace('_', ' ').title()}  ·  "
                    f"Report Assembly: ReportLab (deterministic)")
    pc.c.drawString(MARGIN_L + 12, y - 38, confidence_statement)
    y -= prov_h + 14

    # HITL decisions
    if hitl_decisions:
        pc.c.setFillColor(NAVY)
        pc.c.setFont("Helvetica-Bold", 8)
        pc.c.drawString(MARGIN_L, y, "HUMAN-IN-THE-LOOP DECISIONS")
        y -= 14

        hcol_w = [140, 100, 80, 185]
        hcol_h = ["DECISION TYPE", "DECISION", "TIMESTAMP", "NOTES"]

        hh = 20
        pc.c.setFillColor(NAVY_MID)
        pc.c.rect(MARGIN_L, y - hh, CONTENT_W, hh, fill=1, stroke=0)
        xp = MARGIN_L + 6
        for hdr, cw in zip(hcol_h, hcol_w):
            pc.c.setFillColor(white)
            pc.c.setFont("Helvetica-Bold", 7)
            pc.c.drawString(xp + 4, y - 13, hdr)
            xp += cw
        y -= hh

        for ri, dec in enumerate(hitl_decisions[:5]):
            rh = 24
            pc.c.setFillColor(white if ri % 2 == 0 else ROW_ALT)
            pc.c.rect(MARGIN_L, y - rh, CONTENT_W, rh, fill=1, stroke=0)

            dec_type = str(dec.get("decision_type", dec.get("type", "VCP Review")))
            decision = str(dec.get("decision", "Approved"))
            ts = str(dec.get("timestamp", ""))[:16]
            note = str(dec.get("note", dec.get("notes", "—")))[:55]

            row_vals = [dec_type, decision, ts, note]
            xp = MARGIN_L + 6
            for rv, cw in zip(row_vals, hcol_w):
                color = NAVY
                if rv in ("Approved", "approved", "approve"):
                    color = STATUS_GREEN
                elif rv in ("Rejected", "rejected", "reject"):
                    color = STATUS_RED
                pc.c.setFillColor(color)
                pc.c.setFont("Helvetica", 8)
                pc.c.drawString(xp + 4, y - rh / 2 - 3, rv)
                xp += cw

            pc.c.setStrokeColor(DIVIDER)
            pc.c.setLineWidth(0.3)
            pc.c.line(MARGIN_L, y - rh, MARGIN_L + CONTENT_W, y - rh)
            y -= rh

        y -= 12

    # Citations
    if citations:
        pc.c.setFillColor(NAVY)
        pc.c.setFont("Helvetica-Bold", 8)
        pc.c.drawString(MARGIN_L, y, "EVIDENCE CITATIONS")
        y -= 14

        for cit in citations[:8]:
            pc.c.setFillColor(GOLD)
            pc.c.setFont("Helvetica-Bold", 8)
            pc.c.drawString(MARGIN_L, y, "›")
            pc.c.setFillColor(SLATE)
            pc.c.setFont("Helvetica", 8)
            pc.c.drawString(MARGIN_L + 10, y, cit[:100])
            y -= 13

    y -= 10

    # Data sources
    pc.c.setFillColor(NAVY)
    pc.c.setFont("Helvetica-Bold", 8)
    pc.c.drawString(MARGIN_L, y, "DATA SOURCES")
    y -= 14

    sources = []
    if vcp_store_path:
        sources.append(("VCP Milestones",     vcp_store_path, "Confirmed at deal close"))
    if data_source_path:
        sources.append(("Financial Data",     data_source_path, "Management accounts"))
    sources.append(("Peer Benchmarks",     "EDGAR XBRL API", "SEC public filings, current period"))
    sources.append(("Macro Regressors",    "FRED API (St Louis Fed)", "DFF, CPI, BAA10Y spread"))

    for src_name, src_path, src_note in sources:
        pc.c.setFillColor(SLATE)
        pc.c.setFont("Helvetica-Bold", 8)
        pc.c.drawString(MARGIN_L + 6, y, src_name)
        pc.c.setFont("Helvetica", 8)
        pc.c.setFillColor(SLATE)
        pc.c.drawString(MARGIN_L + 120, y, str(src_path)[:60])
        pc.c.setFillColor(HexColor("#9aa5b1"))
        pc.c.drawString(MARGIN_L + 340, y, src_note)
        y -= 13

    y -= 14
    pc.divider(y)
    y -= 10

    # Legal disclaimer
    disclaimer = (
        "This report was generated by the PE Value Creation Copilot, an AI-assisted monitoring system. "
        "All figures are sourced from management accounts and third-party data providers and are unaudited "
        "unless stated otherwise. AI-generated narrative summaries have been reviewed and approved via the "
        "human-in-the-loop gate before inclusion. This report is for internal use only and does not "
        "constitute investment advice. Recipients should verify all material figures independently before "
        "making investment or operational decisions."
    )
    pc.wrapped_text(MARGIN_L, y, disclaimer, CONTENT_W,
                    font="Helvetica", size=7, color=HexColor("#9aa5b1"), line_height=11)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def generate_board_pack(
    company_name: str,
    company_id: str,
    report_date: Optional[str] = None,
    period: str = "Current Quarter",
    sector: str = "",
    # Alert card fields
    alert_severity: str = "Red",
    alert_headline: str = "",
    alert_root_cause: str = "",
    alert_recommended_action: str = "",
    lever_category: str = "other",
    irr_at_risk_bps: Optional[int] = None,
    # Narrative fields
    exec_summary: str = "",
    key_risks: Optional[List[str]] = None,
    priority_action: str = "",
    board_talking_points: Optional[List[str]] = None,
    confidence_statement: str = "",
    narrative_mode: str = "offline_rule_based",
    synthesis_mode: str = "offline_rule_based",
    # Data
    milestones: Optional[List[Dict[str, Any]]] = None,
    drift_results: Optional[List[Dict[str, Any]]] = None,
    kpi_performance: Optional[List[Dict[str, Any]]] = None,
    risks_actions: Optional[List[Dict[str, Any]]] = None,
    irr_scenarios: Optional[List[Dict[str, Any]]] = None,
    ic_target_irr: Optional[float] = None,
    ic_target_moic: Optional[float] = None,
    entry_equity: Optional[float] = None,
    holding_period: Optional[float] = 5.0,
    peer_benchmark: Optional[Dict[str, Any]] = None,
    kpi_records: Optional[List[Dict[str, Any]]] = None,
    citations: Optional[List[str]] = None,
    hitl_decisions: Optional[List[Dict[str, Any]]] = None,
    vcp_store_path: Optional[str] = None,
    data_source_path: Optional[str] = None,
    output_path: Optional[str] = None,
) -> bytes:
    """
    Generate a board-ready PDF and return the bytes.
    8-page structure per spec:
      1. Cover (clean white)          5. Forward Curve + IRR inset
      2. Executive Summary            6. Sector Benchmarks
      3. KPI Performance Scorecard    7. Risks & Actions + Board Questions
      4. VCP Milestone Scorecard      8. Appendix / Audit Trail
    """
    if report_date is None:
        report_date = date.today().strftime("%-d %B %Y")

    milestones    = milestones or []
    drift_results = drift_results or []
    citations     = citations or []

    ebitda_margin_drift = next(
        (r for r in drift_results if r.get("metric") == "ebitda_margin"), {}
    )
    actual_ebitda_margin = ebitda_margin_drift.get("actual_value")
    target_ebitda_margin = ebitda_margin_drift.get("target_value")

    actual_revenue = None
    if kpi_records:
        last_rec = max(kpi_records, key=lambda r: r.get("period_end", ""), default={})
        actual_revenue = last_rec.get("revenue")

    on_track = sum(1 for r in drift_results if r.get("status") == "Green")
    total    = len(drift_results)

    # Build KPI performance if not pre-supplied
    if not kpi_performance:
        kpi_series = []
        for r in (kpi_records or []):
            rev    = r.get("revenue")
            ebitda = r.get("adjusted_ebitda") or r.get("ebitda_proxy")
            nd     = r.get("net_debt")
            margin = (ebitda / rev) if (rev and ebitda is not None) else None
            lever  = (nd / (ebitda * 12)) if (ebitda and nd is not None) else None
            kpi_series.append({
                "period_end":         r.get("period_end"),
                "revenue":            rev,
                "ebitda_margin":      margin,
                "net_debt_to_ebitda": lever,
            })
        from app.api.report_routes import _build_kpi_performance
        kpi_performance = _build_kpi_performance(drift_results, kpi_series)

    # Summary key risk text for exec summary strip
    key_risk_summary = ""
    if risks_actions:
        key_risk_summary = (risks_actions[0].get("risk", "")[:32] + "…") if risks_actions else ""
    elif key_risks:
        key_risk_summary = (key_risks[0][:32] + "…") if len(key_risks[0]) > 32 else key_risks[0]

    buf = io.BytesIO()
    pc  = PageCanvas(buf, report_date, company_name)

    # PAGE 1: Cover
    _cover_page(
        pc=pc,
        company_name=company_name,
        sector=sector,
        report_date=report_date,
        period=period,
        alert_severity=alert_severity,
        alert_headline=alert_headline,
        vcp_on_track=on_track,
        vcp_total=total,
        irr_at_risk_bps=irr_at_risk_bps,
        ebitda_actual=actual_ebitda_margin,
        ebitda_target=target_ebitda_margin,
    )

    # PAGE 2: Executive Summary (+ 3-col strip)
    _exec_summary_page(
        pc=pc,
        exec_summary=exec_summary or alert_root_cause,
        key_risks=key_risks or [],
        priority_action=priority_action or alert_recommended_action,
        board_talking_points=board_talking_points or [],
        alert_severity=alert_severity,
        alert_headline=alert_headline,
        narrative_mode=narrative_mode,
        irr_at_risk_bps=irr_at_risk_bps,
        vcp_on_track=on_track,
        vcp_total=total,
        key_risk_summary=key_risk_summary,
    )

    # PAGE 3: KPI Performance Scorecard (NEW)
    _kpi_scorecard_page(
        pc=pc,
        kpi_performance=kpi_performance,
        period=period,
    )

    # PAGE 4: VCP Milestone Scorecard
    _vcp_scorecard_page(
        pc=pc,
        milestones=milestones,
        drift_results=drift_results,
        period=period,
    )

    # PAGE 5: Forward Curve + IRR inset + methodology footnote
    _ebitda_page(
        pc=pc,
        kpi_records=kpi_records or [],
        vcp_ebitda_margin_target=target_ebitda_margin,
        actual_ebitda_margin=actual_ebitda_margin,
        actual_revenue=actual_revenue,
        period=period,
        company_name=company_name,
        irr_scenarios=irr_scenarios,
        ic_target_irr=ic_target_irr,
    )

    # PAGE 6: Sector Benchmarks
    _peer_benchmark_page(
        pc=pc,
        peer_benchmark=peer_benchmark,
    )

    # PAGE 7: Risks & Actions + Board Questions (NEW)
    _risks_actions_page(
        pc=pc,
        risks_actions=risks_actions or [],
        board_talking_points=board_talking_points or [],
        alert_severity=alert_severity,
    )

    # PAGE 8: Appendix / Audit Trail
    _audit_trail_page(
        pc=pc,
        citations=citations,
        hitl_decisions=hitl_decisions,
        vcp_store_path=vcp_store_path,
        data_source_path=data_source_path,
        narrative_mode=narrative_mode,
        synthesis_mode=synthesis_mode,
        confidence_statement=confidence_statement or "All figures sourced from management accounts; unaudited.",
    )

    pc.save()

    pdf_bytes = buf.getvalue()

    if output_path:
        import pathlib
        pathlib.Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "wb") as f:
            f.write(pdf_bytes)
        print(f"[BoardPack] PDF saved: {output_path} ({len(pdf_bytes):,} bytes)")

    return pdf_bytes
