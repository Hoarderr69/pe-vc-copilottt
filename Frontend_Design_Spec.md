# PE Value Creation Copilot — Frontend Design Specification

**Full-stack SaaS · React (Next.js) + FastAPI**
*Design benchmark: Linear, Perplexity, Claude, Vercel — calm, minimal, data-forward, trust-building*

---

## Design Philosophy

The reference products you listed share one principle: **the UI earns trust by disappearing**. Linear's sidebar is dimmed so the work takes precedence. Claude uses whitespace to make a response feel like it was written just for you. Perplexity Finance surfaces a number and a source — nothing else until you ask.

For a PE Value Creation Copilot, this is non-negotiable. Operating partners and portco CFOs are intelligent, time-poor, and making high-stakes decisions. They don't trust a product that looks like a Bloomberg terminal. They trust one that feels like a well-prepared analyst who has already read everything and is telling you the three things that matter.

**Three design commitments:**

**1. One answer per screen** — every page answers one question. Portfolio Overview: *"Which companies need my attention today?"* VCP Tracker: *"Are we delivering on what we promised?"* Deep Dive: *"What is actually happening at this company right now?"*

**2. Data speaks, the interface is silent** — charts, numbers, and status indicators carry the information. Navigation, borders, labels, and decorative chrome are suppressed. If a UI element isn't communicating data, ask whether it needs to exist.

**3. Trust through traceability** — every number has a source. Every alert has a citation. Every approved alert has a timestamp and an approver. This isn't a feature — it's the design language. The product feels credible because it shows its work.

---

## Tech Stack Decision

**Framework**: Next.js 15 (App Router) — server components for data-heavy pages, client components only where needed (charts, interactive HITL actions). Standard for production SaaS.

**Styling**: Tailwind CSS v4 — utility-first, zero runtime, pairs perfectly with shadcn.

**UI Components**:
- **shadcn/ui** — general-purpose components: buttons, dialogs, dropdowns, tables, forms, badges. Unstyled base on Radix UI, fully customizable.
- **Tremor v3** — analytics-specific components: KPI cards, area charts, bar charts, progress bars, sparklines. Built specifically for finance/data dashboards on top of Recharts + Tailwind.

**Charts**: Recharts (via Tremor) for standard charts; raw Recharts for custom forward curve with IC overlay.

**API State**: TanStack Query (React Query v5) — data fetching, caching, background refetch, optimistic updates for HITL actions.

**Client State**: Zustand — sidebar state, active company selection, filters. Minimal.

**Auth**: NextAuth.js v5 (Auth.js) with credentials provider for the prototype; swap to Clerk or Auth0 for production.

**Backend**: FastAPI (Python) — all ML, LangGraph, LlamaParse, database calls live here. React calls REST endpoints only.

**Type Safety**: TypeScript end-to-end. Zod schemas shared between API response validation and form handling.

---

## Design System

### Colour Palette

**Mode**: Light as default. Finance, board decks, printed PDFs — light is the designed version. Dark mode can be added via CSS variables with no component changes.

```css
/* globals.css — CSS custom properties */
:root {
  /* Surfaces */
  --bg-page:       #F8FAFC;   /* near-white, cool tint */
  --bg-surface:    #FFFFFF;   /* cards, modals */
  --bg-sidebar:    #F1F5F9;   /* sidebar — recedes behind main content */
  --bg-muted:      #F1F5F9;   /* subtle highlights */

  /* Borders */
  --border:        #E2E8F0;   /* 1px default, barely visible */
  --border-strong: #CBD5E1;   /* hover state */

  /* Text */
  --text-primary:  #0F172A;   /* near-black, not harsh */
  --text-secondary:#475569;   /* labels, captions */
  --text-muted:    #94A3B8;   /* timestamps, disabled, footnotes */
  --text-link:     #3B82F6;   /* blue, used sparingly */

  /* Accent */
  --accent:        #1E40AF;   /* deep professional blue — buttons, active */
  --accent-hover:  #1D4ED8;

  /* RAG Status */
  --green:         #10B981;
  --green-bg:      #D1FAE5;
  --amber:         #F59E0B;
  --amber-bg:      #FEF3C7;
  --red:           #EF4444;
  --red-bg:        #FEE2E2;
  --neutral:       #94A3B8;
  --neutral-bg:    #F1F5F9;

  /* Charts */
  --chart-primary: #1E40AF;   /* main data series */
  --chart-peer:    #64748B;   /* peer/plan reference line */
  --chart-band:    #DBEAFE;   /* P10–P90 uncertainty band fill */
}
```

