# Report Generation Module — Complete Specification
## PE Value Creation Copilot

*Format: 16:9 deck (PPTX + PDF export). One key message per slide. Board-room ready.*

---

## 1. Module Purpose & End User Benefits

The report generation module transforms live pipeline data — KPIs, VCP milestones, forward curves, peer benchmarks, AI alerts — into board-ready decks with zero manual assembly.

**The core problem it solves**: An operating partner managing 6–8 portfolio companies currently spends 3–5 hours per company per quarter assembling board packs from Excel models, PowerPoint templates, and management accounts. The data is always slightly stale. The narrative is always written the night before. The format varies by analyst.

**What this module delivers instead**:
- Auto-drafted board pack within 60 seconds of HITL alert approval
- Consistent format and quality regardless of who generates it
- AI narrative grounded in 5 cited data sources, not intuition
- Human review and editing before any deck leaves the system
- One-click export to PPTX (editable) or PDF (final)

**Time saved per operating partner**: estimated 15–20 hours per quarter per portfolio company.

---

## 2. End User Personas & Use Cases

### Persona 1: Operating Partner (GP team)
**Job**: Oversee 4–8 portfolio companies, sit on boards, drive value creation
**Pain today**: Spends too much time on reporting, not enough on advising
**Primary use cases**:
- Generate quarterly board packs for each portco
- Review and approve AI-drafted content before the board meeting
- Edit narrative sections to match their personal communication style
- Export PPTX to present in the board room (or PDF to circulate ahead)

**Key benefit**: Shows up to board meetings with a fully prepared deck that reflects real-time data, not a stale spreadsheet model. The "board questions" slide means they walk in with the right challenges ready.

### Persona 2: Portfolio Company CFO / Finance Director
**Job**: Manage financial performance of the portco, report to the board
**Pain today**: Prepares management accounts, then reformats them again for board pack, then again for GP reporting
**Primary use cases**:
- Receive monthly VCP Status Update showing where they stand vs. committed milestones
- See clearly which milestones are Behind and what action is needed
- Use as a structured framework for internal management discussion

**Key benefit**: One document they receive that already contains their performance vs. the IC-committed targets. No more wondering what the GP is measuring them on.

### Persona 3: LP Relations / Investor Relations Team
**Job**: Communicate portfolio performance to limited partners
**Primary use cases**:
- Generate quarterly LP Summary covering the full portfolio
- High-level narrative per portco without confidential operational detail
- Consistent format across the portfolio for LP digestion

**Key benefit**: LP summaries generated from live data, reviewed and approved, exported in minutes instead of days.

### Persona 4: Investment Committee (internal)
**Job**: Review portfolio health, make capital allocation decisions
**Primary use cases**:
- Flash reports triggered by red alerts (immediate)
- Quarterly IC update with forward IRR scenarios across all portcos

---

## 3. Report Types

Four report types. Each is a separate deck template with different slide sets, audiences, and generation triggers.

| Type | Audience | Format | Trigger | Slides | Cadence |
|---|---|---|---|---|---|
| **Board Pack** | Board + GP | 10 slides, comprehensive | Auto after HITL / manual | Full set | Quarterly |
| **VCP Status Update** | Portco management | 5 slides, milestone-focused | Scheduled monthly / manual | VCP + action only | Monthly |
| **Operating Flash** | GP team internal | 4 slides, KPI + risks only | Scheduled weekly / manual | No benchmarks, no narrative | Weekly/monthly |
| **LP Summary** | Limited partners | 5 slides, portfolio-level | Manual | No portco operational detail | Quarterly |

---

## 4. Deck Format: Design Specification

All reports use 16:9 landscape format (1920×1080px / standard widescreen).

**Why deck over A4 portrait**:
- PE board rooms use projectors and screens — portrait A4 at 10pt font is unreadable at 3 metres
- One key message per slide forces clarity; no hiding bad news in dense paragraphs
- Charts fill a full slide and are actually legible
- PPTX export lets the operating partner make last-minute edits in the board room
- Navigation is faster: jump to slide 4 (VCP) without scrolling through a document

### Master Slide Layout

```
┌─────────────────────────────────────────────────────────┐  ← 1920px
│  [Firm logo]              [Company name] · [Period]      │  40px header bar, navy #0F2044
├─────────────────────────────────────────────────────────┤
│                                                         │
│                                                         │
│               [Slide content area]                      │  920px usable height
│                                                         │
│                                                         │
├─────────────────────────────────────────────────────────┤
│  [Section label]          [Page N / Total] CONFIDENTIAL │  32px footer bar, light grey
└─────────────────────────────────────────────────────────┘
```

**Header bar**: 40px, `#0F2044` (dark navy). Left: firm logo placeholder (white, 120px wide). Centre: company name 14px/500, period "Q4 2027" 14px/400, both white. Right: "CONFIDENTIAL" in 10px uppercase, slate.

**Footer bar**: 32px, `#F1F5F9`. Left: section label (e.g. "Executive Summary"). Right: "Page 3 / 10 · STRICTLY CONFIDENTIAL".

**Content area**: 1920×1008px minus header/footer = 1920×936px effective. Margins: 64px left/right, 40px top/bottom.

### Typography (Deck)

| Use | Font | Size | Weight |
|---|---|---|---|
| Slide title | Inter | 28px | 600 |
| Key message (sub-title) | Inter | 18px | 400, slate |
| Body text | Inter | 14px | 400 |
| Data labels | JetBrains Mono | 13px | 500 |
| Table headers | Inter | 11px, uppercase | 500 |
| Footnotes / citations | Inter | 10px | 400, muted |
| Stat callout (large number) | JetBrains Mono | 48px | 700 |

