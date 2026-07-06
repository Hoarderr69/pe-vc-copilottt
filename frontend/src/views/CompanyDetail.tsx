import React, { useEffect, useMemo, useState } from "react";
import { getPeers, getIrrScenarios, type CompanyDetail, type IrrScenarioData, type Milestone, type PeerBenchmark } from "../lib/api";
import { Badge, FreshnessBadge, MetricCard, SectionLabel } from "../components/ui";
import { ForwardCurveChart, type CurveRow } from "../components/ForwardCurveChart";
import { bpsAbs, fullDate, money, mult, pct, signedPct } from "../lib/format";

type MetricKey = "annual_revenue" | "ebitda_margin" | "net_debt_to_ebitda";

const CHART_META: Record<MetricKey, { label: string; field: keyof CompanyDetail["kpi_series"][number]; annualFlow: boolean }> = {
  annual_revenue: { label: "Revenue", field: "revenue", annualFlow: true },
  ebitda_margin: { label: "EBITDA Margin", field: "ebitda_margin", annualFlow: false },
  net_debt_to_ebitda: { label: "Net Debt / EBITDA", field: "net_debt_to_ebitda", annualFlow: false },
};

export function CompanyDetailView({ data, onConnectData }: { data: CompanyDetail; onConnectData?: () => void }) {
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
  const freshness = data.data_freshness;
  // OVERDUE actuals are unreliable — gate the whole analysis. HISTORICAL (e.g.
  // Qualtrics pre-take-private) is real, finalized data: show it as-is, just
  // framed by the freshness badge and a context note.
  const monitoringPaused = freshness?.freshness_status === "overdue";
  const isHistorical = freshness?.freshness_status === "historical";

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
        <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
          {freshness && <FreshnessBadge freshness={freshness} />}
          <Badge status={data.health} />
        </div>
      </div>

      {monitoringPaused && freshness && <MonitoringPausedPanel freshness={freshness} onConnectData={onConnectData} />}

      {isHistorical && freshness && (
        <div
          className="card section-gap card-pad"
          style={{ background: "rgba(96,165,250,0.08)", border: "1px solid rgba(96,165,250,0.3)" }}
        >
          <div style={{ fontWeight: 700, fontSize: 13, marginBottom: 4, color: "var(--blue-text, #60a5fa)" }}>
            Historical Baseline
          </div>
          <div className="card-hint">{freshness.message}</div>
        </div>
      )}

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

      {/* GAAP/non-GAAP basis context: EDGAR actuals vs non-GAAP VCP targets look
          like massive drift without this explanation. */}
      {data.data_source === "edgar" && data.basis_mismatch && (
        <div
          style={{
            display: "flex",
            alignItems: "flex-start",
            gap: 10,
            marginTop: 16,
            padding: "12px 16px",
            borderRadius: 8,
            background: "rgba(245,158,11,0.08)",
            border: "1px solid rgba(245,158,11,0.35)",
          }}
        >
          <svg width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true"
            style={{ flexShrink: 0, marginTop: 2 }}>
            <circle cx="8" cy="8" r="7" stroke="rgba(245,158,11,0.9)" strokeWidth="1.5" />
            <path d="M8 7v4M8 5h.01" stroke="rgba(245,158,11,0.9)" strokeWidth="1.5" strokeLinecap="round" />
          </svg>
          <span style={{ fontSize: 13, lineHeight: 1.5, color: "var(--text-secondary)" }}>
            Actuals sourced from SEC EDGAR XBRL (GAAP basis, includes stock-based
            compensation). Last filing: <span className="mono" style={{ color: "var(--text-primary)" }}>{fullDate(data.last_filing_date)}</span>.
            VCP targets are from the DEFM14C management projections (non-GAAP basis).
            The margin gap reflects the GAAP/non-GAAP difference, not operational
            underperformance vs plan.
          </span>
        </div>
      )}

      {!monitoringPaused && (
        <>
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
          <QuantSections company={data} />
        </>
      )}
    </div>
  );
}

/**
 * Data freshness gate: drift/IRR analysis is suppressed for OVERDUE (late
 * submission) companies — a stale-data signal is itself the alert, so it
 * replaces the analysis rather than running underneath it. There's no live
 * data-source integration here — the CTA just jumps to the financials
 * upload flow so the GP (or the portco) can submit the missing period.
 */
