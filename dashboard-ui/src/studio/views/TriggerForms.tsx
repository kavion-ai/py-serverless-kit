import { useEffect, useState } from "react";
import { SearchInput } from "../../components/Inputs";
import { api, errorMessage } from "../api";
import { ComboInput, EnumSelect, FieldForm, FormRow, JsonInput, ListEditor, NumberInput, Segmented, TextInput, Toggle } from "../components/Forms";
import { useStudio } from "../store";
import type { DiscoverItem, DiscoverResult, EventType, Field, Json, JsonObject, TriggerRule } from "../types";
import { asArray, asObject, describeCron, isObject, NAME_RE, pathParams, str, uniqueName, validCron, type NormalEvent } from "../util";

export const EVENT_INFO: Record<EventType, { label: string; icon: string; blurb: string }> = {
  http: { label: "HTTP endpoint", icon: "⇄", blurb: "Call the function with an HTTP request (API route)." },
  schedule: { label: "Schedule", icon: "⏱", blurb: "Run on a timer: every N minutes, at a set time, or a cron expression." },
  queue: { label: "Queue", icon: "☰", blurb: "Process messages from a queue in batches, with retries." },
  storage: { label: "Storage", icon: "▣", blurb: "React to files created or deleted in a bucket." },
  topic: { label: "Topic", icon: "✺", blurb: "Receive published messages (fan-out pub/sub)." },
  smtp: { label: "E-mail (SMTP)", icon: "✉", blurb: "Run when mail arrives for your domain: from, to, cc, subject, body and attachments (on premises)." },
};

export function defaultEvent(type: EventType, name: string): NormalEvent {
  switch (type) {
    case "http":
      return { type, config: { method: "GET", path: `/${name.replace(/_/g, "-")}` } };
    case "schedule":
      return { type, config: { rate: "5 minutes" } };
    case "queue":
      return { type, config: { name: `${name}-jobs`, batch_size: 10 } };
    case "storage":
      return { type, config: { bucket: `${name}-uploads`, events: ["created"] } };
    case "smtp":
      return { type, config: { resource: "" } };
    default:
      return { type, config: { name: `${name}-events` } };
  }
}

// --------------------------------------------------------------------- provider rules

/** Rules (from the provider's own validation) for one trigger type on the draft's provider. */
export function useTriggerRules(type: EventType): { provider: string; rules: TriggerRule[] } {
  const { provider, providerName } = useStudio();
  return { provider: provider?.display_name || providerName, rules: provider?.trigger_support?.[type] || [] };
}

/** Does `config` use the option a rule is about? */
export function ruleApplies(rule: TriggerRule, config: JsonObject): boolean {
  const v = config[rule.key];
  if (v === undefined || v === null || v === "" || v === false) return rule.value === false && v === false;
  if (rule.key === "events") return asArray(v).map((x) => str(x)).includes(str(rule.value));
  if (rule.key === "timezone") return str(v).toUpperCase() !== "UTC";
  if (rule.key === "cron") return !!v;
  if (typeof rule.value === "string" && rule.key !== "prefix" && rule.key !== "suffix" && rule.key !== "dead_letter") return v === rule.value;
  if (typeof rule.value === "boolean") return v === rule.value;
  return true;
}

/** What this provider rejects or ignores for this trigger type; the ones the config uses are highlighted. */
export function ProviderRules({ type, config }: { type: EventType; config: JsonObject }) {
  const { provider, rules } = useTriggerRules(type);
  if (!rules.length) return null;
  const active = rules.filter((r) => ruleApplies(r, config));
  return (
    <div className={`hint-box${active.some((r) => r.level === "error") ? " err" : active.length ? " warn" : ""}`}>
      <b>On {provider}:</b>
      <ul className="trigger-notes">
        {rules.map((r, i) => {
          const on = active.includes(r);
          return (
            <li key={i} className={on ? (r.level === "error" ? "err-text" : "warn-text") : "muted"}>
              {r.level === "error" ? "not supported" : "ignored"}: <code className="mono">{r.key}</code>
              {typeof r.value === "string" || typeof r.value === "boolean" || typeof r.value === "number" ? <> = {String(r.value)}</> : null} —{" "}
              {r.message}
              {on && " (used here)"}
            </li>
          );
        })}
      </ul>
    </div>
  );
}

