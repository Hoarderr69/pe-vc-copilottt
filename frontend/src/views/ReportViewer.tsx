import { useEffect, useMemo, useState } from "react";
import {
  getReport, approveReport, editReportSection, reportExportUrl, type ReportDetail,
} from "../lib/api";
import { Spinner } from "../components/ui";
import { SlideRenderer } from "../components/slides/SlideRenderer";
import type { ExecEditCtx } from "../components/slides/SlideExecutiveSummary";

interface Props {
  reportId: string;
  onBack: () => void;
}

export function ReportViewer({ reportId, onBack }: Props) {
  const [report, setReport] = useState<ReportDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [active, setActive] = useState(0);
  const [approving, setApproving] = useState(false);
  const [notes, setNotes] = useState<Record<number, string>>({});
  const [exportOpen, setExportOpen] = useState(false);

  async function load() {
    setLoading(true);
    try { setReport(await getReport(reportId)); }
    finally { setLoading(false); }
  }
  useEffect(() => { load(); }, [reportId]);

  // Keyboard navigation
  const slides = report?.slides ?? [];
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "ArrowRight") setActive(a => Math.min(a + 1, slides.length - 1));
      if (e.key === "ArrowLeft") setActive(a => Math.max(a - 1, 0));
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [slides.length]);

  // Exec-summary edit context (only editable section in the deck)
  const execEdit = useMemo<ExecEditCtx | undefined>(() => {
    if (!report) return undefined;
    return {
      content: report.exec_summary,
      original: report.exec_summary_ai,
      editedBy: report.exec_summary_edited ? (report.approved_by ?? "Operating Partner") : null,
      editedAt: report.exec_summary_edited ? report.generated_at : null,
      onSave: async (text: string) => {
        await editReportSection(report.id, "exec_summary", text);
        await load();
      },
      onRestore: async () => {
        await editReportSection(report.id, "exec_summary", report.exec_summary_ai);
        await load();
      },
    };
  }, [report]);

  async function handleApprove() {
    if (!report) return;
    setApproving(true);
    try {
      await approveReport(report.id, { approved_by: "Operating Partner", note: "Approved as presented" });
      await load();
    } finally { setApproving(false); }
  }

  if (loading) return <Spinner label="Loading deck…" />;
  if (!report) return <div style={{ color: "var(--text-muted)", padding: 32 }}>Report not found.</div>;

  if (slides.length === 0) {
    return (
      <div style={{ padding: 32 }}>
        <button className="crumb" onClick={onBack} style={{ marginBottom: 16 }}>‹ Reports</button>
        <div style={{ color: "var(--text-muted)", fontSize: 13 }}>
          This report has no slide payload. Regenerate it to produce the 10-slide deck.
        </div>
      </div>
    );
  }

  const isApproved = report.status === "approved";
  const slide = slides[active];

  return (
    <div style={{ maxWidth: 1280, margin: "0 auto", padding: "16px 24px 48px" }}>
      {/* Top bar */}
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginBottom: 14 }}>
        <button className="crumb" onClick={onBack}>‹ Reports</button>
        <div style={{ flex: 1 }}>
          <div style={{ fontWeight: 700, fontSize: 16, color: "var(--text-primary)" }}>
            {report.company_name} — {report.period} Board Pack
          </div>
          <div style={{ fontSize: 11, color: "var(--text-muted)" }}>
            Generated {new Date(report.generated_at).toLocaleString()} ·{" "}
            {report.narrative_mode === "azure_openai" ? "GPT-4o" : "Rule-based"} ·{" "}
            <span style={{ color: isApproved ? "var(--green-text)" : "var(--amber-text)" }}>
              {isApproved ? `Approved by ${report.approved_by}` : "Draft · pending approval"}
            </span>
          </div>
        </div>
        {!isApproved && (
          <button className="btn primary" onClick={handleApprove} disabled={approving}>
            {approving ? "Approving…" : "Approve & Finalise"}
          </button>
        )}
        <div style={{ position: "relative" }}
             onBlur={(e) => { if (!e.currentTarget.contains(e.relatedTarget as Node)) setExportOpen(false); }}>
          <button className="btn" onClick={() => setExportOpen(o => !o)}>
            ↓ Export{!isApproved ? " (draft)" : ""} ▾
          </button>
          {exportOpen && (
            <div style={{
              position: "absolute", right: 0, top: "calc(100% + 4px)", zIndex: 20,
              minWidth: 200, background: "var(--bg-surface)", border: "1px solid var(--border)",
              borderRadius: 8, boxShadow: "var(--shadow-raised)", padding: 4,
            }}>
              <a href={reportExportUrl(report.id, "pptx")} target="_blank" rel="noreferrer"
                 onClick={() => setExportOpen(false)}
                 style={{ display: "block", padding: "8px 12px", borderRadius: 6, fontSize: 13,
                          textDecoration: "none", color: "var(--text-primary)" }}>
                PowerPoint (.pptx)
                <span style={{ display: "block", fontSize: 11, color: "var(--text-muted)" }}>
                  Editable deck{!isApproved ? " · DRAFT watermark" : ""}
                </span>
              </a>
              <a href={reportExportUrl(report.id, "pdf")} target="_blank" rel="noreferrer"
                 onClick={() => setExportOpen(false)}
                 style={{ display: "block", padding: "8px 12px", borderRadius: 6, fontSize: 13,
                          textDecoration: "none", color: "var(--text-primary)" }}>
                PDF (.pdf)
                <span style={{ display: "block", fontSize: 11, color: "var(--text-muted)" }}>
                  Rendered from deck{!isApproved ? " · DRAFT watermark" : ""}
                </span>
              </a>
            </div>
          )}
        </div>
      </div>

      {/* Slide navigator thumbnails */}
      <div style={{ display: "flex", gap: 6, overflowX: "auto", paddingBottom: 8, marginBottom: 12 }}>
        {slides.map((s, i) => (
          <button key={s.id} onClick={() => setActive(i)}
            style={{
              flexShrink: 0, padding: "5px 10px", borderRadius: 6, fontSize: 11, cursor: "pointer",
              border: `1px solid ${i === active ? "var(--accent)" : "var(--border)"}`,
              background: i === active ? "var(--accent-subtle)" : "var(--bg-surface)",
              color: i === active ? "var(--accent-text)" : "var(--text-secondary)",
              fontWeight: i === active ? 600 : 400, whiteSpace: "nowrap",
            }}>
            {i + 1} {s.title}
          </button>
        ))}
      </div>

      {/* 16:9 deck frame */}
      <div style={{ border: "1px solid var(--border)", borderRadius: 10, overflow: "hidden",
                     boxShadow: "var(--shadow-raised)", background: "#fff" }}>
        {/* Header bar — navy */}
        <div style={{ height: 40, background: "#0F2044", color: "#fff", display: "flex",
                       alignItems: "center", justifyContent: "space-between", padding: "0 20px",
                       fontSize: 12 }}>
          <span style={{ fontWeight: 700, letterSpacing: "0.1em", opacity: 0.85 }}>VCP COPILOT</span>
          <span>{report.company_name} · {report.period}</span>
          <span style={{ fontSize: 10, letterSpacing: "0.08em", color: "#94a3b8" }}>CONFIDENTIAL</span>
        </div>

        {/* Content area — 16:9 */}
        <div style={{ aspectRatio: "16 / 9", position: "relative", background: "#fff", color: "#0F172A" }}>
          <div style={{ position: "absolute", inset: 0, padding: "clamp(16px,2.4vw,32px)",
                         display: "flex", flexDirection: "column", overflow: "hidden" }}>
            {/* Title + key message (cover has its own layout) */}
            {slide.type !== "Cover" && (
              <div style={{ marginBottom: 14 }}>
                <h2 style={{ margin: 0, fontSize: "clamp(18px,2.4vw,28px)", fontWeight: 600,
                              color: "#0F172A" }}>{slide.title}</h2>
                {slide.key_message && (
                  <div style={{ fontSize: 14, color: "#475569", marginTop: 2 }}>{slide.key_message}</div>
                )}
              </div>
            )}
            <div style={{ flex: 1, minHeight: 0 }}>
              <SlideRenderer slide={slide} execEdit={execEdit} />
            </div>
          </div>
        </div>

        {/* Footer bar */}
        <div style={{ height: 32, background: "#F1F5F9", color: "#475569", display: "flex",
                       alignItems: "center", justifyContent: "space-between", padding: "0 20px",
                       fontSize: 10.5 }}>
          <span>{slide.title}</span>
          <span>Page {active + 1} / {slides.length} · STRICTLY CONFIDENTIAL</span>
        </div>
      </div>

      {/* Prev / Next */}
      <div style={{ display: "flex", justifyContent: "space-between", marginTop: 12 }}>
        <button className="btn" disabled={active === 0} onClick={() => setActive(a => a - 1)}>
          ← Prev
        </button>
        <span style={{ fontSize: 12, color: "var(--text-muted)", alignSelf: "center" }}>
          Use ← → arrow keys to navigate
        </span>
        <button className="btn" disabled={active === slides.length - 1} onClick={() => setActive(a => a + 1)}>
          Next →
        </button>
      </div>

      {/* Slide notes panel */}
      <div style={{ marginTop: 18 }}>
        <div style={{ fontSize: 11, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.05em",
                       color: "var(--text-muted)", marginBottom: 6 }}>
          Speaker notes — slide {active + 1}
        </div>
        <textarea
          value={notes[active] ?? ""}
          onChange={e => setNotes(n => ({ ...n, [active]: e.target.value }))}
          placeholder="Operating partner notes for this slide. These export to PPTX speaker notes — not visible to the board."
          style={{
            width: "100%", minHeight: 64, boxSizing: "border-box", fontFamily: "var(--font-sans)",
            fontSize: 13, lineHeight: 1.5, padding: "10px 12px", borderRadius: 6,
            border: "1px solid var(--border)", outline: "none", resize: "vertical",
            color: "var(--text-primary)", background: "var(--bg-surface)",
          }}
        />
      </div>
    </div>
  );
}
