import type { Slide } from "../../lib/api";
import { Dot, Label, thStyle, tdStyle, monoTd, ragColor } from "./shared";

export function SlideKPIScorecard({ slide }: { slide: Slide }) {
  const d = slide.data;
  const rows: any[] = d.rows || [];

  return (
    <div style={{ display: "grid", gridTemplateColumns: "75fr 25fr", gap: 20, height: "100%" }}>
      <div style={{ display: "flex", flexDirection: "column", minHeight: 0 }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>
              <th style={{ ...thStyle, textAlign: "left" }}>Metric</th>
              <th style={{ ...thStyle, textAlign: "right" }}>Actual</th>
              <th style={{ ...thStyle, textAlign: "right" }}>IC Target</th>
              <th style={{ ...thStyle, textAlign: "right" }}>Delta</th>
              <th style={{ ...thStyle, textAlign: "right" }}>vs LQ</th>
              <th style={{ ...thStyle, textAlign: "center" }}>Trend</th>
              <th style={{ ...thStyle, textAlign: "center" }}>Status</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i}>
                <td style={{ ...tdStyle, color: "var(--text-primary)", fontWeight: 500 }}>
                  {r.metric}
                  {r.inverse && <span style={{ fontSize: 9, color: "var(--text-muted)" }}> (↑=worse)</span>}
                </td>
                <td style={{ ...monoTd, color: ragColor(r.status), fontWeight: 600 }}>{r.actual}</td>
                <td style={{ ...monoTd, color: "var(--text-secondary)" }}>{r.ic_target}</td>
                <td style={{ ...monoTd }}>{r.delta}</td>
                <td style={{ ...monoTd, color: "var(--text-secondary)" }}>{r.vs_last_qtr}</td>
                <td style={{ ...tdStyle, textAlign: "center", fontFamily: "var(--font-mono)",
                              color: ragColor(r.status), fontSize: 13 }}>{r.trend}</td>
                <td style={{ ...tdStyle, textAlign: "center" }}><Dot rag={r.status} /></td>
              </tr>
            ))}
          </tbody>
        </table>

        <div style={{ marginTop: "auto", paddingTop: 10 }}>
          <div style={{ fontSize: 10.5, color: "var(--text-muted)" }}>{d.legend}</div>
          <div style={{ fontSize: 10, color: "var(--text-muted)", marginTop: 4 }}>
            Source: {d.source}
          </div>
        </div>
      </div>

      {/* Right sidebar — period-over-period narrative */}
      <div style={{ borderLeft: "1px solid var(--border)", paddingLeft: 16 }}>
        <Label>Period-over-Period</Label>
        <p style={{ fontSize: 12, lineHeight: 1.6, color: "var(--text-secondary)", margin: 0 }}>
          {d.narrative || "No narrative available for this period."}
        </p>
      </div>
    </div>
  );
}