### Colour System (Deck)

```
Background:       #FFFFFF  (slide canvas — always white)
Header/footer:    #0F2044  (deep navy — firm colour, adjustable)
Primary text:     #0F172A
Secondary text:   #475569
Muted:            #94A3B8
Accent blue:      #1E40AF  (chart primary, links, active)
Status green:     #059669
Status amber:     #D97706
Status red:       #DC2626
Chart band fill:  #DBEAFE  (P10-P90 uncertainty, very light)
Table header bg:  #F8FAFC
Table row alt:    #FFFFFF / #F8FAFC alternating
Border:           #E2E8F0  (0.5pt)
```

**Print rule**: Never use background fills on table cells for status — use text colour only. Printer calibration makes fills unpredictable.

---

## 5. Slide-by-Slide Specification

### Board Pack (10 slides)

---

**Slide 1: Cover**

*Purpose*: Establish identity and context. The first thing the board sees when they open the deck on a projector.

```
Layout: Full-bleed left panel (40% width, navy #0F2044) + white right panel (60%)

LEFT PANEL (navy):
  [Firm logo, white, top-left]

  [Company name]            ← 36px/600, white
  [Sector · Deal Year]      ← 14px/400, slate-300
  ─────────────────────────
  Board Pack                ← 20px/500, white
  Q4 2027                   ← 16px/400, slate-300
  ─────────────────────────
  ● GREEN  Overall Status   ← RAG badge — most important element on the cover
  IRR Base Case: 16.2%      ← 14px mono, white
  IC Underwritten: 19.0%    ← 14px mono, slate-300
  Gap: -280bps              ← 13px mono, red-300 if negative

RIGHT PANEL (white):
  Prepared by:  Operating Partner Team
  Date:         29 June 2026
  Period:       Q4 2027
  Classification: Confidential — Board Only
  ─────────────────────────
  [Generated by PE Value Creation Copilot]  ← 10px, muted
  [Approved by: Name · Date · Time]         ← 10px, muted

  FUND CONTEXT (bottom of right panel)
  Investment date:    March 2024
  Entry EBITDA:       £9.2M · 11.2x
  Initial equity:     £42M
  Hold target:        5 years (exit Year 2029)
```

**Key design decision**: IRR base case vs. IC underwritten goes on the cover — the board should know the return status before they read anything else. If it's red, they'll read everything more carefully.

---

**Slide 2: At a Glance (Summary Dashboard)**

*Purpose*: One slide that answers "are we on track?" across all dimensions simultaneously. A busy board member who only sees this slide should leave informed.

*Key message line*: Auto-generated from status — e.g. "Revenue ahead of plan · EBITDA margin compressing · 4 of 7 VCP milestones on track"

```
Layout: 2×2 grid of quadrants

┌──────────────────────┬──────────────────────┐
│  KPI PERFORMANCE     │  VCP MILESTONES      │
│                      │                      │
│  Revenue    ● 92.6%  │  ██████░░ 4 / 7     │
│  EBITDA M   ● 86.7%  │  ● 1 Behind          │
│  Net Debt   ● 95.0%  │  ● 2 At Risk         │
│                      │  ● 4 On Track        │
├──────────────────────┼──────────────────────┤
│  IRR OUTLOOK         │  PEER POSITION       │
│                      │                      │
│  Bear   11.8%        │  EBITDA M   35th pct │
│  Base   16.2% ←      │  Rev Growth 28th pct │
│  Bull   22.4%        │  Gross M    55th pct │
│  IC     19.0%        │                      │
│  Gap    -280bps ▼    │  Sector: B2B SaaS    │
└──────────────────────┴──────────────────────┘

PRIORITY ACTION (full-width strip at bottom):
  [amber left border] CFO must implement SG&A audit by Q2 2028 — AI Generated
```

**What this replaces**: The traditional "one metric per slide" approach that forces board members to reconstruct the picture in their heads. This slide gives the whole picture at once, then subsequent slides drill into each quadrant.

---

**Slide 3: Executive Summary**

*Purpose*: The narrative. What happened, why it matters, what to do. Written by GPT-4o, edited by the operating partner.

*Key message line*: First sentence of the AI narrative — e.g. "EBITDA margin compressing 280bps below IC target driven by SG&A growth in US office; IRR at risk -280bps."

```
Layout: Two columns (60/40 split)

LEFT COLUMN (60%):
  SITUATION                         ← 11px uppercase label
  [AI narrative paragraph 1 — 3-4 sentences on performance]

  KEY RISKS                         ← 11px uppercase label
  1  [Risk statement, 1 sentence]
  2  [Risk statement, 1 sentence]
  3  [Risk statement, 1 sentence]

  PRIORITY ACTION THIS QUARTER
  [Single bold action sentence, amber left border]

RIGHT COLUMN (40%):
  THREE SUMMARY STATS (stacked):

  ┌──────────────────────┐
  │ IRR AT RISK          │
  │ -280bps              │  ← 48px mono, red if negative
  │ vs IC underwritten   │
  └──────────────────────┘
  ┌──────────────────────┐
  │ VCP ON TRACK         │
  │ 4 / 7                │  ← 48px mono
  │ milestones           │
  └──────────────────────┘
  ┌──────────────────────┐
  │ PEER RANK            │
  │ 35th pct             │  ← 48px mono
  │ EBITDA margin        │
  └──────────────────────┘

FOOTER: ● AI Generated · GPT-4o · [timestamp] · Approved by [name]
```

