import type { CSSProperties, ReactNode } from "react";

/** RAG token ("red"|"amber"|"green"|"grey") → CSS colour variable. */
export function ragColor(rag: string): string {
  switch ((rag || "").toLowerCase()) {
    case "red": return "var(--red)";
    case "amber": return "var(--amber-text)";
    case "green": return "var(--green)";
    default: return "var(--neutral)";
  }
}

export function ragLabel(rag: string): string {
  switch ((rag || "").toLowerCase()) {
    case "red": return "Behind";
    case "amber": return "At Risk";
    case "green": return "On Track";
    default: return "No Data";
  }
}

/** Filled status dot. */
export function Dot({ rag, size = 9 }: { rag: string; size?: number }) {
  return (
    <span style={{
      display: "inline-block", width: size, height: size, borderRadius: "50%",
      background: ragColor(rag), flexShrink: 0,
    }} />
  );
}

/** Small uppercase section label used across slides. */
export function Label({ children, style }: { children: ReactNode; style?: CSSProperties }) {
  return (
    <div style={{
      fontSize: 11, fontWeight: 600, textTransform: "uppercase", letterSpacing: "0.06em",
      color: "var(--text-muted)", marginBottom: 8, ...style,
    }}>
      {children}
    </div>
  );
}

/** Large mono stat callout (spec: 48px JetBrains Mono). */
export function Stat({ label, value, sub, negative }: {
  label: string; value: string; sub?: string; negative?: boolean;
}) {
  return (
    <div style={{
      border: "1px solid var(--border)", borderRadius: 8, padding: "12px 16px",
      background: "var(--bg-surface)",
    }}>
      <div style={{ fontSize: 10, fontWeight: 600, textTransform: "uppercase",
                     letterSpacing: "0.06em", color: "var(--text-muted)", marginBottom: 4 }}>
        {label}
      </div>
      <div style={{ fontFamily: "var(--font-mono)", fontWeight: 700, fontSize: "clamp(22px, 3.2vw, 40px)",
                     lineHeight: 1.05, color: negative ? "var(--red)" : "var(--text-primary)" }}>
        {value}
      </div>
      {sub && <div style={{ fontSize: 11, color: "var(--text-secondary)", marginTop: 3 }}>{sub}</div>}
    </div>
  );
}

/* ---- Shared table primitives ---- */

export const thStyle: CSSProperties = {
  padding: "6px 8px", fontWeight: 600, fontSize: 10, textTransform: "uppercase",
  letterSpacing: "0.04em", color: "var(--text-muted)",
  borderBottom: "1px solid var(--border)",
};

export const tdStyle: CSSProperties = {
  padding: "6px 8px", fontSize: 12, borderBottom: "1px solid var(--border)",
};

export const monoTd: CSSProperties = {
  ...tdStyle, fontFamily: "var(--font-mono)", textAlign: "right",
};

/** Amber-bordered callout strip used for priority actions / AI analysis. */
export function ActionStrip({ label, children }: { label?: string; children: ReactNode }) {
  return (
    <div style={{
      borderLeft: "3px solid var(--amber)", background: "var(--amber-bg)",
      borderRadius: "0 6px 6px 0", padding: "10px 14px",
    }}>
      {label && (
        <div style={{ fontSize: 10, fontWeight: 700, textTransform: "uppercase",
                       letterSpacing: "0.05em", color: "var(--amber-text)", marginBottom: 4 }}>
          {label}
        </div>
      )}
      <div style={{ fontSize: 12.5, color: "var(--text-primary)", lineHeight: 1.5 }}>{children}</div>
    </div>
  );
}

/** AI-generated provenance badge. */
export function AiBadge({ label = "AI Generated" }: { label?: string }) {
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", gap: 5, fontSize: 10.5,
      color: "var(--text-muted)", fontWeight: 500,
    }}>
      <span style={{ display: "inline-block", width: 6, height: 6, borderRadius: "50%",
                      background: "var(--accent)" }} />
      {label}
    </span>
  );
}
