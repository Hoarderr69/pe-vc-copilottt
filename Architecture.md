# PE Value Creation Copilot — System Architecture

---

## Diagram 1: Full System Architecture

```mermaid
flowchart TD

    %% ── EXTERNAL DATA SOURCES ─────────────────────────────────────────────
    subgraph EXT ["🌐 External Data Sources"]
        direction LR
        EDGAR["SEC EDGAR XBRL API
        10-K · 10-Q · 8-K
        Free REST · no auth
        15yr quarterly history"]

        FRED["FRED API
        Real interest rates
        Sector PPI · Credit spreads
        Free · St. Louis Fed"]

        FMP["FMP / yfinance
        EV/EBITDA multiples
        Sector exit comps
        Free tier"]

        ICPDF["Synthetic IC Memos
        Fabricated PDFs
        Revenue · EBITDA · leverage
        milestone targets"]

        PROD_DR["⚙️ PRODUCTION ONLY
        Data Room Financials
        Seeds model at deal close
        not built in prototype"]

        PROD_BP["⚙️ PRODUCTION ONLY
        Quarterly Board Packs
        Extends time-series post-close
        +1 data point per quarter"]
    end

    %% ── INGESTION / SCHEDULING LAYER ──────────────────────────────────────
    subgraph SCHED ["⏱ Scheduling & Ingestion"]
        direction LR
        MON["EDGAR Monitor
        APScheduler · daily poll
        Detects new 10-K / 10-Q / 8-K
        Triggers pipeline on new filing"]

        INDEXER["IC Memo Indexer
        PyMuPDF → chunk → embed
        text-embedding-3-large
        → Azure AI Search index"]
    end

    %% ── LANGGRAPH STATE MACHINE ────────────────────────────────────────────
    subgraph GRAPH ["🤖 LangGraph Agent Pipeline  |  Stateful Graph Execution"]

        STATE["📦 Shared State Object
        filing_metadata · kpi_series
        forward_curves P10/P50/P90
        irr_scenarios · peer_composite
        thesis_milestones · gaps
        alerts · hitl_status"]

        subgraph AGENTS ["Agent Nodes"]
            direction TB

            KPI["KPI Extraction Agent
            EDGAR XBRL → structured pull
            Revenue · EBITDA · net debt
            Working capital · margins
            60-quarter DataFrame"]

            PEER["Peer Benchmarking Agent
            SIC code → 20-50 sector peers
            EDGAR peer financials pull
            Sector median: rev growth
            EBITDA margin · leverage
            Company-vs-sector gap score"]

            QUANT["Quant Agent
            STL decomposition (statsmodels)
            SARIMA + Holt-Winters ensemble
            Prophet with FRED macro regressors
            P10 / P50 / P90 forward curves
            Uncertainty bands per horizon
            → Exit IRR scenario table
            (bear · base · bull)"]

            THESIS["Thesis RAG Agent
            Azure AI Search retrieval
            IC memo milestone extraction
            Milestone schema per KPI:
            {metric, target, date}
            Actual vs thesis gap %
            Overlaid on forward curve"]

            ALERT["Alert & Synthesis Agent
            GPT-4o structured output
            Combines: KPI deviation
            + forward curve gap
            + thesis milestone miss
            + sector underperformance
            Severity: 🔴 Red / 🟡 Amber / 🟢 Green
            Cited corrective action"]
        end

        ROUTER{"Routing Logic
        filing_type?
        severity?
        confidence?"}
    end

    %% ── HITL GATE ──────────────────────────────────────────────────────────
    subgraph HITL ["👁 Human-in-the-Loop Gate"]
        GATE["Streamlit Approval Widget
        Deal team reviews all alerts
        Views: forward curve preview
        thesis gap table · IRR shift
        Actions: Approve / Edit / Reject
        Full audit trail · timestamp · user"]
    end

    %% ── OUTPUT LAYER ───────────────────────────────────────────────────────
    subgraph OUTPUT ["📊 Output Layer"]
        direction LR

        DASH["Streamlit Dashboard
        Forward curve chart
        P10/P50/P90 bands
        IC milestone dots overlay
        IRR scenario heatmap
        Thesis scorecard (RAG status)
        Sector comparison chart
        Filing activity timeline"]

        REPORT["Report Agent · ReportLab
        Board-ready monthly PDF:
        — Cover + executive summary
        — Forward curve + IC overlay
        — P10/P50/P90 IRR table
        — Thesis milestone scorecard
        — Sector benchmark comparison
        — Evidence citations
        — HITL approval record"]

        OBS["LangSmith
        Full agent trace
        Token usage per agent
        Latency logging
        Audit trail for responsible AI"]
    end

    %% ── AZURE INFRASTRUCTURE ───────────────────────────────────────────────
    subgraph INFRA ["☁️ Azure Infrastructure"]
        direction LR
        AOI["Azure OpenAI GPT-4o
        Guidance extraction from 8-K
        Alert synthesis
        Structured output mode
        128K context window"]

        AIS["Azure AI Search
        IC memo thesis index
        Hybrid BM25 + dense vector
        Semantic reranking
        text-embedding-3-large"]

        ACA["Azure Container Apps
        Main app deployment
        Serverless · scales to zero
        Between polling cycles
        EY Azure subscription"]
    end

    %% ── DATA FLOW CONNECTIONS ──────────────────────────────────────────────
    EDGAR -->|daily poll| MON
    ICPDF -->|on upload| INDEXER
    PROD_DR -.->|production path| KPI
    PROD_BP -.->|production path| KPI

    MON -->|new filing trigger| STATE
    INDEXER -->|index ready| AIS

    STATE --> KPI
    STATE --> PEER
    QUANT -->|FRED macro pull| FRED
    QUANT -->|exit multiples| FMP
    KPI -->|kpi_series| STATE
    PEER -->|peer_composite| STATE
    QUANT -->|forward_curves + irr_scenarios| STATE
    THESIS -->|thesis_milestones + gaps| STATE
    ALERT -->|alerts + severity| STATE

    KPI --> QUANT
    KPI --> PEER
    QUANT --> THESIS
    PEER --> THESIS
    THESIS --> ALERT

    ALERT --> ROUTER
    ROUTER -->|Red severity: immediate| GATE
    ROUTER -->|Amber/Green: batch daily| GATE
    ROUTER -->|low confidence: cap horizon| QUANT

    GATE -->|approved| REPORT
    GATE -->|approved| DASH

    ALERT --> AOI
    THESIS --> AIS
    AOI --> INFRA
    AIS --> INFRA
    REPORT --> OBS
    ALERT --> OBS
```

