import type { Slide } from "../../lib/api";
import { Dot, Label, ActionStrip } from "./shared";

function Quadrant({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ border: "1px solid var(--border)", borderRadius: 8, padding: "14px 16px",
                   display: "flex", flexDirection: "column", minHeight: 0 }}>
      <Label>{title}</Label>
      <div style={{ flex: 1 }}>{children}</div>
    </div>
  );
}

export function SlideAtAGlance({ slide }: { slide: Slide }) {
  const d = slide.data;
  const vcp = d.vcp_milestones || {};
  const irr = d.irr_outlook || {};
  const total = vcp.total || 0;
  const filled = Math.round(((vcp.on_track || 0) / (total || 1)) * 8);

  const line = (l: string, v: React.ReactNode, rag?: string) => (
    <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between",
                   padding: "4px 0", fontSize: 13 }}>
      <span style={{ display: "flex", alignItems: "center", gap: 7, color: "var(--text-secondary)" }}>
        {rag && <Dot rag={rag} size={8} />}{l}
      </span>
      <span style={{ fontFamily: "var(--font-mono)", fontWeight: 600, color: "var(--text-primary)" }}>{v}</span>
    </div>
  );

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", gap: 14 }}>
      <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gridTemplateRows: "1fr 1fr",
                     gap: 14, flex: 1, minHeight: 0 }}>
        <Quadrant title="KPI Performance">
          {(d.kpi_performance || []).map((k: any, i: number) =>
            <span key={i}>{line(k.label, k.value, k.status)}</span>)}
        </Quadrant>

        <Quadrant title="VCP Milestones">
          <div style={{ fontFamily: "var(--font-mono)", fontSize: 16, letterSpacing: 1, marginBottom: 6 }}>
            {"█".repeat(filled)}{"░".repeat(Math.max(0, 8 - filled))}
            <span style={{ marginLeft: 10, fontWeight: 700 }}>{vcp.on_track} / {total}</span>
          </div>
          {line("Behind", vcp.behind, "red")}
          {line("At Risk", vcp.at_risk, "amber")}
          {line("On Track", vcp.on_track, "green")}
        </Quadrant>

        <Quadrant title="IRR Outlook">
          {line("Bear", irr.bear ?? "—")}
          <div style={{ background: "var(--bg-muted)", borderRadius: 4, margin: "2px -6px", padding: "0 6px" }}>
            {line("Base ←", irr.base ?? "—")}
          </div>
          {line("Bull", irr.bull ?? "—")}
          {line("IC", irr.ic ?? "—")}
          {irr.gap_bps != null &&
            <div style={{ marginTop: 4, fontSize: 12, fontWeight: 600, fontFamily: "var(--font-mono)",
                           color: irr.gap_bps < 0 ? "var(--red)" : "var(--green)" }}>
              Gap {irr.gap_bps > 0 ? "+" : ""}{irr.gap_bps}bps ▼
            </div>}
        </Quadrant>

        <Quadrant title="Peer Position">
          {(d.peer_position || []).map((p: any, i: number) =>
            <span key={i}>{line(p.metric, p.percentile ?? "—")}</span>)}
          <div style={{ marginTop: 8, fontSize: 11, color: "var(--text-muted)" }}>
            Sector: {d.sector}
          </div>
        </Quadrant>
      </div>

      {d.priority_action && (
        <ActionStrip label="Priority Action">
          {d.priority_action} <span style={{ color: "var(--text-muted)", fontSize: 11 }}>— AI Generated</span>
        </ActionStrip>
      )}
    </div>
  );
}