function MonitoringPausedPanel({ freshness, onConnectData }: {
  freshness: NonNullable<CompanyDetail["data_freshness"]>;
  onConnectData?: () => void;
}) {
  return (
    <div
      className="card section-gap card-pad"
      style={{ background: "rgba(239,68,68,0.08)", border: "1px solid rgba(239,68,68,0.3)" }}
    >
      <div style={{ fontWeight: 700, fontSize: 13, marginBottom: 6, color: "rgba(239,68,68,0.95)" }}>
        Monitoring Paused
      </div>
      <div className="card-hint" style={{ marginBottom: 10 }}>{freshness.message}</div>
      <button className="btn primary" onClick={onConnectData} disabled={!onConnectData}>
        Upload Latest Financials
      </button>
    </div>
  );
}

/**
 * Fetches the quant IRR payload once and feeds both quant-driven sections:
 * the EBITDA forward curve (P10/P50/P90 band) and the IRR scenario matrix.
 */
function QuantSections({ company }: { company: CompanyDetail }) {
  const [irr, setIrr] = useState<IrrScenarioData | null>(null);

  useEffect(() => {
    setIrr(null);
    getIrrScenarios(company.company_id).then(setIrr).catch(() => { /* no IRR data — sections stay hidden */ });
  }, [company.company_id]);

  if (!irr) return null;
  return (
    <>
      <ForecastSection company={company} irr={irr} />
      <IrrSection data={irr} />
    </>
  );
}

/**
 * EBITDA forward curve: actual EBITDA history (resampled to quarterly for
 * monthly reporters, to match the quant engine's quarterly basis) followed by
 * the ensemble's P50 path inside its P10–P90 confidence band.
 */
function ForecastSection({ company, irr }: { company: CompanyDetail; irr: IrrScenarioData }) {
  const curve = useMemo<CurveRow[]>(() => {
    const forecast = irr.forecast_quarterly ?? [];
    if (!forecast.length) return [];

    // Quarterly actual EBITDA. EDGAR data is already quarterly; monthly private
    // CSVs are summed per calendar quarter (complete quarters only) so actuals
    // and forecast are on the same flow basis.
    const monthly = (company.periods_per_year || 12) >= 12;
    let actuals: Array<{ period_end: string; value: number }>;
    if (!monthly) {
      actuals = company.kpi_series
        .filter((k) => k.ebitda != null)
        .map((k) => ({ period_end: k.period_end, value: k.ebitda as number }));
    } else {
      const byQuarter = new Map<string, { period_end: string; sum: number; n: number }>();
      company.kpi_series.forEach((k) => {
        if (k.ebitda == null) return;
        const d = new Date(k.period_end);
        const key = `${d.getFullYear()}-Q${Math.floor(d.getMonth() / 3)}`;
        const q = byQuarter.get(key) ?? { period_end: k.period_end, sum: 0, n: 0 };
        q.sum += k.ebitda;
        q.n += 1;
        if (k.period_end > q.period_end) q.period_end = k.period_end;
        byQuarter.set(key, q);
      });
      actuals = [...byQuarter.values()]
        .filter((q) => q.n === 3)
        .map((q) => ({ period_end: q.period_end, value: q.sum }));
    }
    actuals.sort((a, b) => a.period_end.localeCompare(b.period_end));

    const last = actuals[actuals.length - 1];
    return [
      ...actuals.map((a) => ({ period_end: a.period_end, actual: a.value })),
      // bridge point so the P50 path and band visually connect to the last actual
      ...(last ? [{ period_end: last.period_end, actual: last.value, p50: last.value, band: [last.value, last.value] as [number, number] }] : []),
      ...forecast.slice(0, 8).map((f) => ({
        period_end: f.period_end,
        actual: null,
        p50: f.p50,
        band: [f.p10, f.p90] as [number, number],
      })),
    ];
  }, [company, irr]);

  if (!curve.length || irr.basis_mismatch) return null;
  const fmt = (v: number) => money(v, irr.currency);

  return (
    <div className="card section-gap card-pad">
      <div className="chart-head">
        <SectionLabel>EBITDA Forward Curve · P10–P90 Confidence Band</SectionLabel>
      </div>
      <ForwardCurveChart data={curve} format={fmt} />
      <div className="card-hint" style={{ marginTop: 10 }}>
        Quarterly EBITDA: actuals, then the quant ensemble's P50 path (STL decomposition +
        SARIMA + Holt-Winters). The shaded band is the P10–P90 model uncertainty range —
        the same projection that drives the Bear/Base/Bull IRR scenarios below.
      </div>
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

function IrrSection({ data }: { data: IrrScenarioData }) {
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
              {c.value != null ? (
                <div className="mono" style={{ fontSize: 18, fontWeight: 600 }}>
                  {c.value.toFixed(1)}%
                </div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-start", gap: 4 }}>
                  <div className="mono" style={{ fontSize: 18, fontWeight: 600, color: "rgba(239,68,68,0.95)" }}>
                    —
                  </div>
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
                </div>
              )}
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
