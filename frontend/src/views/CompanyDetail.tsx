import React, { useEffect, useMemo, useState } from "react";
import { getPeers, getIrrScenarios, type CompanyDetail, type IrrScenarioData, type Milestone, type PeerBenchmark } from "../lib/api";
import { Badge, MetricCard, SectionLabel } from "../components/ui";
import { ForwardCurveChart, type CurveRow } from "../components/ForwardCurveChart";
import { bpsAbs, money, mult, pct, signedPct } from "../lib/format";

type MetricKey = "annual_revenue" | "ebitda_margin" | "net_debt_to_ebitda";

const CHART_META: Record<MetricKey, { label: string; field: keyof CompanyDetail["kpi_series"][number]; annualFlow: boolean }> = {
  annual_revenue: { label: "Revenue", field: "revenue", annualFlow: true },
  ebitda_margin: { label: "EBITDA Margin", field: "ebitda_margin", annualFlow: false },
  net_debt_to_ebitda: { label: "Net Debt / EBITDA", field: "net_debt_to_ebitda", annualFlow: false },
};

export function CompanyDetailView({ data }: { data: CompanyDetail }) {
  const [metric, setMetric] = useState<MetricKey>("ebitda_margin");
  const driftBy = useMemo(() => new Map(data.drift_results.map((d) => [d.metric, d])), [data]);
  const msBy = useMemo(() => new Map(data.milestones.map((m) => [m.metric, m])), [data]);
  const hasDrift = (data.status_counts.Red || 0) + (data.status_counts.Amber || 0) > 0;
  const lastCash = [...data.kpi_series].reverse().find((k) => k.cash != null)?.cash ?? null;
  const cur = data.currency;
  // Plan targets are annual values; actuals are per reporting period. Convert by
  // the company's real reporting cadence (quarterly EDGAR vs monthly private).
  const periodsPerYear = data.periods_per_year || 12;
  const chartFmt = useMemo<Record<MetricKey, (v: number) => string>>(() => ({
    annual_revenue: (v) => money(v, cur),
    ebitda_margin: (v) => pct(v),
    net_debt_to_ebitda: (v) => mult(v),
  }), [cur]);

  const rev = driftBy.get("annual_revenue");
  const marg = driftBy.get("ebitda_margin");
  const lev = driftBy.get("net_debt_to_ebitda");

  const curve = useMemo<CurveRow[]>(() => {
    const meta = CHART_META[metric];
    const ms = msBy.get(metric);
    const planByDate = new Map<string, number>();
    (ms?.metadata?.plan_path || []).forEach((p) => {
      planByDate.set(p.period_end, meta.annualFlow ? p.planned_value / periodsPerYear : p.planned_value);
    });
    const actualByDate = new Map<string, number | null>();
    data.kpi_series.forEach((k) => {
      actualByDate.set(k.period_end, (k[meta.field] as number | null) ?? null);
    });
    // Union of actual and plan dates so the plan line renders past the latest
    // reported actual (the underwriting path extends to the target date).
    const dates = Array.from(new Set([...actualByDate.keys(), ...planByDate.keys()])).sort();
    return dates.map((d) => ({
      period_end: d,
      actual: actualByDate.get(d) ?? null,
      plan: planByDate.get(d) ?? null,
    }));
  }, [data, metric, msBy, periodsPerYear]);

  const chartTarget = useMemo(() => {
    const ms = msBy.get(metric);
    if (ms?.target_value == null) return null;
    return CHART_META[metric].annualFlow ? ms.target_value / periodsPerYear : ms.target_value;
  }, [metric, msBy, periodsPerYear]);

  return (
    <div>
      <div className="page-head" style={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between" }}>
        <div>
          <h1 className="page-title">{data.company_name}</h1>
          {data.data_source === "edgar" && (
            <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 4 }}>
              <span style={{
                fontSize: 11, fontWeight: 700, letterSpacing: "0.05em",
                padding: "2px 8px", borderRadius: 4,
                background: "rgba(59,130,246,0.15)", color: "var(--blue-text, #60a5fa)",
                border: "1px solid rgba(59,130,246,0.3)",
              }}>EDGAR</span>
              <span style={{ fontSize: 12, color: "var(--text-secondary)" }}>
                Live SEC filing data
                {data.cik && (
                  <> · CIK <a
                    href={`https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK=${data.cik.padStart(10, "0")}&type=10-K&dateb=&owner=include&count=10`}
                    target="_blank" rel="noopener noreferrer"
                    style={{ color: "var(--blue-text, #60a5fa)", textDecoration: "underline" }}
                  >{data.cik}</a></>
                )}
              </span>
            </div>
          )}
        </div>
        <Badge status={data.health} />
      </div>

      {/* KPI grid */}
      <div className="grid grid-4">
        <MetricCard label="Revenue (run-rate)" value={money(rev?.actual_value, cur)}
          delta={signedPct(rev?.gap_pct)} deltaUp={(rev?.gap_pct ?? 0) >= 0}
          vs={`Target ${money(rev?.target_value, cur)}`} />
        <MetricCard label="EBITDA Margin" value={pct(marg?.actual_value)}
          delta={bpsAbs(marg?.actual_value, marg?.target_value)} deltaUp={(marg?.actual_value ?? 0) >= (marg?.target_value ?? 0)}
          vs={`Target ${pct(marg?.target_value)}`} />
        <MetricCard label="Net Debt / EBITDA" value={mult(lev?.actual_value)}
          delta={lev?.actual_value != null && lev?.target_value != null ? `${lev.actual_value - lev.target_value >= 0 ? "+" : ""}${(lev.actual_value - lev.target_value).toFixed(1)}x` : null}
          deltaUp={(lev?.actual_value ?? 0) <= (lev?.target_value ?? 0)}
          vs={`Target ${mult(lev?.target_value)}`} />
        <MetricCard label="Cash" value={money(lastCash, cur)} vs={`as of ${data.latest_period_end}`} />
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
        <ForwardCurveChart data={curve} target={chartTarget} format={chartFmt[metric]}
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

function IrrCellContent({ irr }: { irr: number | undefined }) {
  if (irr == null) {
    return (
      <span
        style={{
          display: "inline-block",
          padding: "2px 7px",
          borderRadius: 4,
          fontSize: 10,
          fontWeight: 700,
          letterSpacing: "0.04em",
          background: "rgba(239,68,68,0.18)",
          color: "rgba(239,68,68,0.95)",
          border: "1px solid rgba(239,68,68,0.35)",
        }}
      >
        EQUITY AT RISK
      </span>
    );
  }
  return <>{irr.toFixed(1)}%</>;
}

function IrrSection({ companyId }: { companyId: string }) {
  const [data, setData] = useState<IrrScenarioData | null>(null);

  useEffect(() => {
    setData(null);
    getIrrScenarios(companyId).then(setData).catch(() => { /* no IRR data — section stays hidden */ });
  }, [companyId]);

  if (!data) return null;
  const cur = data.currency;

  // Forecast-basis mismatch (e.g. GAAP proxy vs adjusted entry EBITDA): the
  // scenarios are not meaningful — explain why rather than render them or a
  // false distress alarm.
  if (data.basis_mismatch) {
    return (
      <div className="card section-gap card-pad">
        <div className="chart-head">
          <SectionLabel>IRR Scenario Analysis · Exit Multiple × Hold Year</SectionLabel>
        </div>
        <div
          style={{
            marginTop: 14,
            padding: "14px 16px",
            borderRadius: 8,
            background: "rgba(245,158,11,0.08)",
            border: "1px solid rgba(245,158,11,0.35)",
          }}
        >
          <div style={{ fontWeight: 700, color: "rgba(245,158,11,0.95)", marginBottom: 6, fontSize: 13 }}>
            Not Projectable · EBITDA Basis Mismatch
          </div>
          <div className="card-hint">
            {data.basis_warning ??
              "The quant forecast's EBITDA basis differs from the deal's entry EBITDA basis, so exit-value scenarios are not comparable."}
          </div>
        </div>
      </div>
    );
  }

  const lookup = new Map(
    data.scenarios.map((s) => [`${s.exit_multiple}:${s.hold_years}`, s.irr_percent])
  );

  // equity_at_risk with zero matrix cells = full distress: net debt overwhelms
  // EBITDA*multiple at every exit multiple × hold year combination.
  if (data.equity_at_risk && data.scenarios.length === 0) {
    const d = data.equity_at_risk_detail;
    return (
      <div className="card section-gap card-pad">
        <div className="chart-head">
          <SectionLabel>IRR Scenario Analysis · Exit Multiple × Hold Year</SectionLabel>
        </div>
        <div
          style={{
            marginTop: 14,
            padding: "14px 16px",
            borderRadius: 8,
            background: "rgba(239,68,68,0.08)",
            border: "1px solid rgba(239,68,68,0.35)",
          }}
        >
          <div style={{ fontWeight: 700, color: "rgba(239,68,68,0.95)", marginBottom: 6, fontSize: 13 }}>
            CRITICAL · Equity at Risk
          </div>
          <div className="card-hint" style={{ marginBottom: 8 }}>
            Base-case DCF projects negative exit equity — net debt exceeds EBITDA × entry
            multiple across the full hold period. IRR is undefined because equity value is
            wiped before lenders are made whole.
          </div>
          {d && (
            <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 8, marginTop: 10 }}>
              {[
                { label: "Net Debt / Trailing EBITDA", value: d.nd_ebitda_trailing != null ? `${d.nd_ebitda_trailing}x` : "n/a" },
                { label: "Entry Net Debt", value: money(d.entry_net_debt, cur) },
                { label: "Terminal EBITDA (Base)", value: d.terminal_ebitda_base > 0 ? money(d.terminal_ebitda_base, cur) : `< ${money(0, cur)}` },
              ].map((stat) => (
                <div key={stat.label} style={{ background: "var(--surface)", borderRadius: 6, padding: "8px 10px" }}>
                  <div className="card-hint" style={{ marginBottom: 3 }}>{stat.label}</div>
                  <div className="mono" style={{ fontWeight: 700, fontSize: 15 }}>{stat.value}</div>
                </div>
              ))}
            </div>
          )}
          <div className="card-hint" style={{ marginTop: 10 }}>
            Recommended: urgent operating review + refinancing assessment. Alert raised in HITL queue.
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="card section-gap card-pad">
      <div className="chart-head">
        <SectionLabel>IRR Scenario Analysis · Exit Multiple × Hold Year</SectionLabel>
      </div>
      {data.equity_at_risk && (
        <div
          style={{
            marginBottom: 12,
            padding: "10px 14px",
            borderRadius: 6,
            background: "rgba(239,68,68,0.08)",
            border: "1px solid rgba(239,68,68,0.30)",
            display: "flex",
            alignItems: "center",
            gap: 10,
          }}
        >
          <span style={{ fontWeight: 700, color: "rgba(239,68,68,0.95)", fontSize: 12 }}>
            EQUITY AT RISK
          </span>
          <span className="card-hint" style={{ margin: 0 }}>
            Base-case exit equity is negative — cells showing "EQUITY AT RISK" indicate
            that net debt exceeds EBITDA × multiple at that exit point. Alert raised in HITL queue.
          </span>
        </div>
      )}
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
                  <td key={y} className="mono" style={irr != null ? irrCellStyle(irr) : { padding: "6px 4px" }}>
                    <IrrCellContent irr={irr} />
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
      <div className="card-hint" style={{ marginTop: 10 }}>
        Sensitivity on the quant engine's P50 EBITDA forecast at exit, over exit multiple × hold year.
        Entry equity is fixed at deal close. Green ≥ 25% · Amber 15–25% · Red &lt; 15%.
      </div>
      {data.summary && (
        <div
          style={{
            display: "grid",
            gridTemplateColumns: `repeat(${data.summary.ic_underwritten != null ? 4 : 3}, 1fr)`,
            gap: 1,
            marginTop: 16,
            border: "1px solid var(--border)",
            borderRadius: 8,
            overflow: "hidden",
            background: "var(--border)",
          }}
        >
          {[
            { label: "Bear (P10)", value: data.summary.bear_p10 as number | null },
            { label: "Base (P50)", value: data.summary.base_p50 as number | null },
            { label: "Bull (P90)", value: data.summary.bull_p90 as number | null },
            // IC Underwritten only appears when sourced from the VCP store (never assumed).
            ...(data.summary.ic_underwritten != null
              ? [{
                  label: "IC Underwritten",
                  value: data.summary.ic_underwritten as number | null,
                  gap: data.summary.gap_bps,
                }]
              : []),
          ].map((c) => (
            <div key={c.label} style={{ background: "var(--surface)", padding: "12px 14px" }}>
              <div className="card-hint" style={{ marginBottom: 4 }}>{c.label}</div>
              <div className="mono" style={{ fontSize: 18, fontWeight: 600 }}>
                {c.value != null ? `${c.value.toFixed(1)}%` : "—"}
              </div>
              {"gap" in c && c.gap != null && (
                <div
                  className="mono"
                  style={{
                    fontSize: 12,
                    marginTop: 2,
                    color: c.gap >= 0 ? "rgba(34,197,94,0.95)" : "rgba(239,68,68,0.95)",
                  }}
                >
                  {c.gap >= 0 ? "+" : ""}{c.gap}bps vs base
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function milestoneTarget(m?: Milestone): number | null {
  return m?.target_value ?? null;
}
