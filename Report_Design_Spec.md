# Report Design Specification
## PE Value Creation Copilot — End-to-End Report Experience

*Two surfaces: in-app live viewer (always fresh) + PDF board pack (timestamped snapshot)*

---

## The Core Insight

Most reporting tools produce a PDF. The best PE tools produce a **living document** that becomes a PDF when you need to hand it to someone.

The in-app report viewer is what operating partners and portco management use every day — always up-to-date, interactive, with drill-down. The PDF is the board meeting artefact — a timestamped snapshot of the same data, formatted for print. Both should be the same document; one is live, one is frozen.

The design goal: **a report that a senior operating partner can scan in 90 seconds, act on in 5 minutes, and hand to a board in PDF form without reformatting anything**.

---

## Report Types & Their Audiences

| Type | Primary Reader | Cadence | Length | Focus |
|---|---|---|---|---|
| **Board Pack** | Board members + GP team | Quarterly | 8–10 pages | Performance vs IC + forward view + recommendations |
| **Operating Partner Flash** | Operating partner (internal) | Monthly | 4–5 pages | KPI trends + VCP drift + action items only |
| **LP Summary** | Limited partners | Quarterly | 3–4 pages | High-level portfolio narrative, no portco detail |
| **VCP Status Update** | Portco management team | Monthly | 2–3 pages | Milestone scorecard only — what's on track, what isn't |

For the prototype, build **Board Pack** and **VCP Status Update** — the two that demonstrate the intelligence layer most clearly.

---

## Part 1: In-App Report Experience

### 1A. Reports Library Page (`/reports`)

**Question it answers**: *What reports exist and what do I need to generate?*

```
REPORTS                                                    [ + Generate New ]
────────────────────────────────────────────────────────────────────────────────

RECENT  ──────────────────────────────────────────────────────────────────────

┌─────────────────────────────────────────────────────────────────────────────┐
│  BOARD PACK                                                                 │
│  Company A · Q3 2025                                                        │
│  ● Auto-generated · 2 hours ago · approved by you                          │
│                                                        [View]  [↓ PDF]     │
├─────────────────────────────────────────────────────────────────────────────┤
│  BOARD PACK                                                                 │
│  Company B · Q3 2025                                                        │
│  ● Auto-generated · 3 hours ago · pending your review                      │
│                                              [Review →]  [↓ PDF (draft)]  │
├─────────────────────────────────────────────────────────────────────────────┤
│  VCP STATUS UPDATE                                                          │
│  Company A · October 2025                                                   │
│  ○ Generated manually · 3 days ago · approved                              │
│                                                        [View]  [↓ PDF]     │
└─────────────────────────────────────────────────────────────────────────────┘

GENERATE  ────────────────────────────────────────────────────────────────────

  Company        [ Company A ▾ ]
  Report type    [ ● Board Pack    ○ Operating Flash    ○ VCP Status Update ]
  Period         [ Q3 2025 ▾ ]

  Sections to include
  [✓] Executive summary (AI narrative)      [✓] Forward curve + IC overlay
  [✓] KPI performance scorecard             [✓] IRR scenarios (P10/P50/P90)
  [✓] VCP milestone scorecard               [✓] Sector benchmark comparison
  [✓] Risk flags & recommended actions      [✓] Evidence citations + audit log

  Tone           [ ● Board-ready   ○ Management-internal ]
  Narration      [ ● Include AI narrative   ○ Data only ]

                                                         [ Generate Report → ]
  ─────────────────────────────────────────────────────────────────────────────
  ● AI Generated label appears on all AI-written sections in both the in-app
    viewer and the PDF. Sources and approver name are always included.
```

**Design decisions:**
- Auto-generated reports (triggered by the monitoring pipeline after HITL approval) appear automatically — the operating partner doesn't have to click "generate" after every filing
- "Pending your review" state is visually distinct from "approved" — soft amber indicator, no heavy colour
- PDF download is always available, even for drafts (labelled "draft" in the filename)
- The tone toggle ("Board-ready" vs "Management-internal") tells the narrative agent whether to use formal board language or direct internal language — meaningful difference in how GPT-4o frames the executive summary

