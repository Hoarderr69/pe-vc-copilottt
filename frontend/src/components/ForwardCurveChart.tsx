import {
  ComposedChart, Line, ReferenceLine, ReferenceDot, XAxis, YAxis,
  Tooltip, ResponsiveContainer, CartesianGrid,
} from "recharts";
import { shortDate } from "../lib/format";

export interface CurveRow {
  period_end: string;
  actual: number | null;
  plan?: number | null;
}

interface Props {
  data: CurveRow[];
  target?: number | null;
  format: (v: number) => string;
  anomalyIndex?: number | null;
  height?: number;
}

interface TipPayload { name: string; value: number; color: string; }

export function ForwardCurveChart({ data, target, format, anomalyIndex, height = 280 }: Props) {
  const lastPlan = [...data].reverse().find((d) => d.plan != null);
  const anomalyDate = anomalyIndex != null && data[anomalyIndex] ? data[anomalyIndex].period_end : null;

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

          {anomalyDate && (
            <ReferenceLine x={anomalyDate} stroke="var(--red)" strokeDasharray="3 3" strokeOpacity={0.5}
              label={{ value: "drift", position: "top", fontSize: 10, fill: "var(--red-text)" }} />
          )}

          {target != null && (
            <ReferenceLine y={target} stroke="var(--chart-peer)" strokeDasharray="6 4"
              label={{ value: "Target", position: "right", fontSize: 10, fill: "var(--text-muted)" }} />
          )}

          {/* VCP plan path (sparse, connected) */}
          <Line type="monotone" dataKey="plan" stroke="var(--chart-peer)" strokeWidth={1.75}
            strokeDasharray="5 4" dot={false} connectNulls isAnimationActive={false} />

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
        <span><i className="dash" /> VCP plan path</span>
        {target != null && <span><i className="dot" /> Month-24 target</span>}
      </div>
    </div>
  );
}

function CurveTip({ active, payload, label, format }: {
  active?: boolean; payload?: TipPayload[]; label?: string; format: (v: number) => string;
}) {
  if (!active || !payload?.length) return null;
  const get = (k: string) => payload.find((p) => p.name === k)?.value;
  const actual = get("actual");
  const plan = get("plan");
  return (
    <div className="tip">
      <div className="tip-row" style={{ marginBottom: 4 }}>
        <span className="tip-k">{shortDate(label)}</span>
      </div>
      {actual != null && (
        <div className="tip-row"><span className="tip-k">Actual</span><span className="tip-v" style={{ color: "var(--chart-primary)" }}>{format(actual)}</span></div>
      )}
      {plan != null && (
        <div className="tip-row"><span className="tip-k">Plan</span><span className="tip-v" style={{ color: "var(--chart-peer)" }}>{format(plan)}</span></div>
      )}
    </div>
  );
}