**AI generation rules for this slide**:
- 4 paragraphs maximum but rendered as dense short copy, not prose blocks
- The priority action must be one sentence naming a specific person (CFO, CEO) and a specific deadline
- No hedging language ("may", "could", "might") — this is a board document
- Tone: "Board-ready" mode uses formal past tense for performance, future tense for actions

---

**Slide 4: KPI Performance Scorecard**

*Purpose*: Detailed financial performance vs. IC targets. The operating partner's primary accountability slide.

*Key message line*: Auto-derived from worst metric — e.g. "EBITDA margin 280bps below IC target for second consecutive quarter."

```
Layout: Full-width table + small chart column

TABLE (75% width):
  Column widths: Metric(30%) Actual(13%) IC Target(13%) Delta(12%) vs LQtr(14%) Trend(10%) Status(8%)

  METRIC              ACTUAL    IC TARGET    DELTA      VS LAST QTR    TREND    STATUS
  ─────────────────────────────────────────────────────────────────────────────────────
  Revenue             £46.9M    £46.0M       +2.0%      +1.6% ▲        ▁▂▃▄▅   ● Green
  Gross Margin        68.1%     70.0%        -190bps    -20bps ▼        ▄▃▃▃▂   ● Amber
  EBITDA              £9.4M     £10.9M       -14.9%     -8.3% ▼        ▄▃▃▃▂   ● Red
  EBITDA Margin       20.0%     21.0%        -100bps    -50bps ▼        ▄▃▃▃▂   ● Amber
  SG&A % Revenue      27.4%     24.0%        +340bps ↑  +80bps ▲        ▂▃▄▄▅   ● Red   (↑=worse)
  Net Debt/EBITDA     1.73x     1.80x        +3.9%      +0.1x ▲        ▃▃▂▂▂   ● Green
  Cash                £4.2M     £4.0M        +5.0%      -£0.3M ▼       ▃▄▄▄▄   ● Green
  ─────────────────────────────────────────────────────────────────────────────────────

TREND COLUMN: 5-period sparkline as Unicode block characters (▁▂▃▄▅▆▇)
— Renders cleanly in PPTX without needing embedded images
— Ascending = improving, descending = declining
— Colour matches status: green/amber/red

LEGEND STRIP (below table):
  ● Red = >10% below IC target · ● Amber = 5–10% · ● Green = within ±5%
  ▲/▼ = vs prior quarter · (↑=worse) flags inverse metrics

FOOTNOTE: Source: Management accounts · IC Memo confirmed [date]

RIGHT SIDEBAR (25%):
  PERIOD-OVER-PERIOD NARRATIVE  ← AI-generated, 2 sentences
  "Revenue grew 1.6% QoQ driven by..."
  "SG&A intensity continues to widen..."
```

**Bug fixes from current implementation**:
- DUE DATE / STATUS column overflow: fixed by narrower date format ("Q4-27" not "2027-12-31") and right-aligning status dot to its own 40px column
- Gap percentages for benchmark comparison: express as percentage POINTS (pp) not percentage-of-median
- All financial figures use JetBrains Mono, right-aligned — never left-aligned numbers in a finance table

---

**Slide 5: Value Creation Plan Scorecard**

*Purpose*: The milestone accountability slide. "We promised this at IC. Here is where we stand."

*Key message line*: Auto-derived — e.g. "3 of 7 VCP milestones on track; ERP implementation overdue by 2 quarters."

```
Layout: Top summary strip + milestone table + mini timeline

SUMMARY STRIP (top, 80px):
  ┌─────────────┬─────────────┬─────────────┬─────────────┐
  │ 1 Behind    │ 2 At Risk   │ 4 On Track  │ 0 No Data   │
  │ ● red       │ ● amber     │ ● green     │ ○ grey      │
  └─────────────┴─────────────┴─────────────┴─────────────┘
  Each number is 32px/700 in its RAG colour. Label is 11px muted.

MILESTONE TABLE (middle, sorted: Behind → At Risk → On Track → No Data):

  INITIATIVE           CATEGORY    BASELINE   TARGET    ACTUAL    GAP       STATUS   DUE
  ───────────────────────────────────────────────────────────────────────────────────────
  Revenue Growth       Financial   £30.5M     £46.0M    £46.9M    +2.0%     ●        Q4-27
  EBITDA Margin        Financial   15.0%      20.0%     20.0%     +0.0%     ●        Q4-27
  SG&A Reduction       Financial   28.0%      24.0%     27.4%     +340bps   ●        Q4-27
  ERP Implementation   Operational —          Done      Delayed   Overdue   ●        Q1-27 ⚠
  CRO Hire             Org         0          1         ✓Done     —         ●        M3
  Customer NPS         Commercial  38         45        47        +4.7%     ●        Q4-27
  Net Debt/EBITDA      Financial   3.90x      1.80x     1.73x     +3.9%     ●        Q4-27
  ───────────────────────────────────────────────────────────────────────────────────────

  Key fix: STATUS dot is its own 32px column, never combined with DUE DATE.
  Key fix: DUE DATE uses short format "Q4-27" or "M3" — never ISO "2027-12-31".
  Key fix: Overdue items get a ⚠ suffix on the due date — visual flag without colour.

MINI TIMELINE (bottom 25% of slide — horizontal Gantt):
  Y1 Q1  Y1 Q2  Y1 Q3  Y1 Q4  Y2 Q1  Y2 Q2  Y2 Q3 ← today
    │      │      │      │      │      │        │
    ●CRO✓                       ●ERP━━━━━━━━━━►(delayed)
                                        ●SG&A target
                                                ●Revenue/EBITDA targets

  Completed: filled green dot. On track: filled blue dot. Delayed: dashed line → revised date.
  Today marker: vertical dashed grey line at current period.

SOURCE: IC Memo · confirmed [date] · [approver name]
```