**Rules**: No gradients. No box shadows except a single `0 1px 3px rgba(0,0,0,0.06)` on cards. Status colours appear only on status elements — never as background fills on cards or section headers. If everything is red, nothing is red.

---

### Typography

```css
/* layout.tsx — font imports */
import { Inter, JetBrains_Mono } from 'next/font/google'

const inter = Inter({ subsets: ['latin'], variable: '--font-sans' })
const mono  = JetBrains_Mono({ subsets: ['latin'], variable: '--font-mono' })
```

```css
/* tailwind.config.ts */
fontFamily: {
  sans: ['var(--font-sans)', 'system-ui', 'sans-serif'],
  mono: ['var(--font-mono)', 'monospace'],
}
```

| Usage | Size | Weight | Family | Colour |
|---|---|---|---|---|
| Page title (h1) | 20px | 700 | Inter | --text-primary |
| Section title (h2) | 15px | 600 | Inter | --text-primary |
| Card title (h3) | 13px | 600 | Inter | --text-primary |
| Body | 13px | 400 | Inter | --text-secondary |
| Table header | 11px / uppercase / +0.05em | 500 | Inter | --text-muted |
| KPI value (large) | 28px | 700 | JetBrains Mono | --text-primary |
| Table cell (number) | 13px | 500 | JetBrains Mono | --text-primary |
| Caption / footnote | 11px | 400 | Inter | --text-muted |
| Status badge | 12px | 600 | Inter | RAG colour |

All numbers in data tables, KPI cards, and metric displays use `font-mono`. This ensures digit-level vertical alignment in columns — essential in a finance product.

---

### Spacing & Layout

```
Base unit:          4px (Tailwind default)
Standard scale:     4, 8, 12, 16, 24, 32, 48, 64

Sidebar width:      240px fixed
Content max-width:  1200px (centred in remaining space)
Content padding:    24px horizontal
Card padding:       16px
Card gap:           8px
Section gap:        24px
Page header height: 56px
Border radius — card:   8px
Border radius — badge:  4px
Border radius — button: 6px
```

---

### Component Glossary

**KPI Card** — `<MetricCard />`
```
┌──────────────────────────────┐
│  REVENUE                     │  ← 11px uppercase, --text-muted
│  £ 21.4M          ▲ +8.2%   │  ← 28px mono, delta right-aligned
│  Plan: £23.1M · -7.4%       │  ← 11px secondary, vs-plan gap
└──────────────────────────────┘
```
White card, 1px border, 8px radius. Delta is green/red. Never colour the card background — let the number carry sentiment.

**Status Badge** — `<StatusBadge status="behind" />`
```
● Behind    ← 6px coloured dot + label, pill shape, 10% opacity bg
● At Risk
● On Track
● Complete
○ No Data
```

**Alert Card** — `<AlertCard />`
```
┌──────────────────────────────────────────────────────┐
│  ● RED  ·  Company A  ·  2 hours ago                 │
│                                                      │
│  Revenue 12% below IC target. IRR at risk -280bps.   │
│  Root cause: SG&A expansion outpacing revenue…       │
│  Lever: Pricing review + cost structure audit        │
│                                                      │
│  [ ✓ Approve ]  [ ✎ Edit ]  [ ✕ Reject ]            │
│  Source: EDGAR 10-Q · IC Memo p.4 · FRED DFF         │
└──────────────────────────────────────────────────────┘
```
Left border: 3px solid RAG colour — the only heavy colour in the UI. Everything else is text.

**Sidebar Nav Item** — `<NavItem />`
Active state: slightly darker background (`--bg-muted` → `--border`) + primary text. Inactive: muted text, no background. No icons in prototype.

---

## Project Structure

