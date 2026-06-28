import { useEffect, useRef, useState, type DragEvent } from "react";
import {
  getIngestStatus, ingestFinancialsUpload,
  type CompanyOverview, type IngestResult, type IngestStatus,
} from "../lib/api";
import { Badge, SectionLabel } from "../components/ui";
import { money, pct, shortDate } from "../lib/format";

const BASE_CURRENCY = "USD";
const ACCEPT = ".pdf,.docx,.pptx,.html,.xhtml,.md,.markdown,.txt,.csv,.xlsx,.xls";

export function IngestView({ companies, onOpenCompany, onFinancialsIngested }: {
  companies: CompanyOverview[];
  onOpenCompany?: (id: string) => void;
  onFinancialsIngested?: () => void;
}) {
  const [status, setStatus] = useState<IngestStatus | null>(null);
  const [activeId, setActiveId] = useState<string>("");
  const [result, setResult] = useState<IngestResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState("");
  const [dragOver, setDragOver] = useState(false);
  const [stagedFile, setStagedFile] = useState<File | null>(null);
  const [periodLabel, setPeriodLabel] = useState("");
  const fileInput = useRef<HTMLInputElement>(null);

  const activeCompany = companies.find((c) => c.company_id === activeId);
  const live = status?.mode === "azure_openai";
  const step = !activeId ? 1 : !stagedFile && !busy && !result ? 2 : result ? 4 : 3;

  useEffect(() => { getIngestStatus().then(setStatus).catch(() => {}); }, []);

  function resetToUpload() {
    setStagedFile(null); setResult(null); setErr(""); setPeriodLabel("");
  }

  function changeCompany(id: string) {
    setActiveId(id);
    resetToUpload();
  }

  async function runUpload() {
    if (!activeId || !stagedFile) { setErr("Select a company and file first."); return; }
    setBusy(true); setErr(""); setResult(null);
    try {
      const r = await ingestFinancialsUpload(stagedFile, {
        companyId: activeId,
        companyName: activeCompany?.company_name,
        baseCurrency: BASE_CURRENCY,
      });
      setResult(r);
      setStagedFile(null);
      onFinancialsIngested?.();
    } catch (e) { setErr(e instanceof Error ? e.message : "Ingestion failed"); }
    finally { setBusy(false); }
  }

  function stageFile(file: File) {
    setErr(""); setResult(null); setStagedFile(file);
  }

  function onDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files?.[0];
    if (file && !busy) stageFile(file);
  }

  const norm = result?.currency_normalization;

  return (
    <div>
      <div className="page-head">
        <h1 className="page-title">Ingest Financials</h1>
        <p className="page-sub">
          Upload management accounts, QPR board packs, or Excel/CSV exports. The pipeline normalizes
          currency and unit scale, then writes the KPI time series the monitoring graph runs on.
        </p>
      </div>

      {/* Agent status bar */}
      {status && (
        <div className={`card card-pad extract-banner ${live ? "live" : "offline"}`}
          style={{ marginBottom: 24, display: "flex", gap: 12, alignItems: "center" }}>
          <Badge status={live ? "Green" : "Amber"} label={live ? "AGENT LIVE" : "OFFLINE"} />
          <div>
            <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)" }}>
              {live ? `GPT table extraction · ${status.deployment}` : "Deterministic table parser (no LLM)"}
            </div>
            <div style={{ fontSize: 12.5, color: "var(--text-secondary)" }}>
              {live
                ? "PDFs parsed locally (PyMuPDF4LLM / Docling), then read by the language model. CSV/Excel parsed directly."
                : `Add ${status.missing_vars.join(", ")} to .env to enable live GPT extraction.`}
            </div>
          </div>
        </div>
      )}

      {/* Step indicators */}
      <StepBar step={step} steps={["Select Company", "Upload Document", "Confirm Ingestion", "Review Results"]} />

      {/* ── STEP 1: Company Selection ── */}
      <div className="card card-pad" style={{ marginBottom: 20 }}>
        <div style={{ marginBottom: 14 }}>
          <StepBadge n={1} active={step >= 1} done={step > 1} />
          <span style={{ fontWeight: 600, fontSize: 14, marginLeft: 10 }}>Select Portfolio Company</span>
        </div>

        {/* Company cards grid */}
        <div style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(200px, 1fr))",
          gap: 10,
        }}>
          {companies.map((c) => {
            const selected = c.company_id === activeId;
            return (
              <button
                key={c.company_id}
                onClick={() => changeCompany(c.company_id)}
                style={{
                  textAlign: "left", padding: "12px 14px", borderRadius: 8, cursor: "pointer",
                  border: selected ? "2px solid var(--accent)" : "1px solid var(--border)",
                  background: selected ? "var(--accent-subtle)" : "var(--bg-muted)",
                  transition: "border-color .15s, background .15s",
                  display: "flex", flexDirection: "column", gap: 4,
                }}
              >
                <div style={{ fontWeight: 600, fontSize: 13, color: "var(--text-primary)" }}>
                  {c.company_name}
                </div>
                <div style={{ fontSize: 11.5, color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>
                  {c.company_id}
                </div>
                {selected && (
                  <div style={{ fontSize: 11, color: "var(--accent)", fontWeight: 600, marginTop: 2 }}>
                    ✓ Selected
                  </div>
                )}
              </button>
            );
          })}
        </div>

        {/* Sector context for benchmarking */}
        {activeCompany && (
          <div style={{
            marginTop: 14, padding: "10px 14px", borderRadius: 8,
            background: "var(--bg-muted)", border: "1px solid var(--border)",
            display: "flex", alignItems: "center", gap: 16, flexWrap: "wrap",
          }}>
            <div style={{ fontSize: 13 }}>
              <span style={{ color: "var(--text-muted)", fontSize: 12 }}>Company </span>
              <strong>{activeCompany.company_name}</strong>
            </div>
            <div style={{ fontSize: 13 }}>
              <span style={{ color: "var(--text-muted)", fontSize: 12 }}>Normalize to </span>
              <span className="mono" style={{ fontWeight: 600 }}>{BASE_CURRENCY}</span>
            </div>
            <div style={{ fontSize: 13, color: "var(--text-muted)", fontSize: 12 }}>
              Sector classification is derived from the ingested financial data for peer benchmarking.
            </div>
          </div>
        )}
      </div>

      {/* ── STEP 2: File Upload ── */}
      <div className="card card-pad" style={{
        marginBottom: 20,
        opacity: !activeId ? 0.45 : 1,
        pointerEvents: !activeId ? "none" : undefined,
      }}>
        <div style={{ marginBottom: 14 }}>
          <StepBadge n={2} active={step >= 2} done={step > 2} />
          <span style={{ fontWeight: 600, fontSize: 14, marginLeft: 10 }}>Upload Financial Document</span>
        </div>

        {/* Period label input */}
        <div style={{ marginBottom: 14, display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
          <div>
            <label style={{ fontSize: 12, color: "var(--text-muted)", display: "block", marginBottom: 4 }}>
              PERIOD LABEL <span style={{ color: "var(--text-muted)", fontWeight: 400 }}>(optional)</span>
            </label>
            <input
              className="input mono"
              style={{ width: 160 }}
              placeholder="e.g. Q2 2024"
              value={periodLabel}
              onChange={(e) => setPeriodLabel(e.target.value)}
            />
          </div>
          <div style={{ fontSize: 12.5, color: "var(--text-muted)", paddingTop: 18 }}>
            Helps identify this document in the ingestion history
          </div>
        </div>

        <div
          className={`upload-zone${dragOver ? " drag-over" : ""}`}
          onDragOver={(e) => { e.preventDefault(); setDragOver(true); }}
          onDragLeave={() => setDragOver(false)}
          onDrop={onDrop}
          onClick={() => !busy && !stagedFile && fileInput.current?.click()}
          role="button"
          tabIndex={0}
          style={{
            textAlign: "center", cursor: busy || stagedFile ? "default" : "pointer",
            borderStyle: "dashed", borderWidth: 2, borderRadius: 8, padding: "32px 20px",
            borderColor: dragOver ? "var(--accent)" : "var(--border)",
            background: dragOver ? "var(--accent-subtle)" : "var(--bg-muted)",
            transition: "border-color .15s, background .15s",
          }}
        >
          <input
            ref={fileInput} type="file" accept={ACCEPT} style={{ display: "none" }}
            onChange={(e) => { const f = e.target.files?.[0]; if (f) stageFile(f); e.target.value = ""; }}
          />
          {busy ? (
            <>
              <div style={{ fontSize: 28, marginBottom: 10 }}>⏳</div>
              <div style={{ fontSize: 14, fontWeight: 600, color: "var(--text-primary)" }}>
                Normalizing financials…
              </div>
              <div style={{ fontSize: 12.5, color: "var(--text-secondary)", marginTop: 4 }}>
                Parsing, currency normalizing, and writing KPI time series
              </div>
            </>
          ) : stagedFile ? (
            <>
              <div style={{ fontSize: 28, marginBottom: 10 }}>📄</div>
              <div style={{ fontSize: 14, fontWeight: 600, color: "var(--text-primary)" }}>
                {stagedFile.name}
              </div>
              <div style={{ fontSize: 12.5, color: "var(--text-secondary)", marginTop: 4 }}>
                {(stagedFile.size / 1024).toFixed(0)} KB · ready to ingest
              </div>
            </>
          ) : (
            <>
              <div style={{ fontSize: 28, marginBottom: 10, opacity: 0.5 }}>⬆</div>
              <div style={{ fontSize: 14, fontWeight: 600, color: "var(--text-primary)" }}>
                Drag & drop a financials document, or click to browse
              </div>
              <div style={{ fontSize: 12.5, color: "var(--text-secondary)", marginTop: 4 }}>
                Management accounts · QPR board pack · Excel/CSV export · PDF
              </div>
              <div style={{ marginTop: 12, display: "flex", gap: 6, justifyContent: "center", flexWrap: "wrap" }}>
                {[".PDF", ".XLSX", ".CSV", ".DOCX", ".HTML"].map((ext) => (
                  <span key={ext} className="mono" style={{
                    fontSize: 11, padding: "2px 8px", borderRadius: 4,
                    background: "var(--bg-surface)", border: "1px solid var(--border)",
                    color: "var(--text-muted)",
                  }}>{ext}</span>
                ))}
              </div>
            </>
          )}
        </div>
      </div>

      {/* ── STEP 3: Confirm Ingestion ── */}
      {stagedFile && !busy && (
        <div className="card card-pad" style={{
          marginBottom: 20,
          borderLeft: "3px solid var(--accent)",
        }}>
          <div style={{ marginBottom: 14 }}>
            <StepBadge n={3} active done={false} />
            <span style={{ fontWeight: 600, fontSize: 14, marginLeft: 10 }}>Confirm Ingestion</span>
          </div>

          <div style={{
            background: "var(--bg-muted)", borderRadius: 8, padding: "14px 16px", marginBottom: 16,
            display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(160px, 1fr))", gap: 12,
          }}>
            <ConfirmRow label="Company" value={activeCompany?.company_name ?? activeId} />
            <ConfirmRow label="Document" value={stagedFile.name} mono />
            <ConfirmRow label="File size" value={`${(stagedFile.size / 1024).toFixed(0)} KB`} mono />
            <ConfirmRow label="Period" value={periodLabel || "—"} mono />
            <ConfirmRow label="Normalize to" value={BASE_CURRENCY} mono />
          </div>

          <div style={{ display: "flex", gap: 10 }}>
            <button className="btn primary" onClick={runUpload} disabled={busy}>
              Confirm & Ingest
            </button>
            <button className="btn" onClick={resetToUpload}>Cancel</button>
          </div>
        </div>
      )}

      {err && (
        <div className="card card-pad" style={{ color: "var(--red-text)", marginBottom: 20, borderLeft: "3px solid var(--red)" }}>
          {err}
        </div>
      )}

      {/* ── STEP 4: Results Preview ── */}
      {result && (
        <div className="card card-pad" style={{ marginBottom: 20 }}>
          <div style={{ marginBottom: 14, display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 10 }}>
            <div>
              <StepBadge n={4} active done />
              <span style={{ fontWeight: 600, fontSize: 14, marginLeft: 10 }}>Ingestion Results</span>
            </div>
            <div style={{ display: "flex", gap: 8 }}>
              <Badge status="Green" label="Ingested" />
              <span className="mono" style={{ fontSize: 12, color: "var(--text-muted)", alignSelf: "center" }}>
                {result.document_loader ?? result.source_type}
                {result.model ? ` · ${result.model}` : ""}
              </span>
            </div>
          </div>

          {/* Summary row */}
          <div style={{
            display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(140px, 1fr))",
            gap: 10, marginBottom: 20,
          }}>
            <SummaryTile label="Periods ingested" value={String(result.period_count)} />
            <SummaryTile label="Source document" value={result.source_document} mono />
            <SummaryTile label="Base currency" value={result.base_currency} mono />
            {norm?.source_currency && norm.source_currency !== norm.base_currency && (
              <SummaryTile
                label="FX applied"
                value={`${norm.source_currency}→${norm.base_currency} @ ${norm.fx_rate_to_base}`}
                mono
              />
            )}
            {norm?.scale_detected && (
              <SummaryTile
                label="Scale"
                value={`${norm.scale_detected} ×${norm.scale_multiplier.toLocaleString()}`}
                mono
              />
            )}
          </div>

          {/* Data quality warning */}
          {(result.quality_status === "poor" || result.quality_status === "partial" || result.missing_required_fields.length > 0) && (
            <div style={{
              padding: "12px 14px", borderRadius: 8, marginBottom: 16,
              borderLeft: `3px solid var(--${result.quality_status === "poor" ? "red" : "amber"})`,
              background: result.quality_status === "poor" ? "var(--red-bg)" : "var(--amber-bg)",
            }}>
              <div style={{ fontWeight: 600, fontSize: 13, color: `var(--${result.quality_status === "poor" ? "red-text" : "amber-text"})`, marginBottom: 6 }}>
                ⚠ Data Quality Issues
              </div>
              {result.missing_required_fields.length > 0 && (
                <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 8 }}>
                  {result.missing_required_fields.map((f) => (
                    <span key={f} className="mono" style={{
                      fontSize: 12, padding: "2px 8px", borderRadius: 4,
                      background: "var(--bg-surface)", border: "1px solid var(--border)",
                      color: "var(--text-secondary)",
                    }}>{f}</span>
                  ))}
                </div>
              )}
              <div style={{ fontSize: 12.5, color: "var(--text-secondary)" }}>
                These fields are required for VCP drift monitoring. Review the source document layout.
              </div>
            </div>
          )}

          {/* Normalized periods table */}
          <SectionLabel>Normalized Periods ({result.periods.length})</SectionLabel>
          <div style={{ overflowX: "auto", borderRadius: 8, border: "1px solid var(--border)" }}>
            <table className="data-table" style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead>
                <tr style={{ background: "var(--bg-muted)" }}>
                  <th style={{ textAlign: "left", padding: "10px 12px", color: "var(--text-muted)", fontSize: 11, textTransform: "uppercase", letterSpacing: ".04em", fontWeight: 600 }}>Period</th>
                  {["Revenue", "EBITDA", "Margin", "Net Debt", "Cash"].map((h) => (
                    <th key={h} style={{ padding: "10px 12px", textAlign: "right", color: "var(--text-muted)", fontSize: 11, textTransform: "uppercase", letterSpacing: ".04em", fontWeight: 600 }}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {result.periods.map((p, i) => (
                  <tr key={i} style={{ borderTop: "1px solid var(--border)" }}>
                    <td style={{ padding: "10px 12px", color: "var(--text-secondary)", fontWeight: 500 }}>{shortDate(p.period_end)}</td>
                    <td className="mono" style={{ padding: "10px 12px", textAlign: "right" }}>{money(p.revenue, result.base_currency)}</td>
                    <td className="mono" style={{ padding: "10px 12px", textAlign: "right" }}>{money(p.ebitda, result.base_currency)}</td>
                    <td className="mono" style={{ padding: "10px 12px", textAlign: "right" }}>{pct(p.ebitda_margin)}</td>
                    <td className="mono" style={{ padding: "10px 12px", textAlign: "right" }}>{money(p.net_debt, result.base_currency)}</td>
                    <td className="mono" style={{ padding: "10px 12px", textAlign: "right" }}>{money(p.cash, result.base_currency)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          <div style={{ marginTop: 16, display: "flex", gap: 10 }}>
            <button className="btn primary" onClick={() => onOpenCompany?.(result.company_id)}>
              View Company Deep Dive →
            </button>
            <button className="btn" onClick={resetToUpload}>
              Upload another document
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

/* ── Sub-components ── */

function StepBar({ step, steps }: { step: number; steps: string[] }) {
  return (
    <div style={{ display: "flex", alignItems: "center", marginBottom: 24, overflowX: "auto" }}>
      {steps.map((label, i) => {
        const n = i + 1;
        const done = step > n;
        const active = step === n;
        return (
          <div key={n} style={{ display: "flex", alignItems: "center", flex: i < steps.length - 1 ? 1 : undefined, minWidth: 0 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 7, flexShrink: 0 }}>
              <div style={{
                width: 24, height: 24, borderRadius: "50%", flexShrink: 0,
                display: "flex", alignItems: "center", justifyContent: "center",
                fontSize: 11, fontWeight: 700,
                background: done ? "var(--green)" : active ? "var(--accent)" : "var(--bg-muted)",
                color: done || active ? "#fff" : "var(--text-muted)",
                border: done || active ? "none" : "1px solid var(--border)",
              }}>
                {done ? "✓" : n}
              </div>
              <span style={{
                fontSize: 12.5, fontWeight: active ? 600 : 400, whiteSpace: "nowrap",
                color: active ? "var(--text-primary)" : done ? "var(--text-secondary)" : "var(--text-muted)",
              }}>{label}</span>
            </div>
            {i < steps.length - 1 && (
              <div style={{
                flex: 1, height: 1, margin: "0 10px",
                background: step > n ? "var(--green)" : "var(--border)",
                minWidth: 20,
              }} />
            )}
          </div>
        );
      })}
    </div>
  );
}

function StepBadge({ n, active, done }: { n: number; active: boolean; done: boolean }) {
  return (
    <span style={{
      display: "inline-flex", alignItems: "center", justifyContent: "center",
      width: 22, height: 22, borderRadius: "50%", fontSize: 11, fontWeight: 700,
      background: done ? "var(--green)" : active ? "var(--accent)" : "var(--bg-muted)",
      color: done || active ? "#fff" : "var(--text-muted)",
      verticalAlign: "middle",
    }}>{done ? "✓" : n}</span>
  );
}

function ConfirmRow({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div>
      <div style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: ".04em", color: "var(--text-muted)", marginBottom: 3 }}>
        {label}
      </div>
      <div className={mono ? "mono" : undefined} style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)", wordBreak: "break-all" }}>
        {value}
      </div>
    </div>
  );
}

function SummaryTile({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div style={{
      padding: "10px 12px", borderRadius: 8,
      background: "var(--bg-muted)", border: "1px solid var(--border)",
    }}>
      <div style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: ".04em", color: "var(--text-muted)", marginBottom: 4 }}>
        {label}
      </div>
      <div className={mono ? "mono" : undefined} style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)", wordBreak: "break-word" }}>
        {value}
      </div>
    </div>
  );
}