---

### 1B. In-App Report Viewer (`/reports/[id]`)

This is the live interactive view. Not a PDF render — a proper React page with the same component system used everywhere else in the app.

**Layout: full-width reading experience, no sidebar for this page**

The sidebar collapses on report view pages. Reports are read, not navigated. Give the content the full width it deserves.

```
←  Reports              Company A — Q3 2025 Board Pack          [ ↓ Export PDF ]
────────────────────────────────────────────────────────────────────────────────
● AI Generated · Generated 2h ago · Approved by Suryansh D · 14 Oct 2025, 11:42

                    REPORT NAVIGATION (sticky left rail, 180px)
                    ─────────────────
                    → Executive Summary
                      Performance
                      VCP Milestones
                      Forward View
                      Benchmarks
                      Risks & Actions
                      Appendix
                    ─────────────────
                    Confidence: High
                    Data as of: 01 Oct 2025
                    Peer set: 34 cos
```

**Full-width with sticky mini-nav on the left** — same pattern Notion and Linear use for long documents. The mini-nav floats as you scroll, showing which section is active with a thin left indicator. Clicking a section item smooth-scrolls to it.

---

### Section Structure (in-app viewer)

**Section 0: Report Header (not a section — the page top)**

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                                                                              │
│  Company A                                  Q3 2025 · Board Pack            │
│  B2B SaaS · £15–30M Revenue               As of 01 October 2025            │
│                                                                              │
│  ● Behind       Revenue -7.4% vs IC         IRR Base Case: 16.2%           │
│  overall        EBITDA -280bps vs IC        IC Underwritten: 19.0%         │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

The header is a wide card spanning the full content width. Status badge top-left. The gap between IRR base case and IC underwritten is the most important number in the entire document — it goes here, at the top, before the operating partner reads anything else.

---

**Section 1: Executive Summary**

```
EXECUTIVE SUMMARY                              ● AI Generated · GPT-4o · 14 Oct 2025
────────────────────────────────────────────────────────────────────────────────────

Company A delivered revenue of £21.4M in Q3 2025, representing 92.6% of the
IC target of £23.1M. EBITDA margin compressed to 18.2% against a committed
20.0% target, driven by SG&A growth (+£340k ahead of plan) outpacing revenue
in the US office. This compression is company-specific — sector peers reported
flat EBITDA margins over the same period.

The base case IRR now sits at 16.2%, 280bps below the 19.0% underwritten at
investment. The primary lever to close this gap is SG&A efficiency: moving to
sector-median SG&A (21% of revenue from 27.4% current) would recover
approximately 180bps of IRR.

4 of 7 VCP milestones are on track. The ERP implementation remains delayed
(originally Q1 Y2, now tracking Q3 Y2). No milestones have been missed
permanently; all are recoverable within the investment horizon.

Recommended board action: Approve the SG&A audit scope presented by management
and request a revised timeline for the ERP go-live.

────────────────────────────────────────────────────────────────────────────────────
Source: EDGAR 10-Q Q3 2025  ·  IC Memo (confirmed 2024-03-17)  ·  FRED DFF (macro)
Peer benchmark: 34 companies, SIC 7372, EDGAR XBRL, Q3 2025
```

**Design rules for Executive Summary:**
- 4 paragraphs maximum: Performance / IRR impact / VCP status / Recommended action
- Written in present tense, past tense only for historical data points
- The recommended action is a concrete sentence, not a vague prompt — "Approve the SG&A audit scope" not "Consider addressing cost efficiency"
- Citation block at the bottom, always
- `● AI Generated` label top-right, small, not apologetic

The user should be able to read only Section 1 and walk into a board meeting prepared. Everything else is support.

---

**Section 2: KPI Performance Scorecard**

