import { useEffect, useState } from "react";

const API_BASE_URL =
  (import.meta.env.VITE_API_BASE_URL as string) || "http://localhost:8000";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`);
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed: ${res.status}`);
  }
  return res.json();
}

async function post<T>(path: string, payload: unknown): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed: ${res.status}`);
  }
  return res.json();
}

/* ---------- Types ---------- */
export type Status = "Red" | "Amber" | "Green" | "Not Evaluable";

export interface HeadlineMetric { actual: number | null; target: number | null; gap_pct: number | null; status: Status; }

export interface CompanyOverview {
  company_id: string;
  company_name: string;
  health: Status;
  status_counts: Record<string, number>;
  milestones_on_track: number;
  milestones_total: number;
  headline_metrics: Partial<Record<string, HeadlineMetric>>;
  alert_count: number;
  hitl_status: string;
  priority: string | null;
  priority_rank: number | null;
  headline: string | null;
  recommended_action: string | null;
  primary_risks: string[];
}

export interface ActionItem {
  company_id: string;
  company_name: string;
  priority: string;
  priority_rank: number;
  priority_score: number;
  red_alert_count: number;
  amber_alert_count: number;
  headline: string;
  recommended_action: string;
  primary_risks: string[];
  evidence: Evidence[];
}

export interface Evidence {
  metric: string;
  severity: string;
  summary: string;
  source_path?: string;
  source_column?: string;
}

export interface PortfolioOverview {
  portfolio_company_count: number;
  total_alerts: number;
  severity_counts: Record<string, number>;
  action_item_count: number;
  companies: CompanyOverview[];
  action_items: ActionItem[];
}

export interface PlanPoint { month: number; period_end: string; planned_value: number; }

export interface Milestone {
  initiative: string;
  metric: string;
  category: string;
  owner_role: string | null;
  baseline_value: number | null;
  target_value: number | null;
  target_date: string | null;
  confidence: number;
  metadata?: { plan_path?: PlanPoint[] };
}

export interface DriftResult {
  metric: string;
  initiative: string;
  category: string;
  target_value: number | null;
  actual_value: number | null;
  gap_pct: number | null;
  status: Status;
  reason: string;
}

export interface KpiPoint {
  period_end: string;
  revenue: number | null;
  ebitda: number | null;
  ebitda_margin: number | null;
  net_debt: number | null;
  net_debt_to_ebitda: number | null;
  cash: number | null;
}

export interface CompanyDetail {
  company_id: string;
  company_name: string;
  currency: string;
  health: Status;
  status_counts: Record<string, number>;
  latest_period_end: string;
  milestones: Milestone[];
  drift_results: DriftResult[];
  kpi_series: KpiPoint[];
}

export interface ReviewItem {
  review_id: string;
  status: string;
  priority: string;
  company_id: string;
  company_name: string;
  headline: string;
  recommended_action: string;
  primary_risks: string[];
  red_alert_count: number;
  amber_alert_count: number;
  evidence: Evidence[];
  decision: {
    decision_status: string;
    reviewed_by: string | null;
    reviewed_at: string | null;
    reviewer_note: string | null;
    edited_recommended_action: string | null;
  };
}

export interface HitlQueue {
  queue_item_count: number;
  pending_review_count: number;
  queue_items: ReviewItem[];
}

export interface ExtractStatus {
  llm_configured: boolean;
  mode: "azure_openai" | "offline_heuristic";
  missing_vars: string[];
  deployment: string;
}

export interface ExtractedMilestone {
  company_id: string;
  company_name: string;
  initiative: string;
  metric: string;
  target_value: number | null;
  target_date: string | null;
  category: string;
  owner_role: string | null;
  baseline_value: number | null;
  confidence: number;
  source_text: string;
  confirmed: boolean;
  metadata?: {
    extraction_mode?: string;
    model?: string | null;
    value_unit?: string;
    target_horizon_months?: number | null;
    ambiguity_note?: string | null;
  };
}

export interface ExtractionResult {
  company_id: string;
  company_name: string;
  extraction_mode: string;
  model: string | null;
  source_document: string | null;
  document_loader: string | null;
  milestone_count: number;
  needs_review_count: number;
  milestones: ExtractedMilestone[];
}

export interface ConfirmResult {
  company_id: string;
  company_name: string;
  version: number;
  confirmed_count: number;
  store_path: string;
  milestones: ExtractedMilestone[];
}

export interface ConfirmedVcp {
  company_id: string;
  confirmed: boolean;
  version: number;
  milestone_count: number;
  milestones: ExtractedMilestone[];
}

export interface PeerMetricResult {
  metric: string;
  direction: "higher_is_better" | "lower_is_better";
  company_value: number | null;
  sector_median: number | null;
  gap: number | null;
  gap_pct: number | null;
  status: "Outperform" | "In-line" | "Underperform" | "Not Evaluable";
  reason: string;
}

export interface PeerBenchmark {
  company_id: string;
  company_name: string;
  sector_label: string;
  peer_set_size: number;
  latest_period_end: string;
  composite_outperformance: number | null;
  status_counts: Record<string, number>;
  results: PeerMetricResult[];
}

export interface IrrScenarioPoint {
  exit_multiple: number;
  hold_years: number;
  irr_percent: number;
}

export interface IrrScenarioData {
  company_id: string;
  exit_multiples: number[];
  hold_years: number[];
  scenarios: IrrScenarioPoint[];
}

async function postForm<T>(path: string, form: FormData): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, { method: "POST", body: form });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new Error(body.detail || `Request failed: ${res.status}`);
  }
  return res.json();
}

/* ---------- Financials / data-room ingestion (Path 2) ---------- */

export interface IngestStatus {
  llm_configured: boolean;
  mode: "azure_openai" | "offline_heuristic";
  missing_vars: string[];
  deployment: string;
  supported_types: string[];
}

export interface CurrencyNormalization {
  base_currency: string;
  source_currency: string | null;
  fx_rate_to_base: number;
  fx_rate_source: string;
  scale_multiplier: number;
  scale_detected: string | null;
  scale_source: string;
  periods_normalized: number;
  monetary_fields_present: string[];
  note: string;
}

export interface IngestedPeriod {
  period_end: string;
  currency: string;
  revenue: number | null;
  ebitda: number | null;
  ebitda_margin: number | null;
  net_debt: number | null;
  cash: number | null;
}

export interface IngestResult {
  company_id: string;
  company_name: string;
  source_document: string;
  source_type: string;
  base_currency: string;
  extraction_mode: string;
  model: string | null;
  document_loader: string | null;
  period_count: number;
  evidence_count: number;
  quality_status: string | null;
  missing_required_fields: string[];
  currency_normalization: CurrencyNormalization | null;
  kpi_records_path: string;
  periods: IngestedPeriod[];
}

export const getIngestStatus = () => get<IngestStatus>("/api/ingest/status");

export const ingestFinancialsUpload = (
  file: File,
  opts: { companyId?: string; companyName?: string; baseCurrency?: string },
) => {
  const form = new FormData();
  form.append("file", file);
  if (opts.companyId) form.append("company_id", opts.companyId);
  if (opts.companyName) form.append("company_name", opts.companyName);
  form.append("base_currency", opts.baseCurrency || "USD");
  return postForm<IngestResult>("/api/ingest/financials-upload", form);
};

/* ---------- Calls ---------- */
export const getPortfolio = () => get<PortfolioOverview>("/api/vcp/portfolio");
export const getExtractStatus = () => get<ExtractStatus>("/api/vcp/extract/status");
export const runExtraction = (companyId: string) =>
  post<ExtractionResult>(`/api/vcp/extract/${companyId}`, {});
export const runExtractionFromUpload = (
  file: File,
  opts?: { companyId?: string; companyName?: string },
) => {
  const form = new FormData();
  form.append("file", file);
  if (opts?.companyId) form.append("company_id", opts.companyId);
  if (opts?.companyName) form.append("company_name", opts.companyName);
  return postForm<ExtractionResult>("/api/vcp/extract-upload", form);
};
export const confirmVcp = (companyId: string, payload: {
  company_name?: string;
  reviewed_by: string;
  reviewer_note?: string;
  milestones: ExtractedMilestone[];
}) => post<ConfirmResult>(`/api/vcp/extract/${companyId}/confirm`, payload);
export const getConfirmedVcp = (companyId: string) =>
  get<ConfirmedVcp>(`/api/vcp/store/${companyId}`);
export const getPeers = (companyId: string) =>
  get<PeerBenchmark>(`/api/vcp/company/${companyId}/peers`);
export const getIrrScenarios = (companyId: string) =>
  get<IrrScenarioData>(`/api/vcp/company/${companyId}/irr`);
export const getCompany = (id: string) => get<CompanyDetail>(`/api/vcp/company/${id}`);
export const getHitl = () => get<HitlQueue>("/api/vcp/hitl");
export const getMemo = () => get<{ markdown: string }>("/api/vcp/memo");
export const generateMemo = () => post<{ markdown: string; generated_at: string; action_item_count: number }>("/api/vcp/memo/generate", {});
export const postDecision = (payload: {
  review_id: string;
  decision: "approve" | "edit" | "reject";
  reviewed_by: string;
  reviewer_note?: string;
  edited_recommended_action?: string;
}) => post<ReviewItem>("/api/vcp/hitl/decision", payload);

/* ---------- Reports ---------- */

export type ReportType = "board_pack" | "vcp_status_update";
export type ReportStatus = "draft" | "pending_review" | "approved";

export interface ReportSummary {
  id: string;
  company_id: string;
  company_name: string;
  report_type: ReportType;
  period: string;
  status: ReportStatus;
  generation_mode: "auto" | "manual";
  narrative_mode: string;
  alert_severity: Status;
  generated_at: string;
  approved_by: string | null;
  has_pdf: boolean;
}

export interface KpiPerformanceRow {
  metric_key: string;
  metric: string;
  actual: number | null;
  ic_target: number | null;
  delta_pct: number | null;
  qoq_pct: number | null;
  qoq_up: boolean | null;
  inverse: boolean;
  status: string;
  unit: string;
  fmt_actual: string;
  fmt_target: string;
  fmt_delta: string;
  fmt_qoq: string;
}

export interface RiskAction {
  priority: number;
  status: string;
  risk: string;
  irr_at_risk_bps: number | null;
  recommended_action: string;
}

/** A single slide in the 10-slide Board Pack payload (see slide_data_builder.py). */
export interface Slide {
  id: string;
  index: number;
  type:
    | "Cover" | "AtAGlance" | "ExecSummary" | "KPIScorecard" | "VCPScorecard"
    | "ForwardCurve" | "Benchmarks" | "RisksActions" | "IRRMatrix" | "AuditTrail";
  title: string;
  key_message: string;
  // Slide-specific payload — shape varies by type (see slide_data_builder.py).
  data: any;
}

/** Generation progress, polled from GET /api/reports/{id}/status. */
export interface ReportGenStatus {
  id: string;
  status: ReportStatus;
  progress_step: string;
  progress_label: string;
  progress_pct: number;
  slide_count: number;
  has_pdf: boolean;
}

export interface ReportDetail {
  id: string;
  company_id: string;
  company_name: string;
  report_type: ReportType;
  period: string;
  sector: string;
  status: ReportStatus;
  generation_mode: string;
  narrative_mode: string;
  generated_at: string;
  approved_at: string | null;
  approved_by: string | null;
  has_pdf: boolean;
  alert_severity: Status;
  alert_headline: string;
  irr_at_risk_bps: number | null;
  exec_summary: string;
  exec_summary_ai: string;
  exec_summary_edited: boolean;
  key_risks: string[];
  priority_action: string;
  board_talking_points: string[];
  confidence_statement: string;
  kpi_performance: KpiPerformanceRow[];
  drift_results: DriftResult[];
  milestones: Milestone[];
  risks_actions: RiskAction[];
  irr_scenarios: Record<string, unknown>[] | null;
  peer_benchmark: Record<string, unknown> | null;
  citations: string[];
  hitl_decisions: Record<string, unknown>[];
  edited_sections: Record<string, string>;
  // Fully-structured per-slide payload (10-slide Board Pack spec)
  board_questions: string[];
  risks_output: Record<string, unknown> | null;
  slides: Slide[];
}

export const listReports = () =>
  get<{ count: number; reports: ReportSummary[] }>("/api/reports");

export const deleteReport = (id: string) =>
  fetch(`${API_BASE_URL}/api/reports/${id}`, { method: "DELETE" }).then(r => {
    if (!r.ok) return r.json().then(b => Promise.reject(new Error(b.detail || "Delete failed")));
  });

export const generateReport = (payload: {
  company_id: string;
  report_type?: ReportType;
  period?: string;
  tone?: string;
  generation_mode?: string;
}) => post<ReportSummary>("/api/reports/generate", payload);

export const getReport = (id: string) =>
  get<ReportDetail>(`/api/reports/${id}`);

export const approveReport = (id: string, payload: { approved_by: string; note?: string }) =>
  fetch(`${API_BASE_URL}/api/reports/${id}/approve`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }).then(r => r.json());

export const editReportSection = (id: string, section_key: string, content: string) =>
  fetch(`${API_BASE_URL}/api/reports/${id}/section`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ section_key, content }),
  }).then(r => r.json());

export const getReportStatus = (id: string) =>
  get<ReportGenStatus>(`/api/reports/${id}/status`);

/* ---------- Progress polling hook ---------- */

/**
 * Poll GET /api/reports/{id}/status every `intervalMs` until generation
 * completes (status leaves "draft"/progress reaches 100). Returns the latest
 * status snapshot, or null before the first response. Pass `null` to disable.
 */
export function useReportStatus(
  reportId: string | null,
  opts: { intervalMs?: number; enabled?: boolean } = {},
): ReportGenStatus | null {
  const { intervalMs = 2000, enabled = true } = opts;
  const [status, setStatus] = useState<ReportGenStatus | null>(null);

  useEffect(() => {
    if (!reportId || !enabled) { setStatus(null); return; }
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout>;

    async function tick() {
      try {
        const s = await getReportStatus(reportId!);
        if (cancelled) return;
        setStatus(s);
        if (s.progress_pct >= 100 || s.status !== "draft") return; // done
      } catch {
        /* keep polling through transient errors */
      }
      if (!cancelled) timer = setTimeout(tick, intervalMs);
    }
    tick();
    return () => { cancelled = true; clearTimeout(timer); };
  }, [reportId, intervalMs, enabled]);

  return status;
}
