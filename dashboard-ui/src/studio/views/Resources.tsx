import { useEffect, useState } from "react";
import { DataTable, type Column } from "../../components/DataTable";
import { Drawer } from "../../components/Drawer";
import { CloudResources } from "../components/CloudResources";
import { Markdown } from "../components/Markdown";
import { CreateDrawer, OnPremServices, ServiceUsageDrawer } from "../components/OnPremServices";
import { ResourceData } from "../components/ResourceData";
import { ResourceGuides, type GuideRef } from "../components/ResourceGuides";
import { ResourceTester } from "../components/ResourceTester";
import { useConfirm, useToast } from "../components/Feedback";
import { EnumSelect, FieldForm, FormRow, KeyValueEditor, Segmented, TextInput, Toggle } from "../components/Forms";
import { DiscoverModal, InlineIssues, PageHeader } from "../components/Misc";
import { href, navigate } from "../route";
import { api, errorMessage } from "../api";
import { useStudio } from "../store";
import type { Driver, Json, JsonObject, OnPremService, OnPremServicesState, ResourceBinding } from "../types";
import { asArray, asObject, CLASS_RE, getIn, NAME_RE, setIn, str, uniqueName, type Path } from "../util";

interface Row {
  name: string;
  res: JsonObject;
}

const MANAGEABLE = ["storage", "queue", "topic", "smtp"];
const CLOUD_ORDER = ["aws", "azure", "gcp", "alibaba", "tencent", "huawei", "oracle", "ibm", "digitalocean", "cloudflare", "s3-clouds", "self-hosted", "any"];
const CLOUD_LABEL: Record<string, string> = {
  aws: "AWS",
  azure: "Azure",
  gcp: "Google Cloud",
  alibaba: "Alibaba Cloud",
  tencent: "Tencent Cloud",
  huawei: "Huawei Cloud",
  oracle: "Oracle Cloud",
  ibm: "IBM Cloud",
  digitalocean: "DigitalOcean",
  cloudflare: "Cloudflare",
  "s3-clouds": "Other S3-compatible clouds",
  "self-hosted": "Self-hosted",
  any: "Built-in & custom",
};

