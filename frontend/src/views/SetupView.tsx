import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type DragEvent,
  type ReactNode,
} from "react";

function useWide(breakpoint = 960) {
  const [wide, setWide] = useState(() => window.innerWidth >= breakpoint);
  useEffect(() => {
    const mq = window.matchMedia(`(min-width: ${breakpoint}px)`);
    const handler = (e: MediaQueryListEvent) => setWide(e.matches);
    mq.addEventListener("change", handler);
    return () => mq.removeEventListener("change", handler);
  }, [breakpoint]);
  return wide;
}

import {
  confirmVcp,
  getConfirmedVcp,
  getExtractStatus,
  runExtraction,
  runExtractionFromUpload,
  type CompanyOverview,
  type ConfirmedVcp,
  type ExtractStatus,
  type ExtractedMilestone,
  type ExtractionResult,
} from "../lib/api";
import { Badge, SectionLabel } from "../components/ui";
import { metricLabel, metricValue, shortDate } from "../lib/format";

const REVIEWER = "operating.partner@firm.com";
const ACCEPT = ".pdf,.docx,.pptx,.html,.xhtml,.md,.markdown,.txt";

function slugify(name: string) {
  return (
    name
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "_")
      .replace(/^_|_$/g, "") || "new_company"
  );
}

export function SetupView({ companies, onVcpLocked, onGoToIngest }: {
  companies: CompanyOverview[];
  onVcpLocked?: () => void;
  onGoToIngest?: () => void;
}) {
  const wide = useWide(960);
  const [status, setStatus] = useState<ExtractStatus | null>(null);
  const [activeId, setActiveId] = useState<string>("");
  const [isNewCompany, setIsNewCompany] = useState(true);
  const [newCompanyName, setNewCompanyName] = useState("");
  const [result, setResult] = useState<ExtractionResult | null>(null);
  const [items, setItems] = useState<ExtractedMilestone[]>([]);
  const [confirmed, setConfirmed] = useState<ConfirmedVcp | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [err, setErr] = useState("");
  const [dragOver, setDragOver] = useState(false);
  const [uploadName, setUploadName] = useState<string>("");
  const fileInput = useRef<HTMLInputElement>(null);

  const activeCompany = companies.find((c) => c.company_id === activeId);
  const live = status?.mode === "azure_openai";
  const hasExistingVcp = confirmed?.confirmed && confirmed.milestone_count > 0;

  // For new company mode: company identity comes from the name field OR is auto-detected from document
  const resolvedCompanyId = isNewCompany ? slugify(newCompanyName) : activeId;
  const resolvedCompanyName = isNewCompany
    ? newCompanyName
    : activeCompany?.company_name;

  // Step is ready to upload when: existing company selected OR new company has a name entered (or will be auto-detected)
  const companyReady = isNewCompany ? true : !!activeId;
  const step = !companyReady ? 1 : !result ? 2 : 3;

  const loadConfirmed = useCallback((cid: string) => {
    getConfirmedVcp(cid)
      .then(setConfirmed)
      .catch(() => setConfirmed(null));
  }, []);

  useEffect(() => {
    getExtractStatus()
      .then(setStatus)
      .catch(() => {});
  }, []);
  useEffect(() => {
    if (!isNewCompany && activeId) loadConfirmed(activeId);
    else setConfirmed(null);
    setResult(null);
    setItems([]);
    setErr("");
  }, [activeId, isNewCompany, loadConfirmed]);

  async function run() {
    if (!resolvedCompanyId) return;
    setBusy(true);
    setErr("");
    setResult(null);
    setItems([]);
    setUploadName("sample memo");
    try {
      const r = await runExtraction(resolvedCompanyId);
      setResult(r);
      setItems(r.milestones);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Extraction failed");
    } finally {
      setBusy(false);
    }
  }

  async function runUpload(file: File) {
    setBusy(true);
    setErr("");
    setResult(null);
    setItems([]);
    setUploadName(file.name);
    try {
      const r = await runExtractionFromUpload(file, {
        // For new companies with no name entered yet, omit the ID so the backend
        // derives it from the filename rather than falling back to "new_company".
        companyId: (isNewCompany && !newCompanyName) ? undefined : (resolvedCompanyId || undefined),
        companyName: resolvedCompanyName || undefined,
      });
      setResult(r);
      setItems(r.milestones);
      // If the document revealed a company name and we're in new-company mode, pre-fill it
      if (isNewCompany && r.company_name && !newCompanyName) {
        setNewCompanyName(r.company_name);
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Extraction failed");
    } finally {
      setBusy(false);
    }
  }

  function onDrop(e: DragEvent<HTMLDivElement>) {
    e.preventDefault();
    setDragOver(false);
    const file = e.dataTransfer.files?.[0];
    if (file && !busy) runUpload(file);
  }

  function patch(idx: number, field: keyof ExtractedMilestone, value: unknown) {
    setItems((prev) =>
      prev.map((m, i) => (i === idx ? { ...m, [field]: value } : m)),
    );
  }
  function remove(idx: number) {
    setItems((prev) => prev.filter((_, i) => i !== idx));
  }
  function addBlank() {
    setItems((prev) => [
      ...prev,
      {
        company_id: activeId,
        company_name: activeCompany?.company_name ?? activeId,
        initiative: "",
        metric: "other",
        target_value: null,
        target_date: null,
        category: "operational",
        owner_role: null,
        baseline_value: null,
        confidence: 1,
        source_text: "Added manually by reviewer",
        confirmed: false,
      },
    ]);
  }

  async function confirm() {
    if (!items.length) return;
    const cid = result?.company_id || resolvedCompanyId;
    if (!cid) return;
    setConfirming(true);
    setErr("");
    try {
      await confirmVcp(cid, {
        company_name: result?.company_name || resolvedCompanyName,
        reviewed_by: REVIEWER,
        reviewer_note: `Confirmed ${items.length} milestone(s) via Setup review`,
        milestones: items,
      });
      setResult(null);
      setItems([]);
      loadConfirmed(cid);
      onVcpLocked?.();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Confirmation failed");
    } finally {
      setConfirming(false);
    }
  }

  return (
    <div>
      <div className="page-head">
        <h1 className="page-title">VCP Setup</h1>
        <p className="page-sub">
          Extract value-creation commitments from an IC memo, review candidate
          milestones, and lock the confirmed VCP.
        </p>
      </div>

      {/* Agent status bar */}
      {status && (
        <div
          className={`card card-pad extract-banner ${live ? "live" : "offline"}`}
          style={{
            marginBottom: 24,
            display: "flex",
            gap: 12,
            alignItems: "center",
          }}
        >
          <Badge
            status={live ? "Green" : "Amber"}
            label={live ? "AGENT LIVE" : "OFFLINE"}
          />
          <div>
            <div
              style={{
                fontSize: 13,
                fontWeight: 600,
                color: "var(--text-primary)",
              }}
            >
              {live
                ? `GPT extraction · ${status.deployment}`
                : "Deterministic fallback (no LLM)"}
            </div>
            <div style={{ fontSize: 12.5, color: "var(--text-secondary)" }}>
              {live
                ? "Documents parsed locally with Docling, then read by the language model."
                : `Add ${status.missing_vars.join(", ")} to .env to enable live GPT extraction.`}
            </div>
          </div>
        </div>
      )}

      {/* Step indicators */}
      <StepBar
        step={step}
        steps={["Select Company", "Upload Document", "Review & Confirm"]}
      />

      {/* ── STEP 1: Company Selection ── */}
      <div className="card card-pad" style={{ marginBottom: 20 }}>
        <div
          style={{
            marginBottom: 14,
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            flexWrap: "wrap",
            gap: 10,
          }}
        >
          <div>
            <StepBadge n={1} active={step >= 1} />
            <span style={{ fontWeight: 600, fontSize: 14, marginLeft: 10 }}>
              Select Portfolio Company
            </span>
          </div>
          {/* Toggle between existing and new company */}
          <div
            style={{
              display: "flex",
              gap: 0,
              borderRadius: 7,
              border: "1px solid var(--border)",
              overflow: "hidden",
              fontSize: 12.5,
            }}
          >
            <button
              onClick={() => {
                setIsNewCompany(false);
                setNewCompanyName("");
              }}
              style={{
                padding: "5px 14px",
                border: "none",
                cursor: "pointer",
                fontWeight: !isNewCompany ? 600 : 400,
                background: !isNewCompany
                  ? "var(--accent)"
                  : "var(--bg-surface)",
                color: !isNewCompany ? "#fff" : "var(--text-secondary)",
              }}
            >
              Existing company
            </button>
            <button
              onClick={() => {
                setIsNewCompany(true);
                setActiveId("");
              }}
              style={{
                padding: "5px 14px",
                border: "none",
                cursor: "pointer",
                fontWeight: isNewCompany ? 600 : 400,
                background: isNewCompany
                  ? "var(--accent)"
                  : "var(--bg-surface)",
                color: isNewCompany ? "#fff" : "var(--text-secondary)",
              }}
            >
              New investment
            </button>
          </div>
        </div>

        {!isNewCompany ? (
          <>
            <div
              style={{
                display: "flex",
                gap: 12,
                alignItems: "center",
                flexWrap: "wrap",
              }}
            >
              <select
                className="input"
                style={{
                  maxWidth: 340,
                  fontWeight: activeId ? 600 : undefined,
                }}
                value={activeId}
                onChange={(e) => setActiveId(e.target.value)}
              >
                <option value="">— Choose a company —</option>
                {companies.map((c) => (
                  <option key={c.company_id} value={c.company_id}>
                    {c.company_name}
                  </option>
                ))}
              </select>
              {activeId && (
                <span
                  className="mono"
                  style={{ fontSize: 12, color: "var(--text-muted)" }}
                >
                  ID: {activeId}
                </span>
              )}
            </div>

            {/* VCP lock status for selected company */}
            {activeCompany && (
              <div style={{ marginTop: 14 }}>
                {hasExistingVcp ? (
                  <div
                    style={{
                      display: "flex",
                      alignItems: "flex-start",
                      gap: 12,
                      padding: "12px 14px",
                      borderRadius: 8,
                      background: "var(--amber-bg)",
                    }}
                  >
                    <span style={{ fontSize: 18, marginTop: 1 }}>⚠</span>
                    <div>
                      <div
                        style={{
                          fontWeight: 600,
                          fontSize: 13,
                          color: "var(--amber-text)",
                          marginBottom: 3,
                        }}
                      >
                        VCP already locked — {confirmed!.milestone_count}{" "}
                        milestone(s) · version {confirmed!.version}
                      </div>
                      <div
                        style={{
                          fontSize: 12.5,
                          color: "var(--text-secondary)",
                        }}
                      >
                        Uploading a new document will propose a{" "}
                        <strong>new version</strong>. You'll review and confirm
                        before it replaces the current VCP.
                      </div>
                      <div
                        style={{
                          display: "flex",
                          gap: 6,
                          marginTop: 8,
                          flexWrap: "wrap",
                        }}
                      >
                        {confirmed!.milestones.map((m, i) => (
                          <span key={i} className="chip">
                            {metricLabel(m.metric)}
                          </span>
                        ))}
                      </div>
                    </div>
                  </div>
                ) : (
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: 10,
                      padding: "10px 14px",
                      borderRadius: 8,
                      background: "var(--bg-muted)",
                      border: "1px solid var(--border)",
                      fontSize: 13,
                      color: "var(--text-secondary)",
                    }}
                  >
                    <span style={{ fontSize: 16 }}>○</span>
                    No VCP established yet for{" "}
                    <strong
                      style={{ color: "var(--text-primary)", marginLeft: 4 }}
                    >
                      {activeCompany.company_name}
                    </strong>
                    <span style={{ marginLeft: 4 }}>
                      — upload an IC memo to begin.
                    </span>
                  </div>
                )}
              </div>
            )}
          </>
        ) : (
          /* New investment — company doesn't exist in portfolio yet */
          <div>
            <div style={{ marginBottom: 10 }}>
              <label
                style={{
                  fontSize: 12,
                  color: "var(--text-muted)",
                  display: "block",
                  marginBottom: 6,
                  textTransform: "uppercase",
                  letterSpacing: ".04em",
                }}
              >
                Company name
              </label>
              <input
                className="input"
                style={{
                  maxWidth: 360,
                  fontWeight: newCompanyName ? 600 : undefined,
                }}
                placeholder="e.g. Acme Holdings"
                value={newCompanyName}
                onChange={(e) => setNewCompanyName(e.target.value)}
              />
              {newCompanyName && (
                <div
                  className="mono"
                  style={{
                    fontSize: 12,
                    color: "var(--text-muted)",
                    marginTop: 6,
                  }}
                >
                  Company ID will be: <strong>{slugify(newCompanyName)}</strong>
                </div>
              )}
            </div>
            <div
              style={{
                display: "flex",
                alignItems: "flex-start",
                gap: 10,
                padding: "10px 14px",
                borderRadius: 8,
                background: "var(--bg-muted)",
                border: "1px solid var(--border)",
                fontSize: 12.5,
                color: "var(--text-secondary)",
              }}
            >
              <span style={{ marginTop: 1, flexShrink: 0 }}>💡</span>
              <span>
                You can leave the name blank and upload the IC memo — the agent
                will automatically detect the company name from the document.
                You can confirm or edit it before locking the VCP.
              </span>
            </div>
          </div>
        )}
      </div>

      {/* ── STEP 2: Upload ── */}
      <div
        className="card card-pad"
        style={{
          marginBottom: 20,
          opacity: !companyReady ? 0.45 : 1,
          pointerEvents: !companyReady ? "none" : undefined,
        }}
      >
        <div style={{ marginBottom: 14 }}>
          <StepBadge n={2} active={step >= 2} />
          <span style={{ fontWeight: 600, fontSize: 14, marginLeft: 10 }}>
            Upload IC Memo or Thesis Document
          </span>
        </div>

        <div
          className={`upload-zone${dragOver ? " drag-over" : ""}`}
          onDragOver={(e) => {
            e.preventDefault();
            setDragOver(true);
          }}
          onDragLeave={() => setDragOver(false)}
          onDrop={onDrop}
          onClick={() => !busy && fileInput.current?.click()}
          role="button"
          tabIndex={0}
          style={{
            textAlign: "center",
            cursor: busy ? "default" : "pointer",
            borderStyle: "dashed",
            borderWidth: 2,
            borderRadius: 8,
            padding: "32px 20px",
            borderColor: dragOver ? "var(--accent)" : "var(--border)",
            background: dragOver ? "var(--accent-subtle)" : "var(--bg-muted)",
            transition: "border-color .15s, background .15s",
          }}
        >
          <input
            ref={fileInput}
            type="file"
            accept={ACCEPT}
            style={{ display: "none" }}
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) runUpload(f);
              e.target.value = "";
            }}
          />
          {busy ? (
            <>
              <div style={{ fontSize: 28, marginBottom: 10 }}>⏳</div>
              <div
                style={{
                  fontSize: 14,
                  fontWeight: 600,
                  color: "var(--text-primary)",
                }}
              >
                Extracting from {uploadName}…
              </div>
              <div
                style={{
                  fontSize: 12.5,
                  color: "var(--text-secondary)",
                  marginTop: 4,
                }}
              >
                Parsing with Docling · reading milestones with GPT
              </div>
            </>
          ) : (
            <>
              <div style={{ fontSize: 28, marginBottom: 10, opacity: 0.5 }}>
                ⬆
              </div>
              <div
                style={{
                  fontSize: 14,
                  fontWeight: 600,
                  color: "var(--text-primary)",
                }}
              >
                Drag & drop an IC memo, or click to browse
              </div>
              <div
                style={{
                  fontSize: 12.5,
                  color: "var(--text-secondary)",
                  marginTop: 4,
                }}
              >
                PDF, DOCX, PPTX, HTML, Markdown · will be extracted for{" "}
                <strong>
                  {resolvedCompanyName ||
                    (isNewCompany ? "new company (name from document)" : "—")}
                </strong>
              </div>
              <div
                style={{
                  marginTop: 12,
                  display: "flex",
                  gap: 6,
                  justifyContent: "center",
                  flexWrap: "wrap",
                }}
              >
                {[".PDF", ".DOCX", ".PPTX", ".HTML", ".MD", ".TXT"].map(
                  (ext) => (
                    <span
                      key={ext}
                      className="mono"
                      style={{
                        fontSize: 11,
                        padding: "2px 8px",
                        borderRadius: 4,
                        background: "var(--bg-surface)",
                        border: "1px solid var(--border)",
                        color: "var(--text-muted)",
                      }}
                    >
                      {ext}
                    </span>
                  ),
                )}
              </div>
            </>
          )}
        </div>

        <div
          style={{
            marginTop: 12,
            display: "flex",
            alignItems: "center",
            gap: 12,
          }}
        >
          <div style={{ flex: 1, height: 1, background: "var(--border)" }} />
          <span style={{ fontSize: 12, color: "var(--text-muted)" }}>or</span>
          <div style={{ flex: 1, height: 1, background: "var(--border)" }} />
        </div>

        {!isNewCompany && (
          <div style={{ marginTop: 12, textAlign: "center" }}>
            <button
              className="btn"
              style={{ fontSize: 12.5 }}
              disabled={busy || !activeId}
              onClick={run}
            >
              {busy && uploadName === "sample memo"
                ? "Loading…"
                : "Use sample memo (demo)"}
            </button>
            <div
              style={{
                fontSize: 11.5,
                color: "var(--text-muted)",
                marginTop: 6,
              }}
            >
              Runs extraction on the pre-loaded demo IC memo for this company
            </div>
          </div>
        )}
      </div>

      {err && (
        <div
          className="card card-pad"
          style={{
            color: "var(--red-text)",
            marginBottom: 20,
            borderLeft: "3px solid var(--red)",
          }}
        >
          {err}
        </div>
      )}

      {/* ── STEP 3: Review & Confirm ── */}
      {result && (
        <div className="card card-pad" style={{ marginBottom: 20 }}>
          <div
            style={{
              marginBottom: 14,
              display: "flex",
              alignItems: "center",
              justifyContent: "space-between",
              flexWrap: "wrap",
              gap: 10,
            }}
          >
            <div>
              <StepBadge n={3} active />
              <span style={{ fontWeight: 600, fontSize: 14, marginLeft: 10 }}>
                Review Candidate Milestones
              </span>
            </div>
            <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <span
                className="mono"
                style={{ fontSize: 12, color: "var(--text-muted)" }}
              >
                {result.document_loader === "docling"
                  ? "Docling"
                  : result.document_loader}
                {" · "}
                {result.source_document}
                {result.model ? ` · ${result.model}` : ""}
              </span>
            </div>
          </div>

          {/* New investment: show detected company identity and allow editing */}
          {isNewCompany && result && (
            <div
              style={{
                padding: "12px 14px",
                borderRadius: 8,
                marginBottom: 16,
                background: "var(--bg-muted)",
                border: "1px solid var(--border)",
              }}
            >
              <div style={{ fontWeight: 600, fontSize: 13, marginBottom: 8 }}>
                Company identified from document
              </div>
              <div
                style={{
                  display: "flex",
                  gap: 12,
                  alignItems: "center",
                  flexWrap: "wrap",
                }}
              >
                <div>
                  <div
                    style={{
                      fontSize: 11,
                      textTransform: "uppercase",
                      letterSpacing: ".04em",
                      color: "var(--text-muted)",
                      marginBottom: 4,
                    }}
                  >
                    Company name
                  </div>
                  <input
                    className="input"
                    style={{ width: 260, fontWeight: 600 }}
                    value={newCompanyName || result.company_name}
                    onChange={(e) => setNewCompanyName(e.target.value)}
                    placeholder="Enter company name"
                  />
                </div>
                <div>
                  <div
                    style={{
                      fontSize: 11,
                      textTransform: "uppercase",
                      letterSpacing: ".04em",
                      color: "var(--text-muted)",
                      marginBottom: 4,
                    }}
                  >
                    Company ID
                  </div>
                  <span
                    className="mono"
                    style={{ fontSize: 13, color: "var(--text-secondary)" }}
                  >
                    {slugify(newCompanyName || result.company_name)}
                  </span>
                </div>
              </div>
              <div
                style={{
                  fontSize: 12,
                  color: "var(--text-muted)",
                  marginTop: 8,
                }}
              >
                Edit the name above if needed — this becomes the permanent
                company ID in the VCP store.
              </div>
            </div>
          )}

          {hasExistingVcp && (
            <div
              style={{
                padding: "10px 14px",
                borderRadius: 8,
                marginBottom: 16,
                background: "var(--amber-bg)",
                fontSize: 13,
                color: "var(--amber-text)",
              }}
            >
              <strong>Updating existing VCP</strong> — confirming will replace
              version {confirmed!.version} with {items.length} new milestone(s).
            </div>
          )}

          <SectionLabel>Candidate Milestones ({items.length})</SectionLabel>
          <div className="grid">
            {items.map((m, i) => (
              <EditableCandidate
                key={i}
                m={m}
                onPatch={(f, v) => patch(i, f, v)}
                onRemove={() => remove(i)}
              />
            ))}
          </div>

          <div
            style={{
              marginTop: 16,
              display: "flex",
              gap: 10,
              alignItems: "center",
              flexWrap: "wrap",
            }}
          >
            <button className="btn" onClick={addBlank}>
              + Add milestone
            </button>
            <button
              className="btn primary"
              disabled={confirming || !items.length}
              onClick={confirm}
            >
              {confirming
                ? "Locking…"
                : `Confirm & lock VCP (${items.length} milestone${items.length !== 1 ? "s" : ""})`}
            </button>
            <button
              className="btn"
              style={{ marginLeft: "auto" }}
              onClick={() => {
                setResult(null);
                setItems([]);
              }}
            >
              Start over
            </button>
          </div>
          <p
            style={{
              marginTop: 10,
              fontSize: 12.5,
              color: "var(--text-muted)",
            }}
          >
            Milestones are unconfirmed until you lock them. Locking writes to
            the VCPStore as audit-logged ground truth.
          </p>
        </div>
      )}

      {/* VCP locked confirmation state (after confirming) */}
      {!result && confirmed?.confirmed && (
        <div
          className="card card-pad"
          style={{ borderLeft: "3px solid var(--green)", marginBottom: 20 }}
        >
          <div style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 8 }}>
            <Badge status="Green" label="VCP Locked" />
            <strong style={{ fontSize: 13 }}>
              {confirmed.milestone_count} milestone(s) · version {confirmed.version}
            </strong>
          </div>
          <div style={{ fontSize: 12.5, color: "var(--text-secondary)", marginBottom: 12 }}>
            This company's VCP is ground truth for all monitoring runs. Upload a new document above to propose a revision.
          </div>
          <div className="risk-chips" style={{ marginBottom: 16 }}>
            {confirmed.milestones.map((m, i) => (
              <span className="chip" key={i}>{metricLabel(m.metric)}</span>
            ))}
          </div>
          {onGoToIngest && (
            <div
              style={{
                borderTop: "1px solid var(--border)",
                paddingTop: 14,
                display: "flex",
                alignItems: "center",
                justifyContent: "space-between",
              }}
            >
              <div>
                <div style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)", marginBottom: 2 }}>
                  Next step: connect financial data
                </div>
                <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
                  Upload a management pack or Excel to start KPI monitoring against this VCP.
                </div>
              </div>
              <button className="btn primary" onClick={onGoToIngest} style={{ marginLeft: 16, flexShrink: 0 }}>
                Upload Financials →
              </button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/* ── Step progress bar ── */
function StepBar({ step, steps }: { step: number; steps: string[] }) {
  return (
    <div
      style={{
        display: "flex",
        alignItems: "center",
        gap: 0,
        marginBottom: 24,
      }}
    >
      {steps.map((label, i) => {
        const n = i + 1;
        const done = step > n;
        const active = step === n;
        return (
          <div
            key={n}
            style={{
              display: "flex",
              alignItems: "center",
              flex: i < steps.length - 1 ? 1 : undefined,
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
              <div
                style={{
                  width: 24,
                  height: 24,
                  borderRadius: "50%",
                  flexShrink: 0,
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  fontSize: 11,
                  fontWeight: 700,
                  background: done
                    ? "var(--green)"
                    : active
                      ? "var(--accent)"
                      : "var(--bg-muted)",
                  color: done || active ? "#fff" : "var(--text-muted)",
                  border: done || active ? "none" : "1px solid var(--border)",
                }}
              >
                {done ? "✓" : n}
              </div>
              <span
                style={{
                  fontSize: 12.5,
                  fontWeight: active ? 600 : 400,
                  color: active
                    ? "var(--text-primary)"
                    : done
                      ? "var(--text-secondary)"
                      : "var(--text-muted)",
                  whiteSpace: "nowrap",
                }}
              >
                {label}
              </span>
            </div>
            {i < steps.length - 1 && (
              <div
                style={{
                  flex: 1,
                  height: 1,
                  margin: "0 12px",
                  background: step > n ? "var(--green)" : "var(--border)",
                }}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}

function StepBadge({ n, active }: { n: number; active: boolean }) {
  return (
    <span
      style={{
        display: "inline-flex",
        alignItems: "center",
        justifyContent: "center",
        width: 22,
        height: 22,
        borderRadius: "50%",
        fontSize: 11,
        fontWeight: 700,
        background: active ? "var(--accent)" : "var(--bg-muted)",
        color: active ? "#fff" : "var(--text-muted)",
        verticalAlign: "middle",
      }}
    >
      {n}
    </span>
  );
}

function EditableCandidate({
  m,
  onPatch,
  onRemove,
}: {
  m: ExtractedMilestone;
  onPatch: (field: keyof ExtractedMilestone, value: unknown) => void;
  onRemove: () => void;
}) {
  const [showReasoning, setShowReasoning] = useState(false);
  const lowConf = m.confidence < 0.7;
  const note = m.metadata?.ambiguity_note;
  const confPct = Math.round(m.confidence * 100);

  return (
    <div
      className={`card card-pad alert-card ${lowConf ? "Amber" : "Green"}`}
      style={lowConf ? { borderLeft: "3px solid var(--amber)" } : undefined}
    >
      <div
        className="alert-meta"
        style={{ display: "flex", gap: 8, alignItems: "center" }}
      >
        <Badge
          status={lowConf ? "Amber" : "Green"}
          label={lowConf ? "Review" : "Confident"}
        />
        <input
          className="input"
          style={{ flex: 1, fontWeight: 600 }}
          value={m.initiative}
          placeholder="Initiative name"
          onChange={(e) => onPatch("initiative", e.target.value)}
        />
        <span
          style={{
            fontSize: 12,
            fontWeight: 600,
            padding: "2px 8px",
            borderRadius: 99,
            background: lowConf ? "var(--amber)" : "var(--green)",
            color: "#fff",
            whiteSpace: "nowrap",
          }}
        >
          {confPct}%
        </span>
        <button
          className="btn ghost-red"
          style={{ padding: "2px 9px" }}
          onClick={onRemove}
          title="Remove milestone"
        >
          ✕
        </button>
      </div>

      <div
        style={{
          display: "flex",
          gap: 14,
          flexWrap: "wrap",
          margin: "10px 0 4px",
          alignItems: "flex-end",
        }}
      >
        <Field label="Metric">
          <span className="mono" style={{ fontSize: 13 }}>
            {metricLabel(m.metric)}
          </span>
        </Field>
        <Field label="Target">
          <input
            className="input mono"
            style={{ width: 130 }}
            value={m.target_value ?? ""}
            placeholder="—"
            onChange={(e) =>
              onPatch(
                "target_value",
                e.target.value === "" ? null : Number(e.target.value),
              )
            }
          />
        </Field>
        <Field label="Target date">
          <input
            className="input mono"
            style={{ width: 130 }}
            type="date"
            value={(m.target_date ?? "").slice(0, 10)}
            onChange={(e) => onPatch("target_date", e.target.value || null)}
          />
        </Field>
        <Field label="Normalized">
          <span
            className="mono"
            style={{ fontSize: 12.5, color: "var(--text-muted)" }}
          >
            {metricValue(m.metric, m.target_value)} · {shortDate(m.target_date)}
          </span>
        </Field>
      </div>

      {m.source_text && (
        <div style={{ marginTop: 8 }}>
          <button
            className="btn"
            style={{ fontSize: 11.5, padding: "2px 8px" }}
            onClick={() => setShowReasoning((v) => !v)}
          >
            {showReasoning ? "Hide source ▴" : "Show source ▾"}
          </button>
          {showReasoning && (
            <blockquote
              className="citation"
              style={{
                fontStyle: "italic",
                borderLeft: "2px solid var(--border)",
                paddingLeft: 10,
                margin: "8px 0 0",
                fontSize: 12.5,
                color: "var(--text-secondary)",
              }}
            >
              "{m.source_text}"
            </blockquote>
          )}
        </div>
      )}
      {note && (
        <div
          style={{ fontSize: 12.5, color: "var(--amber-text)", marginTop: 8 }}
        >
          ⚠ {note}
        </div>
      )}
    </div>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div>
      <div
        style={{
          fontSize: 11,
          textTransform: "uppercase",
          letterSpacing: ".04em",
          color: "var(--text-muted)",
          marginBottom: 3,
        }}
      >
        {label}
      </div>
      {children}
    </div>
  );
}