---

**Slide 6: EBITDA Forward Curve**

*Purpose*: Where are we heading? This is the centrepiece of the entire deck — the single chart that answers the most important question in PE.

*Key message line*: Auto-derived from P50 vs. IC target gap — e.g. "P50 forecast tracks £1.2M below IC exit target; recovery requires sustained SG&A discipline."

```
Layout: Full-width chart with KPI strip above and IRR table inset

KPI STRIP (above chart, 4 stats):
  ACTUAL EBITDA MARGIN   VCP TARGET   GAP VS PLAN   REVENUE (annualised)
        20.0%              20.0%          +0.0%           £46.9M
  (28px mono)           (28px mono)   (28px mono, green/red)  (28px mono)

CHART (full slide width, 480px height):
  Recharts ComposedChart rendered to PNG by the backend (playwright headless)
  
  Elements:
  — Actual EBITDA line: solid, 2.5px, #1E40AF (blue)
  — P50 projection: dashed, 2px, #1E40AF, dashes 8/4
  — P10-P90 band: Area fill #DBEAFE (very light blue), no stroke
  — IC target: horizontal dashed line at target value, grey #94A3B8, labelled "IC Target 20%"
  — VCP target dots: ReferenceDot at each target date/value, filled #1E40AF, white stroke
  — Today marker: vertical dashed line, #CBD5E1, "NOW" label below x-axis
  — X-axis: quarterly periods, 11px Inter
  — Y-axis: left-side, EBITDA £M, 11px JetBrains Mono, currency formatted
  — Legend: horizontal, below chart, 4 items (Actual / P50 / P10-P90 / IC Target)
  — NO bar chart for historicals — pure line only. Bars were the bug causing the chart
    to look half-width. A line chart renders to full width cleanly.

IRR INSET TABLE (bottom-right of chart area, 280×120px, white card):
  ┌────────────────────────────────┐
  │ IRR SCENARIOS                  │
  │ Bear (P10)     11.8%           │
  │ Base (P50)     16.2%           │  ← bold
  │ Bull (P90)     22.4%           │
  │ IC Case        19.0%  -280bps  │  ← red delta
  └────────────────────────────────┘
  This is the IRR table that was missing from the current implementation.

METHODOLOGY FOOTNOTE (below chart, 10px muted):
  STL decomposition + SARIMA ensemble + Prophet · FRED macro regressors (DFF, INDPRO, CPILFESL)
  Confidence: Moderate (12 quarters of history · 8 minimum recommended)
  P10–P90 band = model uncertainty range · not guaranteed return range
```

**Implementation note**: The chart is rendered to a PNG at 1600×500px by a headless Playwright instance in the backend, then embedded in the PPTX slide. This avoids all matplotlib font/sizing issues seen in the current implementation. Python-pptx inserts the PNG with exact pixel positioning.

---

**Slide 7: Sector Benchmarking**

*Purpose*: How does this company compare to its peers? Gives the board external context for performance.

*Key message line*: Auto-derived — e.g. "EBITDA margin at 35th percentile vs. sector — 380bps gap to median is recoverable through SG&A efficiency."

```
Layout: Left column (dot plot chart) + Right column (table + AI analysis)

LEFT (55%): PERCENTILE DOT PLOT
  One row per metric. Horizontal range bar from P25 to P75 (grey fill).
  Company dot at its actual percentile position (filled navy circle).
  Median marker (vertical tick on bar).
  
  Net Debt/EBITDA  ○────────●──────────────────────────  78th  (inverse — high is good here)
  Gross Margin     ────────────────●───────────────────  55th
  EBITDA Margin    ──────────●─────────────────────────  35th
  Revenue Growth   ─────────●──────────────────────────  28th
                   P25          P75
  
  ● = Company A   ── = P25-P75 range   ○ = median

  This replaces the broken horizontal bar chart that mixed % and x multipliers
  on the same axis. Each metric has its own contextual range — no shared axis.

RIGHT (45%):
  METRIC TABLE:
  METRIC          COMPANY   P25    MEDIAN   P75    PCT
  Revenue Growth  23.6%     8%     18%      26%    28th
  EBITDA Margin   20.0%     14%    22%      28%    35th
  Gross Margin    47.9%     42%    70%      77%    55th
  Net Debt/EBITDA  1.73x   2.1x    3.2x    4.5x   78th

  Fix: GAP column now shows "+13.6pp" not "+135.6%" for percentage metrics.
  Format rule: percentage metrics → "pp" gap. Multiplier metrics → "x" gap.

  AI ANALYSIS (below table, amber left border):
  ● AI Generated · 10px
  "EBITDA margin at 35th percentile. Gross margin at 55th percentile confirms
  healthy unit economics — the gap is a cost efficiency issue, not a pricing
  or delivery problem. SG&A normalisation to sector median would recover
  ~180bps of EBITDA margin and close 2/3 of the IRR gap."

SOURCE: EDGAR XBRL · 28 peers · SIC [code] · as of [date]
```

---

**Slide 8: Risks & Recommended Actions**

*Purpose*: What needs to happen. The most actionable slide in the deck.

*Key message line*: Auto-derived from highest IRR-at-risk item — e.g. "SG&A overrun is the primary value destruction risk — 180bps of IRR recoverable through GTM efficiency."