export function ResourcesView({ rest }: { rest: string[] }) {
  const { draft, replace, issuesAt, state } = useStudio();
  const confirm = useConfirm();
  const toast = useToast();
  const resources = asObject(draft.resources);
  const rows: Row[] = Object.entries(resources).map(([name, res]) => ({ name, res: asObject(res) }));
  const editing = rest[0] === "new" ? "new" : rest[0] && rest[0] in resources ? rest[0] : null;
  const [testing, setTesting] = useState<string | null>(null);
  const [guide, setGuide] = useState<GuideRef | null>(null);
  const [usage, setUsage] = useState<string | null>(null);
  const [browse, setBrowse] = useState<string | null>(null);
  const [smtpGuide, setSmtpGuide] = useState<string | null>(null);
  const { providerName } = useStudio();
  const onpremTarget = (state.target?.provider || providerName) === "onprem";
  // One-click on-prem services: create one straight into the list, or add one that is not in pskit.yml yet.
  const [onprem, setOnprem] = useState<OnPremServicesState | null>(null);
  const [createOnprem, setCreateOnprem] = useState<{ type?: string } | null>(null);
  const [onpremVersion, setOnpremVersion] = useState(0);
  useEffect(() => {
    api.onpremServices().then(setOnprem, () => setOnprem(null));
  }, [onpremVersion]);
  const declared = (key: string) => key in resources || key in asObject(getIn(draft, ["providers", "onprem", "resources"]));
  const notDeclared = (onprem?.services || []).filter((svc) => svc.kind === "service" && svc.resource && !declared(svc.key));
  const backing = (key: string) => (onprem?.services || []).find((svc) => svc.key === key && svc.kind === "service");
  const addService = async (svc: OnPremService, attach?: string[]) => {
    try {
      const { raw } = await api.onpremApply(draft, svc.key, attach);
      replace(raw);
      toast(`Added ${svc.key} (${svc.service}) to the resources${attach && attach.length ? ` with triggers on ${attach.join(", ")}` : ""}; save to keep it`, "ok");
    } catch (exc) {
      toast(errorMessage(exc), "err");
    }
  };
  const test = (key: string) => {
    setTesting(key);
    window.setTimeout(() => document.getElementById("resource-test")?.scrollIntoView({ behavior: "smooth", block: "start" }), 0);
  };

  // Which handler files call resource("key") (read from the saved code; triggers come from the draft below).
  const [codeUse, setCodeUse] = useState<Record<string, ResourceBinding>>({});
  useEffect(() => {
    api.resourceBindings().then(
      (r) => setCodeUse(r.resources),
      () => setCodeUse({}),
    );
  }, [state.mtime]);
  const functionNames = Object.keys(asObject(draft.functions)).sort();

  const usedBy = (name: string) =>
    Object.entries(asObject(draft.functions))
      .filter(([, fn]) => asArray(asObject(fn).events).some((e) => Object.values(asObject(e)).some((c) => asObject(c).resource === name)))
      .map(([n]) => n);

  const remove = async (name: string) => {
    const users = usedBy(name);
    const res = asObject(resources[name]);
    const target = state.target || { provider: providerName, stage: "dev" };
    // A one-click on-prem service behind it, or built-in data on the on-prem host?
    const service = await api.onpremServices().then((s) => s.services.find((x) => x.key === name && x.kind === "service"), () => undefined);
    const builtinOnHost =
      !service && target.provider === "onprem" && !res.external && ["queue", "storage", "topic"].includes(str(res.type)) && !str(asObject(res.options).driver);
    const warn = users.length ? ` Triggers in ${users.join(", ")} use it and will stop validating until you change them.` : "";
    let body: string;
    let extra: { label: string; value: string; danger?: boolean }[] | undefined;
    let confirmLabel = "Delete";
    if (service) {
      body = `${name} is backed by the ${service.service} container on ${service.target_label}. Remove only the pskit.yml entry, or also stop the service: keeping its data volume (create it again later with the same key to reuse it) or deleting the data.${warn}`;
      confirmLabel = "pskit.yml only";
      extra = [
        { label: "Stop service, keep data", value: "svc-keep" },
        { label: "Delete service and data", value: "svc-delete", danger: true },
      ];
    } else if (builtinOnHost) {
      body = `The messages / objects of ${name} stay in the host's data folder unless you delete them too.${warn}`;
      confirmLabel = "Delete, keep data";
      extra = [{ label: "Delete with its data", value: "purge", danger: true }];
    } else {
      body =
        (res.external
          ? "Bound functions lose its PSKIT_RESOURCE_* variables. Nothing is deleted in the cloud (it is external)."
          : "Bound functions lose its PSKIT_RESOURCE_* variables. It is managed by pskit, so the next deploy deletes it from the cloud with its data (or delete it now under In the cloud).") + warn;
    }
    const answer = await confirm({ title: `Delete resource ${name}?`, body, confirmLabel, extra, danger: true });
    if (!answer) return;
    try {
      if (answer === "purge") {
        const out = await api.resourceClear(target.provider, target.stage, name);
        toast(`Deleted ${out.deleted} item(s) of ${name} on the host`, "ok");
      } else if (answer === "svc-keep" || answer === "svc-delete") {
        await api.onpremRemove(name, answer === "svc-delete");
        toast(`Removing the ${name} service${answer === "svc-delete" ? " and its data" : " (data kept)"}; progress under On-prem services`, "info");
      }
    } catch (exc) {
      toast(errorMessage(exc), "err");
      if (answer === "purge") return;
    }
    let raw: Json = setIn(draft, ["resources", name], undefined);
    if (getIn(raw, ["providers", "onprem", "resources", name]) !== undefined) raw = setIn(raw, ["providers", "onprem", "resources", name], undefined);
    replace(raw as JsonObject);
    toast(`Deleted ${name} from pskit.yml (not saved yet)`, "info");
  };

  const columns: Column<Row>[] = [
    {
      key: "name",
      header: "Resource",
      sortValue: (r) => r.name,
      render: (r) => (
        <div className="cell-name">
          <a href={href("resources", r.name)}>
            <b>{r.name}</b>
          </a>
          <span className="muted mono small">{str(r.res.name) || r.name}</span>
        </div>
      ),
    },
    { key: "type", header: "Type", sortValue: (r) => str(r.res.type), render: (r) => <span className="badge badge-accent">{str(r.res.type)}</span> },
    {
      key: "mode",
      header: "Mode",
      render: (r) => {
        const svc = backing(r.name);
        return (
          <span className="row-gap">
            {r.res.external ? <span className="badge badge-warn">external</span> : <span className="badge badge-ok">managed</span>}
            {svc && (
              <span className="badge" title={`One-click on-prem service on ${svc.target_label}`}>
                on-prem {svc.service} · {svc.target_label}
              </span>
            )}
          </span>
        );
      },
    },
    {
      key: "driver",
      header: "On-prem driver",
      render: (r) => {
        const d = str(asObject(r.res.options).driver) || str(asObject(getIn(draft, ["providers", "onprem", "resources", r.name, "options"])).driver);
        return d ? <span className="mono small">{d}</span> : <span className="muted">builtin</span>;
      },
    },
    {
      key: "fns",
      header: "Bound to",
      render: (r) => {
        // `functions:` limits who gets the variables; without it every function could, so show who really uses it:
        // a trigger on it, or code that calls resource("key") / reads PSKIT_RESOURCE_<KEY>_*.
        const restricted = Array.isArray(r.res.functions);
        const listed = asArray(r.res.functions).map((f) => str(f));
        const triggers = usedBy(r.name);
        const code = (codeUse[r.name]?.code || []).filter((f) => functionNames.includes(f));
        const used = Array.from(new Set([...triggers, ...code])).sort();
        const shown = restricted ? Array.from(new Set([...listed, ...used])).sort() : used;
        const kind = (f: string) =>
          [triggers.includes(f) && "trigger", code.includes(f) && "code", restricted && !listed.includes(f) && "not in functions:"].filter(Boolean).join(" + ");
        return (
          <div>
            {shown.length > 0 ? (
              <span className="chips">
                {shown.map((f) => (
                  <a
                    key={f}
                    href={href("functions", f)}
                    className={used.includes(f) ? "chip chip-accent" : "chip"}
                    title={kind(f) ? `${f}: ${kind(f)}` : `${f}: listed in functions:, not used in its trigger or handler code`}
                  >
                    {triggers.includes(f) ? "⚡ " : ""}
                    {f}
                  </a>
                ))}
              </span>
            ) : (
              <span className="muted small">{restricted ? "no functions" : "not used by any function yet"}</span>
            )}
            <div className="muted small">
              {restricted
                ? `functions: ${listed.length} of ${functionNames.length}`
                : `variables available to all ${functionNames.length} function${functionNames.length === 1 ? "" : "s"}`}
            </div>
          </div>
        );
      },
    },
    {
      key: "issues",
      header: "",
      render: (r) => (issuesAt(["resources", r.name]).some((i) => i.level === "error") ? <span className="badge badge-err">error</span> : null),
    },
    {
      key: "actions",
      header: "",
      render: (r) => (
        <span className="row-gap" onClick={(e) => e.stopPropagation()}>
          <button type="button" className="btn btn-sm btn-primary" onClick={() => setUsage(r.name)} title="Libraries, pskit.yml, Python / Node.js code and tests">
            How to use
          </button>
          {str(r.res.type) === "smtp" && onprem?.services.some((s) => s.key === r.name) && (
            <button type="button" className="btn btn-sm" onClick={() => setSmtpGuide(r.name)} title="DNS records to add at your domain provider (A, MX), the port, and the mail fields handlers get">
              DNS guide
            </button>
          )}
          {onpremTarget && ["queue", "storage", "topic"].includes(str(r.res.type)) && (
            <button type="button" className="btn btn-sm" onClick={() => setBrowse(r.name)} title="See the messages / objects it holds">
              Data
            </button>
          )}
          <button type="button" className="btn btn-sm" onClick={() => test(r.name)} title="Send a test message / object">
            Test
          </button>
          <button type="button" className="btn btn-sm btn-danger" onClick={() => void remove(r.name)}>
            Delete
          </button>
        </span>
      ),
    },
  ];

  return (
    <div className="page">
      <PageHeader
        title="Resources"
        subtitle="Buckets, queues, topics, databases and any other service your functions use, once for every cloud."
        actions={
          <span className="row-gap">
            <button type="button" className="btn" onClick={() => setGuide({ cloud: providerName || "index", page: "readme" })}>
              Guides
            </button>
            <button type="button" className="btn" onClick={() => setCreateOnprem({ type: "smtp" })} disabled={!onprem} title="An SMTP server (Node.js) that receives mail for your domain and runs functions with it">
              + SMTP server
            </button>
            <button type="button" className="btn" onClick={() => setCreateOnprem({})} disabled={!onprem} title="Start Redis, Kafka, PostgreSQL, MinIO, OpenBao, ... with Docker and add it here">
              + On-prem service
            </button>
            <a className="btn btn-primary" href={href("resources", "new")}>
              + Add resource
            </a>
          </span>
        }
      />
      {notDeclared.length > 0 && (
        <div className="hint-box row-gap wrap">
          <span>
            On-prem services not in the resource list yet:
          </span>
          {notDeclared.map((svc) => (
            <button key={svc.key} type="button" className="btn btn-sm" onClick={() => void addService(svc)} title={`${svc.service} on ${svc.target_label}`}>
              + {svc.key} <span className="muted small">({svc.service})</span>
            </button>
          ))}
        </div>
      )}
      <div className="card">
        <DataTable
          columns={columns}
          rows={rows}
          rowKey={(r) => r.name}
          onRowClick={(r) => navigate("resources", r.name)}
          emptyTitle="No resources yet"
          emptyHint="Declare a bucket, queue, topic, database or custom service, managed by pskit or one that already exists."
        />
      </div>
      <div id="resource-test">
        <ResourceTester key={testing || ""} selected={testing} onSelect={setTesting} />
      </div>
      <OnPremServices onGuide={setGuide} key={onpremVersion} />
      {createOnprem && onprem && (
        <CreateDrawer
          state={onprem}
          initial={(createOnprem.type === "smtp" && onprem.catalog.find((c) => c.id === "smtp")) || null}
          resourceType={createOnprem.type}
          onClose={() => setCreateOnprem(null)}
          onCreated={(svc, attach) => {
            setOnpremVersion((v) => v + 1);
            void addService(svc, attach);
            if (svc.service === "smtp") setSmtpGuide(svc.key);
          }}
        />
      )}
      <CloudResources />
      {editing && (
        <ResourceDrawer
          key={editing}
          name={editing === "new" ? null : editing}
          onClose={() => navigate("resources")}
          onGuide={setGuide}
          onCreateOnprem={(type) => {
            navigate("resources");
            setCreateOnprem({ type });
          }}
        />
      )}
      <ResourceGuides open={!!guide} start={guide || undefined} onClose={() => setGuide(null)} />
      {browse && <ResourceData resourceKey={browse} onClose={() => setBrowse(null)} />}
      {smtpGuide && <ServiceUsageDrawer serviceKey={smtpGuide} onClose={() => setSmtpGuide(null)} />}
      {usage && <UsageDrawer resourceKey={usage} onClose={() => setUsage(null)} onTest={() => { setUsage(null); test(usage); }} />}
    </div>
  );
}

