import type { Slide } from "../../lib/api";
import { Label } from "./shared";

function provRow(k: string, v: React.ReactNode) {
  return (
    <div style={{ display: "flex", gap: 12, padding: "3px 0", fontSize: 12 }}>
      <span style={{ width: 130, flexShrink: 0, color: "var(--text-muted)" }}>{k}</span>
      <span style={{ color: "var(--text-primary)" }}>{v}</span>
    </div>
  );
}

export function SlideAuditTrail({ slide }: { slide: Slide }) {
  const d = slide.data;
  const p = d.provenance || {};
  const citations: any[] = d.citations || [];
  const hitl: any[] = d.hitl_decisions || [];

  return (
    <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 24, height: "100%" }}>
      <div>
        <Label>Report Provenance</Label>
        {provRow("Generated", p.generated ? new Date(p.generated).toLocaleString() : "—")}
        {provRow("Approved by", p.approved_by
          ? `${p.approved_by}${p.approved_at ? ` · ${new Date(p.approved_at).toLocaleString()}` : ""}`
          : "Pending approval")}
        {provRow("Narrative", p.narrative)}
        {provRow("Assembly", p.assembly)}

        {hitl.length > 0 && (
          <div style={{ marginTop: 18 }}>
            <Label>HITL Approval Log</Label>
            {hitl.map((h, i) => (
              <div key={i} style={{ fontSize: 11, padding: "5px 8px", marginBottom: 4,
                                     background: "var(--bg-muted)", borderRadius: 4 }}>
                ✓ {h.decision} by {h.reviewed_by} · {String(h.timestamp || "").slice(0, 16)}
                {h.note && ` · "${h.note}"`}
              </div>
            ))}
          </div>
        )}
      </div>

      <div style={{ display: "flex", flexDirection: "column", minHeight: 0 }}>
        <Label>Evidence Citations</Label>
        {citations.map((c, i) => (
          <div key={i} style={{ display: "flex", gap: 12, padding: "3px 0", fontSize: 12 }}>
            <span style={{ width: 130, flexShrink: 0, color: "var(--text-secondary)", fontWeight: 500 }}>
              {c.label}
            </span>
            <span style={{ color: "var(--text-muted)" }}>{c.source}</span>
          </div>
        ))}

        <div style={{ marginTop: "auto", paddingTop: 14, fontSize: 10, color: "var(--text-muted)",
                       lineHeight: 1.6, borderTop: "1px solid var(--border)" }}>
          {d.disclaimer}
        </div>
      </div>
    </div>
  );
}
