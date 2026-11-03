import { useCallback, useEffect, useMemo, useState } from "react";
import { ErrorBanner, Spinner } from "../../components/Feedback";
import { api, errorMessage } from "../api";
import { JobConsole } from "../components/Console";
import { useConfirm, useToast } from "../components/Feedback";
import { FormRow, JsonInput, Section, Segmented, TextInput, Toggle } from "../components/Forms";
import { PageHeader } from "../components/Misc";
import { DeployedBadge, ServerSelect, useServerChoice } from "../components/ServerPicker";
import { useJob } from "../jobs";
import { href, navigate } from "../route";
import { useStudio } from "../store";
import type { Json, SavedTestEvent, TestGuide, TestTrigger } from "../types";
import { DeployedLogs } from "./Logs";

const ICON: Record<string, string> = { http: "⇄", schedule: "⏱", queue: "☰", storage: "▣", topic: "✺", smtp: "✉", invoke: "λ" };

function copy(text: string, toast: ReturnType<typeof useToast>) {
  navigator.clipboard.writeText(text).then(
    () => toast("Copied", "ok"),
    () => toast("Copy failed: select the text instead", "warn"),
  );
}

/** Test a function: pick a trigger, edit the event, run it locally or send it to the deployed stage. */
export function TestView({ rest }: { rest: string[] }) {
  const { state, dirty, save, meta } = useStudio();
  const toast = useToast();
  const confirm = useConfirm();
  const target = state.target || { provider: "aws", stage: "dev" };
  const [guide, setGuide] = useState<TestGuide | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<Record<string, SavedTestEvent[]>>({});
  const [index, setIndex] = useState<number | null>(null);
  const [payload, setPayload] = useState<Json | undefined>(undefined);
  const [path, setPath] = useState("");
  const [eventName, setEventName] = useState("");
  const [showLogs, setShowLogs] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const job = useJob(jobId);
  const onprem = target.provider === "onprem";
  const { servers, deployed, server, setServer } = useServerChoice(onprem, target.stage);

  const load = useCallback(() => {
    setError(null);
    api.testGuide(target.provider, target.stage).then(setGuide, (exc: unknown) => setError(errorMessage(exc)));
    api.testEvents().then(setSaved, () => undefined);
  }, [target.provider, target.stage]);
  useEffect(load, [load]);

  const functions = guide?.functions || [];
  const fnName = rest[0] && functions.some((f) => f.name === rest[0]) ? rest[0] : functions[0]?.name;
  const fn = functions.find((f) => f.name === fnName);
  const trigger: TestTrigger | undefined = fn?.triggers.find((t) => t.index === index) || fn?.triggers[0];

  // A new function or trigger: start from its sample event.
  useEffect(() => {
    if (!fn) return;
    const t = fn.triggers.find((x) => x.index === index) || fn.triggers[0];
    if (index === null || !fn.triggers.some((x) => x.index === index)) setIndex(t.index);
    setPayload(t.sample);
    setPath(t.type === "http" ? t.path || "/" : "");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [fnName, index, guide]);

  const savedHere = useMemo(() => (fnName ? saved[fnName] || [] : []), [saved, fnName]);
  const providerName = meta.providers.find((p) => p.name === target.provider)?.display_name || target.provider;

  const ensureSaved = async (): Promise<boolean> => {
    if (!dirty) return true;
    const answer = await confirm({
      title: "Save first?",
      body: "Tests run against pskit.yml on disk, which doesn't have your latest changes.",
      confirmLabel: "Save and run",
      extra: [{ label: "Run without saving", value: "skip" }],
    });
    if (!answer) return false;
    if (answer === "confirm") return save();
    return true;
  };

  const runLocal = async () => {
    if (!fn || !trigger || !(await ensureSaved())) return;
    const args: Record<string, unknown> = { function: fn.name, data: payload === undefined ? undefined : payload };
    if (trigger.index >= 0) args.type = trigger.type;
    if (trigger.type === "http") {
      args.method = trigger.method;
      args.path = path || trigger.path;
      if (trigger.method === "GET" || trigger.method === "HEAD") args.data = undefined;
    }
    if (trigger.type === "storage" && payload && typeof payload === "object" && !Array.isArray(payload)) {
      args.data = { key: (payload as Record<string, Json>).key || "test/hello.txt", bucket: trigger.name, action: (payload as Record<string, Json>).action || "created" };
    }
    try {
      setJobId((await api.startJob("invoke", target.provider, target.stage, args)).job_id);
    } catch (exc) {
      toast(errorMessage(exc), "err");
    }
  };

  const sendRemote = async () => {
    if (!fn || !trigger) return;
    const ok = await confirm({
      title: `Send to ${providerName} / ${target.stage}${onprem ? ` on ${server === "local" ? "this machine" : server || deployed?.label || "the deployed host"}` : ""}?`,
      body: (
        <p>
          This sends a <b>real</b> {trigger.type === "invoke" ? "invocation" : `${trigger.type} event`} ({trigger.summary}) to the deployed
          function, with this machine's credentials.
          {trigger.type === "storage" ? " The object is uploaded to the bucket." : ""}
          {trigger.type === "smtp" ? " The test mail goes to the host like one the SMTP server received, and runs every function attached to the server." : ""}
          {trigger.type === "queue" || trigger.type === "topic" ? " The message is delivered to every subscriber." : ""}
        </p>
      ),
      confirmLabel: "Send",
    });
    if (ok !== "confirm") return;
    const args: Record<string, unknown> = { function: fn.name, event: trigger.index, data: payload === undefined ? undefined : payload };
    if (trigger.type === "http" && path && path !== trigger.path) args.path = path;
    if (onprem && server) args.server = server;
    try {
      setJobId((await api.startJob("trigger", target.provider, target.stage, args)).job_id);
      setShowLogs(true);
    } catch (exc) {
      toast(errorMessage(exc), "err");
    }
  };

  const saveEvent = () => {
    if (!fnName || !trigger) return;
    const name = eventName.trim() || `${trigger.type} ${new Date().toLocaleString()}`;
    const item: SavedTestEvent = { name, event: trigger.index, payload: payload === undefined ? null : payload };
    if (trigger.type === "http" && path) item.path = path;
    const next = { ...saved, [fnName]: [...savedHere.filter((e) => e.name !== name), item] };
    api.saveTestEvents(next).then(
      (r) => {
        setSaved(r);
        setEventName("");
        toast(`Saved test event “${name}”`, "ok");
      },
      (exc: unknown) => toast(errorMessage(exc), "err"),
    );
  };
  const deleteEvent = (name: string) => {
    if (!fnName) return;
    const next = { ...saved, [fnName]: savedHere.filter((e) => e.name !== name) };
    api.saveTestEvents(next).then(setSaved, (exc: unknown) => toast(errorMessage(exc), "err"));
  };

  if (error) return <div className="page"><PageHeader title="Test" /><ErrorBanner message={error} onRetry={load} /></div>;
  if (!guide) return <div className="page"><Spinner label="Loading functions…" /></div>;

  return (
    <div className="page">
      <PageHeader
        title="Test functions"
        subtitle={
          <>
            Send an event to a function: <b>locally</b> (runs the handler on this machine, like <code className="mono">pskit invoke</code>) or to the
            deployed <b>{providerName}</b> / <b>{target.stage}</b> (a real queue message, upload, HTTP call…, like{" "}
            <code className="mono">pskit trigger</code>).
          </>
        }
        actions={
          <button type="button" className="btn" onClick={load}>
            Refresh
          </button>
        }
      />
      {!guide.deployed && (
        <div className="hint-box">
          {providerName}/{target.stage} isn't deployed from this folder yet, so only local tests are available.{" "}
          <a href={href("deploy")}>Deploy</a> to send real events.
        </div>
      )}
      {!functions.length ? (
        <p className="muted">No functions yet. <a href={href("functions", "new")}>Create one</a>.</p>
      ) : (
        <div className="test-layout">
          <nav className="test-fns card" aria-label="Functions">
            {functions.map((f) => (
              <button key={f.name} type="button" className={`test-fn${f.name === fnName ? " active" : ""}`} onClick={() => { setIndex(null); navigate("test", f.name); }}>
                <b>{f.name}</b>
                <span className="muted small">{f.triggers.filter((t) => t.index >= 0).map((t) => t.type).join(", ") || "invoke only"}</span>
              </button>
            ))}
          </nav>
          {fn && trigger && (
            <div className="stack grow test-main">
              <Section title="1. Choose the event" hint={fn.description || undefined}>
                <div className="trigger-grid">
                  {fn.triggers.map((t) => (
                    <button key={t.index} type="button" className={`trigger-card${t.index === trigger.index ? " active" : ""}`} onClick={() => setIndex(t.index)}>
                      <span className="trigger-icon" aria-hidden="true">{ICON[t.type] || "λ"}</span>
                      <b>{t.index < 0 ? "Direct invoke" : t.type}</b>
                      <span className="muted small mono">{t.index < 0 ? "no trigger" : t.summary}</span>
                    </button>
                  ))}
                </div>
              </Section>
              <Section title="2. Edit the event" hint={trigger.payload_help}>
                <div className="form">
                  {trigger.type === "http" && (
                    <FormRow label="Request" help="Path with query string, e.g. /items/42?verbose=1. Path parameters ({id}) need real values.">
                      <div className="route-input">
                        <span className="badge badge-accent">{trigger.method}</span>
                        <TextInput mono value={path} onChange={setPath} placeholder={trigger.path} />
                      </div>
                    </FormRow>
                  )}
                  {!(trigger.type === "http" && (trigger.method === "GET" || trigger.method === "HEAD")) && (
                    <FormRow label="Payload (JSON)">
                      <JsonInput key={`${fnName}-${trigger.index}`} value={payload} onChange={setPayload} rows={8} />
                    </FormRow>
                  )}
                  <FormRow label="Saved events" help="Kept in .pskit/studio/test-events.json for this project.">
                    <div className="stack-xs">
                      <div className="chips">
                        <button type="button" className="chip chip-btn" onClick={() => { setPayload(trigger.sample); setPath(trigger.path || ""); }}>
                          sample
                        </button>
                        {savedHere.filter((e) => e.event === trigger.index).map((e) => (
                          <span key={e.name} className="chip">
                            <button type="button" className="chip-link" onClick={() => { setPayload(e.payload ?? undefined); if (e.path) setPath(e.path); }}>
                              {e.name}
                            </button>
                            <button type="button" className="chip-x" aria-label={`Delete ${e.name}`} onClick={() => deleteEvent(e.name)}>
                              ✕
                            </button>
                          </span>
                        ))}
                      </div>
                      <div className="row-gap">
                        <TextInput value={eventName} onChange={setEventName} placeholder="name, e.g. big order" />
                        <button type="button" className="btn btn-sm" onClick={saveEvent}>
                          Save event
                        </button>
                      </div>
                    </div>
                  </FormRow>
                </div>
              </Section>
              <Section title="3. Run it">
                {onprem && guide.deployed && (
                  <div className="row-gap wrap deploy-machine">
                    <b>Server</b>
                    <ServerSelect value={server} onChange={setServer} servers={servers} deployed={deployed} />
                    <DeployedBadge deployed={deployed} />
                  </div>
                )}
                <div className="row-gap wrap">
                  <button type="button" className="btn btn-primary" disabled={job.status === "running"} onClick={() => void runLocal()} title="Runs the handler on this machine with a synthetic event">
                    ▶ Run locally
                  </button>
                  <button
                    type="button"
                    className="btn btn-primary"
                    disabled={job.status === "running" || !trigger.remote.supported}
                    title={trigger.remote.supported ? `Send a real event to ${providerName}/${target.stage}` : trigger.remote.reason}
                    onClick={() => void sendRemote()}
                  >
                    ☁ Send to {providerName} / {target.stage}
                  </button>
                  {guide.deployed && <Toggle checked={showLogs} onChange={setShowLogs} label="Show the function's logs" />}
                </div>
                {!trigger.remote.supported && guide.deployed && <p className="muted small">Deployed: {trigger.remote.reason}</p>}
                {jobId && <JobConsole job={job} />}
                {showLogs && guide.deployed && <DeployedLogs provider={target.provider} stage={target.stage} functions={[fn.name]} only={fn.name} server={onprem ? server || undefined : undefined} />}
              </Section>
              <HowTo fnName={fn.name} trigger={trigger} provider={providerName} deployed={guide.deployed} toast={toast} />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function Commands({ lines, toast }: { lines: string[]; toast: ReturnType<typeof useToast> }) {
  return (
    <div className="stack-xs">
      {lines.map((c) => (
        <div key={c} className="cmd-row">
          <code className="mono pre-inline">{c}</code>
          <button type="button" className="btn btn-sm" onClick={() => copy(c, toast)}>
            Copy
          </button>
        </div>
      ))}
    </div>
  );
}

/** Step-by-step: in this studio, in a terminal (pskit and the cloud's CLI) and in the cloud console. */
function HowTo({ fnName, trigger, provider, deployed, toast }: { fnName: string; trigger: TestTrigger; provider: string; deployed: boolean; toast: ReturnType<typeof useToast> }) {
  const [tab, setTab] = useState<"studio" | "terminal" | "console">("studio");
  const r = trigger.remote;
  return (
    <Section title="How to test this" hint="studio, terminal or cloud console" defaultOpen={false}>
      <Segmented
        label="How"
        value={tab}
        onChange={setTab}
        options={[
          { value: "studio", label: "In the studio" },
          { value: "terminal", label: "Terminal" },
          { value: "console", label: `${provider} console`, disabled: !deployed || !r.console.length },
        ]}
      />
      {tab === "studio" && (
        <ol className="steps">
          <li>Pick the function on the left and the event ({trigger.index < 0 ? "Direct invoke" : trigger.summary}) in step 1.</li>
          <li>Edit the payload in step 2 ({trigger.payload_help}) or load a saved event; Save event keeps it for next time.</li>
          <li>
            <b>Run locally</b> to run the handler on this machine (no cloud needed; the result and logs appear below).
          </li>
          <li>
            <b>Send to {provider}</b> (after Deploy) to fire the real trigger. Turn on <i>Show the function's logs</i> to watch it run.
          </li>
        </ol>
      )}
      {tab === "terminal" && (
        <div className="stack">
          <div>
            <b>Locally</b> <span className="muted small">(runs the handler on this machine)</span>
            <Commands lines={trigger.local} toast={toast} />
          </div>
          {deployed && (
            <div>
              <b>Deployed, with pskit</b>
              {r.pskit.length ? <Commands lines={r.pskit} toast={toast} /> : <p className="muted small">{r.reason}</p>}
            </div>
          )}
          {deployed && r.cli.length > 0 && (
            <div>
              <b>Deployed, with the {provider} CLI</b>
              <Commands lines={r.cli} toast={toast} />
            </div>
          )}
          {deployed && (
            <div>
              <b>Watch the logs</b>
              <Commands lines={[`pskit logs -f --function ${fnName}`]} toast={toast} />
            </div>
          )}
          {!deployed && <p className="muted small">Deploy to get the commands for the real {trigger.type === "invoke" ? "function" : trigger.type}.</p>}
        </div>
      )}
      {tab === "console" && (
        <ol className="steps">
          {r.console.map((s, i) => (
            <li key={i}>{s}</li>
          ))}
        </ol>
      )}
    </Section>
  );
}