```
KPI PERFORMANCE                                             Period: Q3 2025
────────────────────────────────────────────────────────────────────────────

  METRIC              ACTUAL      IC TARGET    DELTA        VS LAST QTR    STATUS
  ─────────────────────────────────────────────────────────────────────────────
  Revenue             £21.4M      £23.1M       -7.4%        +2.1% ▲        ● Behind
  Gross Margin        68.1%       70.0%        -190bps      -20bps ▼       ● At Risk
  EBITDA              £3.9M       £4.6M        -14.9%       -8.3% ▼        ● Behind
  EBITDA Margin       18.2%       21.0%        -280bps      -110bps ▼      ● Behind
  SG&A % Revenue      27.4%       24.0%        +340bps      +80bps ▲       ● Behind  (↑ = worse)
  Net Debt / EBITDA   3.8x        3.4x         +0.4x        +0.1x ▲        ● At Risk (↑ = worse)
  Cash                £4.2M       £4.0M        +5.0%        -£0.3M ▼       ● On Track
  ─────────────────────────────────────────────────────────────────────────────
  Source: EDGAR 10-Q Q3 2025 · Company A management accounts · Oct 2025

  TREND (6-quarter sparklines, one per KPI, right-aligned)
  Revenue        ╱‾‾‾╲__           ← plateau visible
  EBITDA Margin  ‾‾‾‾╲__           ← compression visible
  SG&A %         ___╱‾‾‾           ← growing (bad)
  Cash           ‾‾‾‾‾‾            ← stable
```

**Design rules:**
- Direction arrows on "vs last quarter" column: ▲ green for improving, ▼ red for declining — BUT for inverse metrics (SG&A%, leverage), swap the colours and add "(↑ = worse)" footnote. Never let a green arrow mislead.
- Sparklines in this section are 120px × 30px — slightly larger than alert cards, because the trend is important here
- Metrics are sorted: worst status first (Behind → At Risk → On Track)
- Source line under the table, always

---

**Section 3: VCP Milestone Scorecard**

```
VCP MILESTONE SCORECARD           4 on track · 2 at risk · 1 behind
────────────────────────────────────────────────────────────────────────────────

  INITIATIVE           CATEGORY    TARGET       ACTUAL      STATUS       DUE
  ──────────────────────────────────────────────────────────────────────────────
  Revenue Growth       Financial   £23.1M       £21.4M      ● Behind     Y2 Q3
  EBITDA Margin        Financial   21.0%        18.2%       ● Behind     Year 3
  ERP Implementation   Operational Done         In progress ● At Risk    Overdue
  SG&A Rationalisation Operational 24% rev      27.4%       ● At Risk    Year 2
  Customer NPS         Commercial  Score 45     Score 47    ● On Track   Year 2
  Net Debt/EBITDA      Financial   3.4x         3.8x        ● At Risk    Year 3
  CRO Hire             Org         Done         ✓ Done      ● Complete   Month 3
  ──────────────────────────────────────────────────────────────────────────────
  Source: VCP confirmed 2024-03-17 · EDGAR 10-Q Q3 2025 · Management accounts

  MILESTONE TIMELINE
  ──────────────────────────────────────────────────────────────────────────────
  Y1 Q1   Y1 Q2   Y1 Q3   Y1 Q4   Y2 Q1   Y2 Q2   Y2 Q3  ← today
    │       │       │       │       │       │         │
    ●CRO✓                           ●ERP━━━━━━━━━━━━►(delayed Q3 Y2)
                                            ●SG&A target
                                                      ●Revenue target
  ──────────────────────────────────────────────────────────────────────────────
```

The timeline is a mini Gantt. Completed milestones are solid dots. Delayed milestones show a dashed line extending past their original target date, pointing toward the revised date. This visual immediately shows the operating partner what slipped and by how much.

---

**Section 4: Forward View**