function ResourceDrawer({
  name: existing,
  onClose,
  onGuide,
  onCreateOnprem,
}: {
  name: string | null;
  onClose: () => void;
  onGuide: (ref: GuideRef) => void;
  onCreateOnprem?: (type: string) => void;
}) {
  const studio = useStudio();
  const { draft, meta, providerName, replace, issuesAt, state } = studio;
  const toast = useToast();
  const resources = asObject(draft.resources);
  const [name, setName] = useState(existing || uniqueName("my-resource", Object.keys(resources)));
  const [res, setRes] = useState<JsonObject>(() => (existing ? { ...asObject(resources[existing]) } : { type: "storage" }));
  const onpremPath: Path = providerName === "onprem" ? [] : ["providers", "onprem", "resources"];
  const [onpremOptions, setOnpremOptions] = useState<JsonObject>(() =>
    providerName === "onprem"
      ? asObject(asObject(existing ? resources[existing] : {}).options)
      : asObject(getIn(draft, [...onpremPath, existing || "", "options"])),
  );
  const [browse, setBrowse] = useState(false);
  const type = str(res.type, "storage");
  const managedAllowed = MANAGEABLE.includes(type);
  const external = res.external === true || !managedAllowed;
  const functions = Object.keys(asObject(draft.functions));
  const nameError = !NAME_RE.test(name) ? "letters, digits, - and _; start with a letter" : name !== existing && name in resources ? "already exists" : null;
  const driverList: Driver[] = (meta.onprem.drivers as Record<string, Driver[] | undefined>)[type] || [];
  const target = state.target?.provider || providerName;

  const set = (key: string, value: Json | undefined) =>
    setRes((r) => {
      const next = { ...r };
      if (value === undefined || value === "" || (Array.isArray(value) && !value.length)) delete next[key];
      else next[key] = value;
      return next;
    });

  const apply = () => {
    if (nameError) return;
    const body: JsonObject = { ...res };
    if (!managedAllowed) body.external = true;
    if (body.external !== true) delete body.external;
    const cleanOpts: JsonObject = {};
    for (const [k, v] of Object.entries(onpremOptions)) if (v !== undefined && v !== "" && v !== null) cleanOpts[k] = v;
    let raw: Json = draft;
    if (existing && existing !== name) {
      raw = setIn(raw, ["resources", existing], undefined);
      if (onpremPath.length) raw = setIn(raw, [...onpremPath, existing], undefined);
    }
    if (providerName === "onprem") {
      if (Object.keys(cleanOpts).length) body.options = cleanOpts;
      else delete body.options;
    } else {
      // Keep the on-prem driver in a provider override so the base config stays portable.
      const overridePath = [...onpremPath, name];
      if (Object.keys(cleanOpts).length) raw = setIn(raw, overridePath, { ...asObject(getIn(raw, overridePath)), options: cleanOpts });
      else if (getIn(raw, overridePath) !== undefined) raw = setIn(raw, [...overridePath, "options"], undefined);
    }
    raw = existing === name ? setIn(raw, ["resources", name], body) : setIn(raw, ["resources"], { ...asObject((raw as JsonObject).resources), [name]: body });
    replace(raw as JsonObject);
    toast(`${existing ? "Updated" : "Added"} resource ${name} (not saved yet)`, "ok");
    onClose();
  };

  const driver = str(onpremOptions.driver) || "builtin";
  const selected = driverList.find((d) => d.name === driver);
  const fieldKeys = new Set((selected?.fields || []).flatMap((f) => [f.key, `${f.key}_env`]));
  const extraArgs: JsonObject = {};
  if (driver === "custom") {
    for (const [k, v] of Object.entries(onpremOptions)) if (k !== "driver" && !fieldKeys.has(k)) extraArgs[k] = v;
  }

  return (
    <Drawer
      open
      title={existing ? `Resource ${existing}` : "Add resource"}
      onClose={onClose}
      actions={
        <button type="button" className="btn btn-primary" disabled={!!nameError} onClick={apply}>
          {existing ? "Apply" : "Add"}
        </button>
      }
    >
      <div className="form">
        {existing && <InlineIssues issues={issuesAt(["resources", existing])} />}
        {!existing && onCreateOnprem && type !== "topic" && (
          <div className="hint-box row-between wrap">
            <span className="small">
              Need the {type} itself on premises? pskit can start one with Docker (here or on an SSH server) and add it to this list, with its
              connection and credentials.
            </span>
            <button type="button" className="btn btn-sm btn-primary" onClick={() => onCreateOnprem(type)}>
              Create a {type} on premises
            </button>
          </div>
        )}
        <FormRow label="Key" required error={nameError} help="How handlers refer to it: resource(&quot;key&quot;), and triggers use resource: key.">
          <TextInput mono value={name} onChange={setName} invalid={!!nameError} autoFocus={!existing} />
        </FormRow>
        <FormRow label="Type">
          <EnumSelect
            value={type}
            options={meta.resource_types.length ? meta.resource_types : ["storage", "queue", "topic", "database", "cache", "custom"]}
            onChange={(t) => setRes((r) => ({ ...r, type: t, ...(MANAGEABLE.includes(t) ? {} : { external: true }) }))}
          />
        </FormRow>
        <FormRow
          label="Mode"
          help={external ? "Already exists or runs elsewhere. pskit never creates or deletes it." : "pskit creates it on deploy and removes it with pskit remove."}
        >
          <Segmented
            label="Mode"
            value={external ? "external" : "managed"}
            onChange={(m) => set("external", m === "external" ? true : undefined)}
            options={[
              { value: "managed", label: "Managed by pskit", disabled: !managedAllowed, title: managedAllowed ? undefined : `pskit doesn't create ${type} resources` },
              { value: "external", label: "External / existing" },
            ]}
          />
        </FormRow>
        <FormRow label="Native name" help={external ? "The exact bucket/queue/topic name (or put an arn in connection)." : "Defaults to the key; pskit prefixes service and stage where the provider needs it."}>
          <div className="row-gap">
            <TextInput mono value={str(res.name)} placeholder={name} onChange={(v) => set("name", v)} />
            {external && managedAllowed && (
              <button type="button" className="btn" onClick={() => setBrowse(true)}>
                Browse account…
              </button>
            )}
          </div>
        </FormRow>
        {driverList.length === 0 && (
          <p className="muted small">
            Step by step for each cloud:{" "}
            <button type="button" className="btn btn-sm" onClick={() => onGuide({ cloud: providerName === "onprem" ? "onprem" : providerName, page: type })}>
              {type} guide
            </button>
          </p>
        )}
        <FormRow label="Connection" help="Values handed to handlers as PSKIT_RESOURCE_<KEY>_<NAME>. Use ${env} for secrets, never a literal password.">
          <KeyValueEditor value={asObject(res.connection)} keyPattern={/^[A-Za-z][A-Za-z0-9_]*$/} keyPlaceholder="host" onChange={(v) => set("connection", v)} addLabel="Add connection value" />
        </FormRow>
        <FormRow label="Bound functions" help="Empty = every function (generated orchestrators excluded).">
          <div className="check-grid">
            {functions.map((f) => {
              const list = asArray(res.functions).map((x) => str(x));
              return (
                <label key={f} className="check">
                  <input
                    type="checkbox"
                    checked={list.includes(f)}
                    onChange={(e) => set("functions", e.target.checked ? [...list, f] : list.filter((x) => x !== f))}
                  />
                  {f}
                </label>
              );
            })}
            {!functions.length && <span className="muted">No functions yet.</span>}
          </div>
        </FormRow>

        {driverList.length > 0 && (
          <div className="driver-box card card-pad">
            <div className="row-between">
              <h3>On-premises driver</h3>
              <button type="button" className="btn btn-sm" onClick={() => onGuide({ cloud: "onprem", page: type })}>
                How to set up a {type}
              </button>
            </div>
            <p className="muted small">
              {providerName === "onprem" ? (
                <>
                  Where the on-prem host reads this {type} from. Stored in <code className="mono">resources.{name}.options</code>.
                </>
              ) : (
                <>
                  Used when you deploy with <code className="mono">--provider onprem</code>. Stored in{" "}
                  <code className="mono">providers.onprem.resources.{name}.options</code>, so {meta.providers.find((p) => p.name === providerName)?.display_name} isn't affected.
                </>
              )}
            </p>
            <DriverPicker drivers={driverList} value={driver} onChange={(d) => setOnpremOptions(d === "builtin" ? {} : { driver: d })} />
            {selected && selected.notes && <p className="muted small">{selected.notes}</p>}
            {selected && selected.fields.length > 0 && (
              <FieldForm
                fields={selected.fields}
                value={onpremOptions}
                envStyle="key"
                idPrefix={`drv-${driver}`}
                onChange={(k, v) =>
                  setOnpremOptions((o) => {
                    const next: JsonObject = { ...o, driver };
                    if (v === undefined || v === "") delete next[k];
                    else next[k] = v;
                    return next;
                  })
                }
              />
            )}
            {driver === "custom" && (
              <>
                {!(selected?.fields || []).some((f) => f.key === "class") && (
                  <FormRow label="Class" required error={onpremOptions.class && !CLASS_RE.test(str(onpremOptions.class)) ? "use package.module:ClassName" : !onpremOptions.class ? "required" : null}>
                    <TextInput mono value={str(onpremOptions.class)} placeholder="app.backends:RabbitQueue" onChange={(v) => setOnpremOptions((o) => ({ ...o, driver, class: v }))} />
                  </FormRow>
                )}
                {onpremOptions.class && !CLASS_RE.test(str(onpremOptions.class)) && (selected?.fields || []).some((f) => f.key === "class") && (
                  <div className="form-error">class must look like package.module:ClassName</div>
                )}
                <FormRow label="Constructor arguments" help="Passed as keyword arguments. A key ending in _env is read from the host's environment.">
                  <KeyValueEditor
                    value={extraArgs}
                    secrets={false}
                    keyPattern={/^[A-Za-z_][A-Za-z0-9_]*$/}
                    keyPlaceholder="url_env"
                    addLabel="Add argument"
                    onChange={(kv) =>
                      setOnpremOptions((o) => {
                        const next: JsonObject = { driver };
                        for (const [k, v] of Object.entries(o)) if (k === "driver" || fieldKeys.has(k) || k === "class") next[k] = v;
                        return { ...next, ...(kv || {}) };
                      })
                    }
                  />
                </FormRow>
                <p className="muted small">
                  The class implements submit / claim / settle / depth / recover (queues) or scan / put / get / delete (storage). See examples/19-custom-drivers.
                </p>
              </>
            )}
          </div>
        )}
        <details className="advanced">
          <summary>Provider-specific options</summary>
          <p className="muted small">resources.{name}.options for the main provider, as JSON key/value pairs.</p>
          {providerName === "onprem" ? (
            <p className="muted small">On-prem options are set with the driver above.</p>
          ) : (
            <KeyValueEditor value={asObject(res.options)} secrets={false} onChange={(v) => set("options", v)} addLabel="Add option" />
          )}
        </details>
        <Toggle checked={external} onChange={(b) => managedAllowed && set("external", b ? true : undefined)} label="external (pskit doesn't create it)" />
      </div>
      <DiscoverModal
        open={browse}
        provider={target}
        kind={type === "storage" ? "storage" : type === "queue" ? "queue" : "topic"}
        region={str(asObject(draft.provider).region) || undefined}
        onClose={() => setBrowse(false)}
        onPick={(item) => {
          set("name", item.name);
          if (item.arn) set("connection", { ...asObject(res.connection), arn: item.arn });
        }}
      />
    </Drawer>
  );
}

