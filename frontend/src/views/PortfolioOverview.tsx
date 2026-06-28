import type React from "react";
import type { CompanyOverview, PortfolioOverview } from "../lib/api";
import { Badge, MetricCard, SectionLabel } from "../components/ui";
import { metricLabel, money, pct, signedPct, bpsAbs } from "../lib/format";

interface Props {
  data: PortfolioOverview;
  onOpenCompany: (id: string) => void;
}

export function PortfolioOverviewView({ data, onOpenCompany }: Props) {
  const red = data.severity_counts.Red || 0;
  const amber = data.severity_counts.Amber || 0;
  const onTrack = data.companies.filter((c) => c.health === "Green").length;

  return (
    <div>
      <style>{`
        @keyframes pulse {
          0%, 100% { opacity: 1; transform: scale(1); }
          50% { opacity: 0.5; transform: scale(1.4); }
        }
      `}</style>
      <div className="page-head">
        <h1 className="page-title">Portfolio Overview</h1>
      </div>

      {/* Fund summary */}
      <SectionLabel>Fund Summary</SectionLabel>
      <div className="grid grid-3" style={{ marginBottom: 26 }}>
        <MetricCard label="Portfolio" value={String(data.portfolio_company_count ?? "—")} vs="companies under monitoring" icon="domain" />
        <MetricCard label="VCP Health" value={`${onTrack} / ${data.companies.length}`} vs="on track · green status" icon="trending_up" deltaUp />
        <MetricCard label="Active Alerts" value={String(data.total_alerts ?? red + amber)} vs={`${red} critical · ${amber} watch`} icon="warning" iconColor="var(--red-text, #f87171)" delta={red > 0 ? `${red} critical` : undefined} />
      </div>

      {/* Attention list */}
      <SectionLabel>Needs Attention</SectionLabel>
      {data.action_items.length === 0 ? (
        <div className="card attention allclear allclear-banner" style={{ marginBottom: 26 }}>
          <span className="check">✓</span>
          <span style={{ fontSize: 13 }}>All companies on track — no value-creation drift detected this period.</span>
        </div>
      ) : (
        <div className="card attention" style={{ marginBottom: 26 }}>
          {data.action_items.map((a, i) => (
            <div key={a.company_id} className="card-pad"
              style={{ borderTop: i ? "1px solid var(--border)" : "none", display: "flex", gap: 14 }}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div className="alert-meta" style={{ marginBottom: 4 }}>
                  <Badge status={a.priority === "P1" ? "Red" : "Amber"} label={a.priority} />
                  <button className="crumb" style={{ margin: 0, fontWeight: 600, color: "var(--text-primary)" }}
                    onClick={() => onOpenCompany(a.company_id)}>{a.company_name} ›</button>
                </div>
                <p className="alert-headline" style={{ margin: "0 0 4px" }}>{a.headline}</p>
                <p className="alert-rec"><b>Recommended:</b> {a.recommended_action}</p>
                <div className="risk-chips">
                  {a.primary_risks.map((r) => <span className="chip" key={r}>{metricLabel(r)}</span>)}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Company grid */}
      <SectionLabel>Portfolio Companies</SectionLabel>
      <div className="grid grid-3" style={{ marginBottom: 26 }}>
        {data.companies.map((c) => <PortfolioCard key={c.company_id} c={c} onOpen={() => onOpenCompany(c.company_id)} />)}
      </div>
    </div>
  );
}

function PortfolioCard({ c, onOpen }: { c: CompanyOverview; onOpen: () => void }) {
  const rev = c.headline_metrics.annual_revenue;
  const marg = c.headline_metrics.ebitda_margin;

  const dotColor = c.health === "Red" ? "var(--red, #ef4444)" : c.health === "Amber" ? "var(--amber, #f59e0b)" : "var(--green, #22c55e)";
  const alertHeadline = c.headline ?? null;
  const showAlert = (c.health === "Red" || c.health === "Amber") && alertHeadline != null;

  const footerStyle: React.CSSProperties = c.health === "Red"
    ? { background: "rgba(239,68,68,0.08)", borderTop: "1px solid rgba(239,68,68,0.2)", color: "var(--red-text, #f87171)" }
    : { background: "rgba(245,158,11,0.08)", borderTop: "1px solid rgba(245,158,11,0.2)", color: "var(--amber-text, #fbbf24)" };

  return (
    <div className="card co-card" style={{ padding: 0, display: "flex", flexDirection: "column", overflow: "hidden" }} onClick={onOpen}>
      {/* Header */}
      <div className="card-pad" style={{ borderBottom: "1px solid var(--border)", display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: 8 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 7 }}>
          <span style={{
            width: 8, height: 8, borderRadius: "50%", flexShrink: 0,
            background: dotColor,
            animation: c.health === "Red" ? "pulse 2s infinite" : undefined,
          }} />
          <div className="co-name">{c.company_name}</div>
        </div>
        <Badge status={c.health} />
      </div>
      {/* Body */}
      <div className="card-pad" style={{ flex: 1 }}>
        <KpiLine label="Revenue (run-rate)" value={money(rev?.actual)} delta={rev?.gap_pct != null ? signedPct(rev.gap_pct) : ""} down={(rev?.gap_pct ?? 0) < 0} />
        <KpiLine label="EBITDA Margin" value={pct(marg?.actual)} delta={bpsAbs(marg?.actual, marg?.target)} down={(marg?.actual ?? 0) < (marg?.target ?? 0)} />
        <div className="co-kpi">
          <span className="k">VCP on track</span>
          <span className="v">{c.milestones_on_track} / {c.milestones_total}</span>
        </div>
        <div className="co-open">Deep Dive →</div>
      </div>
      {/* Footer — only for Red/Amber with a headline */}
      {showAlert && (
        <div style={{ padding: "10px 24px", fontSize: 12, lineHeight: 1.4, ...footerStyle }}>
          <span className="material-symbols-outlined" style={{ fontSize: 13, verticalAlign: "middle", marginRight: 4 }}>warning</span>{alertHeadline}
        </div>
      )}
    </div>
  );
}

function KpiLine({ label, value, delta, down }: { label: string; value: string; delta: string; down: boolean }) {
  return (
    <div className="co-kpi">
      <span className="k">{label}</span>
      <span style={{ display: "flex", alignItems: "baseline", gap: 8 }}>
        <span className="v">{value}</span>
        {delta && delta !== "—" && <span className={`d ${down ? "down" : "up"}`}>{delta}</span>}
      </span>
    </div>
  );
}
