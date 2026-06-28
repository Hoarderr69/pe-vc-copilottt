import { useState } from "react";

interface Props {
  content: string;
  isAI: boolean;
  isEdited: boolean;
  sectionKey: string;
  onSave: (sectionKey: string, content: string) => Promise<void>;
}

export function EditableSection({ content, isAI, isEdited, sectionKey, onSave }: Props) {
  const [editing, setEditing] = useState(false);
  const [value, setValue] = useState(content);
  const [saving, setSaving] = useState(false);

  async function handleSave() {
    setSaving(true);
    try {
      await onSave(sectionKey, value);
      setEditing(false);
    } finally {
      setSaving(false);
    }
  }

  function handleCancel() {
    setValue(content);
    setEditing(false);
  }

  if (editing) {
    return (
      <div style={{ marginTop: 8 }}>
        <textarea
          value={value}
          onChange={e => setValue(e.target.value)}
          style={{
            width: "100%",
            minHeight: 120,
            fontFamily: "var(--font-sans)",
            fontSize: 13,
            lineHeight: 1.6,
            padding: "10px 12px",
            border: "1px solid var(--border-strong)",
            borderRadius: 6,
            resize: "vertical",
            outline: "none",
            color: "var(--text-primary)",
            background: "var(--bg-surface)",
            boxSizing: "border-box",
          }}
          autoFocus
        />
        <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
          <button
            className="btn primary"
            onClick={handleSave}
            disabled={saving}
          >
            {saving ? "Saving…" : "Save"}
          </button>
          <button className="btn" onClick={handleCancel}>Cancel</button>
        </div>
      </div>
    );
  }

  return (
    <div
      onClick={() => setEditing(true)}
      style={{
        cursor: "text",
        borderRadius: 6,
        padding: "8px 10px",
        margin: "-8px -10px",
        transition: "background 0.1s",
        position: "relative",
      }}
      className="editable-section-hover"
      title="Click to edit"
    >
      <p style={{ margin: 0, fontSize: 13, lineHeight: 1.65, color: "var(--text-primary)" }}>
        {content}
      </p>
      <span style={{
        fontSize: 11,
        color: "var(--text-muted)",
        display: "block",
        marginTop: 4,
        opacity: 0,
        transition: "opacity 0.15s",
      }} className="edit-hint">
        {isEdited ? "✎ Edited · click to revise · " : "✎ Click to edit · "}
        {isAI && !isEdited && <span style={{ color: "var(--text-muted)" }}>AI Generated</span>}
        {isEdited && <span style={{ color: "var(--text-muted)" }}>original AI text preserved</span>}
      </span>
    </div>
  );
}
