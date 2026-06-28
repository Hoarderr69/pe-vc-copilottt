import type { Slide } from "../../lib/api";
import { Dot, thStyle, tdStyle, monoTd, ragColor, ragLabel } from "./shared";

function SummaryCell({ n, label, rag }: { n: number; label: string; rag: string }) {
  return (
    <div style={{ flex: 1, textAlign: "center", padding: "8px 4px" }}>
      <div style={{ fontFamily: "var(--font-mono)", fontWeight: 700, fontSize: 26, color: ragColor(rag) }}>{n}</div>
      <div style={{ fontSize: 10.5, color: "var(--text-muted)", textTransform: "uppercase",
                     letterSpacing: "0.04em" }}>{label}</div>
    </div>
  );
}

export function SlideVCPScorecard({ slide }: { slide: Slide }) {
  const d = slide.data;
  const s = d.summary || {};
  const rows: any[] = d.rows || [];

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", gap: 14 }}>
      {/* Summary strip */}
      <div style={{ display: "flex", border: "1px solid var(--border)", borderRadius: 8,
                     overflow: "hidden" }}>
        <SummaryCell n={s.behind || 0} label="Behind" rag="red" />
        <div style={{ width: 1, background: "var(--border)" }} />
        <SummaryCell n={s.at_risk || 0} label="At Risk" rag="amber" />
        <div style={{ width: 1, background: "var(--border)" }} />
        <SummaryCell n={s.on_track || 0} label="On Track" rag="green" />
        <div style={{ width: 1, background: "var(--border)" }} />
        <SummaryCell n={s.no_data || 0} label="No Data" rag="grey" />
      </div>

      {/* Milestone table */}
      <div style={{ flex: 1, minHeight: 0, overflow: "auto" }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>
              <th style={{ ...thStyle, textAlign: "left" }}>Initiative</th>
              <th style={{ ...thStyle, textAlign: "left" }}>Category</th>
              <th style={{ ...thStyle, textAlign: "right" }}>Baseline</th>
              <th style={{ ...thStyle, textAlign: "right" }}>Target</th>
              <th style={{ ...thStyle, textAlign: "right" }}>Actual</th>
              <th style={{ ...thStyle, textAlign: "right" }}>Gap</th>
              <th style={{ ...thStyle, textAlign: "center" }}>Status</th>
              <th style={{ ...thStyle, textAlign: "right" }}>Due</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i}>
                <td style={{ ...tdStyle, color: "var(--text-primary)", fontWeight: 500 }}>{r.initiative}</td>
                <td style={{ ...tdStyle, color: "var(--text-secondary)" }}>{r.category}</td>
                <td style={monoTd}>{r.baseline}</td>
                <td style={monoTd}>{r.target}</td>
                <td style={{ ...monoTd, color: ragColor(r.status), fontWeight: 600 }}>{r.actual}</td>
                <td style={monoTd}>{r.gap}</td>
                <td style={{ ...tdStyle, textAlign: "center" }} title={ragLabel(r.status)}>
                  <Dot rag={r.status} />
                </td>
                <td style={{ ...monoTd, color: "var(--text-muted)" }}>
                  {r.due}{r.overdue && <span style={{ color: "var(--red)" }}> ⚠</span>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div style={{ fontSize: 10, color: "var(--text-muted)" }}>Source: {d.source}</div>
    </div>
  );
}
