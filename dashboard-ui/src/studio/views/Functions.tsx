import { useCallback, useEffect, useState } from "react";
import { Chip } from "../../components/Badge";
import { DataTable, type Column } from "../../components/DataTable";
import { SearchInput } from "../../components/Inputs";
import { api, errorMessage } from "../api";
import { useConfirm, useToast } from "../components/Feedback";
import { ComboInput, EnumSelect, FieldForm, FormRow, KeyValueEditor, NumberInput, Section, Segmented, TextInput, Toggle } from "../components/Forms";
import { DiffView, InlineIssues, PageHeader } from "../components/Misc";
import { isEnabled } from "../compat";
import { EnableControl } from "../components/EnableControl";
import { GroupBadge, readPlacement, renameInPlacement, RunsOnField, usePlacementTargets } from "../components/Placement";
import { useOnPremServers } from "../components/ServerPicker";
import {
  applyRunsOn,
  deployTargetWhere,
  groupOf,
  hasRunsOnErrors,
  initialRunsOn,
  NEW_GROUP,
  placementPath,
  runsOnErrors,
  targetBody,
  targetLabel,
  type RunsOnChoice,
} from "../placement";
import { DeployedLogs } from "./Logs";
import { href, navigate } from "../route";
import { providersSupporting, useStudio } from "../store";
import { flushHandlerStubs, forgetHandlerStub, queueHandlerStub } from "../stubs";
import { EVENT_TYPES, type EventType, type FunctionSplitResult, type Json, type JsonObject, type ProviderMeta } from "../types";
import {
  asArray,
  asObject,
  deepEqual,
  languageOf,
  runtimeLabel,
  defaultHandler,
  eventSummary,
  eventToRaw,
  functionKind,
  getIn,
  HANDLER_RE,
  NAME_RE,
  normalizeEvent,
  setIn,
  str,
  toYaml,
  uniqueName,
  type NormalEvent,
} from "../util";
import { durationLabel, memoryLabel, MEMORY, timeoutChoices } from "./Overview";
import { defaultEvent, EVENT_INFO, TriggerForm } from "./TriggerForms";

interface Row {
  name: string;
  fn: JsonObject;
}

/** Workflows (and nested branches) whose task states call `fn`. */
export function workflowsUsing(draft: JsonObject, fn: string): string[] {
  const found = new Set<string>();
  const walk = (wf: string, def: Json) => {
    for (const st of Object.values(asObject(asObject(def).states))) {
      const s = asObject(st);
      if (s.function === fn) found.add(wf);
      asArray(s.branches).forEach((b) => walk(wf, b));
      if (s.iterator) walk(wf, s.iterator);
    }
  };
  for (const [name, wf] of Object.entries(asObject(draft.workflows))) walk(name, wf);
  return Array.from(found);
}

export function FunctionsView({ rest }: { rest: string[] }) {
  if (rest[0] === "new") return <FunctionWizard name={null} />;
  if (rest[0]) return <FunctionWizard name={rest[0]} />;
  return <FunctionList />;
}

/** The module of a handler: `app.handlers.hello` -> `app.handlers` ("" when it is not a valid handler). */
export function handlerModule(handler: string): string {
  if (!HANDLER_RE.test(handler)) return "";
  return handler.replace(":", ".").split(".").slice(0, -1).join(".");
}

/** A function whose handler sits in a code file with other functions' handlers (GET /api/functions/shared). */
export interface SharedFile {
  file: string;
  others: string[];
}

export function sharedFileOf(shared: Record<string, string[]>, name: string, handler: string): SharedFile | null {
  const module = handlerModule(handler);
  const names = module ? shared[module] : undefined;
  if (!names || !names.includes(name)) return null;
  return { file: `${module.replace(/\./g, "/")}.py`, others: names.filter((n) => n !== name) };
}

/** The plan of `pskit function split` (its `lines`), for the confirm dialogs. */
function SplitPlan({ plans }: { plans: FunctionSplitResult[] }) {
  const unknown = Array.from(new Set(plans.flatMap((p) => p.unknown_imports || [])));
  return (
    <div className="stack-xs">
      <pre className="split-plan mono">{plans.flatMap((p) => p.lines).join("\n")}</pre>
      <p className="small muted">
        The handler and the module-level helpers and imports it uses move to its folder with its own requirements.txt; helpers are copied, so the
        other functions keep theirs. pskit.yml on disk gets the new handler.
      </p>
      {unknown.length > 0 && <p className="small warn-text">Check the new requirements.txt for: {unknown.join(", ")}.</p>}
    </div>
  );
}