export function TriggerForm({ event, onChange, fnName }: { event: NormalEvent; onChange: (next: NormalEvent) => void; fnName: string }) {
  const set = (key: string, value: Json | undefined) => {
    const config = { ...event.config };
    if (value === undefined || value === "") delete config[key];
    else config[key] = value;
    onChange({ ...event, config });
  };
  let form;
  switch (event.type) {
    case "http":
      form = <HttpForm config={event.config} set={set} />;
      break;
    case "schedule":
      form = <ScheduleForm config={event.config} set={set} replace={(c) => onChange({ ...event, config: c })} />;
      break;
    case "smtp":
      form = <SmtpForm config={event.config} set={set} />;
      break;
    default:
      form = <SourceForm type={event.type} config={event.config} set={set} replace={(c) => onChange({ ...event, config: c })} fnName={fnName} />;
  }
  return (
    <div className="stack">
      <ProviderRules type={event.type} config={event.config} />
      {form}
    </div>
  );
}

// --------------------------------------------------------------------- SMTP

/** Mail received by an SMTP server (the `smtp` on-prem service, an smtp resource). */
function SmtpForm({ config, set }: { config: JsonObject; set: (k: string, v: Json | undefined) => void }) {
  const { draft } = useStudio();
  const servers = Object.entries(asObject(draft.resources)).filter(([, r]) => str(asObject(r).type) === "smtp");
  const resource = str(config.resource);
  return (
    <div className="form">
      <FormRow
        label="SMTP server"
        required
        error={!resource ? "pick the SMTP server that receives the mail" : null}
        help="Create one under Resources → + SMTP server (or On-prem services → Mail); its DNS guide lists the records to add at your domain provider."
      >
        <EnumSelect value={resource} allowEmpty emptyLabel="choose…" options={servers.map(([k]) => k)} onChange={(v) => set("resource", v)} />
      </FormRow>
      <p className="muted small">
        The handler gets <code className="mono">event.data</code>: from, from_name, to, cc, bcc, reply_to, subject, text, html, headers, attachments (filename,
        content_type, size, content in base64), the SMTP envelope, and the same mail as an Amazon SES event (<code className="mono">Records[0].ses</code>, raw
        message in <code className="mono">content</code>).
      </p>
    </div>
  );
}

// --------------------------------------------------------------------- HTTP

