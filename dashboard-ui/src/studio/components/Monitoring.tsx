import { useEffect, useRef, useState } from "react";
import { api, errorMessage } from "../api";
import { useStudio } from "../store";
import { asObject } from "../util";
import type { OnPremAlert, OnPremAlertRecord, OnPremMonitorSample, ServerMetrics } from "../types";
import { EnumSelect, FormRow, NumberInput, TextInput, Toggle } from "./Forms";

const HISTORY = 40;

/** Poll `fetch` every `ms` while `on`; one request at a time, newest result wins. */
function useLive<T>(on: boolean, fetch: () => Promise<T>, ms: number): { data: T | null; error: string | null; history: T[] } {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [history, setHistory] = useState<T[]>([]);
  const fetchRef = useRef(fetch);
  fetchRef.current = fetch;
  useEffect(() => {
    if (!on) return undefined;
    let live = true;
    let timer: number | undefined;
    const tick = () => {
      fetchRef
        .current()
        .then((d) => {
          if (!live) return;
          setData(d);
          setError(null);
          setHistory((h) => [...h, d].slice(-HISTORY));
        })
        .catch((exc: unknown) => live && setError(errorMessage(exc)))
        .finally(() => {
          if (live) timer = window.setTimeout(tick, ms);
        });
    };
    tick();
    return () => {
      live = false;
      window.clearTimeout(timer);
    };
  }, [on, ms]);
  useEffect(() => {
    if (!on) setHistory([]);
  }, [on]);
  return { data, error, history };
}

function level(value: number, warn = 70, err = 90): string {
  return value >= err ? "var(--err)" : value >= warn ? "var(--warn)" : "var(--ok)";
}

/** A labelled percent meter: green, amber from 70 %, red from 90 % (or the alert limit). */
export function UsageBar({ label, value, detail, limit }: { label: string; value: number | null | undefined; detail?: string; limit?: number }) {
  const v = typeof value === "number" ? Math.max(0, Math.min(100, value)) : null;
  return (
    <div className={`usage-bar${label ? "" : " no-label"}`} title={limit ? `alert at ${limit}%` : undefined}>
      {label && <span className="usage-label small">{label}</span>}
      <span className="usage-track" aria-label={`${label} ${v === null ? "unknown" : `${v}%`}`}>
        {v !== null && <span className="usage-fill" style={{ width: `${v}%`, background: level(v, limit ? limit * 0.8 : 70, limit || 90) }} />}
        {limit && <span className="usage-limit" style={{ left: `${limit}%` }} />}
      </span>
      <span className="usage-value mono small">{v === null ? "—" : `${v.toFixed(v < 10 ? 1 : 0)}%`}</span>
      {detail && <span className="muted small usage-detail">{detail}</span>}
    </div>
  );
}

/** A tiny line of the last values (0-100 by default). */
export function Sparkline({ values, max = 100, color = "var(--accent)", width = 120, height = 26 }: { values: (number | null | undefined)[]; max?: number; color?: string; width?: number; height?: number }) {
  const nums = values.map((v) => (typeof v === "number" ? v : 0));
  if (nums.length < 2) return <svg width={width} height={height} aria-hidden="true" />;
  const top = Math.max(max, ...nums) || 1;
  const step = width / (HISTORY - 1);
  const start = width - step * (nums.length - 1);
  const points = nums.map((v, i) => `${(start + i * step).toFixed(1)},${(height - 2 - (v / top) * (height - 4)).toFixed(1)}`).join(" ");
  return (
    <svg width={width} height={height} className="sparkline" aria-hidden="true">
      <polyline points={points} fill="none" stroke={color} strokeWidth={1.6} strokeLinejoin="round" />
    </svg>
  );
}

/** Live CPU / memory / disk of a saved server, while shown. */
export function ServerLive({ name }: { name: string }) {
  const { data, error, history } = useLive<ServerMetrics>(true, () => api.onpremServerMetrics(name), 4000);
  if (error) return <div className="form-error small">{error}</div>;
  if (!data) return <div className="muted small">Measuring {name}…</div>;
  if (!data.reachable) return <div className="form-error small">{data.error || "not reachable"}</div>;
  return (
    <div className="server-live">
      <div className="row-gap">
        <UsageBar label="CPU" value={data.cpu} detail={data.cpus ? `${data.cpus} cores · load ${data.load || ""}` : undefined} />
        <Sparkline values={history.map((h) => h.cpu)} />
      </div>
      <div className="row-gap">
        <UsageBar label="RAM" value={data.memory} detail={data.memory_mb ? `${Math.round(data.memory_mb / 1024)} GB` : undefined} />
        <Sparkline values={history.map((h) => h.memory)} color="var(--info)" />
      </div>
      <div className="row-gap">
        <UsageBar label="Disk" value={data.disk} detail={data.disk_gb ? `of ${data.disk_gb} GB (/)` : undefined} />
      </div>
    </div>
  );
}