---

## Diagram 2: LangGraph Agent State Machine (Internal Flow)

```mermaid
stateDiagram-v2
    [*] --> EDGARMonitor : APScheduler daily trigger

    EDGARMonitor --> FilingRouter : new filing detected

    state FilingRouter <<choice>>
    FilingRouter --> KPIExtraction : 10-Q (quarterly)
    FilingRouter --> KPIExtraction : 10-K (annual)
    FilingRouter --> GuidanceExtract : 8-K (earnings release)

    GuidanceExtract --> KPIExtraction : management guidance\nextracted → append to state

    state ParallelBlock <<fork>>
    KPIExtraction --> ParallelBlock

    ParallelBlock --> PeerBenchmark : async
    ParallelBlock --> QuantAgent : async

    state ParallelJoin <<join>>
    PeerBenchmark --> ParallelJoin
    QuantAgent --> ParallelJoin

    ParallelJoin --> ThesisRAG : peer_composite + forward_curves ready

    ThesisRAG --> AlertSynthesis : thesis gaps computed

    AlertSynthesis --> SeverityRouter : alert generated

    state SeverityRouter <<choice>>
    SeverityRouter --> ImmediateHITL : 🔴 Red — IRR at risk > 200bps
    SeverityRouter --> BatchHITL : 🟡 Amber — underperforming thesis
    SeverityRouter --> DashboardOnly : 🟢 Green — on track

    state ConfidenceCheck <<choice>>
    QuantAgent --> ConfidenceCheck
    ConfidenceCheck --> CapHorizon : confidence < 0.6\n(< 8 quarters history)
    ConfidenceCheck --> FullHorizon : confidence ≥ 0.6

    CapHorizon --> ThesisRAG : IRR horizon capped at 2yr\nwarning flag added
    FullHorizon --> ThesisRAG : full 5yr projection

    ImmediateHITL --> HITLGate : push notification to deal team
    BatchHITL --> HITLGate : end-of-day digest

    state HITLGate {
        [*] --> Review
        Review --> Approve
        Review --> Edit
        Review --> Reject
        Approve --> [*]
        Edit --> [*]
        Reject --> [*]
    }

    HITLGate --> ReportAgent : approved
    HITLGate --> AuditLog : all decisions logged
    HITLGate --> [*] : rejected — suppressed

    ReportAgent --> BoardPDFOutput : monthly board pack
    ReportAgent --> StreamlitDashboard : live dashboard update
    DashboardOnly --> StreamlitDashboard : green status update

    BoardPDFOutput --> [*]
    StreamlitDashboard --> [*]
```