function HttpForm({ config, set }: { config: JsonObject; set: (k: string, v: Json | undefined) => void }) {
  const { meta } = useStudio();
  const { provider, rules } = useTriggerRules("http");
  const methods = meta.http_methods.length ? meta.http_methods : ["GET", "POST", "PUT", "PATCH", "DELETE", "ANY"];
  const auths = meta.auth_modes && meta.auth_modes.length ? meta.auth_modes : ["none", "iam", "jwt", "key"];
  const authRule = (a: string) => rules.find((r) => r.key === "auth" && r.value === a && r.level === "error");
  const path = str(config.path, "/");
  const pathOk = /^\/?([\w.~-]+|\{[A-Za-z_]\w*\})?(\/([\w.~-]+|\{[A-Za-z_]\w*\}))*(\/\{[A-Za-z_]\w*\+\})?\/?$/.test(path.trim() || "/");
  const params = pathParams(path);
  const cors = config.cors;
  const corsOn = cors === true || isObject(cors);
  const corsObj = asObject(cors);
  return (
    <div className="form">
      <FormRow label="Route" required error={pathOk ? null : "use segments like /users/{id} or /files/{path+}"}>
        <div className="route-input">
          <EnumSelect value={str(config.method, "GET")} options={methods} onChange={(m) => set("method", m)} />
          <TextInput mono value={path} invalid={!pathOk} placeholder="/users/{id}" onChange={(p) => set("path", p.startsWith("/") ? p : `/${p}`)} />
        </div>
      </FormRow>
      {params.length > 0 && (
        <div className="hint-box">
          Path parameters: {params.map((p) => (
            <code key={p} className="mono chip">
              {p}
            </code>
          ))}{" "}
          → <code className="mono">event.http.path_params["{params[0]}"]</code>
        </div>
      )}
      <FormRow label="Auth" help={`none = public. Options ${provider} can't enforce are disabled (hover for why).`}>
        <Segmented
          label="Auth"
          value={str(config.auth, "none")}
          onChange={(a) => set("auth", a === "none" ? undefined : a)}
          options={auths.map((a) => {
            const rule = authRule(a);
            return { value: a, label: a, disabled: !!rule && str(config.auth, "none") !== a, title: rule ? rule.message : undefined };
          })}
        />
      </FormRow>
      {str(config.auth) === "jwt" && (
        <FormRow label="Authorizer" help='e.g. {"issuer": "https://…", "audience": ["api"]}'>
          <JsonInput value={config.authorizer} onChange={(v) => set("authorizer", v)} rows={4} />
        </FormRow>
      )}
      <FormRow label="CORS">
        <Toggle checked={corsOn} label={corsOn ? "enabled" : "off"} onChange={(on) => set("cors", on ? true : undefined)} />
      </FormRow>
      {corsOn && (
        <FormRow label="Allowed origins" help="Empty = any origin (*).">
          <ListEditor
            value={asArray(corsObj.origins).map((o) => str(o))}
            placeholder="https://app.example.com"
            addLabel="Add origin"
            onChange={(origins) => {
              const { origins: _old, ...others } = corsObj;
              void _old;
              if (origins) set("cors", { ...others, origins });
              else set("cors", Object.keys(others).length ? others : true);
            }}
          />
        </FormRow>
      )}
    </div>
  );
}

// --------------------------------------------------------------------- schedule

const RATE_PRESETS = ["1 minute", "5 minutes", "15 minutes", "1 hour", "6 hours", "1 day"];
const CRON_PRESETS = [
  { label: "Every day 09:00", value: "0 9 * * *" },
  { label: "Weekdays 08:30", value: "30 8 * * 1-5" },
  { label: "Every hour", value: "0 */1 * * *" },
  { label: "1st of month", value: "0 0 1 * *" },
];
const COMMON_ZONES = ["UTC", "Europe/London", "Europe/Berlin", "America/New_York", "America/Chicago", "America/Los_Angeles", "Asia/Kolkata", "Asia/Singapore", "Asia/Shanghai", "Asia/Tokyo", "Australia/Sydney"];
const DAYS = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"];
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** Every IANA zone the browser knows (falls back to a short list). */
export function timeZones(): string[] {
  const intl = Intl as unknown as { supportedValuesOf?: (key: string) => string[] };
  try {
    const all = intl.supportedValuesOf ? intl.supportedValuesOf("timeZone") : [];
    if (all.length) return ["UTC", ...all.filter((z) => z !== "UTC")];
  } catch {
    /* older browser */
  }
  return COMMON_ZONES;
}

type Repeat = "daily" | "weekdays" | "weekly" | "monthly" | "yearly";

export interface TimeSpec {
  repeat: Repeat;
  hour: number;
  minute: number;
  days: number[];
  dom: number;
  month: number;
}

/** Cron for a "run at HH:MM on ..." schedule. */
export function timeToCron(t: TimeSpec): string {
  const hm = `${t.minute} ${t.hour}`;
  switch (t.repeat) {
    case "weekdays":
      return `${hm} * * 1-5`;
    case "weekly":
      return `${hm} * * ${(t.days.length ? [...t.days].sort((a, b) => a - b) : [1]).join(",")}`;
    case "monthly":
      return `${hm} ${t.dom} * *`;
    case "yearly":
      return `${hm} ${t.dom} ${t.month} *`;
    default:
      return `${hm} * * *`;
  }
}