```
pe-copilot/
├── app/                              ← Next.js App Router
│   ├── (auth)/
│   │   ├── login/
│   │   │   └── page.tsx
│   │   └── layout.tsx
│   ├── (dashboard)/
│   │   ├── layout.tsx                ← shared: sidebar + top bar
│   │   ├── page.tsx                  ← Portfolio Overview (/)
│   │   ├── companies/
│   │   │   ├── [id]/
│   │   │   │   ├── page.tsx          ← Company Deep Dive
│   │   │   │   ├── vcp/
│   │   │   │   │   └── page.tsx      ← VCP Tracker
│   │   │   │   └── benchmarks/
│   │   │   │       └── page.tsx      ← Benchmarks
│   │   │   └── [id]/setup/
│   │   │       └── page.tsx          ← VCP Setup Wizard
│   │   ├── alerts/
│   │   │   └── page.tsx              ← HITL Alert Queue
│   │   └── reports/
│   │       └── page.tsx              ← Report Generation
│   ├── api/
│   │   └── [...path]/
│   │       └── route.ts              ← thin proxy to FastAPI (adds auth header)
│   ├── globals.css
│   └── layout.tsx                    ← fonts, providers
│
├── components/
│   ├── layout/
│   │   ├── Sidebar.tsx
│   │   ├── TopBar.tsx
│   │   └── PipelineStatus.tsx        ← "● Live · 2m ago" indicator
│   ├── portfolio/
│   │   ├── PortfolioCard.tsx         ← company summary card
│   │   ├── AttentionList.tsx         ← red/amber alerts strip at top
│   │   └── FundSummaryStrip.tsx      ← 4 fund-level KPI cards
│   ├── company/
│   │   ├── KPIGrid.tsx               ← 4 metric cards row
│   │   ├── ForwardCurveChart.tsx     ← THE centrepiece chart
│   │   ├── IRRScenarioTable.tsx      ← Bear/Base/Bull/IC table
│   │   └── CompanyHeader.tsx         ← breadcrumb + status + actions
│   ├── vcp/
│   │   ├── MilestoneTable.tsx        ← scrollable milestone rows
│   │   ├── MilestoneProgressBars.tsx
│   │   ├── MilestoneTimeline.tsx     ← horizontal Gantt-style
│   │   └── VCPSetupWizard.tsx        ← 3-step onboarding flow
│   ├── alerts/
│   │   ├── AlertCard.tsx
│   │   ├── AlertQueue.tsx
│   │   └── HITLActions.tsx           ← Approve / Edit / Reject
│   ├── benchmarks/
│   │   ├── BenchmarkTable.tsx        ← company vs P25/median/P75
│   │   └── BenchmarkDotPlot.tsx      ← Recharts custom dot plot
│   ├── reports/
│   │   ├── ReportList.tsx
│   │   └── ReportGenerator.tsx       ← checklist + generate button
│   └── ui/
│       ├── MetricCard.tsx            ← wrapper around Tremor Card
│       ├── StatusBadge.tsx
│       ├── SparkLine.tsx             ← 80×40px trend line, no axes
│       ├── Citation.tsx              ← 11px muted source text
│       ├── AILabel.tsx               ← "● AI Generated · 2h ago"
│       └── SectionLabel.tsx          ← 11px uppercase section headers
│
├── lib/
│   ├── api/
│   │   ├── client.ts                 ← typed fetch wrapper (base URL, auth)
│   │   ├── portfolio.ts              ← usePortfolio(), useCompany()
│   │   ├── alerts.ts                 ← useAlerts(), useApproveAlert()
│   │   ├── vcp.ts                    ← useVCP(), useExtractVCP()
│   │   ├── benchmarks.ts             ← useBenchmarks()
│   │   └── reports.ts                ← useGenerateReport()
│   ├── types/
│   │   ├── portfolio.ts
│   │   ├── alert.ts
│   │   ├── vcp.ts
│   │   └── benchmark.ts
│   └── utils/
│       ├── formatters.ts             ← formatCurrency, formatPercent, formatBps
│       └── statusColors.ts           ← RAG → Tailwind class lookup
│
├── hooks/
│   ├── usePolling.ts                 ← re-fetch pipeline status every 60s
│   └── useHITL.ts                   ← optimistic approve/reject with rollback
│
├── store/
│   └── ui.ts                        ← Zustand: sidebar open, active company
│
├── tailwind.config.ts
├── next.config.ts
└── package.json
```

---

## Page Architecture — Product POV

Every page answers exactly one question. If you can't state the question in one sentence, the page is doing too much.

---

### Layout Shell (`app/(dashboard)/layout.tsx`)