```
FORWARD VIEW                                                     Horizon: [5Y ▾]
────────────────────────────────────────────────────────────────────────────────

  EBITDA FORWARD CURVE
  [Full-width ForwardCurveChart component — same as Company Deep Dive page]
  Actual (solid) · P50 forecast (dashed) · P10-P90 band (light fill) · IC targets (dots)

  IRR SCENARIOS
  ─────────────────────────────────────────────────────────────────────────────
                    BEAR (P10)    BASE (P50)    BULL (P90)    IC UNDERWRITTEN
  ─────────────────────────────────────────────────────────────────────────────
  Exit EBITDA        £4.8M         £6.4M         £8.2M         £7.1M
  Exit Multiple       7.5x          8.5x          9.5x          9.0x
  Gross IRR          11.8%         16.2%         22.4%         19.0%  ← bold
  MOIC               1.6x          2.1x          2.8x          2.5x
  ─────────────────────────────────────────────────────────────────────────────
  Gap to IC:        -720bps       -280bps  ←                  underwritten
  ─────────────────────────────────────────────────────────────────────────────
  Methodology: STL decomposition + SARIMA + Prophet ensemble · FRED macro regressors
  Confidence: Moderate (12 quarters of history · 8 minimum recommended)

  KEY ASSUMPTIONS
  ─────────────────────────────────────────────────────────────────────────────
  Revenue CAGR (base):    14.2%    SG&A normalization by:  Year 3
  Gross margin expansion:  +80bps per year    Exit year:   Year 5
  Macro regime:           FRED forward curve · Fed Funds 4.25% terminal
```

**Design rules for Forward View:**
- The IRR table is the most important element in this section — give it more space than the chart
- Colour the IC Underwritten column differently (slightly bold column header, no background colour)
- The gap row (Gap to IC) uses red for negative values, no green needed here — if you're ahead of IC underwritten that's unusual
- The methodology footnote must be present — "we used STL + SARIMA + Prophet" should be legible, not hidden. This is what separates your product from a spreadsheet
- Confidence qualifier: "Moderate (12 quarters of history)" shows the model is aware of its own limitations — another trust signal

---

**Section 5: Sector Benchmarks**

```
SECTOR BENCHMARKS                    B2B SaaS · SIC 7372 · 34 peers · Q3 2025
────────────────────────────────────────────────────────────────────────────────

  METRIC              COMPANY A    P25     MEDIAN    P75     POSITION
  ────────────────────────────────────────────────────────────────────
  EBITDA Margin       18.2%        14%     22%       28%     35th pct  ▓▓▓▓▓░░░░░
  Revenue Growth      12.4%         8%     18%       26%     28th pct  ▓▓▓░░░░░░░
  Gross Margin        68.1%        62%     70%       77%     55th pct  ▓▓▓▓▓▓░░░░
  SG&A % Revenue      27.4%        24%     21%       18%     38th pct  ▓▓▓▓░░░░░░  (lower better)
  Net Debt / EBITDA    3.8x        2.1x    3.2x      4.5x    42nd pct  ▓▓▓▓▓░░░░░

  AI ANALYSIS  ● AI Generated · GPT-4o · 14 Oct 2025
  ──────────────────────────────────────────────────────────────────────────────
  Company A's EBITDA margin (18.2%) places it in the 35th percentile of SaaS
  peers at the same revenue scale. The gap to median (22.0%) is 380bps and is
  driven primarily by above-median SG&A intensity (27.4% vs sector median 21%).

  Gross margin is the one bright spot at 55th percentile — the underlying unit
  economics are healthy. The compression is a cost efficiency issue, not a
  pricing or delivery issue. This is recoverable.

  Peers that moved from 35th to 55th percentile EBITDA percentile over a 2-year
  window most commonly achieved this through GTM efficiency improvement (68% of
  cases) rather than headcount reduction (32%). Pricing lever was secondary.
  ──────────────────────────────────────────────────────────────────────────────
  Source: EDGAR XBRL · 34 companies · SIC 7372 · Revenue £15–50M · Q3 2025
```

---

**Section 6: Risks & Recommended Actions**

