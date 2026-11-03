import { useCallback, useEffect, useState } from "react";
import { api, errorMessage } from "../api";
import { useJob } from "../jobs";
import { href } from "../route";
import { useStudio } from "../store";
import type { Json, ResourceCheck, ResourceTestGuide, ResourceTestItem } from "../types";
import { JobConsole } from "./Console";
import { useConfirm, useToast } from "./Feedback";
import { FormRow, JsonInput, Section, Segmented } from "./Forms";

function copy(text: string, toast: ReturnType<typeof useToast>) {
  navigator.clipboard.writeText(text).then(
    () => toast("Copied", "ok"),
    () => toast("Copy failed: select the text instead", "warn"),
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

/** Handler code to publish to / consume / connect to a resource, in Python and Node.js. */
function ResourceCode({ item, toast }: { item: ResourceTestItem; toast: ReturnType<typeof useToast> }) {
  const [lang, setLang] = useState<"python" | "node">("python");
  const code = item.code;
  if (!code) return null;
  const reqs = code.requirements[lang];
  const reqText = lang === "python" ? reqs.join(String.fromCharCode(10)) : `npm install ${reqs.join(" ")}`;
  const text = code[lang];
  return (
    <FormRow
      label="Use it in a handler"
      help={`${code.note} Paste into your handler module and reference the function in pskit.yml${
        ["queue", "storage", "topic"].includes(item.type) ? ` (the consumer needs a trigger: ${item.type}: {resource: ${item.key}})` : ""
      }.`}
    >
      <div className="stack-xs">
        <Segmented
          label="Language"
          value={lang}
          onChange={setLang}
          options={[
            { value: "python", label: "Python" },
            { value: "node", label: "Node.js" },
          ]}
        />
        {reqs.length > 0 && (
          <div className="cmd-row">
            <span className="muted small">{lang === "python" ? "requirements.txt:" : "install:"}</span>
            <code className="mono pre-inline">{reqText}</code>
            <button type="button" className="btn btn-sm" onClick={() => copy(reqText, toast)}>
              Copy
            </button>
          </div>
        )}
        <div className="code-block">
          <button type="button" className="btn btn-sm code-copy" onClick={() => copy(text, toast)}>
            Copy
          </button>
          <pre className="md-code">{text}</pre>
        </div>
      </div>
    </FormRow>
  );
}

/** Connection / reachability check, from the on-prem host or this machine. */
function CheckButton({ item, provider, stage }: { item: ResourceTestItem; provider: string; stage: string }) {
  const [result, setResult] = useState<ResourceCheck | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  if (!item.check) return null;
  const run = async () => {
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      setResult(await api.resourceCheck(provider, stage, item.key));
    } catch (exc) {
      setError(errorMessage(exc));
    } finally {
      setBusy(false);
    }
  };
  return (
    <FormRow label="Test connection" help={`Checked from ${item.check.where}. Terminal: ${item.check.command}`}>
      <div className="stack-xs">
        <div className="row-gap wrap">
          <button type="button" className="btn" disabled={busy || !item.check.supported} onClick={() => void run()}>
            {busy ? "Checking…" : "Test connection"}
          </button>
          {!item.check.supported && <span className="muted small">Deploy the on-prem host first, or use Send below.</span>}
        </div>
        {result && (
          <div className={result.ok ? "hint-box" : "form-error"}>
            <b>{result.ok ? "OK" : "Failed"}</b>: {result.detail} <span className="muted small">({result.ms} ms, from {result.checked_from})</span>
          </div>
        )}
        {error && <div className="form-error">{error}</div>}
      </div>
    </FormRow>
  );
}

/**
 * Test a resource: send a message to a queue, upload an object to a bucket, publish to a topic,
 * for managed (provider) and external resources; show how to read custom / database / cache ones.
 */
export function ResourceTester({ selected, onSelect }: { selected: string | null; onSelect: (key: string) => void }) {
  const { state, meta } = useStudio();
  const toast = useToast();
  const confirm = useConfirm();
  const target = state.target || { provider: "aws", stage: "dev" };
  const [guide, setGuide] = useState<ResourceTestGuide | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [payload, setPayload] = useState<Json | undefined>(undefined);
  const [tab, setTab] = useState<"studio" | "terminal" | "console">("studio");
  const [jobId, setJobId] = useState<string | null>(null);
  const job = useJob(jobId);
  const providerName = meta.providers.find((p) => p.name === target.provider)?.display_name || target.provider;

  const load = useCallback(() => {
    setError(null);
    api.resourceTestGuide(target.provider, target.stage).then(setGuide, (exc: unknown) => setError(errorMessage(exc)));
  }, [target.provider, target.stage]);
  useEffect(load, [load]);

  const items = guide?.resources || [];
  const item = items.find((r) => r.key === selected) || items[0];
  useEffect(() => {
    if (item) setPayload(item.sample ?? undefined);
  }, [item?.key]); // eslint-disable-line react-hooks/exhaustive-deps

  const sendIt = async () => {
    if (!item) return;
    const ok = await confirm({
      title: `${item.action} to ${item.name}?`,
      body: (
        <p>
          This is real: the {item.type === "storage" ? "object is uploaded to" : "message is delivered to"} {item.external ? "the external" : "the"}{" "}
          {item.type === "storage" ? "bucket" : item.type} <b>{item.name}</b> on {providerName}
          {item.functions.length ? `, and ${item.functions.join(", ")} will receive it if they have a trigger on it` : ""}.
        </p>
      ),
      confirmLabel: "Send",
    });
    if (ok !== "confirm") return;
    try {
      const r = await api.startJob("resource-send", target.provider, target.stage, { resource: item.key, data: payload === undefined ? undefined : payload });
      setJobId(r.job_id);
    } catch (exc) {
      toast(errorMessage(exc), "err");
    }
  };

  return (
    <Section title="Test a resource" hint={`${providerName} / ${target.stage}`} defaultOpen={!!selected}>
      {error && <div className="form-error block">{error}</div>}
      {!guide && !error && <p className="muted">Loading…</p>}
      {guide && !items.length && (
        <p className="muted">
          No resources in the saved pskit.yml. Add one above (and save) to test it. Triggers that create their own queue or bucket can be tested on
          the <a href={href("test")}>Test</a> page.
        </p>
      )}
      {item && (
        <div className="form">
          <FormRow label="Resource">
            <select className="select select-full" value={item.key} onChange={(e) => onSelect(e.target.value)}>
              {items.map((r) => (
                <option key={r.key} value={r.key}>
                  {r.key} · {r.type} {r.name}
                  {r.external ? " (external)" : " (managed)"}
                </option>
              ))}
            </select>
          </FormRow>
          <FormRow label="Used by" help="Functions bound to it (they get its PSKIT_RESOURCE_* variables).">
            <span className="chips">
              {item.functions.length ? item.functions.map((f) => <span key={f} className="chip">{f}</span>) : <span className="muted">no functions</span>}
            </span>
          </FormRow>
          <CheckButton key={`check-${item.key}`} item={item} provider={target.provider} stage={target.stage} />
          {item.sendable ? (
            <>
              <FormRow label={item.type === "storage" ? "Object" : "Message"} help={item.payload_help}>
                <JsonInput key={item.key} value={payload} onChange={setPayload} rows={6} />
              </FormRow>
              <div className="row-gap wrap">
                <button type="button" className="btn btn-primary" disabled={!item.remote.supported || job.status === "running"} title={item.remote.reason || undefined} onClick={() => void sendIt()}>
                  {item.action}
                </button>
                <button type="button" className="btn btn-sm" onClick={() => setPayload(item.sample ?? undefined)}>
                  Reset to sample
                </button>
                {!item.remote.supported && <span className="muted small">{item.remote.reason}</span>}
              </div>
              {jobId && <JobConsole job={job} />}
              <Segmented
                label="How to test"
                value={tab}
                onChange={setTab}
                options={[
                  { value: "studio", label: "In the studio" },
                  { value: "terminal", label: "Terminal" },
                  { value: "console", label: `${providerName} console`, disabled: !item.remote.console.length },
                ]}
              />
              {tab === "studio" && (
                <ol className="steps">
                  <li>Pick the resource above and edit the {item.type === "storage" ? "object (key and content)" : "message"}.</li>
                  <li>
                    Press <b>{item.action}</b>. {item.external ? "External resources work without deploying." : "Managed resources exist after Deploy."}
                  </li>
                  <li>
                    Watch the bound functions on the <a href={href("logs")}>Logs</a> page, or send through a function's trigger on the{" "}
                    <a href={href("test")}>Test</a> page.
                  </li>
                </ol>
              )}
              {tab === "terminal" && (
                <div className="stack">
                  {item.remote.pskit.length > 0 && (
                    <div>
                      <b>With pskit</b>
                      <Commands lines={item.remote.pskit} toast={toast} />
                    </div>
                  )}
                  {item.remote.cli.length > 0 && (
                    <div>
                      <b>With the {providerName} CLI</b>
                      <Commands lines={item.remote.cli} toast={toast} />
                    </div>
                  )}
                  <div>
                    <b>All resources</b>
                    <Commands lines={[`pskit resources send --list -p ${target.provider} -s ${target.stage}`, "pskit logs -f"]} toast={toast} />
                  </div>
                </div>
              )}
              {tab === "console" && (
                <ol className="steps">
                  {item.remote.console.map((s, i) => (
                    <li key={i}>{s}</li>
                  ))}
                </ol>
              )}
              <ResourceCode key={`code-${item.key}`} item={item} toast={toast} />
            </>
          ) : (
            <div className="stack">
              <p className="muted small">
                pskit doesn't send to {item.type} resources: test them from a handler (or your own client) with the connection values pskit passes to
                the bound functions.
              </p>
              <FormRow label="Environment variables">
                <Commands lines={item.env} toast={toast} />
              </FormRow>
              {item.code ? (
                <ResourceCode key={`code-${item.key}`} item={item} toast={toast} />
              ) : (
                <>
                  <FormRow label="Python handler">
                    <Commands lines={[item.snippets.python]} toast={toast} />
                  </FormRow>
                  <FormRow label="Node.js handler">
                    <Commands lines={[item.snippets.node]} toast={toast} />
                  </FormRow>
                </>
              )}
              <p className="muted small">
                Then call that function from the <a href={href("test")}>Test</a> page (Direct invoke) to check the connection.
              </p>
            </div>
          )}
        </div>
      )}
    </Section>
  );
}