```
Layout: Risk table (top 60%) + Board Questions (bottom 40%)

RISK TABLE:

  PRI   RISK                      CATEGORY        IRR AT RISK   RECOMMENDED ACTION
  ─────────────────────────────────────────────────────────────────────────────────
  1  ●  SG&A 340bps above plan    Cost efficiency  -180bps      SG&A audit: US office
        2 consecutive quarters                                   GTM efficiency review
                                                                 Owner: CFO · Q2-28

  2  ●  ERP delay (Q3-27 vs       Operational      -60bps       Weekly status: COO
        Q1-27 target)                                            Escalate dependency
                                                                 Owner: COO · Q1-28

  3  ●  Revenue 1 qtr ahead       —                Positive     Monitor renewal cohorts
        but NRR not tracked                                      Add NRR to KPI pack
                                                                 Owner: CRO · Q4-27
  ─────────────────────────────────────────────────────────────────────────────────
  Total IRR at risk: -240bps     Total recoverable: -240bps (all operational)

  Left border: 3px solid RAG colour (only place in deck where border carries colour)
  "Owner" and deadline on every recommended action — not optional

  Fix from current: If no red/amber risks (GREEN company), the table still renders:
  ┌────────────────────────────────────────────────────────┐
  │ ✓  No material risks identified this period.           │
  │    All VCP milestones within ±5% of IC target.        │
  │    Next scheduled review: Q1 2028 board pack.          │
  └────────────────────────────────────────────────────────┘
  This replaces the current empty page that looks broken.

BOARD QUESTIONS (bottom 40%, horizontal separator):

  BOARD MEETING QUESTIONS  ● AI Generated
  ─────────────────────────────────────────────────────────
  1  What is the CFO's revised timeline and benchmark for SG&A to reach 24% of revenue?
  2  Is the ERP Q3-27 date contractually fixed or still dependent on the vendor roadmap?
  3  What is the net revenue retention rate this quarter, and how does it compare to
     the cohort at equivalent tenure at acquisition?
  ─────────────────────────────────────────────────────────
  Questions are sharp, specific, and name the metric. Not generic prompts.
  The operating partner should be able to read these cold and ask them in the room.
```

---

**Slide 9: IRR Scenario Matrix (Exit Multiple × Hold Year)**

*Purpose*: The sensitivity analysis that answers "what do we need to achieve, and by when, to hit our return threshold?"

*Key message line*: Auto-derived — e.g. "At current P50 trajectory, a Year 5 exit requires 12x or higher to meet the IC 19% IRR threshold."

```
Layout: Full-width sensitivity matrix with highlight

MATRIX:

  IRR SCENARIO ANALYSIS — EXIT MULTIPLE × HOLD YEAR
  ────────────────────────────────────────────────────────────────────────
  EXIT MULTIPLE    YEAR 3     YEAR 4     YEAR 5     YEAR 6     YEAR 7
  ────────────────────────────────────────────────────────────────────────
  8.0x             26.6%      19.3%      15.2%      12.5%      10.4%
  10.0x            38.9%      28.0%      21.8%      17.9%      14.9%
  12.0x            49.4%      35.1%      27.3%      22.2%      18.4%
  14.0x            58.6%      41.3%      31.9%      25.9%      21.3%
  16.0x            66.8%      46.8%      36.0%      29.2%      23.9%
  ────────────────────────────────────────────────────────────────────────

  COLOUR LOGIC:
  Green  ≥ 25%:   very light green bg (#D1FAE5) + green text
  Amber  15-24%:  very light amber bg (#FEF3C7) + amber text
  Red    <15%:    very light red bg   (#FEE2E2) + red text

  TWO OVERLAY MARKERS:
  [IC target cell]: thicker border (2px navy), label "IC underwritten"
                    → marks the cell representing entry assumptions
  [P50 trajectory cell]: diagonal arrow indicator in bottom-left of cell
                    → marks where current P50 forecast is heading

  KEY: These two markers tell the story visually — if the P50 arrow is
  below the IC target cell, value is being destroyed. If it's in the same
  row or higher, the investment is on track.

  BELOW TABLE:
  IC underwritten: 10.0x exit · Year 5 · 19.0% IRR (cell highlighted above)
  Current P50 trajectory: exits at ~10.0x · Year 5 · 16.2% IRR (-280bps gap)
  Recovery path: SG&A normalisation recovers ~1.5x turns of EBITDA multiple expansion

  Sensitivity matrix: STL + SARIMA + Prophet ensemble · entry equity £42M · deal debt £84M
```

---

**Slide 10: Appendix — Audit Trail & Evidence**

*Purpose*: Credibility and traceability. Every number in the deck has a source here.

```
Layout: Three sections

REPORT PROVENANCE:
  Generated:   29 June 2026, 14:23
  Approved by: Suryansh D · 29 June 2026, 15:42
  Narrative:   GPT-4o (Azure OpenAI) · reviewed and approved by human
  Assembly:    PE Value Creation Copilot v0.1
  Pipeline:    Last run 29 June 2026, 14:21 (2 min before generation)

  Fix: "Azure Openai" → "Azure OpenAI" (correct capitalisation)
  Fix: Internal file paths (synthetic_vcp_milestones_seed.json) replaced with
       clean source labels — never expose internal paths in board documents

EVIDENCE CITATIONS:
  KPI Data:         Management accounts · FY2027 · December period close
  VCP Milestones:   IC Memo v1.2 · confirmed 2024-03-17 · Suryansh D
  Peer Benchmarks:  EDGAR XBRL · 28 peers · SIC [code] · Q3 2025
  Macro Data:       FRED API — DFF (Fed Funds), INDPRO, CPILFESL, BAA10Y
  Forecasting:      STL decomposition + SARIMA(2,1,2)(1,1,1) + Prophet ensemble

DISCLAIMER (standard PE legal language):
  This report was generated by the PE Value Creation Copilot, an AI-assisted
  portfolio monitoring system. All financial figures are sourced from management
  accounts and third-party data providers and are unaudited unless stated
  otherwise. AI-generated narrative sections were reviewed and approved by a
  qualified professional via the human-in-the-loop gate before inclusion.
  This document is for internal use only and does not constitute investment
  advice or an offer to buy or sell securities.
```