function FunctionList() {
  const { draft, state, edit, replace, issuesAt, provider, providerName, dirty, save, setProject, reload } = useStudio();
  const confirm = useConfirm();
  const toast = useToast();
  const [q, setQ] = useState("");
  const generated = new Set((state.validation?.functions || []).filter((f) => f.generated).map((f) => f.name));
  const placement = providerName === "onprem" ? readPlacement(draft) : null;
  // Functions sharing a code file (pskit.yml on disk; Python only: `pskit function split` moves Python handlers).
  const python = languageOf(str(asObject(draft.provider).runtime, provider?.default_runtime || "python3.12")) === "python";
  const [shared, setShared] = useState<Record<string, string[]>>({});
  const [splitting, setSplitting] = useState<string | null>(null);
  const loadShared = useCallback(() => {
    if (!python) {
      setShared({});
      return;
    }
    api.functionsShared().then(
      (r) => setShared(r.shared || {}),
      () => setShared({}),
    );
  }, [python]);
  useEffect(loadShared, [loadShared, state.mtime]);
  const sharedOf = (r: Row) => sharedFileOf(shared, r.name, str(r.fn.handler));
  const sharedNames = Object.keys(asObject(draft.functions)).filter((n) => sharedFileOf(shared, n, str(asObject(asObject(draft.functions)[n]).handler)));
  const splitWarnings = issuesAt(["provider", "options", "placement"]).filter((i) => i.message.includes("pskit function split"));

  /** The split edits pskit.yml on disk: save the draft first. */
  const savedFirst = async (): Promise<boolean> => {
    if (!dirty) return true;
    const answer = await confirm({
      title: "Save first?",
      body: "Moving a function to its own folder rewrites pskit.yml on disk, which doesn't have your latest changes. Save them first.",
      confirmLabel: "Save and continue",
    });
    if (answer !== "confirm") return false;
    try {
      if (!(await save())) return false;
      await flushHandlerStubs();
      return true;
    } catch (exc) {
      toast(`Save failed: ${errorMessage(exc)}`, "err");
      return false;
    }
  };

  const splitOne = async (name: string) => {
    if (!(await savedFirst())) return;
    setSplitting(name);
    try {
      const plan = await api.splitFunction(name, true);
      const answer = await confirm({ title: `Move ${name} to its own folder?`, body: <SplitPlan plans={[plan]} />, confirmLabel: "Move it" });
      if (answer !== "confirm") return;
      const done = await api.splitFunction(name);
      setProject(done.project);
      toast(`${name} now lives in ${done.to}`, "ok");
    } catch (exc) {
      toast(errorMessage(exc), "err");
    } finally {
      setSplitting(null);
      loadShared();
    }
  };

  const splitAll = async () => {
    const names = sharedNames;
    if (!names.length || !(await savedFirst())) return;
    setSplitting("*");
    let moved = 0;
    try {
      const plans: FunctionSplitResult[] = [];
      for (const name of names) plans.push(await api.splitFunction(name, true));
      const answer = await confirm({
        title: `Give ${names.length} functions their own folder?`,
        body: <SplitPlan plans={plans} />,
        confirmLabel: `Move ${names.length} functions`,
      });
      if (answer !== "confirm") return;
      let last: FunctionSplitResult | null = null;
      for (const name of names) {
        last = await api.splitFunction(name);
        moved++;
      }
      if (last) setProject(last.project);
      toast(`Moved ${moved} functions to their own folders`, "ok");
    } catch (exc) {
      toast(moved ? `Moved ${moved} of ${names.length}, then: ${errorMessage(exc)}` : errorMessage(exc), "err");
      if (moved) await reload().catch(() => undefined);
    } finally {
      setSplitting(null);
      loadShared();
    }
  };
  const rows: Row[] = Object.entries(asObject(draft.functions)).map(([name, fn]) => ({ name, fn: asObject(fn) }));
  const needle = q.trim().toLowerCase();
  const visible = rows.filter(
    (r) =>
      !needle ||
      [r.name, str(r.fn.handler), str(r.fn.description), ...asArray(r.fn.events).map(eventSummary)].join(" ").toLowerCase().includes(needle),
  );

  const remove = async (name: string) => {
    const usedBy = workflowsUsing(draft, name);
    const answer = await confirm({
      title: `Delete function ${name}?`,
      body: usedBy.length ? (
        <p>
          <b>Used by workflow{usedBy.length > 1 ? "s" : ""} {usedBy.join(", ")}</b>. Those workflows won't validate until you
          point their task states at another function. The handler code is not deleted.
        </p>
      ) : (
        <p>The function and its triggers are removed from pskit.yml. The handler code is not deleted.</p>
      ),
      confirmLabel: "Delete",
      danger: true,
    });
    if (answer !== "confirm") return;
    let raw: Json = renameInPlacement(setIn(draft, ["functions", name], undefined) as JsonObject, name, null);
    for (const [key, res] of Object.entries(asObject(draft.resources))) {
      const list = asArray(asObject(res).functions);
      if (list.includes(name)) raw = setIn(raw, ["resources", key, "functions"], list.filter((f) => f !== name));
    }
    replace(raw as JsonObject);
    forgetHandlerStub(str(asObject(asObject(draft.functions)[name]).handler));
    toast(`Deleted ${name} (not saved yet)`, "info");
  };

  const columns: Column<Row>[] = [
    {
      key: "name",
      header: "Function",
      sortValue: (r) => r.name,
      render: (r) => (
        <div className="cell-name">
          <a href={href("functions", r.name)}>
            <b>{r.name}</b>
          </a>
          {r.fn.description ? <span className="muted small">{str(r.fn.description)}</span> : null}
          {issuesAt(["functions", r.name]).some((i) => i.level === "error") && <span className="badge badge-err">error</span>}
          <GroupBadge placement={placement} fn={r.name} />
          {(() => {
            const sf = sharedOf(r);
            if (!sf) return null;
            const tip = placement
              ? `${sf.file} also holds ${sf.others.join(", ")}: every server running any of them gets all of it`
              : `${sf.file} also holds ${sf.others.join(", ")}: they share its code and the project's requirements.txt`;
            return (
              <span className="badge badge-warn" title={tip} aria-label={`shared file: ${tip}`} tabIndex={0}>
                shared file
              </span>
            );
          })()}
        </div>
      ),
    },
    { key: "kind", header: "Kind", sortValue: (r) => functionKind(r.fn), render: (r) => <span className="badge badge-accent">{functionKind(r.fn)}</span> },
    {
      key: "enabled",
      header: "Deploy",
      sortValue: (r) => (isEnabled(draft, providerName, "functions", r.name) ? 0 : 1),
      render: (r) => (
        <span onClick={(e) => e.stopPropagation()}>
          <EnableControl section="functions" name={r.name} compact />
        </span>
      ),
    },
    {
      key: "triggers",
      header: "Triggers",
      render: (r) => {
        const evs = asArray(r.fn.events);
        return evs.length ? (
          <span className="chips">
            {evs.map((e, i) => (
              <Chip key={i} accent={normalizeEvent(e)?.type === "http"}>
                {eventSummary(e)}
              </Chip>
            ))}
          </span>
        ) : (
          <span className="muted">direct invoke</span>
        );
      },
    },
    {
      key: "runtime",
      header: "Runtime",
      render: (r) => {
        const prov = asObject(draft.provider);
        const part = (own: Json | undefined, inherited: string, unit = "") =>
          own !== undefined && own !== null && own !== "" ? (
            <b>{str(own) + unit}</b>
          ) : (
            <span className="muted" title="inherited from provider">{inherited + unit}</span>
          );
        return (
          <span className="mono small nowrap">
            {part(r.fn.runtime, str(prov.runtime, provider?.default_runtime || "python3.12"))} · {part(r.fn.memory, str(prov.memory, "256"), " MB")} ·{" "}
            {part(r.fn.timeout, str(prov.timeout, "30"), " s")}
          </span>
        );
      },
    },
    { key: "handler", header: "Handler", sortValue: (r) => str(r.fn.handler), render: (r) => <span className="mono small">{str(r.fn.handler)}</span> },
    {
      key: "actions",
      header: "",
      className: "nowrap",
      render: (r) => (
        <span className="row-gap row-actions" onClick={(e) => e.stopPropagation()}>
          <a className="btn btn-sm" href={href("test", r.name)} title="Send a test event">
            Test
          </a>
          <a className="btn btn-sm" href={href("code", handlerFile(str(r.fn.handler)))} title="Open handler code">
            Code
          </a>
          {sharedOf(r) && (
            <button
              type="button"
              className="btn btn-sm"
              disabled={splitting !== null}
              title={`Move ${r.name} out of ${sharedOf(r)?.file} into functions/${r.name.replace(/-/g, "_")}/ with its own requirements.txt`}
              onClick={() => void splitOne(r.name)}
            >
              {splitting === r.name ? "Moving…" : "Own folder"}
            </button>
          )}
          <button type="button" className="btn btn-sm" onClick={() => duplicate(r)}>
            Duplicate
          </button>
          <button type="button" className="btn btn-sm btn-danger" onClick={() => void remove(r.name)}>
            Delete
          </button>
        </span>
      ),
    },
  ];

  const duplicate = (r: Row) => {
    const name = uniqueName(`${r.name}-copy`, Object.keys(asObject(draft.functions)));
    edit(["functions", name], { ...r.fn, events: asArray(r.fn.events).filter((e) => normalizeEvent(e)?.type !== "http") }, { coalesce: false });
    toast(`Created ${name} (HTTP routes were not copied, they must be unique)`, "info");
    navigate("functions", name);
  };

  return (
    <div className="page">
      <PageHeader
        title="Functions"
        subtitle="Each function is a handler plus the triggers that call it."
        actions={
          <a className="btn btn-primary" href={href("functions", "new")}>
            + Create function
          </a>
        }
      />
      {placement && sharedNames.length > 0 && (
        <div className="hint-box warn split-bar">
          <div className="grow">
            <b>
              {sharedNames.length} function{sharedNames.length === 1 ? " shares" : "s share"} a code file
            </b>{" "}
            ({sharedNames.join(", ")}): every server running one of them gets the whole file and the project&apos;s requirements.txt.
            {splitWarnings.map((w, i) => (
              <div key={i} className="small">
                {w.message}
              </div>
            ))}
          </div>
          <button type="button" className="btn btn-sm btn-primary" disabled={splitting !== null} onClick={() => void splitAll()}>
            {splitting === "*" ? "Moving…" : "Give each function its own folder"}
          </button>
        </div>
      )}
      <div className="toolbar">
        <SearchInput value={q} onChange={setQ} placeholder="Search name, handler, trigger…" />
      </div>
      <div className="card">
        <DataTable
          columns={columns}
          rows={visible}
          rowKey={(r) => r.name}
          onRowClick={(r) => navigate("functions", r.name)}
          emptyTitle={rows.length ? "No function matches" : "No functions yet"}
          emptyHint={
            rows.length ? undefined : (
              <a className="btn btn-primary" href={href("functions", "new")}>
                Create your first function
              </a>
            )
          }
        />
      </div>
      {generated.size > 0 && (
        <p className="muted small">
          Plus {generated.size} generated function{generated.size > 1 ? "s" : ""} ({Array.from(generated).join(", ")}) that run embedded
          workflows. pskit adds those itself.
        </p>
      )}
    </div>
  );
}

