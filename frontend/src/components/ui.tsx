import type { ReactNode } from "react";
import type { Status } from "../lib/api";
import { statusClass, statusLabel } from "../lib/format";

export function Badge({ status, label }: { status: Status | string; label?: string }) {
  const cls = statusClass(status);
  return (
    <span className={`badge ${cls}`}>
      <span className="bdot" />
      {label ?? statusLabel(status)}
    </span>
  );
}

export function SectionLabel({ children }: { children: ReactNode }) {
  return <p className="section-label">{children}</p>;
}

export function MetricCard({
  label, value, delta, deltaUp, vs, icon, iconColor,
}: { label: string; value: string; delta?: string | null; deltaUp?: boolean; vs?: string; icon?: string; iconColor?: string }) {
  return (
    <div className="metric">
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start" }}>
        <div className="metric-label">{label}</div>
        {icon && <span className="material-symbols-outlined" style={{ fontSize: 18, opacity: 0.55, color: iconColor ?? "var(--text-muted)" }}>{icon}</span>}
      </div>
      <div className="metric-row1">
        <span className="metric-value">{value}</span>
      </div>
      {(delta || vs) && (
        <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 8 }}>
          {delta && (
            <span className={`metric-delta metric-chip ${deltaUp ? "up" : "down"}`}>{delta}</span>
          )}
          {vs && <div className="metric-vs" style={{ marginTop: 0 }}>{vs}</div>}
        </div>
      )}
    </div>
  );
}

export function Citation({ children }: { children: ReactNode }) {
  return <div className="citation">{children}</div>;
}

export function Spinner({ label }: { label?: string }) {
  return (
    <div className="center-state">
      <div style={{ textAlign: "center" }}>
        <div className="spinner" style={{ margin: "0 auto 12px" }} />
        {label && <div style={{ fontSize: 13 }}>{label}</div>}
      </div>
    </div>
  );
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div className="center-state">
      <div style={{ textAlign: "center", maxWidth: 440 }}>
        <div style={{ fontSize: 15, fontWeight: 600, color: "var(--text-primary)", marginBottom: 6 }}>
          Couldn’t reach the backend
        </div>
        <div style={{ fontSize: 13, marginBottom: 14 }}>{message}</div>
        <div style={{ fontSize: 12, color: "var(--text-muted)", marginBottom: 16 }}>
          Start the API: <span className="mono">uv run uvicorn app.api.main:app --port 8000</span>
        </div>
        {onRetry && <button className="btn primary" onClick={onRetry}>Retry</button>}
      </div>
    </div>
  );
}
