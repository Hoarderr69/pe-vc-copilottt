import {
  ComposedChart, Area, Line, ReferenceLine, XAxis, YAxis, Tooltip,
  ResponsiveContainer, CartesianGrid, Legend,
} from "recharts";
import type { Slide } from "../../lib/api";

function fmtM(v: number | null | undefined): string {
  if (v == null) return "—";
  return `£${(v / 1e6).toFixed(1)}M`;
}

export function SlideForwardCurve({ slide }: { slide: Slide }) {
  const d = slide.data;
  const actual: any[] = d.series?.actual || [];
  const proj: any[] = d.series?.projection || [];

  // Merge into one continuous series. Actual segment carries `actual`; the
  // projection segment carries `p50` + the p10–p90 `band` range.
  const lastActual = actual.length ? actual[actual.length - 1].ebitda : null;
  const merged = [
    ...actual.map(a => ({ period: a.period, actual: a.ebitda })),
    // bridge point so the dashed P50 visually connects to the last actual
    ...(lastActual != null ? [{ period: "NOW", actual: lastActual, p50: lastActual, band: [lastActual, lastActual] }] : []),
    ...proj.map(p => ({ period: p.period, p50: p.p50, band: [p.p10, p.p90] })),
  ];

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", gap: 12 }}>
      {/* KPI strip */}
      <div style={{ display: "flex", gap: 24 }}>
        {(d.kpi_strip || []).map((k: any, i: number) => (
          <div key={i}>
            <div style={{ fontSize: 10, color: "var(--text-muted)", textTransform: "uppercase",
                           letterSpacing: "0.04em" }}>{k.label}</div>
            <div style={{ fontFamily: "var(--font-mono)", fontSize: 22, fontWeight: 700,
                           color: "var(--text-primary)" }}>{k.value}</div>
          </div>
        ))}
      </div>

      {/* Chart */}
      <div style={{ flex: 1, minHeight: 0, position: "relative" }}>
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={merged} margin={{ top: 8, right: 16, bottom: 4, left: 4 }}>
            <CartesianGrid stroke="var(--border)" vertical={false} />
            <XAxis dataKey="period" tick={{ fontSize: 10, fill: "var(--text-muted)" }}
                   tickLine={false} axisLine={{ stroke: "var(--border)" }} minTickGap={20} />
            <YAxis tick={{ fontSize: 10, fill: "var(--text-muted)", fontFamily: "var(--font-mono)" }}
                   tickFormatter={(v) => `£${(v / 1e6).toFixed(1)}M`} tickLine={false} axisLine={false} width={54} />
            <Tooltip
              formatter={(v: any, name: any) => [fmtM(Array.isArray(v) ? v[1] : v), String(name)]}
              contentStyle={{ fontSize: 11, background: "var(--bg-surface)",
                              border: "1px solid var(--border)", borderRadius: 6 }} />
            <Legend wrapperStyle={{ fontSize: 11 }} />

            <Area type="monotone" dataKey="band" name="P10–P90" fill="var(--chart-band)"
                  stroke="none" isAnimationActive={false} legendType="rect" />
            {d.ic_target != null && (
              <ReferenceLine y={d.ic_target} stroke="var(--chart-peer)" strokeDasharray="6 4"
                label={{ value: "IC Target", position: "right", fontSize: 10, fill: "var(--text-muted)" }} />
            )}
            <ReferenceLine x="NOW" stroke="var(--border-strong)" strokeDasharray="3 3"
              label={{ value: "NOW", position: "insideTopRight", fontSize: 9, fill: "var(--text-muted)" }} />
            <Line type="monotone" dataKey="actual" name="Actual" stroke="var(--chart-primary)"
                  strokeWidth={2.5} dot={false} isAnimationActive={false} connectNulls />
            <Line type="monotone" dataKey="p50" name="P50" stroke="var(--chart-primary)"
                  strokeWidth={2} strokeDasharray="8 4" dot={false} isAnimationActive={false} connectNulls />
          </ComposedChart>
        </ResponsiveContainer>

        {/* IRR inset card */}
        <div style={{ position: "absolute", right: 24, bottom: 16, width: 240,
                       background: "var(--bg-surface)", border: "1px solid var(--border)",
                       borderRadius: 8, padding: "10px 12px", boxShadow: "var(--shadow-raised)" }}>
          <div style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase",
                         letterSpacing: "0.05em", color: "var(--text-muted)", marginBottom: 6 }}>
            IRR Scenarios
          </div>
          {(d.irr_inset || []).map((r: any, i: number) => (
            <div key={i} style={{ display: "flex", justifyContent: "space-between", fontSize: 12,
                                   padding: "2px 0", fontWeight: r.bold ? 700 : 400 }}>
              <span style={{ color: "var(--text-secondary)" }}>{r.label}</span>
              <span style={{ fontFamily: "var(--font-mono)", color: "var(--text-primary)" }}>
                {r.irr}
                {r.delta_bps != null && (
                  <span style={{ color: r.delta_bps < 0 ? "var(--red)" : "var(--green)", marginLeft: 6 }}>
                    {r.delta_bps > 0 ? "+" : ""}{r.delta_bps}bps
                  </span>
                )}
              </span>
            </div>
          ))}
        </div>
      </div>

      <div style={{ fontSize: 10, color: "var(--text-muted)", lineHeight: 1.5 }}>{d.methodology}</div>
    </div>
  );
}
