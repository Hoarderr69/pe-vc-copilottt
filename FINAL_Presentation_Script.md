# PE Value Creation Copilot — FINAL Presentation Script
**July 15 · EY · Suryansh Dubey**
**Total session: ~60 minutes including Q&A, demo, and discussion**

---

> **HOW TO USE THIS SCRIPT**
> This is a 1-hour working session — not a pitch. The tone is conversational.
> Invite questions between every major section. Don't treat Q&A as an interruption;
> questions mid-demo are a sign of engagement, not a loss of control.
> `[CUE]` = physical action. `[PAUSE / INVITE Q&A]` = stop, look at the room, ask "any questions before I move on?"
> The timing guide at the bottom shows how the hour breaks down.
> Speak slowly. If you're nervous, you'll rush — the audience needs time to absorb each section.

---

## OPENING — No slides on screen yet

*(Stand still. Make eye contact before you say anything.)*

"During this internship I've worked on two use cases.

The first was assigned — an ongoing project within the team.
A Contract Intelligence Chatbot for Energy and Infrastructure contracts.
Legal documents that run to hundreds of pages — obligations, payment terms, termination rights —
currently navigated by manual clause-by-clause reading.
We built a RAG system that parses contracts into a clause tree, indexes them,
and answers questions with grounded, citation-backed responses.
I'll walk you through that briefly at the end if time allows.

The second use case I proposed myself.

I identified a gap in how private equity firms monitor their portfolio companies
against the investment thesis they underwrote at deal close.
That became the PE Value Creation Copilot — and that's what I want to focus on today,
because it's where I went deeper, built end-to-end, and had something to say.

`[PAUSE]`

Before I show you what I built — I want to earn the right to show it.
The most important question isn't how the technology works.
It's whether the problem is real, and whether it's worth solving.

Let me start there."

`[ADVANCE — Slide: Business Challenge & Solution Approach]`

---

## SLIDE: BUSINESS CHALLENGE & SOLUTION APPROACH
*(~8 minutes — this is the foundation. Take your time. Invite discussion here.)*

"Bain & Company's Global Private Equity Report — published every year — has one finding that's been consistent for a decade.

Seventy percent of PE returns come from operational value creation.
Revenue growth. Margin expansion. Working capital improvement.
Not leverage. Not multiple expansion. Operations.

That means the investment thesis written at deal close — the value creation plan — is doing real work. It's where the return actually comes from.

`[POINT TO: 4–6 weeks callout]`

Here's the problem.
McKinsey found the average lag between a portfolio company missing a value creation milestone and the GP becoming aware is one full reporting cycle.
Four to six weeks.

And EY's own PE Pulse report — published by this practice — flags portfolio monitoring and value creation tracking as one of the top operational priorities GPs want to solve but haven't yet systematised.

`[POINT TO: 120–180 analyst days bullet]`

The scale of that gap: at three days per company per quarterly KPI pull, a fund monitoring ten companies spends a hundred and twenty to a hundred and eighty analyst-days a year — just on data extraction.
Not analysis. Not decisions. Extraction.

`[POINT TO: competitor line below Solution box]`

Now — this isn't a gap that's gone unnoticed. Chronograph raised over sixty million dollars. Allvue runs fund accounting for some of the largest GPs in the world. Visible, Cobalt — real products, real funding.

They proved the category is valuable.
But every one of them requires manual data entry.
None of them read an IC memo and extract the milestones automatically.
None of them ingest live financial data — board packs, management accounts, quarterly reports — the moment it arrives.
None of them run a statistical forecast and tell you how today's filing changes your exit IRR.

`[POINT TO: Solution Approach box]`

That is the workflow that doesn't exist as a product.
IC memo — to live filing data — to thesis gap — to alert.

That's what I built."

`[PAUSE — let it land.]`

`[INVITE Q&A]` *"Before I go into how I built it — does this problem resonate? Have you seen this in your work with PE clients?"*

