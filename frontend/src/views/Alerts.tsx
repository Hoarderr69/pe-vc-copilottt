import { useState } from "react";
import type { HitlQueue, ReviewItem } from "../lib/api";
import { postDecision } from "../lib/api";
import { Badge, SectionLabel } from "../components/ui";
import { dateTime, metricLabel, statusClass } from "../lib/format";

const REVIEWER = "operating.partner@firm.com";

export function AlertsView({ data, onChanged }: { data: HitlQueue; onChanged: () => void }) {
  const items = data.queue_items ?? [];
  const pending = items.filter((i) => i.status === "pending_review");
  const reviewed = items.filter((i) => i.status !== "pending_review");

  return (
    <div>
      <div className="page-head">
        <h1 className="page-title">Alert Center</h1>
      </div>

      {items.length === 0 ? (
        <div className="center-state">
          <div style={{ textAlign: "center" }}>
            <span className="material-symbols-outlined" style={{ fontSize: 40, opacity: 0.3, display: "block", marginBottom: 12 }}>notifications_none</span>
            <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 6 }}>No alerts yet</div>
            <div style={{ fontSize: 13, opacity: 0.6 }}>Alerts appear here once companies are added and financials are ingested.</div>
          </div>
        </div>
      ) : (
        <>
          <SectionLabel>Needs Review ({pending.length})</SectionLabel>
          <div className="grid" style={{ marginBottom: 26 }}>
            {pending.length === 0 && <div className="card card-pad card-hint">Nothing pending — all alerts reviewed.</div>}
            {pending.map((item) => <AlertCard key={item.review_id} item={item} onChanged={onChanged} />)}
          </div>

          {reviewed.length > 0 && (
            <>
              <SectionLabel>Reviewed ({reviewed.length})</SectionLabel>
              <div className="grid">
                {reviewed.map((item) => <AlertCard key={item.review_id} item={item} onChanged={onChanged} />)}
              </div>
            </>
          )}
        </>
      )}
    </div>
  );
}

function AlertCard({ item, onChanged }: { item: ReviewItem; onChanged: () => void }) {
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState(false);
  const [editText, setEditText] = useState(item.recommended_action);
  const [err, setErr] = useState("");
  const pending = item.status === "pending_review";
  const sev = item.priority === "P1" ? "Red" : "Amber";

  async function decide(decision: "approve" | "edit" | "reject") {
    setBusy(true); setErr("");
    try {
      await postDecision({
        review_id: item.review_id, decision, reviewed_by: REVIEWER,
        reviewer_note: decision === "reject" ? "Rejected from queue" : undefined,
        edited_recommended_action: decision === "edit" ? editText : undefined,
      });
      onChanged();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Failed");
    } finally { setBusy(false); }
  }

  const citations = item.evidence
    .map((e) => `${metricLabel(e.metric)} · ${e.source_path?.split("/").pop() ?? "source"}`)
    .filter((v, i, a) => a.indexOf(v) === i);

  return (
    <div className={`card card-pad alert-card ${statusClass(sev)}`}>
      <div className="alert-meta">
        <Badge status={sev} label={item.priority} />
        <strong style={{ color: "var(--text-primary)", fontSize: 13 }}>{item.company_name}</strong>
        <span style={{ marginLeft: "auto" }} className="mono">{item.review_id}</span>
      </div>
      <p className="alert-headline">{item.headline}</p>
      <p className="alert-rec"><b>Lever:</b> {item.recommended_action}</p>
      <div className="risk-chips">
        {item.primary_risks.map((r) => <span className="chip" key={r}>{metricLabel(r)}</span>)}
      </div>

      {editing && <textarea className="input" rows={2} value={editText} onChange={(e) => setEditText(e.target.value)} />}
      {err && <div style={{ color: "var(--red-text)", fontSize: 12.5, marginTop: 8 }}>{err}</div>}

      {pending ? (
        <div className="btn-row">
          {!editing ? (
            <>
              <button className="btn primary" disabled={busy} onClick={() => decide("approve")}>Approve</button>
              <button className="btn" disabled={busy} onClick={() => setEditing(true)}>Edit</button>
              <button className="btn ghost-red" disabled={busy} onClick={() => decide("reject")}>Reject</button>
            </>
          ) : (
            <>
              <button className="btn primary" disabled={busy} onClick={() => decide("edit")}>Save & approve</button>
              <button className="btn" disabled={busy} onClick={() => { setEditing(false); setEditText(item.recommended_action); }}>Cancel</button>
            </>
          )}
        </div>
      ) : (
        <div className="decided">
          <Badge status={item.status.startsWith("approved") ? "Green" : "Red"}
            label={item.status === "approved" ? "Approved" : item.status === "approved_with_edit" ? "Approved (edited)" : "Rejected"} />
          <span>by {item.decision.reviewed_by} · {dateTime(item.decision.reviewed_at)}</span>
        </div>
      )}

      <div className="citation">Source: {citations.join("  ·  ")}</div>
    </div>
  );
}