---

## Diagram 3: Demo Scenario — End-to-End Data Flow

```mermaid
sequenceDiagram
    autonumber
    participant CRON as APScheduler
    participant MON as EDGAR Monitor
    participant XBRL as SEC EDGAR XBRL API
    participant KPI as KPI Extraction Agent
    participant FRED as FRED API
    participant QUANT as Quant Agent
    participant PEER as Peer Benchmarking Agent
    participant AIS as Azure AI Search
    participant THESIS as Thesis RAG Agent
    participant GPT as Azure OpenAI GPT-4o
    participant ALERT as Alert & Synthesis Agent
    participant HITL as Deal Team (HITL)
    participant REPORT as Report Agent
    participant OUT as Streamlit Dashboard

    CRON->>MON: daily trigger 07:00 UTC
    MON->>XBRL: GET /submissions?cik=DEMO_COMPANY
    XBRL-->>MON: new 10-Q detected (Q3 filing)
    MON->>KPI: trigger(filing_url, cik, period)

    KPI->>XBRL: GET /companyfacts/{cik} XBRL JSON
    XBRL-->>KPI: 60 quarters: Revenue, EBITDA, NetDebt, WC
    KPI-->>KPI: parse → pd.DataFrame, compute margins & growth rates

    par Parallel execution
        KPI->>QUANT: kpi_series (60 quarters)
        QUANT->>FRED: GET series: DFF, CPIAUCSL, BAA10Y
        FRED-->>QUANT: macro regressor time-series
        QUANT-->>QUANT: STL decompose → trend + seasonal + residual
        QUANT-->>QUANT: SARIMA(2,1,2) fit on trend component
        QUANT-->>QUANT: Prophet fit with FRED regressors
        QUANT-->>QUANT: ensemble P10/P50/P90 → 20 quarter forecast
        QUANT->>XBRL: GET sector EV/EBITDA multiples (FMP)
        QUANT-->>QUANT: IRR table: entry EV × exit EBITDA × exit multiple
    and
        KPI->>PEER: kpi_series + sic_code
        PEER->>XBRL: GET /companyfacts for 30 SIC-matched peers
        XBRL-->>PEER: peer financials
        PEER-->>PEER: compute sector medians: rev_growth, EBITDA_margin, leverage
        PEER-->>PEER: gap score = company metric − sector median
    end

    QUANT-->>THESIS: forward_curves, irr_scenarios
    PEER-->>THESIS: peer_composite, gap_scores
    THESIS->>AIS: semantic search("revenue target milestone Q3")
    AIS-->>THESIS: IC memo chunks: "Revenue target £58M by Q3 Year 2"
    THESIS-->>THESIS: actual_vs_target: {revenue: -12%, EBITDA: -8%, leverage: +0.5x}

    THESIS->>ALERT: gaps + forward_curves + peer_composite
    ALERT->>GPT: synthesise alert [structured output mode]
    GPT-->>ALERT: {severity: RED, summary: "Revenue 12% below IC target...", irr_impact: "-180bps vs base case", corrective_action: "Review pricing strategy...", citations: ["IC memo p.4", "EDGAR Q3 10-Q", "FRED DFF"]}

    ALERT->>HITL: push RED alert to Streamlit approval widget
    HITL-->>HITL: reviews forward curve chart + IRR shift + thesis gap table
    HITL->>REPORT: approve (with comment: "flag for next board")

    REPORT-->>REPORT: ReportLab PDF: forward curve + IC overlay chart, P10/P50/P90 IRR table, milestone scorecard
    REPORT->>OUT: dashboard updated + PDF available for download
    OUT-->>HITL: board-ready monitoring report ✓
```

