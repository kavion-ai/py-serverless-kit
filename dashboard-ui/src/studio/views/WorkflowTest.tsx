import { useEffect, useState } from "react";
import { ErrorBanner } from "../../components/Feedback";
import { JsonView } from "../../components/JsonView";
import { api, errorMessage, type WorkflowRun, type WorkflowStep, type WorkflowTestTarget } from "../api";
import { useConfirm, useToast } from "../components/Feedback";
import { FormRow, JsonInput, Segmented, Toggle } from "../components/Forms";
import { ServerSelect, useServerChoice } from "../components/ServerPicker";
import { useStudio } from "../store";
import type { Json } from "../types";

export type TraceMark = "done" | "running" | "failed" | "caught" | "cancelled";

const STEP_BADGE: Record<string, string> = {
  done: "badge-ok",
  running: "badge-info",
  retrying: "badge-info",
  caught: "badge-warn",
  cancelled: "badge-warn",
  failed: "badge-err",
};

function runBadge(status: string): string {
  if (status === "SUCCEEDED") return "badge-ok";
  if (status === "RUNNING") return "badge-info";
  if (status === "CANCELLED" || status === "ABORTED") return "badge-warn";
  return "badge-err";
}

function marksOf(steps: WorkflowStep[]): Record<string, TraceMark> {
  const marks: Record<string, TraceMark> = {};
  for (const step of steps) {
    if (step.status === "retrying") marks[step.state] = "running";
    else if (step.status === "done") marks[step.state] = "done";
    else marks[step.state] = step.status;
  }
  return marks;
}

/** Run one workflow and show each function, its output, and the state that ran next. */
export function WorkflowTestPanel({
  name,
  onTrace,
}: {
  name: string;
  onTrace?: (marks: Record<string, TraceMark>) => void;
}) {
  const { state, dirty, save, providerName } = useStudio();
  const confirm = useConfirm();
  const toast = useToast();
  const target = state.target || { provider: providerName, stage: "dev" };
  const onprem = target.provider === "onprem";
  const { servers, deployed, server, setServer } = useServerChoice(onprem, target.stage);
  const [options, setOptions] = useState<WorkflowTestTarget[]>([]);
  const [where, setWhere] = useState<"local" | "deployed">("local");
  const [input, setInput] = useState<Json | undefined>({});
  const [sleep, setSleep] = useState(false);
  const [run, setRun] = useState<WorkflowRun | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);

  useEffect(() => {
    let live = true;
    setRun(null);
    setError(null);
    setWhere("local");
    api.workflowTestOptions(name, target.provider, target.stage).then(
      (found) => {
        if (live) setOptions(found.targets);
      },
      (exc: unknown) => {
        if (live) setError(errorMessage(exc));
      },
    );
    return () => {
      live = false;
    };
  }, [name, target.provider, target.stage]);

  useEffect(() => {
    if (!run || run.status !== "RUNNING") return undefined;
    const timer = window.setInterval(() => {
      api.workflowTestGet(run.run_id).then(setRun, (exc: unknown) => setError(errorMessage(exc)));
    }, 800);
    return () => window.clearInterval(timer);
  }, [run]);

  useEffect(() => {
    if (!onTrace) return undefined;
    onTrace(run ? marksOf(run.steps) : {});
    return () => onTrace({});
  }, [run, onTrace]);

  const chosen = options.find((item) => item.id === where) || options[0];
  const busy = starting || run?.status === "RUNNING";

  const ensureSaved = async (): Promise<boolean> => {
    if (!dirty) return true;
    const answer = await confirm({
      title: "Save first?",
      body: "The test runs pskit.yml on disk, which doesn't have your latest changes.",
      confirmLabel: "Save and test",
      extra: [{ label: "Test without saving", value: "skip" }],
    });
    if (!answer) return false;
    if (answer === "confirm") return save();
    return true;
  };

  const start = async () => {
    if (!(await ensureSaved())) return;
    if (where === "deployed") {
      const answer = await confirm({
        title: `Run ${name} on ${chosen?.label || "the deployed stage"}?`,
        body: "This starts a real execution of the deployed workflow, with this machine's credentials.",
        confirmLabel: "Run",
      });
      if (answer !== "confirm") return;
    }
    setStarting(true);
    setError(null);
    try {
      setRun(
        await api.workflowTestStart({
          workflow: name,
          provider: target.provider,
          stage: target.stage,
          target: where,
          input,
          sleep: where === "local" ? sleep : undefined,
          server: where === "deployed" && onprem && server ? server : undefined,
        }),
      );
    } catch (exc) {
      setError(errorMessage(exc));
    } finally {
      setStarting(false);
    }
  };

  const cancel = async () => {
    if (!run) return;
    try {
      setRun(await api.workflowTestCancel(run.run_id));
    } catch (exc) {
      toast(errorMessage(exc), "err");
    }
  };

  return (
    <div className="wf-test">
      <p className="muted small">
        Runs <span className="mono">{name}</span> and follows it: which function ran, what it returned, and which state ran next.
      </p>
      {error && <ErrorBanner message={error} />}
      {options.length > 0 && (
        <FormRow label="Where">
          <Segmented
            label="Where to run"
            value={where}
            onChange={setWhere}
            options={options.map((item) => ({
              value: item.id,
              label: item.label,
              disabled: !item.available,
              title: item.available ? item.note : item.reason,
            }))}
          />
        </FormRow>
      )}
      {chosen && <p className="muted small">{chosen.available ? chosen.note : chosen.reason}</p>}
      {where === "deployed" && onprem && chosen?.available && (
        <FormRow label="Server">
          <ServerSelect value={server} onChange={setServer} servers={servers} deployed={deployed} />
        </FormRow>
      )}
      <FormRow label="Input (JSON)">
        <JsonInput value={input} onChange={setInput} rows={4} placeholder="{}" />
      </FormRow>
      {where === "local" && (
        <Toggle checked={sleep} onChange={setSleep} label="Honour wait states (otherwise they are skipped)" />
      )}
      <div className="row-gap">
        <button type="button" className="btn btn-primary" disabled={busy || !chosen?.available} onClick={() => void start()}>
          {busy ? "Running…" : "Test"}
        </button>
        {run?.status === "RUNNING" && (
          <button type="button" className="btn btn-danger btn-sm" onClick={() => void cancel()}>
            {run.cancel_requested ? "Cancelling…" : "Cancel"}
          </button>
        )}
        {chosen?.console && (
          <a className="btn btn-sm" href={chosen.console} target="_blank" rel="noreferrer">
            Open console
          </a>
        )}
      </div>
      {run && <RunTrace run={run} />}
    </div>
  );
}

