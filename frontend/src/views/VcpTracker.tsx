import { useMemo } from "react";
import type { CompanyDetail, DriftResult, Milestone } from "../lib/api";
import { Badge, SectionLabel } from "../components/ui";
import { metricValue, shortDate, statusClass } from "../lib/format";

const STATUS_ORDER: Record<string, number> = { Red: 0, Amber: 1, Green: 2, "Not Evaluable": 3 };

export function VcpTrackerView({ data }: { data: CompanyDetail }) {
  const driftBy = useMemo(() => new Map(data.drift_results.map((d) => [d.metric, d])), [data]);

  const rows = useMemo(() => {
    return data.milestones
      .map((m) => ({ m, d: driftBy.get(m.metric) }))
      .sort((a, b) => (STATUS_ORDER[a.d?.status ?? "Not Evaluable"] ?? 9) - (STATUS_ORDER[b.d?.status ?? "Not Evaluable"] ?? 9));
  }, [data, driftBy]);

  const onTrack = data.status_counts.Green || 0;
  const total = Object.values(data.status_counts).reduce((a, b) => a + b, 0);
  const atRisk = (data.status_counts.Red ?? 0) + (data.status_counts.Amber ?? 0);

  return (
    <div>
      <div className="page-head" style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between" }}>
        <div>
          <h1 className="page-title">{data.company_name} — VCP Tracker</h1>
        </div>
        <Badge status={data.health} label={`${onTrack}/${total} on track`} />
      </div>

      <div className="citation" style={{ borderTop: "none", marginTop: 0, marginBottom: 18 }}>
        Source: IC Memo (synthetic) · {data.milestones.length} milestones extracted · confirmed in VCPStore
      </div>

      {/* Summary bar */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 12, marginBottom: 22 }}>
        <SummaryCard
          label="Total Milestones"
          value={data.milestones.length}
          sub={`across ${Object.keys(data.status_counts).length} statuses`}
        />
        <SummaryCard
          label="On Track"
          value={onTrack}
          valueColor="var(--green)"
          sub={onTrack > 0 ? "↗ Progressing" : "No green milestones"}
          subColor={onTrack > 0 ? "var(--green-text)" : undefined}
        />
        <SummaryCard
          label="At-Risk Items"
          value={atRisk}
          valueColor={atRisk > 0 ? "var(--red)" : "var(--text-primary)"}
          sub={atRisk > 0 ? "△ Require Intervention" : "All clear"}
          subColor={atRisk > 0 ? "var(--red-text)" : "var(--green-text)"}
          highlight={atRisk > 0}
        />
        <SummaryCard
          label="Data as of"
          value={data.latest_period_end ?? "—"}
          sub="latest period"
          valueFontSize={20}
        />
      </div>

      {/* Milestone table */}
      <div className="card" style={{ marginBottom: 22 }}>
        <table className="tbl">
          <thead>
            <tr>
              <th>Milestone / Initiative</th>
              <th>Category</th>
              <th className="num">Target</th>
              <th className="num">Actual</th>
              <th>Status</th>
              <th>Progress</th>
              <th>Due</th>
            </tr>
          </thead>
          <tbody>
            {rows.map(({ m, d }) => {
              const isRed = d?.status === "Red";
              const isAmber = d?.status === "Amber";
              const nameColor = isRed
                ? "var(--red-text)"
                : isAmber
                ? "var(--amber-text)"
                : "var(--text-primary)";
              const rowStyle = isRed
                ? { borderLeft: "3px solid var(--red)", background: "var(--red-bg)" }
                : isAmber
                ? { borderLeft: "3px solid var(--amber)", background: "var(--amber-bg)" }
                : { borderLeft: "3px solid transparent" };

              return (
                <tr key={m.metric} style={rowStyle}>
                  <td style={{ paddingTop: 14, paddingBottom: 14 }}>
                    <div style={{ fontWeight: 600, fontSize: 14, color: nameColor, lineHeight: 1.3 }}>
                      {m.initiative}
                    </div>
                    {d?.reason && (
                      <div style={{
                        fontSize: 11,
                        color: "var(--text-secondary)",
                        marginTop: 3,
                        fontStyle: "italic",
                        lineHeight: 1.4,
                      }}>
                        {d.reason}
                      </div>
                    )}
                  </td>
                  <td className="muted" style={{ textTransform: "capitalize", fontSize: 12 }}>{m.category}</td>
                  <td className="num">{metricValue(m.metric, d?.target_value ?? m.target_value)}</td>
                  <td className="num" style={{ color: isRed ? "var(--red-text)" : isAmber ? "var(--amber-text)" : undefined }}>
                    {d ? metricValue(m.metric, d.actual_value) : "—"}
                  </td>
                  <td><Badge status={d?.status ?? "Not Evaluable"} /></td>
                  <td><InlineProgress m={m} d={d} /></td>
                  <td className="muted" style={{ fontSize: 12 }}>{shortDate(m.target_date)}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <SectionLabel>Milestone Timeline</SectionLabel>
      <div className="card card-pad">
        <Timeline rows={rows} />
      </div>
    </div>
  );
}

function SummaryCard({
  label, value, sub, valueColor, subColor, highlight, valueFontSize,
}: {
  label: string;
  value: string | number;
  sub: string;
  valueColor?: string;
  subColor?: string;
  highlight?: boolean;
  valueFontSize?: number;
}) {
  return (
    <div
      className="card card-pad"
      style={{
        textAlign: "center",
        ...(highlight ? { borderColor: "var(--red)", boxShadow: "0 0 0 1px var(--red)" } : {}),
      }}
    >
      <div style={{
        fontFamily: "var(--font-mono)",
        fontSize: 10,
        textTransform: "uppercase",
        letterSpacing: "0.06em",
        color: "var(--text-secondary)",
        marginBottom: 8,
      }}>
        {label}
      </div>
      <div style={{
        fontFamily: "var(--font-headline)",
        fontSize: valueFontSize ?? 28,
        fontWeight: 700,
        color: valueColor ?? "var(--text-primary)",
        lineHeight: 1,
        letterSpacing: "-0.02em",
      }}>
        {value}
      </div>
      <div style={{
        fontFamily: "var(--font-mono)",
        fontSize: 11,
        color: subColor ?? "var(--text-secondary)",
        marginTop: 8,
        fontWeight: subColor ? 600 : 400,
      }}>
        {sub}
      </div>
    </div>
  );
}

function InlineProgress({ m, d }: { m: Milestone; d?: DriftResult }) {
  if (!d || m.category !== "financial") {
    return <span style={{ color: "var(--text-secondary)", fontFamily: "var(--font-mono)", fontSize: 12 }}>—</span>;
  }
  const actual = d.actual_value, target = d.target_value, baseline = m.baseline_value;
  let prog = 0;
  if (actual != null && target != null && baseline != null && target !== baseline) {
    prog = m.metric === "net_debt_to_ebitda"
      ? (baseline - actual) / (baseline - target)
      : (actual - baseline) / (target - baseline);
  }
  prog = Math.max(0, Math.min(1, prog));
  const pct = Math.round(prog * 100);

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 6, minWidth: 100 }}>
      <div style={{ flex: 1, height: 4, background: "var(--border)", borderRadius: 2, overflow: "hidden", position: "relative" }}>
        <div
          className={`fill ${statusClass(d.status)}`}
          style={{ position: "absolute", left: 0, top: 0, bottom: 0, width: `${pct}%`, borderRadius: 2 }}
        />
      </div>
      <span style={{
        fontFamily: "var(--font-mono)",
        fontSize: 11,
        color: "var(--text-secondary)",
        minWidth: 28,
        textAlign: "right",
      }}>
        {pct}%
      </span>
    </div>
  );
}