/** Default name of a new function. */
function name0(functions: JsonObject): string {
  return uniqueName("my-function", Object.keys(functions));
}

/** `my-func` -> `functions.my_func.handler.main` (Python) / `functions.my_func.index.main` (Node.js). */
export function subprojectHandler(name: string, language: "python" | "node"): string {
  const folder = name.replace(/-/g, "_") || "my_function";
  return `functions.${folder}.${language === "node" ? "index" : "handler"}.main`;
}

/** The folder of a sub-project handler (`functions.resize.handler.main` -> `functions/resize`), "" for none. */
function subprojectFolder(handler: string): string {
  if (!HANDLER_RE.test(handler)) return "";
  return handler.replace(":", ".").split(".").slice(0, -2).join("/");
}

export function handlerFile(handler: string): string {
  if (!HANDLER_RE.test(handler)) return "";
  const module = handler.replace(":", ".").split(".").slice(0, -1).join("/");
  return `${module}.py`;
}

// --------------------------------------------------------------------- wizard

type Step = "basics" | "triggers" | "settings" | "review";
const STEPS: { id: Step; label: string }[] = [
  { id: "basics", label: "Basics" },
  { id: "triggers", label: "Triggers" },
  { id: "settings", label: "Environment & permissions" },
  { id: "review", label: "Review" },
];

