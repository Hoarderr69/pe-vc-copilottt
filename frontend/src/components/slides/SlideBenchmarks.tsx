import type { Slide } from "../../lib/api";
import { Label, thStyle, tdStyle, monoTd, ActionStrip, AiBadge } from "./shared";

/** Per-metric percentile dot plot: P25–P75 range bar + company dot. */
function DotPlot({ rows }: { rows: any[] }) {
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      {rows.map((r, i) => {
        const pct = r.percentile_value;
        return (
          <div key={i}>
            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 11,
                           marginBottom: 4 }}>
              <span style={{ color: "var(--text-secondary)" }}>{r.metric}</span>
              <span style={{ fontFamily: "var(--font-mono)", color: "var(--text-muted)" }}>
                {r.percentile ?? "—"}
              </span>
            </div>
            <div style={{ position: "relative", height: 10 }}>
              {/* full axis */}
              <div style={{ position: "absolute", top: 4, left: 0, right: 0, height: 2,
                             background: "var(--border)" }} />
              {/* P25–P75 band */}
              <div style={{ position: "absolute", top: 2, left: "25%", width: "50%", height: 6,
                             background: "var(--bg-surface-raised)", border: "1px solid var(--border-strong)",
                             borderRadius: 3 }} />
              {/* median tick */}
              <div style={{ position: "absolute", top: 0, left: "50%", width: 1, height: 10,
                             background: "var(--text-muted)" }} />
              {/* company dot */}
              {pct != null && (
                <div style={{ position: "absolute", top: 0, left: `${pct}%`, transform: "translateX(-50%)",
                               width: 10, height: 10, borderRadius: "50%", background: "#0F2044",
                               border: "1.5px solid var(--bg-surface)" }} />
              )}
            </div>
          </div>
        );
      })}
      <div style={{ fontSize: 10, color: "var(--text-muted)" }}>
        ● Company · ▬ P25–P75 range · │ median
      </div>
    </div>
  );
}

export function SlideBenchmarks({ slide }: { slide: Slide }) {
  const d = slide.data;
  const rows: any[] = d.rows || [];

  return (
    <div style={{ display: "grid", gridTemplateColumns: "55fr 45fr", gap: 24, height: "100%" }}>
      <div>
        <Label>Percentile vs Sector</Label>
        <DotPlot rows={rows} />
      </div>

      <div style={{ display: "flex", flexDirection: "column", minHeight: 0 }}>
        <table style={{ width: "100%", borderCollapse: "collapse" }}>
          <thead>
            <tr>
              <th style={{ ...thStyle, textAlign: "left" }}>Metric</th>
              <th style={{ ...thStyle, textAlign: "right" }}>Company</th>
              <th style={{ ...thStyle, textAlign: "right" }}>P25</th>
              <th style={{ ...thStyle, textAlign: "right" }}>Median</th>
              <th style={{ ...thStyle, textAlign: "right" }}>P75</th>
              <th style={{ ...thStyle, textAlign: "right" }}>Pct</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r, i) => (
              <tr key={i}>
                <td style={{ ...tdStyle, color: "var(--text-primary)" }}>{r.metric}</td>
                <td style={{ ...monoTd, fontWeight: 600 }}>{r.company}</td>
                <td style={{ ...monoTd, color: "var(--text-muted)" }}>{r.p25}</td>
                <td style={{ ...monoTd, color: "var(--text-secondary)" }}>{r.median}</td>
                <td style={{ ...monoTd, color: "var(--text-muted)" }}>{r.p75}</td>
                <td style={monoTd}>{r.percentile ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>

        {d.ai_analysis && (
          <div style={{ marginTop: 14 }}>
            <div style={{ marginBottom: 6 }}><AiBadge /></div>
            <ActionStrip>{d.ai_analysis}</ActionStrip>
          </div>
        )}

        <div style={{ marginTop: "auto", paddingTop: 10, fontSize: 10, color: "var(--text-muted)" }}>
          Source: {d.source}{d.peer_set_size ? ` · ${d.peer_set_size} peers` : ""} · {d.sector_label}
          {d.estimated_band && " · P25/P75 estimated"}
        </div>
      </div>
    </div>
  );
}
