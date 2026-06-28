import type { Slide } from "../../lib/api";
import { Label, ragColor, AiBadge } from "./shared";

export function SlideRisksActions({ slide }: { slide: Slide }) {
  const d = slide.data;
  const rows: any[] = d.rows || [];
  const questions: string[] = d.board_questions || [];

  return (
    <div style={{ display: "flex", flexDirection: "column", height: "100%", gap: 16 }}>
      {/* Risk table — top 60% */}
      <div style={{ flex: "1 1 60%", minHeight: 0, overflow: "auto" }}>
        {d.has_risks ? (
          <>
            {rows.map((r, i) => (
              <div key={i} style={{
                display: "flex", gap: 14, padding: "10px 14px", marginBottom: 8,
                border: "1px solid var(--border)", borderLeft: `3px solid ${ragColor(r.status)}`,
                borderRadius: 6, background: "var(--bg-surface)",
              }}>
                <div style={{ fontFamily: "var(--font-mono)", fontWeight: 700, color: ragColor(r.status) }}>
                  {r.priority}
                </div>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 13, color: "var(--text-primary)", fontWeight: 500 }}>{r.risk}</div>
                  <div style={{ fontSize: 11.5, color: "var(--text-secondary)", marginTop: 3 }}>
                    {r.recommended_action}
                    {(r.owner || r.deadline) && (
                      <span style={{ color: "var(--text-muted)" }}>
                        {"  ·  Owner: "}{r.owner} · {r.deadline}
                      </span>
                    )}
                  </div>
                </div>
                <div style={{ textAlign: "right", flexShrink: 0 }}>
                  <div style={{ fontSize: 10, color: "var(--text-muted)" }}>{r.category}</div>
                  {r.irr_at_risk_bps != null && (
                    <div style={{ fontFamily: "var(--font-mono)", fontWeight: 700,
                                   color: r.irr_at_risk_bps < 0 ? "var(--red)" : "var(--green)" }}>
                      {r.irr_at_risk_bps > 0 ? "+" : ""}{r.irr_at_risk_bps}bps
                    </div>
                  )}
                </div>
              </div>
            ))}
            <div style={{ fontSize: 11, color: "var(--text-secondary)", marginTop: 4 }}>
              Total IRR at risk: <span style={{ fontFamily: "var(--font-mono)", fontWeight: 600 }}>
                {d.total_irr_at_risk_bps > 0 ? "+" : ""}{d.total_irr_at_risk_bps}bps
              </span>
              {d.all_recoverable && " · all recoverable (operational)"}
            </div>
          </>
        ) : (
          <div style={{ border: "1px solid var(--green)", borderRadius: 8, padding: "16px 20px",
                         background: "var(--green-bg)" }}>
            <div style={{ fontSize: 14, fontWeight: 600, color: "var(--green-text)", marginBottom: 6 }}>
              ✓ {d.no_risk_block?.headline}
            </div>
            <div style={{ fontSize: 12.5, color: "var(--text-secondary)" }}>{d.no_risk_block?.detail}</div>
            <div style={{ fontSize: 12.5, color: "var(--text-muted)", marginTop: 4 }}>
              {d.no_risk_block?.next_review}
            </div>
          </div>
        )}
      </div>

      {/* Board questions — bottom 40% */}
      <div style={{ borderTop: "1px solid var(--border)", paddingTop: 12 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 10, marginBottom: 8 }}>
          <Label style={{ margin: 0 }}>Board Meeting Questions</Label>
          <AiBadge />
        </div>
        {questions.map((q, i) => (
          <div key={i} style={{ display: "flex", gap: 10, marginBottom: 6, fontSize: 12.5 }}>
            <span style={{ fontFamily: "var(--font-mono)", fontWeight: 700, color: "var(--text-muted)" }}>
              {i + 1}
            </span>
            <span style={{ color: "var(--text-primary)" }}>{q}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
