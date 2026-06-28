import { useEffect, useState } from "react";

interface Props {
  content: string;
  isAI?: boolean;
  originalContent?: string;       // preserved AI text for "restore original"
  onEdit: (newText: string) => Promise<void> | void;
  onRestore?: () => Promise<void> | void;
  editedBy?: string | null;
  editedAt?: string | null;
  /** Inline styling for the rendered paragraph. */
  textStyle?: React.CSSProperties;
}

/**
 * Click-to-edit text wrapper for slide narrative. Shows an `● AI Generated`
 * badge that flips to `✎ Edited` once the operator has revised the text, with
 * a "Restore original" affordance. Matches the spec's EditableSlideText.
 */
export function EditableSlideText({
  content, isAI = true, originalContent, onEdit, onRestore,
  editedBy, editedAt, textStyle,
}: Props) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(content);
  const [saving, setSaving] = useState(false);

  useEffect(() => { setValue(content); }, [content]);

  const isEdited =
    originalContent !== undefined && content.trim() !== originalContent.trim();

  async function handleSave() {
    setSaving(true);
    try {
      await onEdit(value);
      setEditing(false);
    } finally {
      setSaving(false);
    }
  }

  async function handleRestore() {
    if (originalContent === undefined) return;
    setSaving(true);
    try {
      if (onRestore) await onRestore();
      else await onEdit(originalContent);
      setValue(originalContent);
    } finally {
      setSaving(false);
    }
  }

  if (editing) {
    return (
      <div>
        <textarea
          value={value}
          onChange={e => setValue(e.target.value)}
          autoFocus
          style={{
            width: "100%", minHeight: 110, boxSizing: "border-box",
            fontFamily: "var(--font-sans)", fontSize: 13, lineHeight: 1.6,
            padding: "10px 12px", borderRadius: 6,
            border: "1px solid var(--accent)", outline: "none", resize: "vertical",
            color: "var(--text-primary)", background: "var(--bg-surface)",
          }}
        />
        <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
          <button className="btn primary" onClick={handleSave} disabled={saving}>
            {saving ? "Saving…" : "Save"}
          </button>
          <button className="btn" onClick={() => { setValue(content); setEditing(false); }}>
            Cancel
          </button>
        </div>
      </div>
    );
  }

  return (
    <div>
      <div
        onClick={() => setEditing(true)}
        title="Click to edit"
        className="editable-section-hover"
        style={{
          cursor: "text", borderRadius: 6, padding: "6px 8px", margin: "-6px -8px",
        }}
      >
        <p style={{ margin: 0, fontSize: 13, lineHeight: 1.6, color: "var(--text-primary)",
                     whiteSpace: "pre-wrap", ...textStyle }}>
          {content || "—"}
        </p>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 10, marginTop: 6, fontSize: 10.5 }}>
        {isEdited ? (
          <>
            <span style={{ color: "var(--accent-text)", fontWeight: 600 }}>
              ✎ Edited{editedBy ? ` · ${editedBy}` : ""}
              {editedAt ? ` · ${new Date(editedAt).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}` : ""}
            </span>
            <button
              onClick={handleRestore}
              disabled={saving}
              style={{ background: "none", border: "none", padding: 0, cursor: "pointer",
                        fontSize: 10.5, color: "var(--text-link)", textDecoration: "underline" }}
            >
              Restore original
            </button>
          </>
        ) : isAI ? (
          <span style={{ display: "inline-flex", alignItems: "center", gap: 5, color: "var(--text-muted)" }}>
            <span style={{ width: 6, height: 6, borderRadius: "50%", background: "var(--accent)",
                            display: "inline-block" }} />
            AI Generated
          </span>
        ) : null}
      </div>
    </div>
  );
}