/** End-to-end guide for one resource: libraries, pskit.yml, code, local and deployed tests. */
function UsageDrawer({ resourceKey, onClose, onTest }: { resourceKey: string; onClose: () => void; onTest: () => void }) {
  const { state, providerName, dirty } = useStudio();
  const target = state.target || { provider: providerName, stage: "dev" };
  const [doc, setDoc] = useState<{ markdown: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    setDoc(null);
    setError(null);
    api
      .resourceUsage(target.provider, target.stage, resourceKey)
      .then((d) => live && setDoc(d))
      .catch((exc: unknown) => live && setError(errorMessage(exc)));
    return () => {
      live = false;
    };
  }, [resourceKey, target.provider, target.stage]);
  return (
    <Drawer
      open
      title={`How to use ${resourceKey}`}
      onClose={onClose}
      actions={
        <span className="row-gap">
          {doc && (
            <button type="button" className="btn" onClick={() => void navigator.clipboard?.writeText(doc.markdown)} title="Copy the whole guide as Markdown">
              Copy guide
            </button>
          )}
          <button type="button" className="btn btn-primary" onClick={onTest}>
            Test it
          </button>
        </span>
      }
    >
      <p className="muted small">
        For {target.provider} / {target.stage}, from the saved pskit.yml{dirty ? " (you have unsaved changes: save to include them)" : ""}. Terminal:{" "}
        <code className="mono">pskit resources usage {resourceKey} -p {target.provider} -s {target.stage}</code>
      </p>
      {error && <div className="form-error">{error}</div>}
      {!doc && !error && <p className="muted">Loading…</p>}
      {doc && <Markdown text={doc.markdown} />}
    </Drawer>
  );
}