---

### VCP Status Update (5 slides)

A lighter deck for portco management teams. No benchmarks. No IRR. Milestone focus only.

| Slide | Content | Key message |
|---|---|---|
| 1 | Cover (simpler — no IRR on cover) | Company + period + overall milestone status |
| 2 | VCP Milestone Scorecard (full Slide 5 from Board Pack) | x of y milestones on track |
| 3 | Milestone Progress Bars (visual companion) | How close to target on each metric |
| 4 | Priority Actions & Accountability | What management must do + owner + deadline |
| 5 | Next Reporting Period Preview | What will be measured in next cycle |

**Key design difference**: Slide 3 (progress bars) replaces the timeline. Portco management care more about "how close am I?" than "when is the deadline?" The deadline is already on the scorecard.

---

### Operating Flash (4 slides)

Internal-only. Fast to generate, fast to read. No AI narrative — numbers only.

| Slide | Content |
|---|---|
| 1 | Cover + traffic light status for each KPI (grid) |
| 2 | KPI vs plan — same table as Board Pack slide 4 |
| 3 | Alert summary — what was flagged this period + disposition |
| 4 | Actions from last flash + status (closed / open / escalated) |

---

### LP Summary (5 slides)

Portfolio-level. No individual company operational detail — only what LPs are entitled to see.

| Slide | Content |
|---|---|
| 1 | Cover — fund name, vintage, period |
| 2 | Portfolio summary — all portcos, status dots only, IRR base case per company |
| 3 | Portfolio EBITDA performance vs. fund model |
| 4 | Value creation highlights — milestone achievements across portfolio |
| 5 | Outlook — fund-level forward curve, key risks, next steps |

---

## 6. Generation Flow

### Trigger A: Automatic (recommended)

```
Monitoring pipeline runs → Alert synthesised by GPT-4o
        ↓
HITL Gate: operating partner approves alert
        ↓
System checks: report cadence setting for this portco
  — Quarterly Board Pack due this period? → auto-draft Board Pack
  — Monthly VCP Update due? → auto-draft VCP Status Update
        ↓
Report drafted in background (60–90 seconds)
        ↓
Notification: "Q4 Board Pack for Company A is ready for review"
        ↓
[Report Viewer opens — see Section 7]
```

### Trigger B: Scheduled

Each portco has configurable report cadences:
```python
class ReportSchedule(BaseModel):
    portco_id:          str
    board_pack:         Literal['monthly', 'quarterly']    # default: quarterly
    vcp_status:         Literal['weekly', 'monthly']       # default: monthly
    operating_flash:    Literal['weekly', 'monthly', 'off'] # default: monthly
    lp_summary:         Literal['quarterly', 'off']         # default: quarterly
    auto_draft:         bool   # draft without manual trigger (default: True)
    auto_notify:        bool   # send notification when ready (default: True)
```

APScheduler runs at midnight on the 1st of each month. If a board pack is due (quarterly cycle), it drafts automatically. The operating partner wakes up to a draft ready for review, not a blank template.

### Trigger C: Manual

```
Operating partner → /reports → [+ Generate New]
Selects: Company, Type, Period, Sections, Tone
Clicks: Generate Report →
        ↓
Loading state (staged progress messages — see Section 8)
~60–90 seconds
        ↓
Report Viewer opens with draft
```

---

## 7. Report Viewer (React)

The in-app viewer renders the same content as the export — live, always fresh, with editing.

### Layout

```
[← Reports]  Company A — Q4 2027 Board Pack     ● Draft    [Edit]  [Approve]  [↓ Export ▾]
─────────────────────────────────────────────────────────────────────────────────────────────
Generated 2h ago · GPT-4o · Pending approval

[Slide navigator — horizontal strip, 10 thumbnails]
  [1 Cover] [2 At a Glance] [3 Exec Summary] [4 KPIs] [5 VCP] [6 Curve] [7 Bench] [8 Risks] [9 IRR] [10 Audit]

[Active slide — full width render, 16:9 aspect ratio]
  ┌─────────────────────────────────────────────────────────────────┐
  │                                                                 │  16:9
  │              [Slide content rendered as React]                  │  aspect
  │                                                                 │  ratio
  └─────────────────────────────────────────────────────────────────┘
  [← Prev slide]                                          [Next slide →]

[Slide notes panel — below slide]
  Operating partner notes for this slide: [editable text field]
  These notes appear in the PPTX speaker notes, not visible to the board.
```

### Editing

Click on any text element in the slide → inline edit mode activates. The element gets a subtle focus border. Typing replaces the content.

```tsx
// Click on executive summary paragraph
<EditableSlideText
  content={slide.executiveSummary}
  isAI={true}
  onEdit={(newText) => updateSlideContent(slide.id, 'executiveSummary', newText)}
  originalContent={slide.originalAIContent}  // preserved for "restore original"
/>
```

When a section has been edited: `● AI Generated` label changes to `✎ Edited · [name] · [time]`. A "Restore original" link appears. Both states are recorded in the audit trail.

### Approval Flow