```
RISKS & RECOMMENDED ACTIONS                           ● AI Generated · 14 Oct 2025
────────────────────────────────────────────────────────────────────────────────

  PRIORITY    RISK                        IRR AT RISK    RECOMMENDED ACTION
  ────────────────────────────────────────────────────────────────────────────
  1  ● RED    SG&A exceeding plan         -180bps        SG&A audit: US office
              by 340bps for 2 quarters                   GTM efficiency review

  2  ● AMBER  ERP delay (Q3 Y2 vs        -60bps         Weekly status review
              Q1 Y2 target) risks                        Escalate to COO
              downstream data quality

  3  ● AMBER  Revenue below IC target    -280bps         Pricing review on
              for 2 consecutive qtrs     (combined)      renewal cohorts
              with no inflection signal                  New logo pipeline audit
  ────────────────────────────────────────────────────────────────────────────
  ● Risk items shown are those with IRR impact > 30bps. Green items omitted.
  Source: Synthesised from EDGAR 10-Q · IC Memo · Sector benchmark · VCP drift

  BOARD QUESTIONS (suggested by system)
  ──────────────────────────────────────────────────────────────────────────────
  1. What is management's revised SG&A target and timeline to reach 24%?
  2. What is the ERP go-live dependency? Is the Q3 Y2 date fixed or still moving?
  3. What is the net revenue retention rate this quarter vs last?
```

**"Board Questions" block** — one of the most useful features. GPT-4o synthesises 2–3 sharp questions the operating partner should ask in the board meeting, based on the gaps and risks identified. This makes the product feel like a prepared analyst briefing, not just a data report.

---

**Section 7: Appendix**

```
APPENDIX                                                              [Collapse ▴]
────────────────────────────────────────────────────────────────────────────────

  A.  Full KPI history (12-quarter table)
  B.  Full VCP milestone extract with source text
  C.  HITL approval audit log
      ✓ Alert approved by Suryansh D · 14 Oct 2025, 11:42 · "Approved as presented"
      ✓ VCP confirmed by Suryansh D · 2024-03-17, 09:15 · "Confirmed post IC call"
  D.  Data sources and methodology
      — EDGAR XBRL pull: company_facts API · as of 01 Oct 2025
      — LlamaParse extraction: IC Memo v1.2 · 2024-03-15
      — Forecasting: STL decomposition + SARIMA(2,1,2)(1,1,1)12 + Prophet
      — Macro: FRED series DFF, INDPRO, CPILFESL
  E.  Peer company list (anonymised)
      34 companies · SIC 7372 · £15–50M trailing revenue · EDGAR XBRL
```

The appendix is **collapsed by default** in the in-app view. The board reads sections 1–6. The detail is there if they need it, but it doesn't dominate the reading experience.

---

## Part 2: PDF Board Pack Layout

The PDF is generated by the FastAPI backend (ReportLab + narrative from GPT-4o). It should look like a professional document produced by an investment firm's internal team — not a software export.

**Paper size**: A4 (international PE standard)
**Margins**: 25mm top/bottom, 20mm left/right
**Binding edge**: left (extra 5mm left margin for printing)

---

### PDF Page-by-Page Layout

**Page 1: Cover**

```
┌────────────────────────────────────────────────────┐
│                                                    │
│  [Firm logo, top-left, 30px height]                │
│                                                    │
│                                                    │
│                                                    │
│  Company A                                         │
│  Board Pack                                        │
│  Q3 2025                                           │
│                                                    │
│  Prepared by: Operating Partner Team               │
│  Date: 14 October 2025                             │
│  Classification: Confidential                      │
│                                                    │
│  ─────────────────────────────────                 │
│                                                    │
│  Generated by PE Value Creation Copilot            │
│  Approved by: Suryansh D · 14 Oct 2025, 11:42     │
│                                                    │
└────────────────────────────────────────────────────┘
```