```
┌──────────────────────────────────────────────────────────────────┐
│ Sidebar (240px fixed)    │ Main content area                     │
│ bg: --bg-sidebar         │ bg: --bg-page                        │
│                          │                                       │
│  VC Copilot              │  [TopBar — breadcrumb + actions]     │
│  ─────────────           │  ─────────────────────────────────── │
│                          │                                       │
│  PORTFOLIO               │  [Page content]                      │
│  ○ Overview              │                                       │
│  ○ Alerts    3 ←badge    │                                       │
│                          │                                       │
│  COMPANIES               │                                       │
│  ○ Company A             │                                       │
│  ● Company B  ← active   │                                       │
│  ○ Company C             │                                       │
│                          │                                       │
│  TOOLS                   │                                       │
│  ○ Benchmarks            │                                       │
│  ○ Reports               │                                       │
│  ○ VCP Setup             │                                       │
│                          │                                       │
│  ──────────────          │                                       │
│  ● Live · 2m ago         │   ← PipelineStatus, always visible  │
└──────────────────────────┴───────────────────────────────────────┘
```

The sidebar uses `--bg-sidebar` (#F1F5F9) — slightly cooler than the page. It recedes. The content area is white and active. The sidebar's job is to orient, not attract attention. This is exactly what Linear does.

The `PipelineStatus` indicator at the bottom (green dot when fresh, grey when stale) is a persistent trust signal: the user always knows data freshness without hunting for it.

---

### Page 1: Portfolio Overview (`/`)

**Question**: *Which companies need my attention today?*

```tsx
// app/(dashboard)/page.tsx
export default async function PortfolioPage() {
  const portfolio = await getPortfolio()  // server component fetch

  return (
    <div className="space-y-6">
      <AttentionList companies={portfolio.needsAttention} />
      <SectionLabel>Portfolio Companies</SectionLabel>
      <div className="grid grid-cols-3 gap-4">
        {portfolio.companies.map(c => <PortfolioCard key={c.id} company={c} />)}
      </div>
      <SectionLabel>Fund Summary</SectionLabel>
      <FundSummaryStrip metrics={portfolio.fundMetrics} />
    </div>
  )
}
```

**`AttentionList`** — appears only if red/amber companies exist. If all green, show a calm `✓ All companies on track` message. Zero visual drama when things are fine.

**`PortfolioCard`** — uniform 3-column grid:
```
┌────────────────┐
│ Company A      │
│ ● Behind       │  ← StatusBadge, first element
│                │
│ Rev  £21.4M    │  ← font-mono
│  vs plan -7.4% │  ← red ▼
│ EBITDA  18.2%  │
│  vs plan -280bp│
│ VCP   4/7 ✓   │
│                │
│  [Open →]      │
└────────────────┘
```

**`FundSummaryStrip`** — 4 `<MetricCard>` components in a row. Portfolio EBITDA, VCP milestones on track, average IRR base case, alert count.

---

### Page 2: Company Deep Dive (`/companies/[id]`)

**Question**: *What is actually happening at this company right now?*

Three stacked sections:

**Section 1 — KPI Grid**
```tsx
<KPIGrid metrics={[
  { label: 'REVENUE',            value: '£21.4M', delta: '-7.4%', vs: '£23.1M target' },
  { label: 'EBITDA MARGIN',      value: '18.2%',  delta: '-280bps', vs: '21.0% target' },
  { label: 'NET DEBT / EBITDA',  value: '3.8x',   delta: '+0.4x',  vs: '3.4x target' },
  { label: 'CASH',               value: '£4.2M',  delta: null,     vs: 'On plan' },
]} />
```

**Section 2 — Forward Curve (centrepiece chart)**

This is the defining visual. A full-width Recharts `ComposedChart` showing:
- **Actual line** — solid, `--chart-primary` (#1E40AF)
- **P50 forecast line** — dashed, same blue
- **P10–P90 band** — `<Area>` fill, `--chart-band` (#DBEAFE), very subtle
- **IC target dots** — `<ReferenceDot>` at each VCP target date/value, labelled
- **Today marker** — `<ReferenceLine>` vertical dashed grey

```tsx
// components/company/ForwardCurveChart.tsx
import { ComposedChart, Line, Area, ReferenceDot, ReferenceLine,
         XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'

export function ForwardCurveChart({ actual, forecast, icTargets }) {
  return (
    <Card className="p-4">
      <div className="flex justify-between items-center mb-4">
        <SectionLabel>EBITDA FORWARD CURVE</SectionLabel>
        <PeriodToggle options={['2Y', '5Y', '10Y']} />
      </div>
      <ResponsiveContainer width="100%" height={280}>
        <ComposedChart data={[...actual, ...forecast]}>
          <XAxis dataKey="period" tick={{ fontSize: 11 }} />
          <YAxis tick={{ fontSize: 11, fontFamily: 'var(--font-mono)' }}
                 tickFormatter={v => `£${v}M`} />
          <Tooltip content={<CurveTooltip />} />

          {/* Uncertainty band */}
          <Area type="monotone" dataKey="p90" fill="var(--chart-band)"
                stroke="none" />
          <Area type="monotone" dataKey="p10" fill="var(--bg-page)"
                stroke="none" />  {/* masks bottom of band */}

          {/* Actual + forecast */}
          <Line type="monotone" dataKey="actual" stroke="var(--chart-primary)"
                strokeWidth={2} dot={false} />
          <Line type="monotone" dataKey="p50" stroke="var(--chart-primary)"
                strokeWidth={2} strokeDasharray="5 4" dot={false} />

          {/* IC milestone dots */}
          {icTargets.map(t => (
            <ReferenceDot key={t.id} x={t.period} y={t.value}
              r={5} fill="var(--chart-primary)" stroke="white" strokeWidth={2}
              label={{ value: t.label, position: 'top', fontSize: 10 }} />
          ))}

          {/* Today */}
          <ReferenceLine x={today} stroke="var(--border-strong)"
                         strokeDasharray="3 3" />
        </ComposedChart>
      </ResponsiveContainer>
      <ChartLegend />
    </Card>
  )
}
```

When the P50 line tracks below the IC target dots, the story is told in one glance. That visual gap is the entire product proposition.

Below the chart: **IRR Scenario Table** — 4 columns (Bear P10 / Base P50 / Bull P90 / IC Underwritten), `font-mono`, `text-right`. The gap to IC underwritten is coloured red if negative.

**Section 3 — Sector Benchmark Summary**

Compact preview (3 metrics with percentile bars). Full benchmarks on their own page.

---

### Page 3: VCP Tracker (`/companies/[id]/vcp`)

**Question**: *Are we delivering on what we promised?*

```
┌─────────────────────────────────────────────────────────────────────┐
│ VCP Health: ● Behind (4/7 on track)                    [Update VCP] │
│ Source: IC Memo · uploaded 2024-03-15 · confirmed 2024-03-17        │
└─────────────────────────────────────────────────────────────────────┘

Milestone Table (sorted: Behind → At Risk → On Track → Complete)
Milestone         Category    Target    Actual    Status      Due
──────────────────────────────────────────────────────────────────────
Revenue Growth    Financial   £23.1M    £21.4M    ● Behind    Y2 Q3
EBITDA Margin     Financial   21.0%     18.2%     ● Behind    Year 3
SG&A Ratio        Operational 24%rev    27.4%     ● At Risk   Year 2
ERP Migration     Operational Done      Q3 Y2     ● Behind    Overdue
CRO Hire          Org         Done      ✓         ● Complete  Month 3
Customer NPS      Commercial  Score 45  Score 47  ● On Track  Year 2
Net Debt/EBITDA   Financial   3.4x      3.8x      ● At Risk   Year 3

Progress bars (visual companion to table)
Revenue  ████████████████░░  £21.4M / £23.1M  92.6%

Timeline (horizontal, mini Gantt)
```

The source citation under the header ("IC Memo · uploaded · confirmed") is the product's trust signal. Users know the milestones didn't appear from nowhere.

---

### Page 4: Alert Queue (`/alerts`)

**Question**: *What do I need to review and approve today?*

```tsx
// components/alerts/AlertQueue.tsx
export function AlertQueue({ pending, approved }) {
  return (
    <div className="space-y-4">
      <SectionLabel>PENDING REVIEW ({pending.length})</SectionLabel>
      {pending.map(alert => (
        <AlertCard key={alert.id} alert={alert} />
      ))}
      <SectionLabel>APPROVED TODAY</SectionLabel>
      <ApprovedList items={approved} />
    </div>
  )
}
```

**`AlertCard`** structure:
- Left border: 3px solid RAG colour (only bold colour in entire UI)
- Top row: severity badge + company name + timestamp
- Headline: 14px, primary, bold
- Root cause + recommended lever: 13px secondary
- Sparkline (80×40px, no axes) showing the relevant trend
- IRR at risk: monospace, red
- Citations: 11px muted, comma-separated
- Actions: Approve (filled blue) / Edit (outlined) / Reject (ghost red)

**HITL Actions** use optimistic updates with rollback:
```tsx
// hooks/useHITL.ts
export function useApproveAlert() {
  const queryClient = useQueryClient()
  return useMutation({
    mutationFn: (alertId: string) => api.alerts.approve(alertId),
    onMutate: async (alertId) => {
      // Optimistically move card to Approved section
      await queryClient.cancelQueries({ queryKey: ['alerts'] })
      const prev = queryClient.getQueryData(['alerts'])
      queryClient.setQueryData(['alerts'], (old) => optimisticApprove(old, alertId))
      return { prev }
    },
    onError: (err, _, ctx) => {
      // Rollback on error
      queryClient.setQueryData(['alerts'], ctx?.prev)
      toast.error('Failed to approve — please try again')
    },
    onSettled: () => queryClient.invalidateQueries({ queryKey: ['alerts'] }),
  })
}
```

---

### Page 5: VCP Setup Wizard (`/companies/[id]/setup`)

**Question**: *How do I onboard a new company at deal close?*

3-step wizard using a `<Steps>` pattern (not full-page routes — state stays in the component):

```tsx
type SetupStep = 'upload' | 'review' | 'confirm'

// Step 1: Upload
<DropZone accept=".pdf" onUpload={handleUpload}
  label="Drop IC Memo or Investment Thesis PDF here"
  subLabel="LlamaParse will extract the text. Extraction takes ~30 seconds." />

// Step 2: Review extracted milestones (most important step)
<MilestoneReviewTable
  milestones={extracted}
  onEdit={handleEdit}
  onDelete={handleDelete}
  onAdd={handleAdd}
/>
// Each row shows confidence dots (●●●●○ = High)
// Low confidence rows: amber left border + inline explanation

// Step 3: Confirm & activate
<ConfirmSummary milestones={confirmed} />
<Button onClick={handleActivate}>Activate Monitoring →</Button>
```

Confidence visualization — 5-dot component, not a percentage. Signals uncertainty honestly without false precision. Low confidence triggers a note: *"Ambiguous language found at IC Memo p.6. Please review and confirm this commitment."*

---

### Page 6: Benchmarks (`/companies/[id]/benchmarks`)

**Question**: *Where does this company stand in its sector, and what does closing the gap look like?*

```
Sector: B2B SaaS  [Change ▾]
Peer set: 34 companies · SIC 7372 · £15–50M revenue · EDGAR XBRL · Q3 2025

Benchmark Table (company vs P25 / Median / P75 / Percentile)
+ Dot Plot (Recharts custom scatter: company dot on horizontal range axis)

AI Gap Analysis (GPT-4o narrative output)
● AI Generated · 1h ago
"To reach sector median EBITDA margin (22.0%), Company A needs to close 
a 280bps gap. Peer companies that moved from 35th to 50th percentile 
most commonly did so through SG&A efficiency improvement (68% of cases)..."
Citation: EDGAR XBRL · 34 companies · 2020–2025
```

The dot plot is a custom Recharts `ScatterChart` where each metric is a separate row — company value shown as a filled dot against a horizontal range bar from P25 to P75. This communicates relative position better than any table.

---

### Page 7: Reports (`/reports`)

Generate board-ready PDFs from live data. Form: company selector + report type + period + section checklist. The FastAPI backend assembles the PDF (ReportLab + narrative from GPT-4o) and returns a download URL.

---

### Login (`/login`)

Minimal. Company logo, email + password, sign in button. Nothing else. Not the product — don't spend time on it.

---

## Key Interaction Patterns

**Progressive Disclosure** — Portfolio Overview shows 3 numbers per card. Company Deep Dive shows 20. Never show everything at once.

**Everything Has a Source** — every AI output, every number, carries an inline citation. 11px muted text. Users might not click it — but its presence builds trust.

**AI Outputs Are Always Labelled** — `<AILabel>● AI Generated · 2h ago</AILabel>` on every LLM-produced section. Not a disclaimer — a signal of honesty.

**Status Is Earned** — Red means red. Very few red alerts in normal operation. If everything is red, the system has failed the user before they open an alert.

**Button Weight = Action Weight** — Approve: `variant="default"` (filled blue). Edit: `variant="outline"`. Reject: `variant="ghost"` with `text-red`. The visual weight tells users what the expected action is without reading labels.

**Background Refetch** — TanStack Query re-fetches alerts and pipeline status every 60 seconds silently. The `PipelineStatus` component in the sidebar shows "● Live · Xm ago" so users never wonder if the data is stale.

---

## Developer Implementation

### API Client

```typescript
// lib/api/client.ts
const BASE = process.env.NEXT_PUBLIC_API_URL  // http://localhost:8000

async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const session = await getSession()
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${session?.accessToken}`,
      ...init?.headers,
    },
  })
  if (!res.ok) throw new APIError(res.status, await res.text())
  return res.json()
}
```

### Typed API Hooks

```typescript
// lib/api/portfolio.ts
import { useQuery } from '@tanstack/react-query'