```
[Approve] button (top bar) → confirmation dialog:
  "Approve this report for export and distribution?
   AI-generated sections will be logged as human-reviewed."
  [Cancel]  [Approve & Finalise]
        ↓
Report status changes: Draft → Approved
PDF and PPTX export unlocked (draft exports are watermarked "DRAFT")
Audit record: approved by [name] at [timestamp]
```

---

## 8. AI Content Generation Spec

### Model Routing

| Content | Model | Why |
|---|---|---|
| Executive summary narrative | GPT-4o (Azure OpenAI) | Best long-form coherent synthesis |
| Board questions (3 questions) | GPT-4o | Needs reasoning about what the GP doesn't know |
| Risks & recommended actions | GPT-4o structured output | JSON schema enforcement for table rows |
| Slide key message lines | GPT-4o | One sentence — needs precision |
| Risk AI analysis (benchmarks) | GPT-4o | Comparative reasoning over peer data |
| All computation (IRR, deltas, percentiles) | Python only | Never use LLM for arithmetic |

### Prompt: Executive Summary (Slide 3)

```python
EXEC_SUMMARY_PROMPT = """
You are writing the executive summary for a Private Equity board pack.
The audience is a board of directors and the GP operating partner team.
Write formally, concisely, and without hedging language.

COMPANY: {company_name} ({sector})
PERIOD: {period}
REPORT DATE: {report_date}

FINANCIAL PERFORMANCE:
{kpi_table_json}

VCP MILESTONE STATUS:
{vcp_summary_json}

IRR SCENARIOS:
Bear: {irr_bear}%  Base: {irr_base}%  Bull: {irr_bull}%  IC: {irr_ic}%

SECTOR BENCHMARK POSITION:
{benchmark_json}

TOP RISKS (from alert agent):
{risks_json}

Write exactly 4 sections in this order:
1. SITUATION (2-3 sentences): Revenue and EBITDA performance vs IC targets. State numbers.
2. KEY RISKS (3 bullet points): One sentence each. Name specific metrics and gaps.
3. PRIORITY ACTION (1 sentence): Name the person responsible (CFO/CEO/COO), the action, and the deadline.
4. Do not include a heading for section 4 — instead write one sentence on the IRR outlook.

Rules:
- Use past tense for performance ("achieved", "delivered", "exceeded")
- Use future tense for actions ("must implement", "will review")
- Never use "may", "might", "could" or other hedging language
- Every number cited must appear in the data provided above
- Maximum 180 words total
- Tone: Board-ready (formal, direct, no jargon)
"""
```

### Prompt: Board Questions (Slide 8)

```python
BOARD_QUESTIONS_PROMPT = """
You are preparing three questions for an operating partner to ask at a PE board meeting.

Context:
- Company: {company_name}
- Period: {period}
- The operating partner has already read the board pack
- These questions should be ones management cannot easily deflect
- They should probe the gaps identified in the data

Risks and gaps identified:
{risks_and_gaps_json}

VCP milestones at risk or missing data:
{vcp_issues_json}

Write exactly 3 questions.
Rules:
- Each question names a specific metric, milestone, or decision point
- Questions cannot be answered with "yes" or "no"
- Questions should reveal whether management has a real plan, not just awareness of the problem
- Do not use "How do you plan to..." — use "What is..." or "When will..." or "What specifically..."
- Maximum 30 words per question
"""
```

### Structured Output Schema: Risks Table

```python
from pydantic import BaseModel
from typing import Literal

class RiskRow(BaseModel):
    priority:           int             # 1, 2, 3...
    severity:           Literal['red', 'amber', 'green']
    risk_statement:     str             # max 15 words
    category:           str             # Cost efficiency / Operational / Commercial / etc.
    irr_at_risk_bps:    int | None      # None if not quantifiable
    recommended_action: str             # max 20 words
    owner:              str             # CFO / CEO / COO / Board
    deadline:           str             # "Q2-28" format

class RisksOutput(BaseModel):
    risks:              list[RiskRow]
    total_irr_at_risk_bps: int
    all_recoverable:    bool
    no_risk_statement:  str | None      # shown when risks list is empty
```

---

## 9. Export & Distribution

### Export Formats

**PPTX (primary)**
- Generated by `python-pptx` in FastAPI backend
- All slides use `python-pptx` native shapes — text boxes, tables, images
- Charts embedded as PNG (rendered by Playwright headless → base64 → inserted)
- Fully editable after export: operating partner can adjust in PowerPoint
- Speaker notes: operating partner's slide notes written to PPTX speaker notes layer
- File naming: `[CompanyName]_BoardPack_[Period]_[GeneratedDate].pptx`

**PDF (circulation)**
- Generated by converting PPTX via LibreOffice headless (`soffice --headless --convert-to pdf`)
- Or directly from the Playwright screenshot route (PPTX → PDF render)
- Watermarked "DRAFT" until approved; watermark removed on approval
- File naming: `[CompanyName]_BoardPack_[Period]_APPROVED_[Date].pdf`

**Both formats available immediately after approval** — the PPTX for the board room, the PDF for email circulation.

### Distribution (future feature, not in prototype)

Post-approval actions:
```
[ ↓ Export PPTX ]
[ ↓ Export PDF  ]
[ → Share Link  ]  ← generates a time-limited read-only URL (7 days, view-only)
[ ✉ Send to Board ]  ← emails PDF to board member list (requires email connector)
```

---

## 10. React Module Architecture