- Cover is clean. Firm name, document type, company, quarter, date, classification.
- "Generated by PE Value Creation Copilot" in small text at bottom — honest attribution, doesn't dominate.
- No images, no decorative elements, no colour fill. Professional white cover with a thin horizontal rule.

**Page 2: Executive Summary**

Single page. The 4-paragraph narrative from Section 1. Font: Inter 10.5pt body. Wide margins. Generous leading (14pt line height).

At the bottom of page 2: a compact 3-column summary strip:

```
  IRR Base Case    VCP On Track    Key Risk
  16.2%            4 / 7           SG&A +340bps
  IC: 19.0%        ● Behind        vs plan
  Gap: -280bps
```

This strip means if someone only reads page 2, they walk away with the three numbers that matter.

**Page 3: KPI Scorecard**

Full-page table. Column widths:
```
Metric (35%) | Actual (12%) | IC Target (12%) | Delta (12%) | vs Last Qtr (12%) | Status (17%)
```

Status column uses coloured text (no background fill — printers render these inconsistently). Sparklines are 60pt × 20pt, right-aligned in the metric column.

**Page 4: VCP Milestone Scorecard**

Table + timeline. Table occupies top 55% of page. Timeline (mini Gantt, simplified for print) occupies bottom 35%. Source citation at bottom.

**Page 5: Forward Curve Chart**

Full-page chart. No table on this page — give the chart breathing room. The IRR scenario table sits in a box at the bottom right of the chart area (not a separate page — it reads together with the curve).

Page layout:
```
┌────────────────────────────────────────┐
│                                        │
│   EBITDA FORWARD CURVE                 │
│                                        │
│   [Chart — 80% of page height]         │
│                                        │
│   ┌─────────────────┐                  │
│   │  IRR SCENARIOS  │ ← inset box     │
│   │  Bear:  11.8%   │   bottom right  │
│   │  Base:  16.2%   │                 │
│   │  Bull:  22.4%   │                 │
│   │  IC:    19.0%   │                 │
│   └─────────────────┘                  │
│                                        │
│   Methodology footnote · 8pt · muted   │
└────────────────────────────────────────┘
```

**Page 6: Sector Benchmarks**

Two-thirds of the page: benchmark table with percentile bars. Bottom third: the AI gap analysis paragraph. Source citation at bottom.

The percentile bars in PDF: simple horizontal bar built with ReportLab rectangles. Company position shown as a filled circle on the bar. This is the clearest way to show relative position in print.

**Page 7: Risks & Recommended Actions + Board Questions**

Top half: risk table (3–5 rows max, red/amber only).
Bottom half: Board Questions block.

**Page 8: Appendix**

HITL audit log, data sources, methodology. Fine print (9pt). Full peer list if requested.

---

### PDF Typography

```
Cover title:        Inter Bold 22pt
Section headers:    Inter SemiBold 11pt, uppercase, letter-spaced
Body:               Inter Regular 10.5pt, 14pt leading
Table headers:      Inter Medium 9pt, uppercase, letter-spaced, slate
Table cells:        JetBrains Mono 9.5pt (numbers), Inter Regular 10pt (text)
Captions:           Inter Regular 8.5pt, slate
Footnotes:          Inter Regular 8pt, muted slate
```

Font consistency between the in-app UI and the PDF is intentional — the same document in two formats, not two separate products.

### PDF Colour Rules (print-safe)

```
Primary blue:       #1E3A8A (slightly deeper than screen — printers shift blue light)
Status Red:         #DC2626 (text only, no background fills)
Status Amber:       #D97706 (text only)
Status Green:       #059669 (text only)
All body text:      #1E293B (not pure black — prints crisper)
Muted text:         #64748B
Borders/rules:      #CBD5E1 (0.5pt weight)
```

Never use background fills on table rows for status — printer calibration is inconsistent and fills create muddy output. Text colour alone carries the RAG status.

---

## Part 3: Report Generation UX Flow

