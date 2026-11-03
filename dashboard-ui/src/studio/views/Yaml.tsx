import { useState } from "react";
import { ErrorBanner, Spinner } from "../../components/Feedback";
import { api, errorMessage } from "../api";
import { CodeEditor } from "../components/CodeEditor";
import { useToast } from "../components/Feedback";
import { Segmented } from "../components/Forms";
import { DiffView, IssueList, PageHeader } from "../components/Misc";
import { useStudio } from "../store";
import type { Issue } from "../types";
import { toYaml } from "../util";

export function YamlView() {
  const { state, draft, replace } = useStudio();
  const toast = useToast();
  const [mode, setMode] = useState<"preview" | "diff" | "edit">("preview");
  const [text, setText] = useState<string | null>(null);
  const [issues, setIssues] = useState<Issue[]>([]);
  const [busy, setBusy] = useState(false);
  const generated = state.validation?.yaml || toYaml(draft) + "\n";
  const onDisk = state.project?.text ?? "";

  const startEdit = () => {
    setText(generated);
    setIssues([]);
    setMode("edit");
  };

  const apply = async () => {
    if (text === null) return;
    setBusy(true);
    try {
      const res = await api.parse(text);
      setIssues(res.issues || []);
      if (res.raw) {
        replace(res.raw);
        toast("Applied the YAML to the draft (not saved yet)", "ok");
        setMode("preview");
        setText(null);
      } else {
        toast("The YAML could not be parsed; see the problems below", "err");
      }
    } catch (exc) {
      toast(errorMessage(exc), "err");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="page page-wide">
      <PageHeader
        title="pskit.yml"
        subtitle="What Save writes. Comments in the original file are not preserved; a backup is kept in .pskit/studio/backups/."
        actions={
          <Segmented
            label="YAML mode"
            value={mode}
            onChange={(m) => (m === "edit" ? startEdit() : setMode(m))}
            options={[
              { value: "preview", label: "Preview" },
              { value: "diff", label: "Diff vs disk" },
              { value: "edit", label: "Edit raw YAML" },
            ]}
          />
        }
      />
      {state.validating && !state.validation?.yaml && <Spinner label="Rendering…" />}
      {mode === "preview" && (
        <div className="card">
          <CodeEditor value={generated} language="yaml" readOnly ariaLabel="Generated pskit.yml" minHeight={420} />
        </div>
      )}
      {mode === "diff" && (
        <div className="card card-pad">
          <DiffView before={onDisk} after={generated} />
        </div>
      )}
      {mode === "edit" && text !== null && (
        <div className="stack">
          <div className="hint-box">Edit the YAML directly, then apply it to the draft. Forms update to match.</div>
          <div className="card">
            <CodeEditor value={text} language="yaml" onChange={setText} onSave={() => void apply()} ariaLabel="Edit pskit.yml" minHeight={420} />
          </div>
          {issues.length > 0 && (
            <div className="card card-pad">
              <IssueList issues={issues} />
            </div>
          )}
          <div className="row-gap">
            <button type="button" className="btn btn-primary" disabled={busy} onClick={() => void apply()}>
              {busy ? "Parsing…" : "Apply to draft"}
            </button>
            <button type="button" className="btn" onClick={() => { setMode("preview"); setText(null); }}>
              Discard
            </button>
          </div>
        </div>
      )}
      {state.validationError && <ErrorBanner message={state.validationError} />}
    </div>
  );
}