```
app/(dashboard)/reports/
  page.tsx                     ← Reports library page
  [id]/
    page.tsx                   ← Report viewer
    edit/
      page.tsx                 ← Full-screen edit mode (optional)

components/reports/
  ReportLibrary.tsx            ← List of reports + generate form
  ReportCard.tsx               ← Single report in list (status, actions)
  ReportViewer.tsx             ← Slide viewer shell
  SlideNavigator.tsx           ← Horizontal thumbnail strip
  SlideRenderer.tsx            ← Routes to correct slide component
  GenerateForm.tsx             ← Report type, period, sections, tone
  GenerateProgress.tsx         ← Staged loading state

  slides/
    SlideCover.tsx
    SlideAtAGlance.tsx
    SlideExecutiveSummary.tsx
    SlideKPIScorecard.tsx
    SlideVCPScorecard.tsx
    SlideForwardCurve.tsx
    SlideBenchmarks.tsx
    SlideRisksActions.tsx
    SlideIRRMatrix.tsx
    SlideAuditTrail.tsx

  editors/
    EditableSlideText.tsx      ← Click-to-edit wrapper
    SlideSectionEditor.tsx     ← Full-section edit panel

lib/api/reports.ts             ← useReports(), useReport(), useGenerateReport(), useApproveReport()
lib/types/report.ts            ← Report, Slide, SlideContent, ReportStatus types
```

### FastAPI Endpoints

```
GET  /api/reports                           → Report[] (library)
GET  /api/reports/{id}                      → Report (full with all slides)
POST /api/reports/generate                  → { report_id, status: 'generating' }
GET  /api/reports/{id}/status               → { status, progress_step, progress_pct }
POST /api/reports/{id}/approve              → Report (status: approved)
PATCH /api/reports/{id}/slides/{slide_id}  → Slide (updated content)
GET  /api/reports/{id}/export/pptx         → PPTX file download
GET  /api/reports/{id}/export/pdf          → PDF file download
DELETE /api/reports/{id}                   → 204 No Content
```

### Generation Progress Polling

The frontend polls `/api/reports/{id}/status` every 2 seconds during generation and updates the staged progress UI:

```tsx
const PROGRESS_STEPS = [
  { key: 'fetching_kpis',       label: 'Fetching KPI data',              pct: 10 },
  { key: 'running_forecast',    label: 'Running forward curve',           pct: 25 },
  { key: 'benchmarking',        label: 'Pulling sector benchmarks',       pct: 40 },
  { key: 'generating_narrative',label: 'Writing executive summary...',    pct: 60 },
  { key: 'generating_questions',label: 'Generating board questions...',   pct: 75 },
  { key: 'rendering_charts',    label: 'Rendering charts',                pct: 85 },
  { key: 'assembling_pptx',     label: 'Assembling deck',                 pct: 95 },
  { key: 'complete',            label: 'Report ready',                    pct: 100 },
]
```

---

## 11. Bug Fixes Required in Current Implementation

From analysis of the submitted PDFs:

| Bug | Root cause | Fix |
|---|---|---|
| "DUISTAT" column overflow | ReportLab column widths sum > page width | Status: 32px fixed column. DUE: "Q4-27" format, 60px. Never combine them. |
| Net Debt 173.1x in chart | Unit multiplied by 100 before plotting | Fix: pass raw value (1.73), not percentage-expressed value (173.1) |
| Internal file paths in Audit Trail | `str(path)` written directly to PDF | Fix: Replace with clean human-readable source labels |
| "KEY RISK" text clipped in strip | Footer strip height too small for variable text | Fix: Truncate to max 8 words + ellipsis, or increase strip height to 48px |
| Risks page empty on GREEN company | Condition `if risks:` skips render entirely | Fix: Render "No material risks" block when list is empty |
| Benchmark gap "+135.6%" misleading | `(company - median) / median * 100` formula | Fix: For % metrics, use `company_pct - median_pct` in pp. For multipliers, use `company_x - median_x`. |
| Chart stops at 65% page width | matplotlib `figsize` not matching ReportLab canvas width | Fix: Use Playwright to render Recharts to PNG at exact pixel dimensions, then embed. Removes all matplotlib sizing issues. |
| Bar chart for forward curve | Legacy matplotlib bar + line combo | Fix: Pure line chart. Historical = solid line. Forecast = dashed. Today = ReferenceLine. |
| Inconsistent report styling | Two separate ReportLab templates | Fix: Single master template class, both report types inherit from it |
| "Azure Openai" spelling | Hardcoded string | Fix: "Azure OpenAI" |
| ISO date "2027-12" on cover | `str(date)[:7]` formatting | Fix: `date.strftime("%B %Y")` → "December 2027" |

---

## 12. PE Standard Checklist

Before a report is considered production-ready for a real PE firm:

- [ ] Firm logo and name on every slide header (configurable per fund)
- [ ] "CONFIDENTIAL — BOARD ONLY" on every slide footer
- [ ] Page numbers on every slide
- [ ] Investment metadata on cover (deal date, entry multiple, equity deployed, fund name)
- [ ] IRR scenario table on the forward view slide
- [ ] Table of contents (slide 2 for Board Pack, after cover)
- [ ] All AI-generated content clearly labelled
- [ ] HITL approval with approver name + timestamp on slide 10
- [ ] No internal file paths, system paths, or developer notes anywhere
- [ ] All dates in full format ("December 2027", not "2027-12")
- [ ] All percentage gaps expressed as "pp" not "%" for percentage metrics
- [ ] Benchmark chart uses per-metric axes, not a shared axis
- [ ] Risk table always renders (no empty section for GREEN companies)
- [ ] Export watermarked "DRAFT" until approved

---

*This specification covers the complete report generation module — end-to-end from user intent to board-room delivery.*