export function usePortfolio() {
  return useQuery({
    queryKey: ['portfolio'],
    queryFn: () => apiFetch<Portfolio>('/api/portfolio'),
    refetchInterval: 60_000,  // background refresh
  })
}

export function useCompany(id: string) {
  return useQuery({
    queryKey: ['company', id],
    queryFn: () => apiFetch<Company>(`/api/companies/${id}`),
  })
}

export function useForwardCurve(companyId: string, horizon: '2Y' | '5Y' | '10Y') {
  return useQuery({
    queryKey: ['curve', companyId, horizon],
    queryFn: () => apiFetch<ForwardCurve>(`/api/companies/${companyId}/curve?horizon=${horizon}`),
  })
}
```

### FastAPI Endpoints (contract)

The React app expects these endpoints from the FastAPI backend:

```
GET  /api/portfolio                        → PortfolioSummary
GET  /api/companies/{id}                   → CompanyDetail
GET  /api/companies/{id}/curve?horizon=    → ForwardCurve (actual + P10/P50/P90 + ic_targets)
GET  /api/companies/{id}/kpis              → KPISet
GET  /api/companies/{id}/vcp               → VCPMilestones[]
GET  /api/companies/{id}/benchmarks        → BenchmarkData
GET  /api/alerts?status=pending|approved   → Alert[]
POST /api/alerts/{id}/approve              → Alert (updated)
POST /api/alerts/{id}/reject               → Alert (updated)
PATCH /api/alerts/{id}                     → Alert (edited narrative)
POST /api/vcp/extract                      → ExtractedMilestones[] (multipart upload)
POST /api/vcp/confirm                      → VCPStore confirmation
POST /api/reports/generate                 → { download_url: string }
GET  /api/pipeline/status                  → { last_run: ISO8601, status: 'live'|'stale' }
```

### TypeScript Types

```typescript
// lib/types/alert.ts
export type Severity = 'red' | 'amber' | 'green'
export type Status   = 'pending' | 'approved' | 'rejected'