```
TRIGGER A: Automatic (recommended path)
────────────────────────────────────────
Monitoring pipeline runs (new EDGAR filing)
        ↓
Alert & Synthesis Agent produces severity + narrative
        ↓
HITL Gate: operating partner approves alert
        ↓
System auto-generates Board Pack draft
Notification: "Q3 Board Pack for Company A is ready for review"
        ↓
Operating partner opens report viewer
Reviews sections 1–7
Makes optional edits to executive summary (text field, directly in-app)
        ↓
Clicks "Approve & Finalise"
        ↓
PDF generated and stored
Report moves to "Approved" in library

TRIGGER B: Manual
────────────────────────────────────────
Operating partner opens /reports
Fills generator form (company, type, period, sections)
Clicks "Generate Report →"
        ↓
Loading state: "Generating narrative... Assembling charts... Building PDF..."
~15–20 seconds total
        ↓
Report viewer opens with the draft
Same approval flow as automatic path
```

**Loading state design** — 15–20 seconds is long in UI terms. Don't show a spinner. Show a staged progress message:

```
┌──────────────────────────────────────────────────┐
│                                                  │
│  Generating Q3 Board Pack for Company A          │
│                                                  │
│  ✓  Fetching KPI data                           │
│  ✓  Running forward curve                       │
│  ●  Writing executive summary...                │
│  ○  Assembling peer benchmarks                  │
│  ○  Building PDF                                │
│                                                  │
│  Estimated: ~15 seconds                          │
└──────────────────────────────────────────────────┘
```

This makes the wait feel purposeful, not frozen. Users understand what the system is doing, which builds trust in the output.

---

## Part 4: In-App Editing

Operating partners often want to edit the AI narrative before it goes to the board. Support this without making it feel like a text editor.

**Inline editing**: click on the Executive Summary paragraph → it becomes an editable text field. The "● AI Generated" label changes to "✎ Edited by Suryansh D". The original AI text is preserved and accessible via "Show original" link.

```tsx
// components/reports/EditableSection.tsx
export function EditableSection({ content, isAI, onEdit }) {
  const [editing, setEditing] = useState(false)
  const [value, setValue]     = useState(content)

  return editing ? (
    <div>
      <Textarea value={value} onChange={e => setValue(e.target.value)}
                className="min-h-[120px] font-sans text-sm" />
      <div className="flex gap-2 mt-2">
        <Button size="sm" onClick={() => { onEdit(value); setEditing(false) }}>Save</Button>
        <Button size="sm" variant="ghost" onClick={() => setEditing(false)}>Cancel</Button>
      </div>
    </div>
  ) : (
    <div onClick={() => setEditing(true)}
         className="cursor-text hover:bg-slate-50 rounded p-2 -m-2 group">
      <p className="text-sm text-slate-600 leading-relaxed">{value}</p>
      <span className="text-xs text-slate-400 opacity-0 group-hover:opacity-100 mt-1 block">
        ✎ Click to edit
      </span>
    </div>
  )
}
```

The edit affordance (`✎ Click to edit`) only appears on hover — it doesn't clutter the reading experience.

---

## Summary: What Makes This Report Design Work

**For the operating partner:**
- Reads section 1 (90 seconds) and knows everything they need for a board meeting
- The board questions block means they walk in prepared
- Inline editing means they can adjust the narrative without leaving the app
- PDF looks like something their firm produced, not a software export

**For the portco management team:**
- VCP Status Update type is specifically for them — milestone scorecard only
- No IRR data, no sector benchmarks — just "here's what we committed to, here's where we are"
- Constructive framing: risks include recommended actions, not just flags

**For LPs:**
- LP Summary type: portfolio narrative only, no portco-level detail
- High signal-to-noise: 3 pages, clean, no jargon

**What makes it different from a PDF export button:**
- The executive summary is synthesised from 5 data sources by GPT-4o — not a template fill
- The board questions are generated from the gap analysis — not boilerplate
- The HITL audit log in the appendix means every stakeholder knows a human reviewed and approved the content
- The in-app viewer is always live; the PDF is a timestamped snapshot of the same data