function Timeline({ rows }: { rows: { m: Milestone; d?: DriftResult }[] }) {
  const dated = rows.filter((r) => r.m.target_date).map((r) => ({ ...r, t: new Date(r.m.target_date as string).getTime() }));
  if (dated.length === 0) return <div className="card-hint">No dated milestones.</div>;
  const min = Math.min(...dated.map((d) => d.t));
  const max = Math.max(...dated.map((d) => d.t));
  const span = max - min || 1;

  // Group milestones sharing a due date so labels can stack instead of collide.
  const seen: Record<number, number> = {};
  const extraTop = 22;

  return (
    <div className="timeline">
      <div className="timeline-axis">
        {dated.map(({ m, d, t }, i) => {
          const order = (seen[t] = (seen[t] ?? -1) + 1);
          const left = 4 + ((t - min) / span) * 88;
          const nearRight = left > 70;
          return (
            <div key={i} className="tl-node" style={{ left: `${left}%` }}>
              <div className="tl-label" style={{
                top: `${-26 - order * extraTop}px`,
                left: nearRight ? "auto" : "50%",
                right: nearRight ? 0 : "auto",
                transform: nearRight ? "none" : "translateX(-50%)",
                textAlign: nearRight ? "right" : "center",
              }}>
                {m.initiative.split(" ").slice(0, 2).join(" ")}
              </div>
              <div className={`dot ${statusClass(d?.status ?? "Not Evaluable")}`} />
              {order === 0 && <div className="tl-date">{shortDate(m.target_date)}</div>}
            </div>
          );
        })}
      </div>
      <div className="legend" style={{ marginTop: 44 }}>
        <span><span className="bdot" style={{ width: 8, height: 8, borderRadius: 4, background: "var(--red)", display: "inline-block", marginRight: 6 }} />Behind</span>
        <span><span style={{ width: 8, height: 8, borderRadius: 4, background: "var(--green)", display: "inline-block", marginRight: 6 }} />On Track</span>
        <span><span style={{ width: 8, height: 8, borderRadius: 4, background: "var(--neutral)", display: "inline-block", marginRight: 6 }} />No Data</span>
      </div>
    </div>
  );
}
