import type { Status } from "./api";

export function money(v: number | null | undefined, currency = "GBP"): string {
  if (v == null || isNaN(v)) return "—";
  const sym = currency === "GBP" ? "£" : currency === "USD" ? "$" : currency === "EUR" ? "€" : "";
  const abs = Math.abs(v);
  if (abs >= 1e9) return `${sym}${(v / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `${sym}${(v / 1e6).toFixed(1)}M`;
  if (abs >= 1e3) return `${sym}${(v / 1e3).toFixed(0)}k`;
  return `${sym}${v.toFixed(0)}`;
}

export function pct(v: number | null | undefined, digits = 1): string {
  if (v == null || isNaN(v)) return "—";
  return `${(v * 100).toFixed(digits)}%`;
}

export function signedPct(v: number | null | undefined, digits = 1): string {
  if (v == null || isNaN(v)) return "—";
  const s = (v * 100).toFixed(digits);
  return `${v >= 0 ? "+" : ""}${s}%`;
}

/** Basis-points delta from a fractional gap (e.g. -0.028 -> "-280bps"). */
export function bps(v: number | null | undefined): string {
  if (v == null || isNaN(v)) return "—";
  const b = Math.round(v * 10000);
  return `${b >= 0 ? "+" : ""}${b}bps`;
}

/** Absolute basis-points difference between two rates (e.g. 0.11 vs 0.24 -> "-1300bps"). */
export function bpsAbs(actual: number | null | undefined, target: number | null | undefined): string {
  if (actual == null || target == null) return "—";
  return bps(actual - target);
}

export function mult(v: number | null | undefined): string {
  if (v == null || isNaN(v)) return "—";
  return `${v.toFixed(2)}x`;
}

export function shortDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleDateString("en-GB", { month: "short", year: "2-digit" });
}

export function dateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("en-GB", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
}

export function metricLabel(metric: string): string {
  const map: Record<string, string> = {
    annual_revenue: "Annual Revenue",
    ebitda_margin: "EBITDA Margin",
    net_debt_to_ebitda: "Net Debt / EBITDA",
    cro_hired: "Chief Revenue Officer Hire",
    reporting_cadence_upgrade_complete: "Monthly Reporting Upgrade",
  };
  return map[metric] || metric;
}

/** Map a drift Status to the CSS class used by badges/dots (collapses "Not Evaluable"). */
export function statusClass(s: Status | string): string {
  if (s === "Not Evaluable") return "Neutral";
  return s;
}

/** Human label in the spec's vocabulary. */
export function statusLabel(s: Status | string): string {
  const map: Record<string, string> = {
    Green: "On Track",
    Amber: "At Risk",
    Red: "Behind",
    "Not Evaluable": "No Data",
  };
  return map[s] || String(s);
}

/** Format a milestone/drift value according to its metric type. */
export function metricValue(metric: string, v: number | null | undefined, currency = "GBP"): string {
  if (v == null) return "—";
  if (metric === "annual_revenue") return money(v, currency);
  if (metric === "ebitda_margin") return pct(v, 1);
  if (metric === "net_debt_to_ebitda") return mult(v);
  return String(v);
}

/** Gap delta formatted per metric: bps for margin, % for revenue, x for leverage. */
export function metricGap(metric: string, gapPct: number | null | undefined): string {
  if (gapPct == null) return "—";
  if (metric === "ebitda_margin") return bps(gapPct);
  return signedPct(gapPct);
}
