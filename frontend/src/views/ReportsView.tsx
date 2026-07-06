import { useEffect, useState } from "react";
import {
  listReports, deleteReport, reportExportUrl,
  type CompanyOverview, type ReportSummary, type ReportType,
} from "../lib/api";
import { Badge, Spinner, ErrorState } from "../components/ui";

const REPORT_TYPE_LABELS: Record<string, string> = {
  board_pack: "Board Pack",
  vcp_status_update: "VCP Status Update",
};

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const h = Math.floor(diff / 3_600_000);
  const d = Math.floor(diff / 86_400_000);
  if (h < 1) return "just now";
  if (h < 24) return `${h} hour${h > 1 ? "s" : ""} ago`;
  return `${d} day${d > 1 ? "s" : ""} ago`;
}

function statusLabel(status: string): string {
  if (status === "approved") return "approved";
  if (status === "pending_review") return "pending your review";
  return "draft";
}

function statusColour(status: string): string {
  if (status === "approved") return "var(--green-text)";
  if (status === "pending_review") return "var(--amber-text)";
  return "var(--text-muted)";
}

interface GenState {
  active: boolean;
  companyId: string;
  companyName: string;
  reportType: string;
  stepIdx: number;
  error: string;
}

interface Props {
  companies: CompanyOverview[];
  onOpenReport: (id: string) => void;
  genState: GenState | null;
  genSteps: string[];
  onGenerate: (opts: {
    companyId: string; companyName: string; reportType: ReportType;
    period: string; tone: "board_ready" | "management_internal";
  }) => void;
}