/** The inverse of timeToCron, or null when the cron isn't a simple "at a time" schedule. */
export function cronToTime(cron: string): TimeSpec | null {
  const m = /^(\d{1,2}) (\d{1,2}) (\*|\d{1,2}) (\*|\d{1,2}) (\*|1-5|[0-6](?:,[0-6])*)$/.exec(cron.trim());
  if (!m) return null;
  const minute = Number(m[1]);
  const hour = Number(m[2]);
  if (minute > 59 || hour > 23) return null;
  const base: TimeSpec = { repeat: "daily", hour, minute, days: [], dom: 1, month: 1 };
  const [dom, month, dow] = [m[3], m[4], m[5]];
  if (dom === "*" && month === "*") {
    if (dow === "*") return base;
    if (dow === "1-5") return { ...base, repeat: "weekdays" };
    return { ...base, repeat: "weekly", days: dow.split(",").map(Number) };
  }
  if (dow !== "*" || dom === "*") return null;
  const d = Number(dom);
  if (d < 1 || d > 31) return null;
  if (month === "*") return { ...base, repeat: "monthly", dom: d };
  const mo = Number(month);
  if (mo < 1 || mo > 12) return null;
  return { ...base, repeat: "yearly", dom: d, month: mo };
}

const pad = (n: number) => String(n).padStart(2, "0");