export interface Alert {
  id:               string
  companyId:        string
  companyName:      string
  severity:         Severity
  status:           Status
  headline:         string
  rootCause:        string
  recommendedAction:string
  leverCategory:    string
  irrAtRiskBps:     number
  vcpMilestonesAtRisk: string[]
  citations:        string[]
  sparklineData:    { period: string; value: number }[]
  generatedAt:      string
  approvedAt?:      string
  approvedBy?:      string
}

// lib/types/vcp.ts
export type MilestoneCategory = 'financial' | 'operational' | 'organizational' | 'commercial'
export type MilestoneStatus   = 'on_track' | 'at_risk' | 'behind' | 'complete' | 'no_data'

export interface VCPMilestone {
  id:             string
  initiative:     string
  metric:         string
  baselineValue:  number | null
  targetValue:    number | null
  actualValue:    number | null
  targetDate:     string
  ownerRole:      string
  category:       MilestoneCategory
  status:         MilestoneStatus
  driftPct:       number | null  // (actual - target) / target
  confidence:     number         // 0-1, from extraction
  sourceText:     string
}
```

### Number Formatting

```typescript
// lib/utils/formatters.ts
export const formatCurrency = (v: number, decimals = 1) =>
  `£${(v / 1_000_000).toFixed(decimals)}M`