export function ReportsView({ companies, onOpenReport, genState, genSteps, onGenerate }: Props) {
  const [reports, setReports] = useState<ReportSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  // Generator form state
  const [genCompany, setGenCompany] = useState(companies[0]?.company_id ?? "");
  const [genType, setGenType] = useState<ReportType>("board_pack");
  const [genPeriod, setGenPeriod] = useState("");
  const [genTone, setGenTone] = useState<"board_ready" | "management_internal">("board_ready");

  async function load() {
    setLoading(true); setError("");
    try {
      const data = await listReports();
      setReports(data.reports);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load reports");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { load(); }, []);

  // Reload list when generation finishes (genState goes from active → null)
  useEffect(() => {
    if (genState === null) { load(); }
  }, [genState]);

  function handleGenerate() {
    if (!genCompany || genState?.active) return;
    const co = companies.find(c => c.company_id === genCompany);
    onGenerate({
      companyId: genCompany,
      companyName: co?.company_name ?? genCompany,
      reportType: genType,
      period: genPeriod,
      tone: genTone,
    });
  }

  async function handleDelete(id: string) {
    if (!confirm("Delete this report? This cannot be undone.")) return;
    try {
      await deleteReport(id);
      setReports(rs => rs.filter(r => r.id !== id));
    } catch (e) {
      alert(e instanceof Error ? e.message : "Delete failed");
    }
  }

  if (companies.length === 0) {
    return (
      <div>
        <div className="page-head">
          <h1 className="page-title">Reports</h1>
          <p className="page-sub">Board packs and VCP status updates — generated, reviewed, approved</p>
        </div>
        <div className="center-state">
          <div style={{ textAlign: "center" }}>
            <span className="material-symbols-outlined" style={{ fontSize: 40, opacity: 0.3, display: "block", marginBottom: 12 }}>summarize</span>
            <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 6 }}>No companies in portfolio yet</div>
            <div style={{ fontSize: 13, opacity: 0.6 }}>Add a portfolio company and ingest financials before generating reports.</div>
          </div>
        </div>
      </div>
    );
  }

  const isGenerating = genState?.active === true;

  return (
    <div>
      <div className="page-head">
        <h1 className="page-title">Reports</h1>
        <p className="page-sub">Board packs and VCP status updates — generated, reviewed, approved</p>
      </div>

      {/* Recent reports */}
      <p className="section-label">Recent</p>

      {loading && <Spinner label="Loading reports…" />}
      {!loading && error && <ErrorState message={error} onRetry={load} />}

      {!loading && !error && reports.length === 0 && (
        <div className="card card-pad" style={{ color: "var(--text-muted)", fontSize: 13 }}>
          No reports generated yet. Use the form below to create your first board pack.
        </div>
      )}

      {!loading && !error && reports.map(r => (
        <div key={r.id} className="card card-pad" style={{ marginBottom: 8 }}>
          <div style={{ display: "flex", alignItems: "flex-start", gap: 12 }}>
            <div style={{ flex: 1 }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 3 }}>
                <span style={{ fontSize: 11, fontWeight: 700, textTransform: "uppercase",
                               letterSpacing: "0.04em", color: "var(--text-muted)" }}>
                  {REPORT_TYPE_LABELS[r.report_type] ?? r.report_type}
                </span>
                <Badge status={r.alert_severity} />
                {r.narrative_mode === "azure_openai" && (
                  <span style={{ fontSize: 10, fontWeight: 600, background: "var(--accent)",
                                  color: "#fff", borderRadius: 4, padding: "1px 5px" }}>AI</span>
                )}
              </div>
              <div style={{ fontWeight: 600, fontSize: 14, color: "var(--text-primary)" }}>
                {r.company_name} · {r.period}
              </div>
              <div style={{ fontSize: 12, color: "var(--text-muted)", marginTop: 3 }}>
                <span style={{ display: "inline-block", width: 7, height: 7, borderRadius: "50%",
                               background: statusColour(r.status), marginRight: 5 }} />
                {r.generation_mode === "auto" ? "Auto-generated" : "Generated manually"}
                {" · "}
                {timeAgo(r.generated_at)}
                {" · "}
                <span style={{ color: statusColour(r.status) }}>{statusLabel(r.status)}</span>
                {r.approved_by && ` by ${r.approved_by}`}
              </div>
            </div>
            <div style={{ display: "flex", gap: 8, alignItems: "center", flexShrink: 0 }}>
              {r.status === "pending_review" ? (
                <button className="btn primary" onClick={() => onOpenReport(r.id)}>Review →</button>
              ) : (
                <button className="btn" onClick={() => onOpenReport(r.id)}>View</button>
              )}
              {r.has_pdf && (
                <a href={reportExportUrl(r.id, "pdf")} target="_blank" rel="noreferrer"
                   className="btn" style={{ textDecoration: "none" }}>
                  ↓ PDF{r.status !== "approved" ? " (draft)" : ""}
                </a>
              )}
              <button className="btn ghost-red" title="Delete report" onClick={() => handleDelete(r.id)}
                      style={{ padding: "5px 10px" }}>
                <span className="material-symbols-outlined" style={{ fontSize: 15 }}>delete</span>
              </button>
            </div>
          </div>
        </div>
      ))}

      {/* Generator form */}
      <div style={{ marginTop: 24 }}>
        <p className="section-label">Generate</p>
        <div className="card card-pad">
          {isGenerating ? (
            <GeneratingProgress
              companyName={genState!.companyName}
              reportType={genState!.reportType}
              steps={genSteps}
              currentIdx={genState!.stepIdx}
            />
          ) : genState && !genState.active && genState.error ? (
            <>
              <div style={{ color: "var(--red-text)", fontSize: 13, marginBottom: 14,
                             padding: "10px 12px", background: "var(--red-bg)", borderRadius: 6 }}>
                {genState.error}
              </div>
              <GeneratorForm
                companies={companies} genCompany={genCompany} genType={genType}
                genPeriod={genPeriod} genTone={genTone}
                setGenCompany={setGenCompany} setGenType={setGenType}
                setGenPeriod={setGenPeriod} setGenTone={setGenTone}
                onGenerate={handleGenerate} disabled={false}
              />
            </>
          ) : (
            <GeneratorForm
              companies={companies} genCompany={genCompany} genType={genType}
              genPeriod={genPeriod} genTone={genTone}
              setGenCompany={setGenCompany} setGenType={setGenType}
              setGenPeriod={setGenPeriod} setGenTone={setGenTone}
              onGenerate={handleGenerate} disabled={false}
            />
          )}
        </div>
      </div>

      <div style={{ marginTop: 10, fontSize: 11, color: "var(--text-muted)", lineHeight: 1.5 }}>
        ● AI label appears on all LLM-written sections in both the viewer and PDF.
        Sources and approver name are always included.
      </div>
    </div>
  );
}

function GeneratingProgress({ companyName, reportType, steps, currentIdx }: {
  companyName: string; reportType: string; steps: string[]; currentIdx: number;
}) {
  return (
    <div style={{ padding: "12px 0" }}>
      <div style={{ fontWeight: 600, marginBottom: 14, fontSize: 13 }}>
        Generating {REPORT_TYPE_LABELS[reportType] ?? reportType} for {companyName}
      </div>
      {steps.map((step, i) => {
        const done = i < currentIdx;
        const active = i === currentIdx;
        return (
          <div key={step} style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8, fontSize: 12 }}>
            <span style={{
              width: 18, height: 18, borderRadius: "50%", flexShrink: 0,
              display: "flex", alignItems: "center", justifyContent: "center",
              fontSize: 10, color: "#fff",
              background: done ? "var(--green)" : active ? "var(--accent)" : "transparent",
              border: done || active ? "none" : "1px solid var(--border)",
            }}>
              {done ? "✓" : active ? "●" : ""}
            </span>
            <span style={{ color: done ? "var(--text-muted)" : active ? "var(--text-primary)" : "var(--text-muted)",
                            fontWeight: active ? 600 : 400 }}>
              {step}
            </span>
          </div>
        );
      })}
      <div style={{ fontSize: 11, color: "var(--text-muted)", marginTop: 10 }}>Estimated: ~15 seconds</div>
    </div>
  );
}

