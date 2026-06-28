import React, { useEffect, useMemo, useState } from "react";
import { getPeers, getIrrScenarios, type CompanyDetail, type IrrScenarioData, type Milestone, type PeerBenchmark } from "../lib/api";
import { Badge, MetricCard, SectionLabel } from "../components/ui";
import { ForwardCurveChart, type CurveRow } from "../components/ForwardCurveChart";
import { bpsAbs, money, mult, pct, signedPct } from "../lib/format";

type MetricKey = "annual_revenue" | "ebitda_margin" | "net_debt_to_ebitda";

const CHART_META: Record<MetricKey, { label: string; field: keyof CompanyDetail["kpi_series"][number]; toMonthly: boolean; fmt: (v: number) => string }> = {
  annual_revenue: { label: "Revenue", field: "revenue", toMonthly: true, fmt: (v) => money(v) },
  ebitda_margin: { label: "EBITDA Margin", field: "ebitda_margin", toMonthly: false, fmt: (v) => pct(v) },
  net_debt_to_ebitda: { label: "Net Debt / EBITDA", field: "net_debt_to_ebitda", toMonthly: false, fmt: (v) => mult(v) },
};

export function CompanyDetailView({ data }: { data: CompanyDetail }) {
  const [metric, setMetric] = useState<MetricKey>("ebitda_margin");
  const driftBy = useMemo(() => new Map(data.drift_results.map((d) => [d.metric, d])), [data]);
  const msBy = useMemo(() => new Map(data.milestones.map((m) => [m.metric, m])), [data]);
  const hasDrift = (data.status_counts.Red || 0) + (data.status_counts.Amber || 0) > 0;
  const lastCash = [...data.kpi_series].reverse().find((k) => k.cash != null)?.cash ?? null;

  const rev = driftBy.get("annual_revenue");
  const marg = driftBy.get("ebitda_margin");
  const lev = driftBy.get("net_debt_to_ebitda");

  const curve = useMemo<CurveRow[]>(() => {
    const meta = CHART_META[metric];
    const ms = msBy.get(metric);
    const planByDate = new Map<string, number>();
    (ms?.metadata?.plan_path || []).forEach((p) => {
      planByDate.set(p.period_end, meta.toMonthly ? p.planned_value / 12 : p.planned_value);
    });
    return data.kpi_series.map((k) => ({
      period_end: k.period_end,
      actual: (k[meta.field] as number | null) ?? null,
      plan: planByDate.get(k.period_end) ?? null,
    }));
  }, [data, metric, msBy]);

  const chartTarget = useMemo(() => {
    const ms = msBy.get(metric);
    if (ms?.target_value == null) return null;
    return CHART_META[metric].toMonthly ? ms.target_value / 12 : ms.target_value;
  }, [metric, msBy]);

  return (
    <div>
      <div className="page-head" style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between" }}>
        <div>
          <h1 className="page-title">{data.company_name}</h1>
        </div>
        <Badge status={data.health} />
      </div>

      {/* KPI grid */}
      <div className="grid grid-4">
        <MetricCard label="Revenue (run-rate)" value={money(rev?.actual_value)}
          delta={signedPct(rev?.gap_pct)} deltaUp={(rev?.gap_pct ?? 0) >= 0}
          vs={`Target ${money(rev?.target_value)}`} />
        <MetricCard label="EBITDA Margin" value={pct(marg?.actual_value)}
          delta={bpsAbs(marg?.actual_value, marg?.target_value)} deltaUp={(marg?.actual_value ?? 0) >= (marg?.target_value ?? 0)}
          vs={`Target ${pct(marg?.target_value)}`} />
        <MetricCard label="Net Debt / EBITDA" value={mult(lev?.actual_value)}
          delta={lev?.actual_value != null && lev?.target_value != null ? `${lev.actual_value - lev.target_value >= 0 ? "+" : ""}${(lev.actual_value - lev.target_value).toFixed(1)}x` : null}
          deltaUp={(lev?.actual_value ?? 0) <= (lev?.target_value ?? 0)}
          vs={`Target ${mult(lev?.target_value)}`} />
        <MetricCard label="Cash" value={money(lastCash)} vs={`as of ${data.latest_period_end}`} />
      </div>

      {/* Centrepiece chart */}
      <div className="card section-gap card-pad">
        <div className="chart-head">
          <SectionLabel>Performance vs VCP Plan</SectionLabel>
          <div className="toggle">
            {(Object.keys(CHART_META) as MetricKey[]).map((m) => (
              <button key={m} className={metric === m ? "active" : ""} onClick={() => setMetric(m)}>
                {CHART_META[m].label}
              </button>
            ))}
          </div>
        </div>
        <ForwardCurveChart data={curve} target={chartTarget} format={CHART_META[metric].fmt}
          anomalyIndex={hasDrift ? 12 : null} />
        <div className="card-hint" style={{ marginTop: 10 }}>
          Solid actual vs the dashed underwriting plan path. When actual diverges below the plan, value is drifting.
        </div>
      </div>

      <PeerSection companyId={data.company_id} />
      <IrrSection companyId={data.company_id} />
    </div>
  );
}