export const formatPercent = (v: number, decimals = 1, showSign = false) => {
  const sign = showSign && v > 0 ? '+' : ''
  return `${sign}${v.toFixed(decimals)}%`
}

export const formatBps = (v: number, showSign = true) => {
  const sign = showSign && v > 0 ? '+' : ''
  return `${sign}${v}bps`
}

export const formatMultiple = (v: number) => `${v.toFixed(1)}x`
```

Always apply `formatters` before rendering numbers. Never format in components directly — keeps formatting consistent and easy to change.

### Status → Style Lookup

```typescript
// lib/utils/statusColors.ts
export const STATUS_CONFIG = {
  on_track: { dot: '●', color: 'text-green-600',  bg: 'bg-green-50',  border: 'border-green-500', label: 'On Track'  },
  at_risk:  { dot: '●', color: 'text-amber-600',  bg: 'bg-amber-50',  border: 'border-amber-500', label: 'At Risk'   },
  behind:   { dot: '●', color: 'text-red-500',    bg: 'bg-red-50',    border: 'border-red-500',   label: 'Behind'    },
  complete: { dot: '✓', color: 'text-green-600',  bg: 'bg-green-50',  border: 'border-green-500', label: 'Complete'  },
  no_data:  { dot: '○', color: 'text-slate-400',  bg: 'bg-slate-50',  border: 'border-slate-300', label: 'No Data'   },
} as const