function FunctionWizard({ name: existing }: { name: string | null }) {
  const studio = useStudio();
  const { draft, meta, provider, providerName, replace, issuesAt, state } = studio;
  const toast = useToast();
  const confirm = useConfirm();
  const functions = asObject(draft.functions);
  const original = existing ? asObject(functions[existing]) : null;
  const [name, setName] = useState(existing || name0(functions));
  const language = languageOf(str(asObject(draft.provider).runtime, provider?.default_runtime || "python3.12"));
  // New functions default to their own folder (functions/<name>/) with their own requirements.txt / package.json.
  const [subproject, setSubproject] = useState(!existing);
  const suggestHandler = (n: string, sub: boolean) => (sub ? subprojectHandler(n, language) : defaultHandler(n, language));
  const [fn, setFn] = useState<JsonObject>(() => (original ? { ...original } : { handler: suggestHandler(name0(functions), true) }));
  const [handlerTouched, setHandlerTouched] = useState(!!existing);
  const [events, setEvents] = useState<NormalEvent[]>(() =>
    asArray(original?.events)
      .map(normalizeEvent)
      .filter((e): e is NormalEvent => !!e),
  );
  const [openEvent, setOpenEvent] = useState<number | null>(events.length ? 0 : null);
  const [step, setStep] = useState<Step>("basics");
  const [stubNow, setStubNow] = useState(true);
  // Triggers switched off on the current provider only (providers.<cloud>.functions.<name>.events).
  const [skipped, setSkipped] = useState<Set<number>>(() => {
    const over = existing ? getIn(draft, ["providers", providerName, "functions", existing, "events"]) : undefined;
    if (!Array.isArray(over)) return new Set();
    const base = asArray(original?.events);
    return new Set(base.map((e, i) => (over.some((o) => deepEqual(o, e)) ? -1 : i)).filter((i) => i >= 0));
  });
  const [showLogs, setShowLogs] = useState(false);
  const onprem = providerName === "onprem";
  const placement = onprem ? readPlacement(draft) : null;
  const [runsOn, setRunsOn] = useState<RunsOnChoice>(() => initialRunsOn(placement, existing || ""));
  const targets = usePlacementTargets(onprem);
  const { deployed } = useOnPremServers(onprem, state.target?.stage || str(asObject(draft.provider).stage, "dev"));
  // The default group's machine when it has no target of its own: pskit.yml's deploy, else where the stage was deployed.
  const defaultWhere = deployTargetWhere(
    draft,
    deployed?.server ? `server:${deployed.server}` : deployed && !deployed.cluster && deployed.method === "local" ? "local" : "",
  );
  const runsOnErrs = onprem ? runsOnErrors(draft, runsOn, defaultWhere) : {};
  const [busy, setBusy] = useState(false);

  if (existing && !original) {
    return (
      <div className="page">
        <PageHeader title="Function not found" subtitle={`There is no function named ${existing}.`} />
        <a className="btn" href={href("functions")}>
          ← Back to functions
        </a>
      </div>
    );
  }

  const depFile = language === "node" ? "package.json" : "requirements.txt";
  const nameTaken = name !== existing && name in functions;
  const nameError = !NAME_RE.test(name) ? "start with a letter; letters, digits, - and _ (max 63)" : nameTaken ? "a function with this name exists" : null;
  const handler = str(fn.handler);
  const handlerError = HANDLER_RE.test(handler) ? null : "use package.module.function, e.g. app.handlers.process";
  const routes = new Set<string>();
  for (const [other, cfg] of Object.entries(functions)) {
    if (other === existing) continue;
    for (const ev of asArray(asObject(cfg).events)) {
      const n = normalizeEvent(ev);
      if (n?.type === "http") routes.add(`${str(n.config.method, "GET").toUpperCase()} ${str(n.config.path, "/").replace(/\/$/, "") || "/"}`);
    }
  }
  const eventErrors = events.map((ev, i) => {
    if (!studio.supports(ev.type) && !skipped.has(i)) return `${provider?.display_name || providerName} has no ${EVENT_INFO[ev.type].label.toLowerCase()} triggers`;
    if (ev.type === "http") {
      const key = `${str(ev.config.method, "GET").toUpperCase()} ${str(ev.config.path, "/").replace(/\/$/, "") || "/"}`;
      if (routes.has(key)) return `route ${key} is already used by another function`;
    }
    if (ev.type === "schedule" && !ev.config.rate && !ev.config.cron) return "pick a rate or a cron expression";
    if ((ev.type === "queue" || ev.type === "topic") && !ev.config.name && !ev.config.resource) return "a name or resource is required";
    if (ev.type === "storage" && !ev.config.bucket && !ev.config.resource) return "a bucket or resource is required";
    if (ev.type === "smtp" && !ev.config.resource) return "pick the SMTP server (an smtp resource) that receives the mail";
    return null;
  });
  const runsOnBad = hasRunsOnErrors(runsOnErrs);
  const blocking = !!nameError || !!handlerError || eventErrors.some(Boolean) || runsOnBad;
  /** Placement after the "Runs on" choice (the function renamed first), for the review diff and the save. */
  const withRunsOn = (raw: JsonObject): JsonObject => {
    if (!onprem) return raw;
    const current = groupOf(readPlacement(raw), name);
    if (runsOn.group !== NEW_GROUP && (!runsOn.group || runsOn.group === current)) return raw;
    return applyRunsOn(raw, name, runsOn);
  };
  // Where the function will run (for the requirements note): the chosen group's target.
  const runsOnLabel =
    runsOn.group === NEW_GROUP
      ? targetLabel(targetBody(runsOn.target))
      : placement
        ? targetLabel(placement.groups.find((g) => g.name === runsOn.group)?.body || {}) || "the deploy target"
        : "";

  const built = (): JsonObject => {
    const out: JsonObject = {};
    for (const [k, v] of Object.entries(fn)) if (v !== undefined && v !== "" && k !== "events") out[k] = v;
    if (events.length) out.events = events.map(eventToRaw);
    return out;
  };

  const updateName = (n: string) => {
    setName(n);
    if (!handlerTouched) setFn((f) => ({ ...f, handler: suggestHandler(n, subproject) }));
  };

  const setField = (key: string, value: Json | undefined) =>
    setFn((f) => {
      const next = { ...f };
      if (value === undefined || value === "") delete next[key];
      else next[key] = value;
      return next;
    });

  const apply = async () => {
    if (blocking) {
      toast("Fix the highlighted fields first", "err");
      return;
    }
    let raw: Json = draft;
    const body = built();
    if (existing && existing !== name) {
      const usedBy = workflowsUsing(draft, existing);
      const ok = await confirm({
        title: `Rename ${existing} to ${name}?`,
        body: usedBy.length ? `Workflow task states in ${usedBy.join(", ")} and resource bindings are updated too.` : "Resource bindings that list it are updated too.",
        confirmLabel: "Rename",
      });
      if (ok !== "confirm") return;
      raw = setIn(raw, ["functions", existing], undefined);
      raw = renameReferences(raw as JsonObject, existing, name);
    }
    // Keep the function's position when editing in place.
    if (existing === name) raw = setIn(raw, ["functions", name], body);
    else raw = setIn(raw, ["functions"], { ...asObject((raw as JsonObject).functions), [name]: body });
    raw = syncProviderOverrides(raw as JsonObject, meta.providers, existing, name, asArray(original?.events), events.map(eventToRaw), providerName, skipped);
    if (existing && existing !== name) raw = renameInPlacement(raw as JsonObject, existing, name);
    raw = withRunsOn(raw as JsonObject);
    replace(raw as JsonObject);
    const sub = !existing && subproject && !!subprojectFolder(str(body.handler));
    const types = events.map((e) => e.type);
    if (!existing || original?.handler !== body.handler) {
      if (stubNow) {
        setBusy(true);
        try {
          const res = await api.ensureHandler(str(body.handler), types, sub);
          toast(res.created ? `Created handler stub in ${res.path}` : `Handler already exists in ${res.path}`, "ok");
        } catch (exc) {
          queueHandlerStub(str(body.handler), types, sub);
          toast(`Couldn't write the handler stub now (${errorMessage(exc)}); it will be created on save`, "warn");
        } finally {
          setBusy(false);
        }
      } else {
        queueHandlerStub(str(body.handler), types, sub);
      }
    }
    toast(existing ? `Updated ${name} (not saved yet)` : `Created ${name} (not saved yet)`, "ok");
    navigate("functions");
  };

  // The review diff also shows placement when "Runs on" changes it.
  const placementBefore = onprem ? getIn(draft, placementPath(draft)) : undefined;
  const placementAfter = onprem
    ? getIn(withRunsOn(existing && existing !== name ? renameInPlacement(draft, existing, name) : draft), placementPath(draft))
    : undefined;
  const placementChanged = JSON.stringify(placementBefore ?? null) !== JSON.stringify(placementAfter ?? null);
  const before = toYaml({
    functions: existing && original ? { [existing]: original } : {},
    ...(placementChanged && placementBefore !== undefined ? { placement: placementBefore } : {}),
  });
  const after = toYaml({ functions: { [name]: built() }, ...(placementChanged && placementAfter !== undefined ? { placement: placementAfter } : {}) });
  const stepIndex = STEPS.findIndex((s) => s.id === step);
  const fieldIssues = (key: string) => (existing ? issuesAt(["functions", existing, key]).map((i) => i.message) : []);

  return (
    <div className="page">
      <PageHeader
        title={existing ? `Edit ${existing}` : "Create function"}
        subtitle={`Target: ${provider?.display_name || providerName}. Triggers the provider can't run are disabled.`}
        actions={
          <>
            <a className="btn" href={href("functions")}>
              Cancel
            </a>
            {existing && (
              <a className="btn" href={href("code", handlerFile(handler))}>
                Open code
              </a>
            )}
            <button type="button" className="btn btn-primary" disabled={blocking || busy} onClick={() => void apply()}>
              {existing ? "Apply changes" : "Create function"}
            </button>
          </>
        }
      />
      <ol className="stepper">
        {STEPS.map((s, i) => (
          <li key={s.id} className={s.id === step ? "active" : i < stepIndex ? "done" : ""}>
            <button type="button" onClick={() => setStep(s.id)}>
              <span className="step-num">{i + 1}</span>
              {s.label}
              {s.id === "basics" && (nameError || handlerError || runsOnBad) && <span className="dot-err" aria-label="has errors" />}
              {s.id === "triggers" && eventErrors.some(Boolean) && <span className="dot-err" aria-label="has errors" />}
            </button>
          </li>
        ))}
      </ol>

      {step === "basics" && (
        <Section title="Basics">
          <div className="form">
            <FormRow label="Function name" required error={nameError} htmlFor="fname">
              <TextInput id="fname" mono autoFocus={!existing} value={name} invalid={!!nameError} onChange={updateName} />
            </FormRow>
            <FormRow label="Deploy" help={existing ? "Disabled functions stay in pskit.yml but are not deployed (everywhere, or only on this provider)." : "Off: kept in pskit.yml but never deployed."}>
              {existing && existing === name ? (
                <EnableControl section="functions" name={existing} />
              ) : (
                <Toggle checked={fn.enabled !== false} label={fn.enabled === false ? "disabled everywhere" : "enabled"} onChange={(b) => setField("enabled", b ? undefined : false)} />
              )}
            </FormRow>
            <FormRow label="Description" htmlFor="fdesc">
              <TextInput id="fdesc" value={str(fn.description)} onChange={(v) => setField("description", v)} placeholder="What does it do?" />
            </FormRow>
            <FormRow
              label="Handler"
              required
              htmlFor="fhandler"
              error={[...(handlerError ? [handlerError] : []), ...fieldIssues("handler")]}
              help={handlerTouched ? undefined : "Derived from the name until you edit it."}
            >
              <TextInput
                id="fhandler"
                mono
                value={handler}
                invalid={!!handlerError}
                onChange={(v) => {
                  setHandlerTouched(true);
                  setField("handler", v);
                }}
              />
            </FormRow>
            {!existing && (
              <FormRow
                label="Dependencies"
                help={
                  <>
                    {!subproject
                      ? "Uses the project's dependencies."
                      : subprojectFolder(handler)
                        ? `Creates ${subprojectFolder(handler)}/${depFile}: this function's own dependencies, installed only with it.`
                        : `Needs a handler in a folder, e.g. ${subprojectHandler(name, language)}`}
                    {onprem && (placement || runsOn.group === NEW_GROUP) && (
                      <span className="help-line">
                        {subproject
                          ? `With placement, its ${depFile} is installed only on the server it runs on${runsOnLabel ? ` (${runsOnLabel})` : ""}.`
                          : `With placement, every server running a function from this shared code gets the project's whole ${depFile}.`}
                      </span>
                    )}
                  </>
                }
              >
                <Toggle
                  checked={subproject}
                  label={`Own folder with its own ${depFile}`}
                  onChange={(on) => {
                    setSubproject(on);
                    if (!handlerTouched) setField("handler", suggestHandler(name, on));
                  }}
                />
              </FormRow>
            )}
            {onprem && (
              <FormRow
                label="Runs on"
                htmlFor="frunson"
                help={
                  placement
                    ? "The placement group (server) this function runs in (provider.options.placement). Functions not listed in a group run on the default group."
                    : "Every function runs on the deploy target. A new group puts this function on another server, cluster or this machine (provider.options.placement)."
                }
              >
                <RunsOnField
                  placement={placement}
                  value={runsOn}
                  onChange={setRunsOn}
                  errors={runsOnErrs}
                  servers={targets.servers}
                  clusters={targets.clusters}
                  onServerAdded={targets.reload}
                />
              </FormRow>
            )}
            <div className="form-grid">
              <FormRow label="Runtime" htmlFor="frt">
                <EnumSelect
                  id="frt"
                  value={str(fn.runtime)}
                  allowEmpty
                  emptyLabel={`inherit (${str(asObject(draft.provider).runtime, provider?.default_runtime || "python3.12")})`}
                  options={(language === "node" ? provider?.node_runtimes || [] : provider?.runtimes.length ? provider.runtimes : ["python3.10", "python3.11", "python3.12", "python3.13"]).map((r) => ({ value: r, label: runtimeLabel(r) }))}
                  onChange={(v) => setField("runtime", v || undefined)}
                />
              </FormRow>
              <FormRow label="Memory (MB)" htmlFor="fmem">
                <ComboInput
                  id="fmem"
                  numeric
                  value={typeof fn.memory === "number" ? String(fn.memory) : ""}
                  options={MEMORY.map((m) => ({ value: String(m), label: memoryLabel(m) }))}
                  emptyLabel={`inherit (${str(asObject(draft.provider).memory, "256")} MB)`}
                  onChange={(v) => setField("memory", v === "" ? undefined : Number(v))}
                />
              </FormRow>
              <FormRow label="Timeout (s)" htmlFor="fto" help={provider ? `max ${provider.max_timeout}s` : undefined} error={fieldIssues("timeout")}>
                <ComboInput
                  id="fto"
                  numeric
                  value={typeof fn.timeout === "number" ? String(fn.timeout) : ""}
                  options={timeoutChoices(provider?.max_timeout).map((s) => ({ value: String(s), label: durationLabel(s) }))}
                  emptyLabel={`inherit (${str(asObject(draft.provider).timeout, "30")} s)`}
                  onChange={(v) => setField("timeout", v === "" ? undefined : Number(v))}
                />
              </FormRow>
              <FormRow label="Architecture">
                <Segmented
                  label="Architecture"
                  value={str(fn.architecture, "inherit")}
                  onChange={(v) => setField("architecture", v === "inherit" ? undefined : v)}
                  options={[
                    { value: "inherit", label: "inherit" },
                    { value: "x86_64", label: "x86_64" },
                    { value: "arm64", label: "arm64" },
                  ]}
                />
              </FormRow>
            </div>
          </div>
        </Section>
      )}

      {step === "triggers" && (
        <>
          <Section title="Add a trigger" hint={`what ${provider?.display_name || providerName} can call this function with`}>
            <div className="trigger-grid">
              {EVENT_TYPES.filter((type) => studio.supports(type)).map((type: EventType) => {
                const info = EVENT_INFO[type];
                const notes = provider?.trigger_support?.[type] || [];
                return (
                  <button
                    key={type}
                    type="button"
                    className="trigger-card"
                    title={info.blurb}
                    onClick={() => {
                      setEvents((evs) => [...evs, defaultEvent(type, name)]);
                      setOpenEvent(events.length);
                    }}
                  >
                    <span className="trigger-icon" aria-hidden="true">
                      {info.icon}
                    </span>
                    <b>{info.label}</b>
                    <span className="muted small">{info.blurb}</span>
                    {notes.length > 0 && (
                      <span className="small warn-text">
                        {notes.length} provider limitation{notes.length > 1 ? "s" : ""}
                      </span>
                    )}
                  </button>
                );
              })}
            </div>
            {EVENT_TYPES.some((type) => !studio.supports(type)) && (
              <p className="muted small">
                Not available on {provider?.display_name || providerName}:{" "}
                {EVENT_TYPES.filter((type) => !studio.supports(type))
                  .map((type) => `${EVENT_INFO[type].label} (${providersSupporting(meta, type).join(", ") || "no provider"})`)
                  .join("; ")}
                .
              </p>
            )}
          </Section>
          {!events.length && <p className="muted pad">No triggers. The function can still be called with invoke() or from a workflow.</p>}
          {events.map((ev, i) => (
            <Section
              key={i}
              title={
                <span className="row-gap">
                  <span aria-hidden="true">{EVENT_INFO[ev.type].icon}</span>
                  {EVENT_INFO[ev.type].label}
                  <span className="muted mono small">{eventSummary(eventToRaw(ev))}</span>
                  {eventErrors[i] && <span className="badge badge-err">fix</span>}
                  {skipped.has(i) && <span className="badge badge-off">off on {provider?.display_name || providerName}</span>}
                </span>
              }
              defaultOpen={openEvent === i}
              actions={
                <>
                  <button
                    type="button"
                    className="btn btn-sm"
                    title={skipped.has(i) ? "Use this trigger again on this provider" : "Keep the trigger for other providers but do not create it on this one"}
                    onClick={() =>
                      setSkipped((s) => {
                        const next = new Set(s);
                        if (next.has(i)) next.delete(i);
                        else next.add(i);
                        return next;
                      })
                    }
                  >
                    {skipped.has(i) ? `Enable on ${provider?.display_name || providerName}` : `Disable on ${provider?.display_name || providerName}`}
                  </button>
                  <button
                    type="button"
                    className="btn btn-sm btn-danger"
                    onClick={() => {
                      setEvents((evs) => evs.filter((_, j) => j !== i));
                      setSkipped((s) => new Set(Array.from(s).filter((j) => j !== i).map((j) => (j > i ? j - 1 : j))));
                      setOpenEvent(null);
                    }}
                  >
                    Remove
                  </button>
                </>
              }
            >
              {eventErrors[i] && (
                <div className="form-error block">
                  {eventErrors[i]}
                  {!studio.supports(ev.type) && <> Use <b>Disable on {provider?.display_name || providerName}</b> to keep it for the other providers.</>}
                </div>
              )}
              {skipped.has(i) && studio.supports(ev.type) && (
                <div className="hint-box">Not created on {provider?.display_name || providerName}; the other providers still get it.</div>
              )}
              {existing && <InlineIssues issues={issuesAt(["functions", existing, "events", i])} />}
              <TriggerForm event={ev} fnName={name} onChange={(next) => setEvents((evs) => evs.map((e, j) => (j === i ? next : e)))} />
            </Section>
          ))}
        </>
      )}

      {step === "settings" && (
        <>
          <Section title="Logging" hint="log level and live logs">
            <div className="form">
              <FormRow label="Log level" help="Sets PSKIT_LOG_LEVEL for this function: ctx.logger output below it is dropped.">
                <Segmented
                  label="Log level"
                  value={str(asObject(fn.environment).PSKIT_LOG_LEVEL, "inherit")}
                  onChange={(lvl) => {
                    const env = { ...asObject(fn.environment) };
                    if (lvl === "inherit") delete env.PSKIT_LOG_LEVEL;
                    else env.PSKIT_LOG_LEVEL = lvl;
                    setField("environment", Object.keys(env).length ? env : undefined);
                  }}
                  options={["inherit", "DEBUG", "INFO", "WARNING", "ERROR"].map((l) => ({ value: l, label: l === "inherit" ? `inherit (${str(asObject(asObject(draft.provider).environment).PSKIT_LOG_LEVEL, "INFO")})` : l }))}
                />
              </FormRow>
              <FormRow label="Live logs" help={existing ? `From the deployed ${state.target?.provider || providerName}/${state.target?.stage || "dev"} (top bar).` : "Available after the function is created and deployed."}>
                {existing ? (
                  <Toggle checked={showLogs} label={showLogs ? "showing" : "off"} onChange={setShowLogs} />
                ) : (
                  <span className="muted">not deployed yet</span>
                )}
              </FormRow>
            </div>
            {showLogs && existing && (
              <DeployedLogs provider={state.target?.provider || providerName} stage={state.target?.stage || "dev"} functions={[existing]} only={existing} streams />
            )}
            {existing && (
              <p className="muted small">
                All functions: <a href={href("logs")}>Logs</a> page.
              </p>
            )}
          </Section>
          <Section title="Environment variables" hint="merged over the provider-wide ones">
            <KeyValueEditor value={asObject(fn.environment)} keyPattern={/^[A-Za-z_][A-Za-z0-9_]*$/} onChange={(v) => setField("environment", v)} />
          </Section>
          <Section title="Concurrency & tags" defaultOpen={fn.concurrency !== undefined || !!fn.tags}>
            <div className="form">
              <FormRow label="Reserved concurrency / max instances" help="Leave empty for the provider default.">
                <NumberInput integer min={0} value={typeof fn.concurrency === "number" ? fn.concurrency : undefined} onChange={(v) => setField("concurrency", v)} />
              </FormRow>
              <FormRow label="Tags">
                <KeyValueEditor value={asObject(fn.tags)} secrets={false} keyPlaceholder="tag" addLabel="Add tag" onChange={(v) => setField("tags", v)} />
              </FormRow>
            </div>
          </Section>
          <IamSection value={asObject(fn.iam)} onChange={(v) => setField("iam", v)} />
          {(meta.function_fields || []).length > 0 && (
            <Section title="Provider-specific options" defaultOpen={!!fn.options} hint="functions.<name>.options">
              <FieldForm
                fields={meta.function_fields || []}
                value={asObject(fn.options)}
                idPrefix="fopt"
                onChange={(k, v) => setField("options", (() => {
                  const o = { ...asObject(fn.options) };
                  if (v === undefined) delete o[k];
                  else o[k] = v;
                  return Object.keys(o).length ? o : undefined;
                })())}
              />
            </Section>
          )}
        </>
      )}

      {step === "review" && (
        <Section title="Changes to pskit.yml">
          <DiffView before={before} after={after} />
          <div className="review-foot">
            <Toggle checked={stubNow} onChange={setStubNow} label="Create the handler stub in the code now (otherwise when you save)" />
            {blocking && <div className="form-error">Some steps have errors. Fix them before creating the function.</div>}
          </div>
        </Section>
      )}

      <div className="wizard-nav">
        <button type="button" className="btn" disabled={stepIndex === 0} onClick={() => setStep(STEPS[stepIndex - 1].id)}>
          ← Back
        </button>
        {stepIndex < STEPS.length - 1 ? (
          <button type="button" className="btn btn-primary" onClick={() => setStep(STEPS[stepIndex + 1].id)}>
            Next: {STEPS[stepIndex + 1].label} →
          </button>
        ) : (
          <button type="button" className="btn btn-primary" disabled={blocking || busy} onClick={() => void apply()}>
            {existing ? "Apply changes" : "Create function"}
          </button>
        )}
      </div>
    </div>
  );
}

