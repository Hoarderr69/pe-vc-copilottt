import type { Slide } from "../../lib/api";
import { Label, Stat, ActionStrip } from "./shared";
import { EditableSlideText } from "../EditableSlideText";

export interface ExecEditCtx {
  content: string;          // current (possibly edited) exec summary
  original: string;         // original AI text
  editedBy?: string | null;
  editedAt?: string | null;
  onSave: (text: string) => Promise<void>;
  onRestore: () => Promise<void>;
}

export function SlideExecutiveSummary({ slide, edit }: { slide: Slide; edit?: ExecEditCtx }) {
  const d = slide.data;
  const footer = d.footer || {};

  return (
    <div style={{ display: "grid", gridTemplateColumns: "60fr 40fr", gap: 24, height: "100%" }}>
      {/* LEFT 60% */}
      <div style={{ display: "flex", flexDirection: "column", minHeight: 0 }}>
        <Label>Situation</Label>
        {edit ? (
          <EditableSlideText
            content={edit.content}
            originalContent={edit.original}
            editedBy={edit.editedBy}
            editedAt={edit.editedAt}
            onEdit={edit.onSave}
            onRestore={edit.onRestore}
          />
        ) : (
          <p style={{ margin: 0, fontSize: 13, lineHeight: 1.6, color: "var(--text-primary)",
                       whiteSpace: "pre-wrap" }}>{d.situation || "—"}</p>
        )}

        {(d.key_risks || []).length > 0 && (
          <div style={{ marginTop: 16 }}>
            <Label>Key Risks</Label>
            {d.key_risks.map((r: string, i: number) => (
              <div key={i} style={{ display: "flex", gap: 10, marginBottom: 6, fontSize: 12.5 }}>
                <span style={{ fontWeight: 700, color: "var(--text-muted)", fontFamily: "var(--font-mono)" }}>
                  {i + 1}
                </span>
                <span style={{ color: "var(--text-primary)" }}>{r}</span>
              </div>
            ))}
          </div>
        )}

        {d.priority_action && (
          <div style={{ marginTop: "auto", paddingTop: 14 }}>
            <ActionStrip label="Priority Action This Quarter">{d.priority_action}</ActionStrip>
          </div>
        )}

        <div style={{ marginTop: 12, fontSize: 10, color: "var(--text-muted)" }}>
          ● {footer.ai_label || "AI Generated"} · {footer.mode}
          {footer.approved_by ? ` · Approved by ${footer.approved_by}` : ""}
        </div>
      </div>

      {/* RIGHT 40% — three stacked stat callouts */}
      <div style={{ display: "flex", flexDirection: "column", gap: 12, justifyContent: "center" }}>
        {(d.stats || []).map((s: any, i: number) => (
          <Stat key={i} label={s.label} value={s.value} sub={s.sub} negative={s.negative} />
        ))}
      </div>
    </div>
  );
}