function ScheduleForm({
  config,
  set,
  replace,
}: {
  config: JsonObject;
  set: (k: string, v: Json | undefined) => void;
  replace: (c: JsonObject) => void;
}) {
  const cron = str(config.cron);
  const parsed = cron ? cronToTime(cron) : null;
  const [mode, setMode] = useState<"rate" | "time" | "cron">(config.cron ? (parsed ? "time" : "cron") : "rate");
  useEffect(() => {
    if (!config.cron && mode !== "rate") setMode("rate");
    else if (config.cron && mode === "rate") setMode(cronToTime(str(config.cron)) ? "time" : "cron");
  }, [config.cron, mode]);
  const rate = str(config.rate, "5 minutes");
  const m = /^\s*(\d+)\s+(minute|minutes|hour|hours|day|days)\s*$/i.exec(rate);
  const amount = m ? Number(m[1]) : 5;
  const unit = m ? m[2].replace(/s$/, "").toLowerCase() : "minute";
  const setRate = (n: number | undefined, u: string) => {
    const count = n && n > 0 ? Math.floor(n) : 1;
    set("rate", `${count} ${u}${count === 1 ? "" : "s"}`);
  };
  const withCron = (c: string) => {
    const { rate: _r, ...rest } = config;
    void _r;
    replace({ ...rest, cron: c });
  };
  const time: TimeSpec = parsed || { repeat: "daily", hour: 9, minute: 0, days: [1], dom: 1, month: 1 };
  const setTime = (patch: Partial<TimeSpec>) => withCron(timeToCron({ ...time, ...patch }));
  const zones = timeZones();
  return (
    <div className="form">
      <FormRow label="Run">
        <Segmented
          label="Schedule type"
          value={mode}
          onChange={(v) => {
            setMode(v);
            const { rate: _r, cron: _c, ...rest } = config;
            void _r;
            void _c;
            if (v === "rate") replace({ ...rest, rate: "5 minutes" });
            else if (v === "time") replace({ ...rest, cron: parsed ? cron : "0 9 * * *" });
            else replace({ ...rest, cron: cron || "0 9 * * *" });
          }}
          options={[
            { value: "rate", label: "Every…" },
            { value: "time", label: "At a specific time", title: "Daily, on weekdays, on chosen days, monthly or yearly at HH:MM" },
            { value: "cron", label: "Cron expression" },
          ]}
        />
      </FormRow>
      {mode === "rate" && (
        <FormRow label="Interval" help="Rates run every N minutes, hours or days from deploy time.">
          <div className="row-gap wrap">
            <span className="muted">every</span>
            <NumberInput integer min={1} value={amount} onChange={(n) => setRate(n, unit)} />
            <EnumSelect value={unit} options={["minute", "hour", "day"]} onChange={(u) => setRate(amount, u)} />
            <span className="chips">
              {RATE_PRESETS.map((p) => (
                <button key={p} type="button" className={rate === p ? "chip chip-accent chip-btn" : "chip chip-btn"} onClick={() => set("rate", p)}>
                  {p}
                </button>
              ))}
            </span>
          </div>
        </FormRow>
      )}
      {mode === "time" && (
        <>
          <FormRow label="Repeat">
            <Segmented
              label="Repeat"
              value={time.repeat}
              onChange={(r) => setTime({ repeat: r, days: r === "weekly" && !time.days.length ? [1] : time.days })}
              options={[
                { value: "daily", label: "Every day" },
                { value: "weekdays", label: "Weekdays" },
                { value: "weekly", label: "On days…" },
                { value: "monthly", label: "Monthly" },
                { value: "yearly", label: "Yearly" },
              ]}
            />
          </FormRow>
          {time.repeat === "weekly" && (
            <FormRow label="Days">
              <div className="row-gap wrap">
                {DAYS.map((d, i) => (
                  <label key={d} className="check">
                    <input
                      type="checkbox"
                      checked={time.days.includes(i)}
                      onChange={(e) => {
                        const next = e.target.checked ? [...time.days, i] : time.days.filter((x) => x !== i);
                        setTime({ days: next.length ? next : [i] });
                      }}
                    />
                    {d}
                  </label>
                ))}
              </div>
            </FormRow>
          )}
          {(time.repeat === "monthly" || time.repeat === "yearly") && (
            <FormRow label="On" help={time.dom > 28 ? "Months without this day are skipped." : undefined}>
              <div className="row-gap">
                {time.repeat === "yearly" && (
                  <EnumSelect value={String(time.month)} options={MONTHS.map((mo, i) => ({ value: String(i + 1), label: mo }))} onChange={(v) => setTime({ month: Number(v) })} />
                )}
                <EnumSelect
                  value={String(time.dom)}
                  options={Array.from({ length: 31 }, (_, i) => ({ value: String(i + 1), label: `day ${i + 1}` }))}
                  onChange={(v) => setTime({ dom: Number(v) })}
                />
              </div>
            </FormRow>
          )}
          <FormRow label="At" help={`→ ${describeCron(timeToCron(time))} (cron ${timeToCron(time)})`}>
            <input
              type="time"
              className="input input-num"
              value={`${pad(time.hour)}:${pad(time.minute)}`}
              onChange={(e) => {
                const [h, mi] = e.target.value.split(":").map(Number);
                if (!isNaN(h) && !isNaN(mi)) setTime({ hour: h, minute: mi });
              }}
            />
          </FormRow>
        </>
      )}
      {mode === "cron" && (
        <FormRow
          label="Cron"
          help={validCron(cron) ? `→ ${describeCron(cron)}` : "5 fields: minute hour day-of-month month day-of-week"}
          error={cron && !validCron(cron) ? "a cron expression has exactly 5 fields" : null}
        >
          <div className="stack-xs">
            <TextInput mono value={cron} invalid={!!cron && !validCron(cron)} placeholder="0 9 * * 1-5" onChange={(c) => set("cron", c)} />
            <span className="chips">
              {CRON_PRESETS.map((p) => (
                <button key={p.value} type="button" className={cron === p.value ? "chip chip-accent chip-btn" : "chip chip-btn"} onClick={() => set("cron", p.value)}>
                  {p.label}
                </button>
              ))}
            </span>
          </div>
        </FormRow>
      )}
      {mode !== "rate" && (
        <FormRow label="Timezone" help="The time above is in this zone.">
          <ComboInput
            value={str(config.timezone)}
            options={zones}
            emptyLabel="UTC (default)"
            onChange={(z) => set("timezone", z === "UTC" || !z ? undefined : z)}
          />
        </FormRow>
      )}
      <FormRow label="Input" help="JSON passed as event.data on every run (optional).">
        <JsonInput value={config.input} onChange={(v) => set("input", v)} rows={3} placeholder='{"report": "daily"}' />
      </FormRow>
      <FormRow label="Enabled">
        <Toggle checked={config.enabled !== false} onChange={(b) => set("enabled", b ? undefined : false)} label={config.enabled === false ? "paused" : "active"} />
      </FormRow>
    </div>
  );
}

