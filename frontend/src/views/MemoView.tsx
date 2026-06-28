import { useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { generateMemo } from "../lib/api";
import { Spinner } from "../components/ui";

interface Props {
  markdown: string;
  onGenerated: (markdown: string) => void;
}

export function MemoView({ markdown, onGenerated }: Props) {
  const [generating, setGenerating] = useState(false);
  const [error, setError] = useState("");

  async function handleGenerate() {
    setGenerating(true);
    setError("");
    try {
      const result = await generateMemo();
      onGenerated(result.markdown);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Generation failed");
    } finally {
      setGenerating(false);
    }
  }

  return (
    <div>
      <div className="page-head">
        <h1 className="page-title">Portfolio Memo</h1>
        <p className="page-sub">Board-ready decision artifact generated from the monitoring state.</p>
      </div>

      {generating && <Spinner label="Generating portfolio memo…" />}

      {!generating && error && (
        <div style={{ color: "var(--red-text)", fontSize: 13, marginBottom: 16, padding: "10px 14px",
                       background: "var(--red-bg)", borderRadius: 6 }}>
          {error}
        </div>
      )}

      {!generating && !markdown ? (
        <div className="center-state">
          <div style={{ textAlign: "center" }}>
            <span className="material-symbols-outlined" style={{ fontSize: 40, opacity: 0.3, display: "block", marginBottom: 12 }}>article</span>
            <div style={{ fontSize: 14, fontWeight: 600, marginBottom: 6 }}>No memo generated yet</div>
            <div style={{ fontSize: 13, opacity: 0.6, marginBottom: 20 }}>Generate a board-ready memo from the live portfolio monitoring state.</div>
            <button className="btn primary" onClick={handleGenerate}>
              Generate Portfolio Memo
            </button>
          </div>
        </div>
      ) : !generating && (
        <>
          <div style={{ display: "flex", justifyContent: "flex-end", marginBottom: 12 }}>
            <button className="btn" onClick={handleGenerate}>
              Regenerate
            </button>
          </div>
          <div className="card card-pad">
            <div className="memo">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{markdown}</ReactMarkdown>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
