import { useCallback, useEffect, useState } from "react";
import {
  generateReport, getCompany, getHitl, getMemo, getPortfolio,
  type CompanyDetail, type HitlQueue, type PortfolioOverview, type ReportType, type Status,
} from "./lib/api";
import { ErrorState, Spinner } from "./components/ui";
import { TopBar } from "./components/TopBar";
import { PortfolioOverviewView } from "./views/PortfolioOverview";
import { CompanyDetailView } from "./views/CompanyDetail";
import { VcpTrackerView } from "./views/VcpTracker";
import { AlertsView } from "./views/Alerts";
import { MemoView } from "./views/MemoView";
import { SetupView } from "./views/SetupView";
import { IngestView } from "./views/IngestView";
import { ReportsView } from "./views/ReportsView";
import { ReportViewer } from "./views/ReportViewer";

type View = "portfolio" | "alerts" | "memo" | "company" | "setup" | "ingest" | "reports" | "report-viewer";
type CompanyTab = "deep" | "vcp";

export default function App() {
  const [view, setView] = useState<View>("portfolio");
  const [companyTab, setCompanyTab] = useState<CompanyTab>("deep");
  const [activeId, setActiveId] = useState<string | null>(null);
  const [showAddModal, setShowAddModal] = useState(false);

  const [portfolio, setPortfolio] = useState<PortfolioOverview | null>(null);
  const [hitl, setHitl] = useState<HitlQueue | null>(null);
  const [company, setCompany] = useState<CompanyDetail | null>(null);
  const [memo, setMemo] = useState<string | null>(null);
  const [activeReportId, setActiveReportId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // Report generation state — lifted here so it survives view navigation
  const [genState, setGenState] = useState<{
    active: boolean;
    companyId: string;
    companyName: string;
    reportType: string;
    stepIdx: number;
    error: string;
  } | null>(null);

  // Mirrors backend PROGRESS_STEPS (spec §10) — 8 staged steps.
  const GEN_STEPS = [
    "Fetching KPI data",
    "Running forward curve",
    "Pulling sector benchmarks",
    "Writing executive summary…",
    "Generating board questions…",
    "Rendering charts",
    "Assembling deck",
    "Report ready",
  ];

  async function startGenerate(opts: {
    companyId: string; companyName: string; reportType: ReportType;
    period: string; tone: "board_ready" | "management_internal";
  }) {
    setGenState({ active: true, companyId: opts.companyId, companyName: opts.companyName,
                  reportType: opts.reportType, stepIdx: 0, error: "" });
    let stepIdx = 0;
    const interval = setInterval(() => {
      stepIdx = Math.min(stepIdx + 1, GEN_STEPS.length - 1);
      setGenState(s => s ? { ...s, stepIdx } : s);
    }, 2200);
    try {
      await generateReport({
        company_id: opts.companyId,
        report_type: opts.reportType,
        period: opts.period || undefined,
        tone: opts.tone,
        generation_mode: "manual",
      });
      setGenState(null);
    } catch (e) {
      const msg = e instanceof Error ? e.message : "Generation failed";
      setGenState(s => s ? { ...s, active: false, error: msg } : s);
    } finally {
      clearInterval(interval);
    }
  }
  const [darkMode, setDarkMode] = useState(() => {
    return localStorage.getItem("theme") === "dark";
  });

  useEffect(() => {
    document.documentElement.setAttribute("data-theme", darkMode ? "dark" : "light");
    localStorage.setItem("theme", darkMode ? "dark" : "light");
  }, [darkMode]);

  const loadCore = useCallback(async () => {
    setLoading(true); setError("");
    try {
      const [p, h] = await Promise.all([getPortfolio(), getHitl()]);
      setPortfolio(p); setHitl(h);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Unknown error");
    } finally { setLoading(false); }
  }, []);

  useEffect(() => { loadCore(); }, [loadCore]);

  async function openCompany(id: string) {
    setActiveId(id); setView("company"); setCompanyTab("deep"); setCompany(null);
    try { setCompany(await getCompany(id)); }
    catch (e) { setError(e instanceof Error ? e.message : "Unknown error"); }
  }

  async function openMemo() {
    setView("memo");
    if (memo == null) {
      try { setMemo((await getMemo()).markdown); }
      catch { setMemo(""); }  // file doesn't exist yet — show empty state with generate button
    }
  }

  const pending = hitl?.pending_review_count ?? 0;
  const isReportViewer = view === "report-viewer";

  const topAlerts = portfolio?.action_items ?? [];

  return (
    <div className="app">
      {!isReportViewer && (
        <aside className="sidebar">
          <div className="brand">
            <div className="brand-mark">VC</div>
            <div>
              <div className="brand-title">Value Creation</div>
              <div className="brand-sub">Copilot</div>
            </div>
          </div>

          <button className="add-portco-btn" onClick={() => setShowAddModal(true)}>
            <span className="material-symbols-outlined" style={{ fontSize: 16 }}>add</span>
            Add Portfolio Co
          </button>

          <NavItem label="Overview" active={view === "portfolio"} onClick={() => setView("portfolio")} icon="dashboard" />
          <NavItem label="Alert Center" active={view === "alerts"} onClick={() => setView("alerts")} badge={pending || undefined} icon="notifications_active" />

          <div className="nav-label">Portfolio</div>
          {portfolio?.companies.map((c) => (
            <NavItem key={c.company_id} label={c.company_name.replace(/^Company /, "")}
              dot={c.health} active={view === "company" && activeId === c.company_id}
              onClick={() => openCompany(c.company_id)} />
          ))}

          <div className="nav-label">Tools</div>
          <NavItem label="Portfolio Memo" active={view === "memo"} onClick={openMemo} icon="description" />
          <NavItem label="Reports" active={view === "reports"} onClick={() => setView("reports")} icon="summarize" />

          <div className="pipeline"><span className="live" />Synthetic portfolio</div>
        </aside>
      )}

      <div className={`app-body ${isReportViewer ? "app-body-full" : ""}`}>
        {!isReportViewer && (
          <TopBar
            pendingAlerts={pending}
            topAlerts={topAlerts}
            onGoToAlerts={() => setView("alerts")}
            darkMode={darkMode}
            onToggleDark={() => setDarkMode(d => !d)}
          />
        )}
        {genState?.active && view !== "reports" && (
          <div style={{
            background: "var(--accent)", color: "#fff", fontSize: 12, fontWeight: 600,
            padding: "6px 20px", display: "flex", alignItems: "center", gap: 10,
            cursor: "pointer",
          }} onClick={() => setView("reports")}>
            <span style={{ display: "inline-block", width: 8, height: 8, borderRadius: "50%",
                            background: "#fff", opacity: 0.7, animation: "pulse 1.2s infinite" }} />
            Generating {GEN_STEPS[genState.stepIdx]}… · Click to view progress
          </div>
        )}
        <main className={`main ${isReportViewer ? "main-full" : ""}`}>
        <div className={isReportViewer ? "content-full" : "content"}>
          {loading && !isReportViewer && <Spinner label="Loading portfolio…" />}
          {!loading && error && !isReportViewer && <ErrorState message={error} onRetry={loadCore} />}

          {view === "reports" && portfolio && (
            <ReportsView
              companies={portfolio.companies}
              onOpenReport={(id) => { setActiveReportId(id); setView("report-viewer"); }}
              genState={genState}
              genSteps={GEN_STEPS}
              onGenerate={startGenerate}
            />
          )}

          {view === "report-viewer" && activeReportId && (
            <ReportViewer
              reportId={activeReportId}
              onBack={() => setView("reports")}
            />
          )}

          {!loading && !error && portfolio && view !== "reports" && view !== "report-viewer" && (
            <>
              {view === "portfolio" && <PortfolioOverviewView data={portfolio} onOpenCompany={openCompany} />}
              {view === "alerts" && hitl && <AlertsView data={hitl} actionItems={portfolio.action_items ?? []} onChanged={loadCore} />}
              {view === "memo" && <MemoView markdown={memo ?? ""} onGenerated={(md) => setMemo(md)} />}
              {view === "setup" && <SetupView companies={portfolio.companies} onVcpLocked={loadCore} onGoToIngest={() => setView("ingest")} />}
              {view === "ingest" && <IngestView companies={portfolio.companies} onOpenCompany={openCompany} onFinancialsIngested={loadCore} />}
              {view === "company" && (
                !company ? <Spinner label="Loading company…" /> : (
                  <>
                    <button className="crumb" onClick={() => setView("portfolio")}>‹ Portfolio</button>
                    <div className="toggle" style={{ marginBottom: 18 }}>
                      <button className={companyTab === "deep" ? "active" : ""} onClick={() => setCompanyTab("deep")}>Deep Dive</button>
                      <button className={companyTab === "vcp" ? "active" : ""} onClick={() => setCompanyTab("vcp")}>VCP Tracker</button>
                    </div>
                    {companyTab === "deep" ? <CompanyDetailView data={company} /> : <VcpTrackerView data={company} />}
                  </>
                )
              )}
            </>
          )}
        </div>
        </main>
      </div>

      {showAddModal && (
        <AddPortcoModal
          companies={portfolio?.companies ?? []}
          onSetupVcp={() => { setShowAddModal(false); setView("setup"); }}
          onConnectData={() => { setShowAddModal(false); setView("ingest"); }}
          onClose={() => setShowAddModal(false)}
        />
      )}
    </div>
  );
}

function AddPortcoModal({ companies, onSetupVcp, onConnectData, onClose }: {
  companies: PortfolioOverview["companies"];
  onSetupVcp: () => void;
  onConnectData: () => void;
  onClose: () => void;
}) {
  // Companies that have a locked VCP but no KPI monitoring data yet are genuinely
  // mid-onboarding — next step is uploading financials.
  const drafts = companies
    .filter((c) => c.health === "Not Evaluable" && c.hitl_status === "vcp_confirmed")
    .map((c) => ({
      ...c,
      draftStatus: "VCP Locked — Upload Financials",
      nextStep: "financials" as const,
    }));

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-panel" onClick={(e) => e.stopPropagation()}>
        <div className="modal-header">
          <div>
            <h2 className="modal-title">Add New Portfolio Company</h2>
            <p className="modal-sub">Initialize the value creation lifecycle. Select an onboarding path to begin configuring tracking parameters, or resume a pending setup.</p>
          </div>
          <button className="modal-close" onClick={onClose} aria-label="Close">
            <span className="material-symbols-outlined">close</span>
          </button>
        </div>

        <div className="modal-options">
          <div className="modal-option-card">
            <div className="modal-option-icon">
              <span className="material-symbols-outlined">table_chart</span>
            </div>
            <h3 className="modal-option-title">Setup Value Creation Plan</h3>
            <p className="modal-option-desc">Extract milestones, targets, and operational initiatives directly from Investment Committee Memos and Thesis documents via AI parsing.</p>
            <button className="btn primary modal-option-btn" onClick={onSetupVcp}>Initialize VCP</button>
          </div>

          <div className="modal-option-card">
            <div className="modal-option-icon">
              <span className="material-symbols-outlined">sync_alt</span>
            </div>
            <h3 className="modal-option-title">Connect Financial Data</h3>
            <p className="modal-option-desc">Configure recurring data streams from ERPs, Excel uploads, or SEC filings for continuous, automated performance tracking.</p>
            <button className="btn modal-option-btn modal-option-btn-outline" onClick={onConnectData}>Configure Monitoring</button>
          </div>
        </div>

        {drafts.length > 0 && (
          <div className="modal-pending">
            <div className="modal-pending-header">
              <span className="section-label" style={{ margin: 0 }}>Pending Onboarding</span>
              <span className="modal-pending-count">{drafts.length} awaiting financials</span>
            </div>
            <div className="modal-pending-list">
              {drafts.map((c) => (
                <div key={c.company_id} className="modal-pending-row">
                  <div className="modal-pending-avatar">{c.company_name.slice(0, 2).toUpperCase()}</div>
                  <div className="modal-pending-info">
                    <div className="modal-pending-name">{c.company_name}</div>
                    <div className="modal-pending-time">
                      <span className="material-symbols-outlined" style={{ fontSize: 12 }}>check_circle</span>
                      VCP confirmed · {c.milestones_total} milestone{c.milestones_total !== 1 ? "s" : ""}
                    </div>
                  </div>
                  <span className="modal-pending-status">{c.draftStatus}</span>
                  <button
                    className="modal-pending-arrow"
                    onClick={() => { onClose(); onConnectData(); }}
                    aria-label="Upload financials"
                    title="Upload financial data"
                  >
                    <span className="material-symbols-outlined" style={{ fontSize: 18 }}>arrow_forward</span>
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

function NavItem({ label, active, onClick, badge, dot, icon }: {
  label: string; active: boolean; onClick: () => void; badge?: number; dot?: Status; icon?: string;
}) {
  return (
    <button className={`nav-item ${active ? "active" : ""}`} onClick={onClick}>
      {dot
        ? <span className="ndot" style={{ background: dotColor(dot) }} />
        : icon && <span className="material-symbols-outlined mat-icon">{icon}</span>
      }
      {label}
      {badge ? <span className="badge-count">{badge}</span> : null}
    </button>
  );
}

function dotColor(s: Status): string {
  return s === "Green" ? "var(--green)" : s === "Amber" ? "var(--amber)" : s === "Red" ? "var(--red)" : "var(--neutral)";
}