const LIVE_KEY = "pskit.studio.live-monitor.";

/** A service's containers, connections, data size and replica lag, polled only while the switch is on. */
export function ServiceMonitor({ serviceKey, alert }: { serviceKey: string; alert?: OnPremAlert | null }) {
  const [on, setOn] = useState(() => window.localStorage.getItem(LIVE_KEY + serviceKey) === "1");
  const { data, error, history } = useLive<OnPremMonitorSample>(on, () => api.onpremMonitor(serviceKey), 5000);
  const toggle = (v: boolean) => {
    setOn(v);
    window.localStorage.setItem(LIVE_KEY + serviceKey, v ? "1" : "0");
  };
  const limits = alert && alert.enabled ? alert : null;
  return (
    <div className="service-monitor stack-xs">
      <div className="row-between">
        <h4>Live monitoring</h4>
        <Toggle checked={on} onChange={toggle} label={on ? "On (every 5 s)" : "Off"} />
      </div>
      {!on && <p className="muted small">Switch it on to see CPU, memory and disk of every container, connections, data size and replica lag. Nothing is measured while it is off.</p>}
      {on && error && <div className="form-error">{error}</div>}
      {on && !data && !error && <p className="muted small">Measuring…</p>}
      {on && data && (
        <>
          <div className="row-gap wrap small">
            {data.database.connections !== undefined && (
              <span className="badge">
                {data.database.connections} connection{data.database.connections === 1 ? "" : "s"}
              </span>
            )}
            {data.database.size_mb !== undefined && <span className="badge">data {data.database.size_mb} MB</span>}
            {Object.entries(data.lag).map(([name, lag]) => (
              <span key={name} className={`badge ${lag === null || (limits && lag >= limits.lag_seconds) ? "badge-err" : "badge-ok"}`}>
                {name}: {lag === null ? "replication stopped" : `${lag} s behind`}
              </span>
            ))}
            <span className="muted">at {data.at.slice(11, 19)} UTC</span>
          </div>
          <div style={{ overflowX: "auto" }}>
            <table className="table">
              <thead>
                <tr>
                  <th>Container</th>
                  <th>State</th>
                  <th>CPU</th>
                  <th>Memory</th>
                  <th>Disk (data)</th>
                </tr>
              </thead>
              <tbody>
                {data.containers.map((c) => (
                  <tr key={c.name}>
                    <td>
                      <b className="mono">{c.name}</b>
                      <div className="muted small">
                        {c.role === "server" ? "database" : c.role === "balancer" ? "load balancer" : c.role}
                        {c.server ? ` · ${c.server}` : ""}
                      </div>
                    </td>
                    <td>
                      <span className={`badge ${c.state === "running" ? "badge-ok" : "badge-err"}`}>{c.state}</span>
                    </td>
                    <td>
                      <UsageBar label="" value={c.cpu} limit={limits?.cpu} />
                      <Sparkline values={history.map((h) => h.containers.find((x) => x.name === c.name)?.cpu)} />
                    </td>
                    <td>
                      <UsageBar label="" value={c.memory} detail={c.memory_usage} limit={limits?.memory} />
                    </td>
                    <td>{c.role === "balancer" ? <span className="muted small">—</span> : <UsageBar label="" value={c.disk} detail={c.disk_total_gb ? `of ${c.disk_total_gb} GB` : undefined} limit={limits?.disk} />}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}

export const NEW_FUNCTION = "__new__";

export interface AlertDraft {
  on: boolean;
  webhook: string;
  /** A function name, "" for none, or NEW_FUNCTION to create `<key>-alert`. */
  function: string;
  cpu?: number;
  memory?: number;
  disk?: number;
  lag_seconds?: number;
  cooldown_minutes?: number;
  down: boolean;
}

export const EMPTY_ALERT: AlertDraft = { on: false, webhook: "", function: "", down: true };

export function alertFunctionName(key: string): string {
  return `${key || "db"}-alert`;
}

export function alertHandler(key: string): string {
  return `alerts.${(key || "db").replace(/[^A-Za-z0-9_]/g, "_")}_alert.handler`;
}

/** The alert part of a request: where alerts go and the limits that trigger them. */
export function alertBody(draft: AlertDraft, key: string): Record<string, unknown> | null {
  if (!draft.on) return null;
  const body: Record<string, unknown> = { enabled: true, webhook: draft.webhook.trim(), down: draft.down };
  if (draft.function === NEW_FUNCTION) {
    body.function = alertFunctionName(key);
    body.function_handler = alertHandler(key);
  } else if (draft.function) body.function = draft.function;
  for (const k of ["cpu", "memory", "disk", "lag_seconds", "cooldown_minutes"] as const) if (draft[k]) body[k] = draft[k];
  return body;
}

export function alertError(draft: AlertDraft): string | null {
  if (!draft.on) return null;
  if (draft.webhook.trim() && !/^https?:\/\/\S+$/.test(draft.webhook.trim())) return "the webhook is an http(s) URL";
  if (!draft.webhook.trim() && !draft.function) return "pick a function, create one, or give a webhook URL";
  return null;
}

/** Alert settings: where they go (function / webhook) and when (limits). Used by the create form and Details. */
export function AlertFields({
  value,
  onChange,
  functions,
  serviceKey,
  replicated,
  optionalSwitch = true,
}: {
  value: AlertDraft;
  onChange: (v: AlertDraft) => void;
  functions: string[];
  serviceKey: string;
  replicated: boolean;
  optionalSwitch?: boolean;
}) {
  const set = (patch: Partial<AlertDraft>) => onChange({ ...value, ...patch });
  const newName = alertFunctionName(serviceKey);
  return (
    <div className="stack-xs">
      {optionalSwitch && <Toggle checked={value.on} onChange={(on) => set({ on })} label="Alert me (optional): CPU, memory, disk, replica lag, a container down" />}
      {value.on && (
        <>
          <FormRow
            label="Run a function"
            help={
              value.function === NEW_FUNCTION
                ? `Adds ${newName} to pskit.yml with a handler stub in ${alertHandler(serviceKey).split(".").slice(0, -1).join("/")}.py. It gets event.data = {kind, key, service, reasons, message, sample}. Deploy the project to run it.`
                : "Called through the deployed host with the alert as event.data (send mail, scale, page someone)."
            }
          >
            <EnumSelect
              value={value.function}
              onChange={(f) => set({ function: f })}
              options={[
                { value: "", label: "No function" },
                ...(functions.includes(newName) ? [] : [{ value: NEW_FUNCTION, label: `+ Create a new function: ${newName}` }]),
                ...functions.map((f) => ({ value: f, label: f })),
              ]}
            />
          </FormRow>
          <FormRow label="Webhook" help="Slack / Teams / Google Chat incoming webhook, or any URL: gets the alert as JSON (text = the message).">
            <TextInput mono value={value.webhook} placeholder="https://hooks.slack.com/services/…" onChange={(webhook) => set({ webhook })} />
          </FormRow>
          <div className="row-gap wrap">
            <FormRow label="CPU %">
              <NumberInput integer min={1} max={100} value={value.cpu} placeholder="90" onChange={(cpu) => set({ cpu })} />
            </FormRow>
            <FormRow label="Memory %">
              <NumberInput integer min={1} max={100} value={value.memory} placeholder="90" onChange={(memory) => set({ memory })} />
            </FormRow>
            <FormRow label="Disk %">
              <NumberInput integer min={1} max={100} value={value.disk} placeholder="85" onChange={(disk) => set({ disk })} />
            </FormRow>
            {replicated && (
              <FormRow label="Replica lag (s)">
                <NumberInput integer min={1} value={value.lag_seconds} placeholder="60" onChange={(lag_seconds) => set({ lag_seconds })} />
              </FormRow>
            )}
            <FormRow label="Cooldown (min)">
              <NumberInput integer min={1} value={value.cooldown_minutes} placeholder="30" onChange={(cooldown_minutes) => set({ cooldown_minutes })} />
            </FormRow>
          </div>
          <Toggle checked={value.down} onChange={(down) => set({ down })} label="Also when a container is down" />
          <p className="muted small">
            The studio checks every minute while it runs; from a server or cron use <code className="mono">pskit resources onprem alerts {serviceKey || "KEY"} --check</code>.
          </p>
        </>
      )}
    </div>
  );
}

function draftOf(a: OnPremAlert): AlertDraft {
  return { on: a.enabled, webhook: a.webhook, function: a.function, cpu: a.cpu, memory: a.memory, disk: a.disk, lag_seconds: a.lag_seconds, cooldown_minutes: a.cooldown_minutes, down: a.down };
}

/** Details: edit a service's alerts, send a test, check now, see the history. */
export function AlertsPanel({ serviceKey, functions, replicated, onLoaded }: { serviceKey: string; functions: string[]; replicated: boolean; onLoaded?: (a: OnPremAlert) => void }) {
  const [draft, setDraft] = useState<AlertDraft>(EMPTY_ALERT);
  const [history, setHistory] = useState<OnPremAlertRecord[]>([]);
  const [last, setLast] = useState<{ checked_at: string; reasons?: string[]; error?: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const { draft: project, replace } = useStudio();
  useEffect(() => {
    api
      .onpremAlert(serviceKey)
      .then((r) => {
        setDraft(draftOf(r.alert));
        setHistory(r.history);
        setLast(r.last || null);
        onLoaded?.(r.alert);
      })
      .catch((exc: unknown) => setError(errorMessage(exc)));
  }, [serviceKey]); // eslint-disable-line react-hooks/exhaustive-deps
  const run = async (what: "save" | "off" | "test" | "check") => {
    setBusy(true);
    setError(null);
    setNote(null);
    try {
      if (what === "save" || what === "off") {
        const body = alertBody({ ...draft, on: true }, serviceKey) || {};
        if (draft.function === NEW_FUNCTION) {
          const name = alertFunctionName(serviceKey);
          const res = await api.onpremAlertFunction(alertHandler(serviceKey));
          replace({ ...project, functions: { ...asObject(project.functions), [name]: { handler: alertHandler(serviceKey), description: `Alerts of ${serviceKey}` } } });
          setNote(`Added the function ${name} to pskit.yml (not saved yet), handler in ${res.path}. Save and deploy to run it.`);
        }
        const r = await api.onpremAlertSave(serviceKey, { ...body, enabled: what === "save" } as Partial<OnPremAlert>);
        setDraft(draftOf(r.alert));
        onLoaded?.(r.alert);
        if (what === "off") setNote("Alerts are off (settings kept).");
      } else if (what === "test") {
        const r = await api.onpremAlertTest(serviceKey);
        setHistory((h) => [...h, r]);
        setNote(r.sent.length ? `Test alert sent to ${r.sent.join(", ")}` : `Not sent: ${r.errors.join("; ")}`);
      } else {
        const r = await api.onpremAlertCheck(serviceKey);
        setLast({ checked_at: r.checked_at, reasons: r.reasons });
        setNote(r.reasons.length ? `Over a limit: ${r.reasons.join("; ")}${r.alert ? "" : " (alerts are off)"}` : "Everything is within the limits.");
        api.onpremAlert(serviceKey).then((x) => setHistory(x.history), () => undefined);
      }
    } catch (exc) {
      setError(errorMessage(exc));
    } finally {
      setBusy(false);
    }
  };
  const err = alertError({ ...draft, on: true });
  return (
    <div className="alerts-panel stack-xs">
      <div className="row-between">
        <h4>Alerts {draft.on ? <span className="badge badge-ok">on</span> : <span className="badge">off</span>}</h4>
        {last && <span className="muted small">last check {last.checked_at.slice(11, 19)} UTC{last.reasons?.length ? ` · ${last.reasons.length} over the limit` : last.error ? ` · ${last.error}` : " · ok"}</span>}
      </div>
      <AlertFields value={{ ...draft, on: true }} onChange={(v) => setDraft({ ...v, on: draft.on })} functions={functions} serviceKey={serviceKey} replicated={replicated} optionalSwitch={false} />
      <div className="row-gap wrap">
        <button type="button" className="btn btn-sm btn-primary" disabled={busy || !!err} onClick={() => void run("save")}>
          {draft.on ? "Save" : "Turn alerts on"}
        </button>
        {draft.on && (
          <button type="button" className="btn btn-sm" disabled={busy} onClick={() => void run("off")}>
            Turn off
          </button>
        )}
        <button type="button" className="btn btn-sm" disabled={busy || !draft.on} onClick={() => void run("test")}>
          Send a test alert
        </button>
        <button type="button" className="btn btn-sm" disabled={busy} onClick={() => void run("check")}>
          Check now
        </button>
      </div>
      {err && <div className="form-error small">{err}</div>}
      {note && <div className="hint-box small">{note}</div>}
      {error && <div className="form-error">{error}</div>}
      {history.length > 0 && (
        <ul className="small alert-history">
          {history
            .slice()
            .reverse()
            .slice(0, 8)
            .map((h, i) => (
              <li key={`${h.at}-${i}`}>
                <span className="mono">{h.at.slice(0, 19).replace("T", " ")}</span> {h.test ? "(test) " : ""}
                {h.message} → {h.sent.length ? h.sent.join(", ") : <span className="form-error">{h.errors.join("; ")}</span>}
              </li>
            ))}
        </ul>
      )}
    </div>
  );
}