function renameReferences(raw: JsonObject, from: string, to: string): JsonObject {
  const fixStates = (def: Json): Json => {
    const d = asObject(def);
    const states: JsonObject = {};
    for (const [k, st] of Object.entries(asObject(d.states))) {
      const s = { ...asObject(st) };
      if (s.function === from) s.function = to;
      if (Array.isArray(s.branches)) s.branches = s.branches.map(fixStates);
      if (s.iterator) s.iterator = fixStates(s.iterator);
      states[k] = s;
    }
    return { ...d, states };
  };
  let out: Json = raw;
  for (const [wf, def] of Object.entries(asObject(raw.workflows))) out = setIn(out, ["workflows", wf], fixStates(def));
  for (const [key, res] of Object.entries(asObject(raw.resources))) {
    const list = asArray(asObject(res).functions);
    if (list.includes(from)) out = setIn(out, ["resources", key, "functions"], list.map((f) => (f === from ? to : f)));
  }
  return out as JsonObject;
}

function IamSection({ value, onChange }: { value: JsonObject; onChange: (v: JsonObject | undefined) => void }) {
  const statements = asArray(value.statements).map(asObject);
  const commit = (next: JsonObject[], role = value.role) => {
    const out: JsonObject = {};
    if (next.length) out.statements = next;
    if (role) out.role = role;
    onChange(Object.keys(out).length ? out : undefined);
  };
  return (
    <Section title="Permissions (IAM)" defaultOpen={false} hint="advanced">
      <div className="form">
        <FormRow label="Existing role" help="Use an existing role / service account instead of the one pskit creates.">
          <TextInput mono value={str(value.role)} placeholder="arn:aws:iam::123456789012:role/my-role" onChange={(r) => commit(statements, r || undefined)} />
        </FormRow>
        {statements.map((st, i) => (
          <div key={i} className="iam-row card card-pad">
            <div className="row-gap">
              <Segmented
                label="Effect"
                value={str(st.effect, "Allow")}
                onChange={(e) => commit(statements.map((s, j) => (j === i ? { ...s, effect: e } : s)))}
                options={[
                  { value: "Allow", label: "Allow" },
                  { value: "Deny", label: "Deny" },
                ]}
              />
              <span className="grow" />
              <button type="button" className="btn btn-sm btn-danger" onClick={() => commit(statements.filter((_, j) => j !== i))}>
                Remove
              </button>
            </div>
            <FormRow label="Actions" help="comma separated, e.g. s3:GetObject, dynamodb:Query">
              <TextInput
                mono
                value={asArray(st.actions).map((a) => str(a)).join(", ")}
                onChange={(t) => commit(statements.map((s, j) => (j === i ? { ...s, actions: t.split(",").map((x) => x.trim()).filter(Boolean) } : s)))}
              />
            </FormRow>
            <FormRow label="Resources" help="comma separated ARNs; empty = *">
              <TextInput
                mono
                value={asArray(st.resources).map((a) => str(a)).join(", ")}
                onChange={(t) => {
                  const list = t.split(",").map((x) => x.trim()).filter(Boolean);
                  commit(
                    statements.map((s, j) => {
                      if (j !== i) return s;
                      const { resources: _old, ...restSt } = s;
                      void _old;
                      return list.length ? { ...restSt, resources: list } : restSt;
                    }),
                  );
                }}
              />
            </FormRow>
          </div>
        ))}
        <button type="button" className="btn btn-sm" onClick={() => commit([...statements, { effect: "Allow", actions: [] }])}>
          + Add statement
        </button>
      </div>
    </Section>
  );
}