// components/ui/StatusBadge.tsx
export function StatusBadge({ status }: { status: MilestoneStatus }) {
  const cfg = STATUS_CONFIG[status]
  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-xs font-semibold ${cfg.color} ${cfg.bg}`}>
      {cfg.dot} {cfg.label}
    </span>
  )
}
```

### Tailwind Config

```typescript
// tailwind.config.ts
import type { Config } from 'tailwindcss'

export default {
  content: ['./app/**/*.{ts,tsx}', './components/**/*.{ts,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['var(--font-sans)', 'system-ui', 'sans-serif'],
        mono: ['var(--font-mono)', 'monospace'],
      },
      colors: {
        // map CSS vars to Tailwind utility names
        'page':    'var(--bg-page)',
        'surface': 'var(--bg-surface)',
        'sidebar': 'var(--bg-sidebar)',
        'accent':  'var(--accent)',
      },
    },
  },
  plugins: [require('tailwindcss-animate')],
} satisfies Config
```

### Package Manifest

```json
{
  "dependencies": {
    "next":                   "15.x",
    "react":                  "19.x",
    "react-dom":              "19.x",
    "tailwindcss":            "4.x",
    "@radix-ui/react-*":      "*",
    "class-variance-authority": "*",
    "clsx":                   "*",
    "tailwind-merge":         "*",
    "@tremor/react":          "3.x",
    "recharts":               "2.x",
    "@tanstack/react-query":  "5.x",
    "zustand":                "4.x",
    "next-auth":              "5.x",
    "zod":                    "3.x",
    "date-fns":               "3.x"
  },
  "devDependencies": {
    "typescript":             "5.x",
    "@types/react":           "*",
    "@types/node":            "*"
  }
}
```

---

## What This Product Is vs V7 Go's UI

V7 Go's UI is document-validation-centric: a user uploads a doc and reviews extracted fields in a table. That's the right UI for their job. Yours is different.

| V7 Go | PE Value Creation Copilot |
|---|---|
| Document-centric (one doc at a time) | Company-centric (portfolio is the entry point) |
| Table of extracted fields | KPI cards + forward curves + benchmark position |
| User validates AI extraction | User makes a business decision |
| Triggered by document submission | Always-on, background monitoring |
| No forward projection | Forward curve + IC overlay is the centrepiece |
| No benchmarking | Sector percentile on every metric |
| Quarterly cadence | Daily/weekly cadence |
| GP desk (reporting) | Operating partner + portco (value creation) |

**The one chart that defines this product**: the EBITDA forward curve with IC target dots overlaid. When a senior operating partner sees the P50 line tracking below the IC target dot, the story is told in one glance — no explanation needed. That's the design moment that makes this product feel genuinely intelligent rather than a faster document processor.

---

*Design system references: [Linear redesign philosophy](https://linear.app/now/behind-the-latest-design-refresh) · [Tremor analytics components](https://tremor.so) · [shadcn/ui](https://ui.shadcn.com) · [Vercel/Next.js App Router](https://nextjs.org/docs/app) · [TanStack Query](https://tanstack.com/query/v5)*