function GeneratorForm({ companies, genCompany, genType, genPeriod, genTone,
  setGenCompany, setGenType, setGenPeriod, setGenTone, onGenerate, disabled }: {
  companies: CompanyOverview[]; genCompany: string; genType: ReportType;
  genPeriod: string; genTone: "board_ready" | "management_internal";
  setGenCompany: (v: string) => void; setGenType: (v: ReportType) => void;
  setGenPeriod: (v: string) => void; setGenTone: (v: "board_ready" | "management_internal") => void;
  onGenerate: () => void; disabled: boolean;
}) {
  return (
    <>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr 1fr", gap: 14, marginBottom: 16 }}>
        <div>
          <label style={{ fontSize: 11, fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase",
                           letterSpacing: "0.04em", display: "block", marginBottom: 6 }}>Company</label>
          <select value={genCompany} onChange={e => setGenCompany(e.target.value)}
                  style={{ width: "100%", padding: "7px 10px", borderRadius: 6,
                           border: "1px solid var(--border)", fontSize: 13,
                           background: "var(--bg-surface)", color: "var(--text-primary)" }}>
            {companies.map(c => <option key={c.company_id} value={c.company_id}>{c.company_name}</option>)}
          </select>
        </div>
        <div>
          <label style={{ fontSize: 11, fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase",
                           letterSpacing: "0.04em", display: "block", marginBottom: 6 }}>Report Type</label>
          <div style={{ display: "flex", gap: 10, paddingTop: 2 }}>
            {(["board_pack", "vcp_status_update"] as ReportType[]).map(t => (
              <label key={t} style={{ display: "flex", alignItems: "center", gap: 6, fontSize: 12, cursor: "pointer" }}>
                <input type="radio" name="report_type" checked={genType === t} onChange={() => setGenType(t)} />
                {REPORT_TYPE_LABELS[t]}
              </label>
            ))}
          </div>
        </div>
        <div>
          <label style={{ fontSize: 11, fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase",
                           letterSpacing: "0.04em", display: "block", marginBottom: 6 }}>Period (optional)</label>
          <input type="text" placeholder="e.g. Q3 2025" value={genPeriod} onChange={e => setGenPeriod(e.target.value)}
                 style={{ width: "100%", padding: "7px 10px", borderRadius: 6,
                          border: "1px solid var(--border)", fontSize: 13,
                          background: "var(--bg-surface)", color: "var(--text-primary)", boxSizing: "border-box" }} />
        </div>
      </div>

      {/* Tone selector with explanations */}
      <div style={{ marginBottom: 18 }}>
        <span style={{ fontSize: 11, fontWeight: 600, color: "var(--text-muted)", textTransform: "uppercase",
                        letterSpacing: "0.04em", display: "block", marginBottom: 8 }}>Tone</span>
        <div style={{ display: "flex", gap: 12 }}>
          {([
            ["board_ready", "Board-Ready", "External-facing. Structured for LP/board distribution. Concise narrative with IC-level judgment, approved action items, and formal sign-off."],
            ["management_internal", "Management-Internal", "Internal working document. Candid diagnostic language, unfiltered drift commentary, and open questions for the deal team. Not for LP distribution."],
          ] as const).map(([val, lbl, desc]) => (
            <label key={val} onClick={() => setGenTone(val)}
                   style={{ flex: 1, border: `1.5px solid ${genTone === val ? "var(--accent)" : "var(--border)"}`,
                             borderRadius: 8, padding: "10px 14px", cursor: "pointer",
                             background: genTone === val ? "color-mix(in srgb, var(--accent) 8%, transparent)" : "transparent" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                <input type="radio" name="tone" checked={genTone === val} onChange={() => setGenTone(val)} style={{ accentColor: "var(--accent)" }} />
                <span style={{ fontWeight: 600, fontSize: 13, color: "var(--text-primary)" }}>{lbl}</span>
              </div>
              <p style={{ fontSize: 11.5, color: "var(--text-muted)", margin: 0, lineHeight: 1.5 }}>{desc}</p>
            </label>
          ))}
        </div>
      </div>

      <div style={{ display: "flex", justifyContent: "flex-end" }}>
        <button className="btn primary" onClick={onGenerate} disabled={!genCompany || disabled}>
          Generate Report →
        </button>
      </div>
    </>
  );
}