/**
 * Keep `providers.<cloud>.functions.<fn>.events` in step with the edited triggers.
 * On `current`, `skipped` (indexes into `after`) decides the list; on other clouds, triggers that were
 * skipped there stay skipped and new ones are added when that cloud supports them. Renames move the override.
 */
function syncProviderOverrides(
  raw: JsonObject,
  providers: ProviderMeta[],
  from: string | null,
  to: string,
  before: Json[],
  after: Json[],
  current: string,
  skipped: Set<number>,
): JsonObject {
  let out: Json = raw;
  for (const p of providers) {
    const path = ["providers", p.name, "functions"];
    const old = from ? asObject(getIn(out, [...path, from])) : {};
    let entry: JsonObject = { ...old };
    if (p.name === current) {
      const kept = after.filter((_, i) => !skipped.has(i));
      if (skipped.size) entry.events = kept;
      else delete entry.events;
    } else if (Array.isArray(old.events)) {
      const overrideList = old.events;
      const wasSkipped = (e: Json) => before.some((b) => deepEqual(b, e)) && !overrideList.some((o) => deepEqual(o, e));
      entry.events = after.filter((e) => !wasSkipped(e) && p.capabilities.includes(normalizeEvent(e)?.type || ""));
      if (deepEqual(entry.events, after)) delete entry.events;
    }
    if (from && from !== to) out = setIn(out, [...path, from], undefined);
    if (Object.keys(entry).length) out = setIn(out, [...path, to], entry);
    else if (getIn(out, [...path, to]) !== undefined) out = setIn(out, [...path, to], undefined);
    entry = asObject(getIn(out, path));
    if (getIn(out, path) !== undefined && !Object.keys(entry).length) out = setIn(out, path, undefined);
    if (getIn(out, ["providers", p.name]) !== undefined && !Object.keys(asObject(getIn(out, ["providers", p.name]))).length) {
      out = setIn(out, ["providers", p.name], undefined);
    }
  }
  if ((out as JsonObject).providers !== undefined && !Object.keys(asObject((out as JsonObject).providers)).length) out = setIn(out, ["providers"], undefined);
  return out as JsonObject;
}