function DriverPicker({ drivers, value, onChange }: { drivers: Driver[]; value: string; onChange: (d: string) => void }) {
  const groups = new Map<string, Driver[]>();
  const withBuiltin = drivers.some((d) => d.name === "builtin") ? drivers : [{ name: "builtin", label: "Built-in (folder on the host)", cloud: "any", fields: [] }, ...drivers];
  for (const d of withBuiltin) groups.set(d.cloud, [...(groups.get(d.cloud) || []), d]);
  const ordered = Array.from(groups.entries()).sort((a, b) => {
    const ia = CLOUD_ORDER.indexOf(a[0]);
    const ib = CLOUD_ORDER.indexOf(b[0]);
    return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib);
  });
  return (
    <div className="driver-groups" role="radiogroup" aria-label="Driver">
      {ordered.map(([cloud, list]) => (
        <div key={cloud} className="driver-group">
          <div className="muted small driver-cloud">{CLOUD_LABEL[cloud] || cloud}</div>
          <div className="chips">
            {list.map((d) => (
              <button
                key={d.name}
                type="button"
                role="radio"
                aria-checked={d.name === value}
                className={d.name === value ? "chip chip-accent chip-btn" : "chip chip-btn"}
                onClick={() => onChange(d.name)}
                title={d.notes}
              >
                {d.label}
              </button>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
