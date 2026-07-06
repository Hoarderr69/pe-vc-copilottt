import {
  ComposedChart, Area, Line, ReferenceLine, ReferenceDot, XAxis, YAxis,
  Tooltip, ResponsiveContainer, CartesianGrid,
} from "recharts";
import { shortDate } from "../lib/format";

export interface CurveRow {
  period_end: string;
  actual: number | null;
  plan?: number | null;
  /** P50 forecast path from the quant engine (forward periods only). */
  p50?: number | null;
  /** P10–P90 confidence band, as [lower, upper] for the Area range. */
  band?: [number, number] | null;
}

interface Props {
  data: CurveRow[];
  target?: number | null;
  format: (v: number) => string;
  anomalyIndex?: number | null;
  height?: number;
}

interface TipPayload { name: string; value: number | [number, number]; color: string; }

export function ForwardCurveChart({ data, target, format, anomalyIndex, height = 280 }: Props) {
  const lastPlan = [...data].reverse().find((d) => d.plan != null);
  const anomalyDate = anomalyIndex != null && data[anomalyIndex] ? data[anomalyIndex].period_end : null;
  const hasForecast = data.some((d) => d.band != null);
  const lastActual = [...data].reverse().find((d) => d.actual != null);

  return (
    <div>
      <ResponsiveContainer width="100%" height={height}>
        <ComposedChart data={data} margin={{ top: 12, right: 16, bottom: 4, left: 4 }}>
          <CartesianGrid stroke="var(--border)" vertical={false} />
          <XAxis
            dataKey="period_end"
            tick={{ fontSize: 11, fill: "var(--text-muted)" }}
            tickFormatter={(v) => shortDate(v)}
            tickLine={false} axisLine={{ stroke: "var(--border)" }}
            minTickGap={40}
          />
          <YAxis
            tick={{ fontSize: 11, fill: "var(--text-muted)", fontFamily: "var(--font-mono)" }}
            tickFormatter={(v) => format(v)}
            tickLine={false} axisLine={false} width={52}
          />
          <Tooltip content={<CurveTip format={format} />} />

          {/* P10–P90 confidence band (rendered first so lines sit on top) */}
          {hasForecast && (
            <Area type="monotone" dataKey="band" fill="var(--chart-band)"
              stroke="var(--chart-primary)" strokeOpacity={0.25} strokeWidth={1}
              connectNulls isAnimationActive={false} />
          )}

          {anomalyDate && (
            <ReferenceLine x={anomalyDate} stroke="var(--red)" strokeDasharray="3 3" strokeOpacity={0.5}
              label={{ value: "drift", position: "top", fontSize: 10, fill: "var(--red-text)" }} />
          )}

          {target != null && (
            <ReferenceLine y={target} stroke="var(--chart-peer)" strokeDasharray="6 4"
              label={{ value: "Target", position: "right", fontSize: 10, fill: "var(--text-muted)" }} />
          )}

          {/* "Now" divider between actuals and the forecast horizon */}
          {hasForecast && lastActual && (
            <ReferenceLine x={lastActual.period_end} stroke="var(--border-strong)" strokeDasharray="3 3"
              label={{ value: "NOW", position: "insideTopRight", fontSize: 9, fill: "var(--text-muted)" }} />
          )}

          {/* VCP plan path (sparse, connected) */}
          <Line type="monotone" dataKey="plan" stroke="var(--chart-peer)" strokeWidth={1.75}
            strokeDasharray="5 4" dot={false} connectNulls isAnimationActive={false} />

          {/* P50 forecast path */}
          {hasForecast && (
            <Line type="monotone" dataKey="p50" stroke="var(--chart-primary)" strokeWidth={2}
              strokeDasharray="8 4" dot={false} connectNulls isAnimationActive={false} />
          )}

          {/* Actual */}
          <Line type="monotone" dataKey="actual" stroke="var(--chart-primary)" strokeWidth={2.25}
            dot={false} isAnimationActive={false} />

          {/* Month-24 plan target dot */}
          {lastPlan?.plan != null && (
            <ReferenceDot x={lastPlan.period_end} y={lastPlan.plan} r={4.5}
              fill="var(--chart-primary)" stroke="#fff" strokeWidth={2} />
          )}
        </ComposedChart>
      </ResponsiveContainer>

      <div className="legend">
        <span><i className="solid" /> Actual</span>
        {data.some((d) => d.plan != null) && <span><i className="dash" /> VCP plan path</span>}
        {hasForecast && <span><i className="dash-primary" /> P50 forecast</span>}
        {hasForecast && <span><i className="band" /> P10–P90 band</span>}
        {target != null && <span><i className="dot" /> Month-24 target</span>}
      </div>
    </div>
  );
}

function CurveTip({ active, payload, label, format }: {
  active?: boolean; payload?: TipPayload[]; label?: string; format: (v: number) => string;
}) {
  if (!active || !payload?.length) return null;
  const get = (k: string) => {
    const v = payload.find((p) => p.name === k)?.value;
    return typeof v === "number" ? v : undefined;
  };
  const band = payload.find((p) => p.name === "band")?.value;
  const [p10, p90] = Array.isArray(band) ? band : [undefined, undefined];
  const rows: Array<{ k: string; v: number | undefined; color: string }> = [
    { k: "Actual", v: get("actual"), color: "var(--chart-primary)" },
    { k: "Plan", v: get("plan"), color: "var(--chart-peer)" },
    { k: "P90", v: p90, color: "var(--text-secondary)" },
    { k: "P50", v: get("p50"), color: "var(--chart-primary)" },
    { k: "P10", v: p10, color: "var(--text-secondary)" },
  ];
  return (
    <div className="tip">
      <div className="tip-row" style={{ marginBottom: 4 }}>
        <span className="tip-k">{shortDate(label)}</span>
      </div>
      {rows.map((r) => r.v != null && (
        <div key={r.k} className="tip-row">
          <span className="tip-k">{r.k}</span>
          <span className="tip-v" style={{ color: r.color }}>{format(r.v)}</span>
        </div>
      ))}
    </div>
  );
}