*(Let the room respond. This is valuable signal — if they push back, address it. If they nod, you've earned the next section.)*

`[ADVANCE when ready]`

---

## SLIDE: INNOVATIONS, TECHNOLOGIES & HIGH-LEVEL ARCHITECTURE
*(~8 minutes — go deep on each pillar. Pause between pillars for questions.)*

`[ADVANCE — Slide: Innovations, Technologies & HL Architecture]`

"Three things make this technically different from what's been built before.

`[POINT TO: Agentic Workflow pillar]`

First — it's an agentic workflow. The system doesn't just store data and display it. It reasons over it. LangGraph orchestrates three separate agent graphs — one that processes the IC memo at deal close, one that monitors every new filing, and one that generates the board report. Each graph runs automatically, checkpointed after every step so nothing is lost if something fails mid-run.

`[POINT TO: HITL Governance pillar]`

Second — every output passes through a human approval gate before it reaches a partner or a board. This is not an optional feature. It is a hard architectural constraint. No alert, no report, no dashboard update goes anywhere without a deal team member reviewing and approving it. Full audit trail — who approved, when, and what they said.

`[POINT TO: Quant-Driven Decision Support pillar]`

Third — the forecasting. The system runs four independent statistical models — STL decomposition, SARIMA, SARIMAX with Federal Reserve macro data, and Prophet — then ensembles them to produce P10, P50, and P90 EBITDA forward curves. Those curves feed directly into IRR scenarios. Bear, base, bull — not arbitrary bands, statistically derived uncertainty that widens as you go further out.

`[POINT TO: HL flow diagram on the right]`

The workflow on the right is the full picture at a glance.
Deal close — IC memo in, milestones extracted.
New filing — financial data in, thesis gap computed, IRR shift quantified.
HITL review — deal team approves.
Output — board pack and live dashboard.

That cycle runs automatically every quarter, for every company in the portfolio."

`[PAUSE / INVITE Q&A]` *"Any questions on the three pillars before I go into the technical design?"*

`[ADVANCE]`

---

## SLIDE: DETAILED SYSTEM ARCHITECTURE
*(~10 minutes — you have the time. Walk every layer. This is where technical credibility is built.)*

`[ADVANCE — Slide: Detailed System Design & Architecture]`

"Let me walk you through the full technical design.

`[POINT TO: top row — User → Frontend → API Layer → External Services]`

Starting at the top. The user is the operating partner or deal team member.
They interact through a React and TypeScript frontend — a single-page application.
Every action goes through a FastAPI backend. That's the layer that orchestrates everything.
On the right, the external services: Azure OpenAI GPT-4o for the two AI agents,
and FRED API for macro data that feeds the forecasting model.

`[POINT TO: Shared State box]`

At the centre is the Shared State — the single source of truth for every graph execution.
Deal context, KPI records, analysis results, alerts, reports, HITL status.
Every agent node reads from and writes to this state. Nothing is passed between nodes
through function arguments — it all flows through state. That's what makes the system
auditable: at any point in time, you can inspect exactly what every agent knew
when it made a decision.

`[POINT TO: three graph boxes]`

Three LangGraph graphs — and this is the key architectural decision.

VCP Setup Graph runs once, at deal close. It reads the IC memo, the VCP Extraction Agent
pulls out every milestone, and the thesis is stored in PostgreSQL.
That's the baseline. The ground truth. It never changes unless the deal team updates it.

KPI Monitoring Graph runs on every new financial data submission.
Financials come in, KPIs are normalised, the quant forecast runs — four models,
ensembled to P10/P50/P90 — the thesis gap is computed, and the Alert & Synthesis Agent
uses GPT-4o to generate a structured alert with severity, IRR impact, and corrective action.

Report Graph runs on approval. It takes everything in shared state and generates
the board-ready PDF and PPTX.

`[POINT TO: HITL box]`

The HITL gate sits between the monitoring graph and the outputs.
Review, approve, edit, reject. The LangGraph workflow literally interrupts here
and waits for a human decision before it resumes. That's not a UI concept —
it's built into the graph execution natively. The node pauses, the state is persisted
to PostgreSQL, and execution resumes only when a human approves.
Full audit trail: who, when, what decision, what comment.

`[POINT TO: Persistence Layer]`

And at the bottom — Azure PostgreSQL. One JSONB table backs every document store:
deal metadata, KPI records, VCP milestones, reports, the HITL queue, the audit log.
LangGraph checkpoint tables also live here — so if any agent node fails mid-run,
the graph resumes from the last checkpoint, not from scratch.

`[PAUSE / INVITE Q&A]`

*"Happy to go deeper on any layer — the forecasting model, the LangGraph design,
the HITL implementation. What's most interesting to you?"*

*(Answer questions here. Then move to demo.)*

Let me show you the whole thing running."

`[ADVANCE — switch to live demo / browser]`

---

## LIVE DEMO
*(~20 minutes — the centrepiece. Go slowly. Narrate what you're clicking and why.
Invite questions after each scene. If someone asks to see something specific, show it.)*

`[OPEN BROWSER — Dashboard]`

"The company I'm using is Qualtrics — taken private by Silver Lake in 2023. Real company, real SEC filings, real financial history. I'm using it as a proxy for a portfolio company the fund has just closed on."

---

### Scene 1 — Onboarding the IC Memo
`[SHOW: IC Memo Upload / Onboarding screen]`

"This is deal close. The deal team uploads the investment committee memo.

`[SHOW: Extracted Milestones]`

The VCP Extraction Agent reads it — unstructured PDF, natural language — and pulls out every value creation milestone. Revenue target of £58 million by Q3 Year Two. EBITDA margin of twenty-two percent by Year Three. Net leverage down from five-and-a-half times to four times by exit.

These become the ground truth the company is measured against for the life of the deal. Automatically. No template, no structured input, no analyst."

`[PAUSE / INVITE Q&A]` *"Any questions on the onboarding flow before I move to monitoring?"*

---

### Scene 2 — Monitoring Dashboard
`[SHOW: Main Portfolio Dashboard]`

"This is the monitoring view. Every portfolio company. Each one has a live RAG status — Red, Amber, Green — based on how the latest filing compares to the IC thesis.

`[CLICK: Qualtrics]`

Qualtrics is flagged Amber. Let me show you why."

---

### Scene 3 — Forward Curves and IRR Scenarios
`[SHOW: KPI Panel + Forward Curve Chart]`

"Revenue for the trailing twelve months is tracking eight percent below the IC target. EBITDA margin is two hundred basis points below plan.

But the system doesn't look at those numbers in isolation. It asks: where does this trajectory lead?

`[POINT TO: P10/P50/P90 bands]`

This is the EBITDA forward curve. Twenty quarters out. Three bands — P10 downside, P50 base case, P90 upside.

The central line is where the ensemble of four models agrees the business is heading, given its own financial history and current Federal Reserve macro conditions. The bands represent genuine statistical uncertainty — not arbitrary plus-or-minus ten percent. They widen as you go further out because uncertainty compounds over time. That's how uncertainty actually behaves.

`[SHOW: IRR Scenario Table]`

And this is what the deal team actually needs to see.

Base case — P50 EBITDA at exit, at the entry multiple, over the base hold period — projects an IRR of approximately eighteen percent. The IC underwrote twenty-two. That is a four-hundred basis point gap. Not a crisis — but it is the difference between a fund-defining return and an average one.

Bear case, using P10 EBITDA, drops the IRR to eleven percent. Below the hurdle rate for most PE funds.

`[SHOW: Sensitivity Matrix]`

The sensitivity matrix tells the deal team exactly how much of that gap they can recover — by either compressing the hold period or pushing for a higher exit multiple at sale. One table. Sixty seconds. Decision made."

`[PAUSE / INVITE Q&A]` *"This is the part most people want to dig into — the forecasting methodology, the IRR assumptions, the sensitivity parameters. Happy to go deeper on any of it."*

*(If asked about the models: "We run four independently — Holt-Winters, SARIMA, SARIMAX with FRED macro data, and Prophet — then average their P10/P50/P90 outputs. Each model has different failure modes, so ensembling reduces the risk that any one model's pathology dominates the output.")*

---

### Scene 4 — Peer Benchmarking
`[SHOW: Sector Comparison Chart]`

"One more layer — and this is what separates a signal from noise.

The system automatically benchmarks Qualtrics against thirty companies in the same SIC sector. Sector median EBITDA margin is nineteen percent. Qualtrics is at sixteen.

If every software company is compressing margins in the same macro environment, an Amber flag might not require intervention. If Qualtrics is the only one compressing while peers expand — that is a different conversation entirely. The system gives you that context automatically, every quarter."

`[PAUSE / INVITE Q&A]` *"Does the peer benchmarking methodology make sense? Happy to explain how the SIC peer selection works."*

---

### Scene 5 — Alert and HITL Gate
`[SHOW: Alert Card]`

"The alert the system generated.

Amber severity. Revenue eight percent below IC target. EBITDA two hundred basis points below plan. Base-case IRR projection down four hundred basis points from underwritten. Suggested corrective action: review pricing strategy and cost structure ahead of next board.

`[SHOW: HITL Approval Widget]`

Before this goes anywhere — before a partner sees it, before a PDF is generated — it stops here. The deal team sees the forward curve, the IRR shift, the thesis gap table. They can approve it, edit the commentary, or reject it. Every decision is logged with a timestamp and the name of the reviewer.

`[CLICK: Approve]`

Approved. Dashboard updates. Board pack generates."

---

### Scene 6 — Board PDF
`[SHOW: Generated PDF]`

"Forty seconds. Cover page, executive summary, EBITDA forward curve with IC milestone overlays, IRR scenario table, thesis scorecard, sector comparison, full evidence citations, HITL approval record.

Three days of analyst work. Forty seconds. And it carries the deal team's approval — it is not an AI output. It is a human-approved document that AI helped produce."

`[PAUSE / INVITE Q&A]` *"That's the full PE VCP workflow. Open floor — what do you want to explore further, or what would you want to see changed before this goes to a real GP?"*

*(Take questions here. This is the richest discussion point of the whole session. Don't rush out of it.)*

`[ADVANCE — Slide: Business Impact & Future Roadmap]`

---

## SLIDE: BUSINESS IMPACT & FUTURE ROADMAP
*(~5 minutes — personas first, then roadmap. Invite input on the roadmap priorities.)*

"Let me close with who this helps and where it goes.

`[POINT TO: Operating Partner column]`

For the operating partner — drift detected weeks before the board meeting, not at it. Portfolio ranked by thesis deviation. Every risk quantified, not estimated.

`[POINT TO: IC / Deal Team column]`

For the deal team — IC milestones tracked automatically against live filings. The bear-base-bull IRR shift visible the morning a filing lands. No quarterly spreadsheet pull.

`[POINT TO: GP / Fund Leadership column]`

For fund leadership — board pack in forty seconds, deal-team approved before it reaches a partner, full audit trail on every decision.

`[POINT TO: Roadmap section]`

On the roadmap — the prototype runs on public EDGAR data. The immediate next step is private company ingestion — board packs and management accounts — which takes this from a prototype to a deployable tool for any GP managing a portfolio.

Longer term: cross-portfolio fund-level benchmarking, data room integrations, LP reporting. A fund-level operating system, not just a single-company monitoring tool.

The infrastructure is built. The workflow is proven. What remains is productisation.

And that is a very solvable problem."

`[PAUSE / INVITE Q&A]` *"On the roadmap — I've prioritised private company ingestion as the immediate next step. But I'm curious what you'd prioritise if this were going to a real PE client. What's the gap that feels most urgent?"*

*(This question turns the closing into a genuine discussion. Let them answer — it's the most useful feedback you can get in the room.)*

---

---

## CONTRACT INTELLIGENCE CHATBOT
*(~10 minutes — this is a full walkthrough, not a summary. Use both slides.)*

`[ADVANCE — Slide: Contract Intelligence Chatbot — Business Challenge]`

"The second project I worked on was assigned — an ongoing project within the team.
Let me give it the time it deserves.

`[POINT TO: Problem Statement box]`

Energy and Infrastructure contracts are some of the most complex legal documents in existence.
A single contract — a Power Purchase Agreement, an EPC contract, a concession agreement —
runs to hundreds of pages. Hierarchical clauses. Defined terms that reference other terms.
Obligations buried in schedules attached to schedules.

The current workflow: a lawyer or analyst reads the whole document to find one clause.
Or they rely on whoever last worked on that contract to remember where something is.
Neither scales across a portfolio of contracts. Neither is fast. Neither is auditable.

Four consequences of that:
Long turnaround time on any contract query.
Risk of missed obligations — clauses that trigger quietly while nobody was watching.
Inconsistent interpretation — two people reading the same clause and reaching different conclusions.
Poor traceability — no record of why a decision was made or which clause backed it.

`[POINT TO: Solution box]`

The solution is a RAG assistant — Retrieval-Augmented Generation.
Contracts are parsed, chunked, embedded, and indexed at ingestion.
When a question comes in, the system retrieves the most relevant clauses
and generates a grounded answer with citations — every fact traced to a source clause.

`[ADVANCE — Slide: Detailed System Architecture — Chatbot]`

`[POINT TO: Ingestion Pipeline]`

At ingestion — which runs once per contract — the document is parsed into a tree structure.
A Power Purchase Agreement isn't a flat list of paragraphs.
It's a hierarchy: Article 12 contains Clause 12.3 which contains Sub-clause 12.3(b).
We preserve that hierarchy. It matters when a question asks about 'termination rights'
and the answer is in a sub-clause three levels deep.

After parsing, the text is chunked, embedded using Azure OpenAI embeddings,
and indexed into Azure AI Search — both vector index for semantic search
and keyword index for exact-match retrieval.
Separately, a Knowledge Graph is extracted into Cosmos DB Gremlin —
this captures relationships between clauses, entities, and defined terms across the document.

`[POINT TO: Query Pipeline]`

At query time — every time a user asks a question — the system has three routes.

Tree Route: uses the hierarchical structure to navigate directly to the relevant section.
If you ask 'what are the payment terms in Section 5?', the tree route goes straight there.

Graph Route: uses the knowledge graph to follow relationships.
If you ask 'what happens if the offtaker defaults?', the graph route traces
the default definition → the remedies clause → the termination trigger.

Hybrid Route: combines vector similarity and keyword search for everything else.

The routing decision is made by an LLM — it classifies the question
and sends it down the most appropriate path. In practice, most questions
hit the hybrid route; the tree and graph routes handle the structured navigational queries.

The answer is generated by Azure OpenAI with the retrieved context.
Every fact in the answer is grounded to a clause and page number.
Defensible in a legal review. Full traceability.

`[PAUSE / INVITE Q&A]` *"Any questions on the architecture or the retrieval strategy?"*

`[PAUSE]`

Two very different problems — Energy contracts, PE portfolios.
Same underlying principle: replace manual reading with structured, auditable AI.

That's the through-line of everything I've built this summer.

The PE VCP Copilot replaces manual quarterly KPI pulls.
The Contract Intelligence Chatbot replaces manual clause-by-clause reading.
Both are built around the same conviction: AI should surface the answer,
a human should own the decision."

`[OPEN FLOOR FOR FINAL Q&A]`

---

---

## Q&A CHEAT SHEET
*(Read these tonight. Know them cold.)*

---

**"What inspired you to build this?"**

> "I'm sitting inside EY's Data and AI practice, which advises PE firms. I kept seeing the same pattern — the analytical capability to monitor a portfolio company exists, the data is there, the models exist — but the workflow to connect an IC memo written at deal close to a filing that lands three years later doesn't exist in any systematic way. LLMs and the EDGAR XBRL API together finally make it possible to close that gap. EY's own PE Pulse report documents this as an unsolved priority. I set out to build what the research said was missing."

---

**"Have you validated this with real deal teams?"**

> "The category validation is in the market — Chronograph, Allvue, Cobalt proved GPs pay for portfolio operations software. For this specific workflow, the next step before any commercial application would be structured discovery with deal teams to validate alert thresholds and the HITL approval flow. I wanted to build something technically credible first and pressure-test the product assumptions with practitioners after. That's the right sequence."

---

**"How accurate are the forecasts?"**

> "The ensemble approach means no single model failure dominates the output. Each model has different failure modes — SARIMA struggles with regime changes, Prophet can over-fit short histories — averaging across four reduces that risk. We also enforce a minimum uncertainty floor: if any model produces overconfident bands on a short data history, the system widens them programmatically. The output tells you the range of plausible outcomes, not a false-precision point estimate."

---

**"What about private companies that don't file with the SEC?"**

> "The architecture is explicitly designed for that. For private companies, the same pipeline accepts board packs and management accounts as inputs instead of EDGAR filings. The forecasting and alerting logic is identical — only the ingestion layer changes. That's the next six months on the roadmap — not a fundamental redesign, a single new data connector."

---

**"Isn't GPT-4o hallucinating milestones from the IC memo?"**

> "The VCP Extraction Agent outputs structured JSON — metric name, target value, target date — and every extracted milestone is shown to the deal team for review at onboarding before it becomes the benchmark. The system cannot monitor against a milestone the team hasn't validated. The HITL gate is the control, not the model's confidence score."

---

**"Why hasn't a big software vendor built this already?"**

> "Two things changed recently. The EDGAR XBRL structured data API became reliable enough to use programmatically at scale — before 2022, data quality was inconsistent. And LLMs became capable enough to read an unstructured IC memo and extract structured milestones without a custom-trained NLP model. Both enablers are genuinely recent — which is why the gap still exists. The timing is right now."

---

**"The Qualtrics data — isn't it outdated?"**

> "Qualtrics went private in 2023, so public filings stop at Q1 2023. What I'm demonstrating is the onboarding flow — what the system does at deal close when a company is first ingested. The monitoring flow — what happens when a new quarterly filing arrives — runs identically on any company still actively filing. The architecture is the same either way. Qualtrics is the best available public dataset to demonstrate the IC memo extraction and forecasting pipeline on a real PE-backed company."

---

**"How does this fit into EY's service offering?"**

> "Two ways. As an internal tool for EY teams advising PE clients — it gives them a structured, auditable view of portfolio performance they can bring to every client conversation. Or as a licensed product deployed directly inside a GP's operations. The HITL architecture is specifically designed for the second model — the deal team owns the approval workflow, EY provides and maintains the platform."

---

## TIMING GUIDE

| Section | Time | Notes |
|---|---|---|
| Opening — two use cases framing | 3 min | Sets context, positions both projects |
| Business Challenge & Solution | 8 min | Invite discussion at the end |
| HL Architecture — Innovations slide | 8 min | Go deep on all three pillars |
| Detailed Architecture | 10 min | Walk every layer — this is where credibility is built |
| Q&A / discussion after architecture | 5 min | Let them ask before demo |
| Live Demo — all 6 scenes | 20 min | Go slowly, invite questions between scenes |
| Business Impact & Roadmap | 5 min | End with roadmap discussion |
| Contract Intelligence Chatbot | 10 min | Full walkthrough, both slides |
| Final Q&A | woven throughout | Target ~15 min total across the session |
| **Full session** | **~60 min** | |

---

## NIGHT-BEFORE CHECKLIST

- [ ] Demo runs end-to-end without live API calls (cache responses)
- [ ] Qualtrics feature matrix CSV exists and loads correctly
- [ ] IRR table shows real numbers (not errors or dashes)
- [ ] Board PDF generates on approval click
- [ ] Slides are in final order, no placeholder text remaining
- [ ] "Allvue" spelled correctly on slide 1
- [ ] Arrows are → not -> on slide 1
- [ ] Read this script aloud once, fully, tonight
- [ ] Sleep before midnight

---

*Good luck tomorrow. You've built something real. Show them that.*
