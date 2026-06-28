import type { Slide } from "../../lib/api";

function cellBg(rag: string): string {
  switch (rag) {
    case "green": return "var(--green-bg)";
    case "amber": return "var(--amber-bg)";
    default: return "var(--red-bg)";
  }
}
function cellFg(rag: string): string {
  switch (rag) {
    case "green": return "var(--green-text)";
    case "amber": return "var(--amber-text)";
    default: return "var(--red-text)";
  }
}

export function SlideIRRMatrix({ slide }: { slide: Slide }) {
  const d = slide.data;
  const m = d.matrix || {};
  const years: number[] = m.hold_years || [];
  const grid: any[] = m.grid || [];

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", gap: 14 }}>
      <table style={{ width: "100%", borderCollapse: "separate", borderSpacing: 3, flex: 1 }}>
        <thead>
          <tr>
            <th style={{ fontSize: 10, textTransform: "uppercase", letterSpacing: "0.04em",
                          color: "var(--text-muted)", textAlign: "left", padding: "4px 8px" }}>
              Exit Multiple
            </th>
            {years.map(y => (
              <th key={y} style={{ fontSize: 11, fontWeight: 600, color: "var(--text-secondary)",
                                    padding: "4px 8px", textAlign: "center" }}>Year {y}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {grid.map((row, i) => (
            <tr key={i}>
              <td style={{ fontFamily: "var(--font-mono)", fontSize: 12, fontWeight: 600,
                            color: "var(--text-primary)", padding: "4px 8px" }}>
                {row.exit_multiple_label}
              </td>
              {row.cells.map((c: any, j: number) => (
                <td key={j} style={{
                  fontFamily: "var(--font-mono)", fontSize: 13, fontWeight: 600, textAlign: "center",
                  padding: "8px 4px", background: cellBg(c.rag), color: cellFg(c.rag),
                  borderRadius: 4, position: "relative",
                  border: c.ic_cell ? "2px solid #0F2044" : "1px solid transparent",
                }}>
                  {c.p50_cell && (
                    <span style={{ position: "absolute", left: 3, bottom: 1, fontSize: 11,
                                    color: "var(--text-primary)" }}>↘</span>
                  )}
                  {c.irr_pct}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>

      <div style={{ fontSize: 11, color: "var(--text-secondary)", lineHeight: 1.7 }}>
        <div>
          <span style={{ display: "inline-block", width: 12, height: 12, border: "2px solid #0F2044",
                          verticalAlign: "middle", marginRight: 6 }} />
          IC underwritten: {d.ic_underwritten?.exit_multiple} · Year {d.ic_underwritten?.year} · {d.ic_underwritten?.irr} IRR
        </div>
        <div>
          <span style={{ marginRight: 6 }}>↘</span>
          Current P50 trajectory: {d.p50_trajectory?.exit_multiple} · Year {d.p50_trajectory?.year} · {d.p50_trajectory?.irr ?? "—"} IRR
          {d.p50_trajectory?.gap_bps != null && (
            <span style={{ color: d.p50_trajectory.gap_bps < 0 ? "var(--red)" : "var(--green)" }}>
              {" "}({d.p50_trajectory.gap_bps > 0 ? "+" : ""}{d.p50_trajectory.gap_bps}bps gap)
            </span>
          )}
        </div>
        <div style={{ color: "var(--text-muted)", fontSize: 10, marginTop: 4 }}>
          {d.legend} · {d.methodology}
        </div>
      </div>
    </div>
  );
}