---

## Component Reference

| Component | Technology | Purpose |
|---|---|---|
| EDGAR Monitor | Python · APScheduler | Daily poll for new 10-K/10-Q/8-K across portfolio watchlist |
| KPI Extraction Agent | SEC EDGAR XBRL REST API · pandas | Structured financial pull — no PDF parsing. Revenue, EBITDA, net debt, WC across 60 quarters |
| Quant Agent | statsmodels · Prophet · pandas | STL decomp + SARIMA + Prophet ensemble. P10/P50/P90 projections. IRR scenario table |
| Peer Benchmarking Agent | EDGAR XBRL · SIC lookup | 20–50 sector peers, quarterly medians, company vs sector gap score |
| Thesis RAG Agent | Azure AI Search · text-embedding-3-large | Semantic retrieval of IC memo milestones. Actual vs target gap computation |
| Alert & Synthesis Agent | Azure OpenAI GPT-4o (structured output) | Multi-signal synthesis. Severity classification. Cited corrective actions |
| HITL Gate | Streamlit modal widget | Deal team approval before any output reaches partners or client boards |
| Report Agent | ReportLab · Plotly | Board-ready PDF: forward curve + IC overlay, IRR table, scorecard, evidence trail |
| Dashboard | Streamlit · Plotly | Live: forward curve chart, IRR heatmap, thesis scorecard, sector comparison |
| Observability | LangSmith | Full agent trace, token usage, latency, audit log |
| Search Index | Azure AI Search (hybrid BM25 + dense) | IC memo thesis corpus, semantic reranking |
| LLM | Azure OpenAI GPT-4o | Guidance extraction from 8-K, alert synthesis, structured JSON output |
| Infra | Azure Container Apps | Serverless deployment, EY Azure subscription, auto-scales to zero |

---

## Key Design Decisions

**Why EDGAR XBRL, not PDF parsing?**
XBRL is structured JSON served via REST — revenue, EBITDA, and 200+ financial tags extracted in a single API call with no parsing errors, no OCR, no ambiguity. 15 years of quarterly history free with no authentication. PDF parsing is the production path for private company board packs and is scoped but not built in the prototype.

**Why an ensemble Quant model, not just trend extrapolation?**
A single SARIMA or naive trend line gives a point forecast with no uncertainty quantification. PE deal teams need to understand downside scenarios (P10) to assess covenant risk, and upside (P90) for LP communication. The STL + SARIMA + Prophet ensemble with macro regressors (FRED) gives statistically grounded confidence intervals, not arbitrary ±10% bands.

**Why HITL before every output?**
A miscalibrated forward curve or a wrong thesis gap reaching a client board pack is a reputational risk. The HITL gate is not an optional feature — it is the architectural boundary between AI analysis and human-approved output. Every approval is logged with timestamp, user, and rationale.

**LangGraph over a simple chain?**
Conditional routing is needed: 8-K filings require guidance extraction before KPI processing; low-confidence models should cap their forecast horizon; Red alerts bypass batch processing for immediate review. LangGraph's stateful graph supports this; a simple chain does not.



flowchart LR
    A["Data Sources<br/>SEC EDGAR XBRL<br/>IC Memo / Thesis Docs<br/>FRED Macro Data<br/>Peer Financials<br/>Production: Board Packs"] 
    --> B["Ingestion & Normalization<br/>EDGAR Monitor<br/>KPI Extraction<br/>IC Memo Indexing"]

    B --> C["Agentic Intelligence Layer<br/>KPI Agent<br/>Quant Agent<br/>Peer Benchmarking Agent<br/>Thesis RAG Agent<br/>Alert Synthesis Agent"]

    C --> D["Human Review Gate<br/>Deal team reviews<br/>Approve / Edit / Reject<br/>Audit trail"]

    D --> E["Outputs<br/>Dashboard<br/>Forward Curve + IC Overlay<br/>IRR Scenario Table<br/>Board-ready Report"]

    F["Azure Infrastructure<br/>Azure OpenAI<br/>Azure AI Search<br/>Azure Container Apps<br/>LangSmith"] -.supports.-> C
    F -.supports.-> E