const PEER_FMT: Record<string, (v: number | null) => string> = {
  revenue_growth_yoy: (v) => pct(v),
  ebitda_margin: (v) => pct(v),
  gross_margin: (v) => pct(v),
  net_debt_to_ebitda: (v) => mult(v),
};
const PEER_LABEL: Record<string, string> = {
  revenue_growth_yoy: "Revenue Growth (YoY)",
  ebitda_margin: "EBITDA Margin",
  gross_margin: "Gross Margin",
  net_debt_to_ebitda: "Net Debt / EBITDA",
};

function peerStatusToRag(status: string): "Green" | "Amber" | "Red" | "Not Evaluable" {
  if (status === "Outperform") return "Green";
  if (status === "In-line") return "Amber";
  if (status === "Underperform") return "Red";
  return "Not Evaluable";
}

function PeerSection({ companyId }: { companyId: string }) {
  const [peers, setPeers] = useState<PeerBenchmark | null>(null);
  const [err, setErr] = useState("");

  useEffect(() => {
    setPeers(null); setErr("");
    getPeers(companyId).then(setPeers).catch((e) => setErr(e instanceof Error ? e.message : "Failed"));
  }, [companyId]);

  if (err) return null;
  if (!peers) return null;

  const comp = peers.composite_outperformance;
  return (
    <div className="card section-gap card-pad">
      <div className="chart-head">
        <SectionLabel>Sector Benchmark · {peers.sector_label}</SectionLabel>
        <span className="mono" style={{ fontSize: 12.5, color: "var(--text-secondary)" }}>
          vs {peers.peer_set_size} peers{comp != null ? ` · ${Math.round(comp * 100)}% beat sector` : ""}
        </span>
      </div>
      <table className="tbl" style={{ marginTop: 10 }}>
        <thead>
          <tr><th>Metric</th><th>Company</th><th>Sector median</th><th>Standing</th></tr>
        </thead>
        <tbody>
          {peers.results.map((r) => {
            const fmt = PEER_FMT[r.metric] ?? ((v: number | null) => (v == null ? "—" : String(v)));
            return (
              <tr key={r.metric}>
                <td>{PEER_LABEL[r.metric] ?? r.metric}</td>
                <td className="mono">{fmt(r.company_value)}</td>
                <td className="mono" style={{ color: "var(--text-secondary)" }}>{fmt(r.sector_median)}</td>
                <td><Badge status={peerStatusToRag(r.status)} label={r.status} /></td>
              </tr>
            );
          })}
        </tbody>
      </table>
      <div className="card-hint" style={{ marginTop: 10 }}>
        VCP drift measures vs-plan; this measures vs-market. Underperforming the sector points to a company-specific issue, not a sector-wide headwind.
      </div>
    </div>
  );
}

function irrCellStyle(irr: number): React.CSSProperties {
  if (irr >= 25) return { background: "rgba(34,197,94,0.15)", color: "var(--text-primary)" };
  if (irr >= 15) return { background: "rgba(245,158,11,0.15)", color: "var(--text-primary)" };
  return { background: "rgba(239,68,68,0.12)", color: "var(--text-primary)" };
}

function IrrSection({ companyId }: { companyId: string }) {
  const [data, setData] = useState<IrrScenarioData | null>(null);

  useEffect(() => {
    setData(null);
    getIrrScenarios(companyId).then(setData).catch(() => { /* no IRR data — section stays hidden */ });
  }, [companyId]);

  if (!data) return null;

  const lookup = new Map(
    data.scenarios.map((s) => [`${s.exit_multiple}:${s.hold_years}`, s.irr_percent])
  );

  return (
    <div className="card section-gap card-pad">
      <div className="chart-head">
        <SectionLabel>IRR Scenario Analysis · Exit Multiple × Hold Year</SectionLabel>
      </div>
      <table className="tbl" style={{ marginTop: 10, textAlign: "center" }}>
        <thead>
          <tr>
            <th style={{ textAlign: "left" }}>Exit Multiple</th>
            {data.hold_years.map((y) => (
              <th key={y}>Year {y}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.exit_multiples.map((em) => (
            <tr key={em}>
              <td className="mono" style={{ textAlign: "left", fontWeight: 600 }}>{em.toFixed(1)}x</td>
              {data.hold_years.map((y) => {
                const irr = lookup.get(`${em}:${y}`);
                return (
                  <td key={y} className="mono" style={irr != null ? irrCellStyle(irr) : {}}>
                    {irr != null ? `${irr.toFixed(1)}%` : "—"}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <div className="card-hint" style={{ marginTop: 10 }}>
        Sensitivity matrix showing projected IRR across exit scenarios. Green ≥ 25% · Amber 15–25% · Red &lt; 15%.
      </div>
    </div>
  );
}

export function milestoneTarget(m?: Milestone): number | null {
  return m?.target_value ?? null;
}