// --------------------------------------------------------------------- queue / storage / topic

type SourceMode = "new" | "resource" | "cloud" | "existing";

const HANDLED = new Set(["name", "bucket", "resource", "existing", "events"]);

function SourceForm({
  type,
  config,
  set,
  replace,
  fnName,
}: {
  type: "queue" | "storage" | "topic";
  config: JsonObject;
  set: (k: string, v: Json | undefined) => void;
  replace: (c: JsonObject) => void;
  fnName: string;
}) {
  const { draft, meta, providerName, edit } = useStudio();
  const nameKey = type === "storage" ? "bucket" : "name";
  const resources = Object.entries(asObject(draft.resources)).filter(([, r]) => str(asObject(r).type) === type);
  const [mode, setModeState] = useState<SourceMode>(config.resource ? "resource" : config.existing ? "existing" : "new");
  const noun = type === "storage" ? "bucket" : type;
  const region = str(asObject(draft.provider).region) || meta.providers.find((p) => p.name === providerName)?.default_region;
  const fields: Field[] = (meta.events[type] || []).filter((f) => !HANDLED.has(f.key));
  const fallback = `${fnName}-${type === "storage" ? "uploads" : type === "queue" ? "jobs" : "events"}`;
  // On-premises a storage trigger can watch any bucket on a storage resource's service.
  const serviceBuckets = type === "storage" && !!meta.providers.find((p) => p.name === providerName)?.storage_service_buckets;

  const setMode = (m: SourceMode) => {
    setModeState(m);
    const { resource: _r, existing: _e, ...rest } = config;
    void _r;
    void _e;
    if (m === "resource") {
      const first = resources[0]?.[0];
      const { [nameKey]: _n, ...noName } = rest;
      void _n;
      replace({ ...noName, resource: first || "" });
    } else if (m === "existing" || m === "cloud") {
      replace({ ...rest, existing: true, [nameKey]: str(rest[nameKey]) });
    } else {
      replace({ ...rest, [nameKey]: str(rest[nameKey]) || fallback });
    }
  };

  /** "Create new": add a managed resource to Resources and select it right away. */
  const createResource = () => {
    const native = str(config[nameKey]).trim() || fallback;
    const taken = Object.keys(asObject(draft.resources));
    const base = native.replace(/[^A-Za-z0-9_-]/g, "-").replace(/^[^A-Za-z]+/, "") || noun;
    const key = uniqueName(NAME_RE.test(base) ? base.slice(0, 60) : noun, taken);
    const res: JsonObject = { type };
    if (native !== key) res.name = native;
    edit(["resources", key], res, { coalesce: false });
    const { [nameKey]: _n, existing: _e, ...rest } = config;
    void _n;
    void _e;
    replace({ ...rest, resource: key });
    setModeState("resource");
  };

  /** Picked in the cloud account: attach directly, optionally through a new external resource. */
  const pick = (item: DiscoverItem, asResource: boolean) => {
    const { resource: _r, [nameKey]: _n, ...rest } = config;
    void _r;
    void _n;
    if (!asResource) {
      replace({ ...rest, existing: true, [nameKey]: item.name });
      return;
    }
    const taken = Object.keys(asObject(draft.resources));
    const existing = resources.find(([, r]) => str(asObject(r).name) === item.name && asObject(r).external === true);
    let key = existing?.[0];
    if (!key) {
      const base = item.name.replace(/[^A-Za-z0-9_-]/g, "-").replace(/^[^A-Za-z]+/, "") || noun;
      key = uniqueName(NAME_RE.test(base) ? base.slice(0, 60) : noun, taken);
      const connection: JsonObject = {};
      if (item.arn) connection.arn = item.arn;
      else if (item.id && /^https?:\/\//.test(item.id)) connection.url = item.id;
      const res: JsonObject = { type, external: true, name: item.name };
      if (Object.keys(connection).length) res.connection = connection;
      edit(["resources", key], res, { coalesce: false });
    }
    const { existing: _e, ...noExisting } = rest;
    void _e;
    replace({ ...noExisting, resource: key });
    setModeState("resource");
  };

  return (
    <div className="form">
      <FormRow label="Source">
        <Segmented
          label={`${noun} source`}
          value={mode}
          onChange={setMode}
          options={[
            { value: "new", label: `Create new ${noun}`, title: "pskit creates it on deploy" },
            {
              value: "resource",
              label: `Project resource${resources.length ? ` (${resources.length})` : ""}`,
              disabled: !resources.length,
              title: resources.length ? "A resources: entry of this project" : `No ${noun} resources defined yet (Resources page)`,
            },
            { value: "cloud", label: `Pick from ${meta.providers.find((p) => p.name === providerName)?.display_name || providerName}`, title: `List the ${noun}s that already exist in your account` },
            { value: "existing", label: "Type a name", title: `An existing ${noun}; you type its exact name` },
          ]}
        />
      </FormRow>
      {mode === "resource" && (
        <FormRow
          label={serviceBuckets ? "Storage service" : "Resource"}
          required
          help={
            serviceBuckets
              ? "The storage resource whose service (driver, endpoint, keys) the trigger watches: MinIO, RustFS, Ceph, AWS S3, R2, Wasabi or any S3-compatible store. Set it up on the Resources page."
              : "Name, managed/external and on-prem driver come from the Resources page."
          }
        >
          <EnumSelect
            value={str(config.resource)}
            options={resources.map(([k, r]) => {
              const driver = storageDriverName(asObject(r));
              return {
                value: k,
                label: `${k}${asObject(r).external ? " (external)" : ""} · ${resourceBucket(k, asObject(r))}${type === "storage" && driver ? ` · ${driver}` : ""}`,
              };
            })}
            onChange={(k) => set("resource", k)}
          />
        </FormRow>
      )}
      {mode === "resource" && serviceBuckets && (
        <FormRow
          label="Bucket"
          help={`Any bucket on this service; empty = the resource's own bucket (${resourceBucket(str(config.resource), asObject(asObject(draft.resources)[str(config.resource)]))}). With create_bucket on the resource, a missing bucket is created on first use.`}
        >
          <TextInput
            mono
            value={str(config.bucket)}
            placeholder={resourceBucket(str(config.resource), asObject(asObject(draft.resources)[str(config.resource)]))}
            onChange={(v) => set("bucket", v.trim() ? v.trim() : undefined)}
          />
        </FormRow>
      )}
      {mode === "cloud" && (
        <CloudPicker
          provider={providerName}
          kind={type}
          region={region}
          selected={str(config[nameKey])}
          onPick={pick}
          onTypeInstead={() => setMode("existing")}
        />
      )}
      {(mode === "new" || mode === "existing") && (
        <FormRow
          label={type === "storage" ? "Bucket name" : `${type[0].toUpperCase()}${type.slice(1)} name`}
          required
          help={
            mode === "new"
              ? "pskit creates it on deploy. “Create & select” also adds it to Resources, so other functions can bind it and it shows up in this list."
              : "The exact name in the account; pskit only attaches the trigger."
          }
        >
          <div className="row-gap">
            <TextInput mono value={str(config[nameKey])} placeholder={fallback} onChange={(v) => set(nameKey, v)} />
            {mode === "new" && (
              <button type="button" className="btn btn-sm btn-primary" onClick={createResource} title={`Add this ${noun} to Resources and select it`}>
                Create &amp; select
              </button>
            )}
          </div>
        </FormRow>
      )}
      {type === "storage" && (
        <FormRow label="Fire on">
          <div className="row-gap">
            {["created", "deleted"].map((ev) => {
              const list = asArray(config.events).map((e) => str(e));
              const current = list.length ? list : ["created"];
              const on = current.includes(ev);
              return (
                <label key={ev} className="check">
                  <input
                    type="checkbox"
                    checked={on}
                    onChange={(e) => {
                      const next = e.target.checked ? [...current.filter((x) => x !== ev), ev] : current.filter((x) => x !== ev);
                      set("events", next.length ? next.sort() : ["created"]);
                    }}
                  />
                  {ev}
                </label>
              );
            })}
          </div>
        </FormRow>
      )}
      {fields.length > 0 && <FieldForm fields={fields} value={config} onChange={set} idPrefix={`ev-${type}`} compact />}
    </div>
  );
}

/** The on-prem driver of a storage resource (`options.driver` or `connection.driver`), e.g. `minio`. */
function storageDriverName(res: JsonObject): string {
  const raw = asObject(res.options).driver ?? asObject(res.connection).driver;
  return typeof raw === "string" ? raw : str(asObject(raw).use);
}

/** The bucket a resource stands for: its driver's `bucket` / `container`, else its name, else its key. */
function resourceBucket(key: string, res: JsonObject): string {
  const options = asObject(res.options);
  const driver = asObject(options.driver);
  return str(driver.bucket) || str(driver.container) || str(options.bucket) || str(options.container) || str(res.name) || key;
}

/** Lists the queues / buckets / topics that exist in the account and attaches one. */
function CloudPicker({
  provider,
  kind,
  region,
  selected,
  onPick,
  onTypeInstead,
}: {
  provider: string;
  kind: "queue" | "storage" | "topic";
  region?: string;
  selected: string;
  onPick: (item: DiscoverItem, asResource: boolean) => void;
  onTypeInstead: () => void;
}) {
  const [result, setResult] = useState<DiscoverResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [q, setQ] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [asResource, setAsResource] = useState(true);
  useEffect(() => {
    let live = true;
    setLoading(true);
    setError(null);
    api
      .discover(provider, kind, region)
      .then((r) => live && setResult(r))
      .catch((exc: unknown) => live && setError(errorMessage(exc)))
      .finally(() => live && setLoading(false));
    return () => {
      live = false;
    };
  }, [provider, kind, region, attempt]);
  const noun = kind === "storage" ? "buckets" : `${kind}s`;
  const items = (result?.items || []).filter((i) => [i.name, i.id, i.arn, i.region, i.detail].join(" ").toLowerCase().includes(q.trim().toLowerCase()));
  return (
    <FormRow label={`Existing ${noun}`} help={region ? `Region ${region}, with this machine's credentials.` : "With this machine's credentials."}>
      <div className="stack-xs">
        <div className="row-gap wrap">
          <SearchInput value={q} onChange={setQ} placeholder={`Filter ${noun}…`} />
          <button type="button" className="btn btn-sm" onClick={() => setAttempt((a) => a + 1)} disabled={loading}>
            {loading ? "Loading…" : "Refresh"}
          </button>
          <Toggle checked={asResource} onChange={setAsResource} label="Also add to Resources (external)" />
        </div>
        {error && <div className="form-error">{error}</div>}
        {result && !result.supported && (
          <div className="hint-box">
            {result.reason || "Listing isn't available here."}{" "}
            <button type="button" className="btn btn-sm" onClick={onTypeInstead}>
              Type the name instead
            </button>
          </div>
        )}
        {result?.error && <div className="form-error">{result.error}</div>}
        {result?.supported && !result.error && (
          <ul className="pick-list inline-pick" role="listbox" aria-label={`Existing ${noun}`}>
            {!items.length && <li className="muted small pad">{result.items.length ? "No match." : `No ${noun} found in this account.`}</li>}
            {items.map((item) => (
              <li key={item.arn || item.id || item.name}>
                <button type="button" className={`pick${item.name === selected ? " active" : ""}`} aria-selected={item.name === selected} onClick={() => onPick(item, asResource)}>
                  <b>{item.name}</b>
                  <span className="muted mono small">{item.arn || item.id || ""}</span>
                  {(item.region || item.detail) && <span className="muted small">{[item.region, item.detail].filter(Boolean).join(" · ")}</span>}
                </button>
              </li>
            ))}
          </ul>
        )}
      </div>
    </FormRow>
  );
}