function RunTrace({ run }: { run: WorkflowRun }) {
  return (
    <div className="wf-trace">
      <div className="row-gap">
        <span className={`badge ${runBadge(run.status)}`}>{run.status}</span>
        {run.current_state && run.status === "RUNNING" && <span className="mono small">at {run.current_state}</span>}
        {typeof run.duration_ms === "number" && <span className="muted small">{Math.round(run.duration_ms)} ms</span>}
        {run.execution_id && <span className="mono small muted">{run.execution_id}</span>}
      </div>
      {run.poll_error && <ErrorBanner message={run.poll_error} />}
      {(run.error || run.cause) && (
        <div className="error-banner" role="alert">
          <div>
            <b>{run.error || "Error"}</b>
            {run.cause && <div className="mono pre">{run.cause}</div>}
          </div>
        </div>
      )}
      {run.note && <p className="muted small">{run.note}</p>}
      {run.console && run.target === "deployed" && (
        <p className="small">
          <a href={run.console} target="_blank" rel="noreferrer">
            Open this execution in the console
          </a>
        </p>
      )}
      {!run.steps.length && run.status === "RUNNING" && <p className="muted small">Waiting for the first state…</p>}
      <ol className="wf-steps">
        {run.steps.map((step, index) => (
          <li key={`${step.state}-${index}`} className={`wf-step wf-step-${step.status}`}>
            <div className="wf-step-head">
              <b>{step.state}</b>
              <span className={`badge ${STEP_BADGE[step.status] || "badge-off"}`}>{step.status}</span>
              {step.type && <span className="muted small">{step.type}</span>}
              {step.function && (
                <span className="mono small">
                  function <b>{step.function}</b>
                </span>
              )}
              {step.attempt ? <span className="muted small">retry {step.attempt}</span> : null}
              {typeof step.duration_ms === "number" && <span className="muted small">{step.duration_ms} ms</span>}
            </div>
            {step.error && step.status !== "done" && <p className="small">{step.error}</p>}
            {step.status === "running" || step.status === "retrying" ? (
              <p className="muted small">Running…</p>
            ) : step.output_known ? (
              <div>
                <div className="muted small">Output{step.output_truncated ? " (cut short)" : ""}</div>
                <JsonView value={step.output} />
              </div>
            ) : (
              step.status !== "cancelled" && <p className="muted small">This engine did not record this step&apos;s output.</p>
            )}
            {step.next && (
              <p className="wf-next">
                Next → <b>{step.next}</b>
              </p>
            )}
            {step.end && !step.next && <p className="wf-next">Then the workflow ends.</p>}
          </li>
        ))}
      </ol>
      {run.status !== "RUNNING" && (
        <div>
          <div className="muted small">Final output</div>
          <JsonView value={run.output} empty={run.status === "SUCCEEDED" ? "—" : "No output"} />
        </div>
      )}
    </div>
  );
}
