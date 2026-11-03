import { useEffect, useState } from "react";
import { api } from "../api";
import type { ExecutionDetail } from "../types";
import { Modal } from "../components/Drawer";
import { ErrorBanner } from "../components/Feedback";
import { Select } from "../components/Inputs";
import { CopyButton } from "../components/CopyButton";

/** JSON input editor that starts a workflow execution and reports its id. */
export function StartDialog({
  deploymentKey,
  workflows,
  initialWorkflow,
  open,
  onClose,
  onStarted,
}: {
  deploymentKey: string;
  workflows: string[];
  initialWorkflow?: string;
  open: boolean;
  onClose: () => void;
  onStarted: (execution: ExecutionDetail) => void;
}) {
  const [workflow, setWorkflow] = useState(initialWorkflow || workflows[0] || "");
  const [text, setText] = useState("{\n  \n}");
  const [parseError, setParseError] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [started, setStarted] = useState<ExecutionDetail | null>(null);

  useEffect(() => {
    if (open) {
      setWorkflow(initialWorkflow || workflows[0] || "");
      setError(null);
      setStarted(null);
    }
  }, [open, initialWorkflow, workflows]);

  useEffect(() => {
    if (!text.trim()) {
      setParseError(null);
      return;
    }
    try {
      JSON.parse(text);
      setParseError(null);
    } catch (err) {
      setParseError(err instanceof Error ? err.message : "invalid JSON");
    }
  }, [text]);

  const submit = async () => {
    if (parseError || !workflow) return;
    setBusy(true);
    setError(null);
    try {
      const input = text.trim() ? JSON.parse(text) : null;
      const result = await api.start(deploymentKey, workflow, input);
      setStarted(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  };

  const footer = started ? (
    <>
      <button type="button" className="btn" onClick={onClose}>
        Close
      </button>
      <button
        type="button"
        className="btn btn-primary"
        onClick={() => {
          onStarted(started);
          onClose();
        }}
      >
        View execution
      </button>
    </>
  ) : (
    <>
      <button type="button" className="btn" onClick={onClose}>
        Cancel
      </button>
      <button type="button" className="btn btn-primary" onClick={submit} disabled={busy || !!parseError || !workflow}>
        {busy ? "Starting…" : "Start execution"}
      </button>
    </>
  );

  return (
    <Modal open={open} title="Start workflow execution" onClose={onClose} footer={footer}>
      {started ? (
        <div className="stack">
          <p>
            Execution started with status <b>{started.status}</b>.
          </p>
          <div className="row-gap">
            <span className="muted">Execution id</span>
            <code className="mono">{started.execution_id}</code>
            <CopyButton value={started.execution_id} />
          </div>
        </div>
      ) : (
        <div className="stack">
          <label className="field">
            <span>Workflow</span>
            <Select label="Workflow" value={workflow} onChange={setWorkflow} options={workflows} />
          </label>
          <label className="field">
            <span>Input (JSON)</span>
            <textarea
              className={parseError ? "code-input invalid" : "code-input"}
              value={text}
              spellCheck={false}
              rows={10}
              onChange={(e) => setText(e.target.value)}
              aria-invalid={!!parseError}
            />
            {parseError && <small className="text-err">{parseError}</small>}
          </label>
          {error && <ErrorBanner message={error} />}
        </div>
      )}
    </Modal>
  );
}
