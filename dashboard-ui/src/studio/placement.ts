import type { Json, JsonObject } from "./types";
import { asArray, asObject, getIn, isObject, setIn, str, type Path } from "./util";

/**
 * provider.options.placement (on premises): groups of functions on different servers, one project.
 * Pure draft edits shared by the Deploy page's editor (components/Placement.tsx) and the function editor.
 *
 *   placement:
 *     default: api                 # functions not listed (and every workflow) run here
 *     groups:
 *       api: {server: app1}        # or {cluster: prod} or {local: true}; only the default group may omit it
 *       gpu: {server: gpu1, functions: [resize, ocr], port: 8081, advertise: http://10.0.0.9:8081}
 */

export const GROUP_RE = /^[a-z][a-z0-9-]{0,20}$/;
export const GROUP_HINT = "a lowercase letter, then letters, digits or - (max 21)";
export const TARGET_KEYS = ["server", "cluster", "local"] as const;
/** Port of an on-prem host without `port` (provider.options.port or a group's port). */
export const DEFAULT_PORT = 8080;
/** Name of the default group when the function editor creates the first placement. */
export const DEFAULT_GROUP = "main";

/** Where placement is written: a `providers.onprem.options` override when one already holds it, else provider.options. */
export function placementPath(draft: JsonObject): Path {
  const override = ["providers", "onprem", "options", "placement"];
  return getIn(draft, override) !== undefined ? override : ["provider", "options", "placement"];
}

export interface PlacementGroup {
  name: string;
  body: JsonObject;
  /** Functions listed under the group. */
  listed: string[];
}

export interface Placement {
  path: Path;
  raw: JsonObject;
  default: string;
  groups: PlacementGroup[];
  /** Every listed function -> its group (unlisted functions run on `default`). */
  listedIn: Record<string, string>;
}

/** The project's placement, or null when every function runs on one target (no `groups`). */
export function readPlacement(draft: JsonObject): Placement | null {
  const path = placementPath(draft);
  const raw = asObject(getIn(draft, path));
  const groupsRaw = asObject(raw.groups);
  const names = Object.keys(groupsRaw);
  if (!names.length) return null;
  const listedIn: Record<string, string> = {};
  const groups = names.map((name) => {
    const body = asObject(groupsRaw[name]);
    const listed = (typeof body.functions === "string" ? [body.functions] : asArray(body.functions)).map((f) => str(f)).filter(Boolean);
    for (const fn of listed) if (!(fn in listedIn)) listedIn[fn] = name;
    return { name, body, listed };
  });
  const def = str(raw.default);
  return { path, raw, default: def && names.includes(def) ? def : names[0], groups, listedIn };
}

/** The group a function runs in (its listed group, else the default group); "" without placement. */
export function groupOf(placement: Placement | null, fn: string): string {
  if (!placement) return "";
  return placement.listedIn[fn] || placement.default;
}

/** User functions placement can list: generated `<workflow>-orchestrator` functions always run on the default group. */
export function placeableFunctions(draft: JsonObject): string[] {
  return Object.keys(asObject(draft.functions)).filter((f) => !f.endsWith("-orchestrator"));
}

export function clusterName(v: Json | undefined): string {
  return typeof v === "string" ? v : str(asObject(v).name);
}

/** `{server: app1}` -> "app1", `{cluster: prod}` -> "cluster prod", `{local: true}` -> "this machine", `{}` -> "". */
export function targetLabel(body: JsonObject): string {
  if (body.server) return str(body.server);
  if (body.cluster) return `cluster ${clusterName(body.cluster)}`;
  if (body.local) return "this machine";
  return "";
}

/** `{server: app1}` -> "server:app1", `{cluster: prod}` -> "cluster:prod", `{local: true}` -> "local", `{}` -> "". */
export function targetValue(body: JsonObject): string {
  if (body.server) return `server:${str(body.server)}`;
  if (body.cluster) return `cluster:${clusterName(body.cluster)}`;
  if (body.local) return "local";
  return "";
}

/** The inverse of `targetValue`: the group keys of a target ("" -> {}). */
export function targetBody(value: string): JsonObject {
  if (value === "local") return { local: true };
  if (value.startsWith("server:") && value.length > 7) return { server: value.slice(7) };
  if (value.startsWith("cluster:") && value.length > 8) return { cluster: value.slice(8) };
  return {};
}

/** Clean group body: drop empty values (and an empty functions list). */
export function clean(body: JsonObject): JsonObject {
  const out: JsonObject = {};
  for (const [k, v] of Object.entries(body)) {
    if (v === undefined || v === null || v === "" || v === false) continue;
    if (Array.isArray(v) && !v.length) continue;
    out[k] = v;
  }
  return out;
}

export function withKey(body: JsonObject, key: string, value: Json | undefined): JsonObject {
  const next = { ...body };
  if (value === undefined) delete next[key];
  else next[key] = value;
  return next;
}

/** Write `groups` (ordered) and `default` back to the draft. */
export function writePlacement(draft: JsonObject, path: Path, def: string, groups: { name: string; body: JsonObject }[]): JsonObject {
  const raw = asObject(getIn(draft, path));
  const out: JsonObject = {};
  for (const [k, v] of Object.entries(raw)) if (k !== "default" && k !== "groups") out[k] = v;
  out.default = def;
  out.groups = Object.fromEntries(groups.map((g) => [g.name, clean(g.body)]));
  return setIn(draft, path, out) as JsonObject;
}

/**
 * Put `fn` in `group`: it leaves every group's `functions` list and joins `group`'s, unless `group` is the default
 * group (unlisted functions run there). `create` adds a new group first. Without placement, one is created only
 * when a group is created: the current deploy target becomes the default group `defaultName` (no target needed).
 */
export function assignFunction(
  draft: JsonObject,
  fn: string,
  group: string,
  create: { name: string; body: JsonObject } | null = null,
  defaultName = DEFAULT_GROUP,
): JsonObject {
  const p = readPlacement(draft);
  if (!p && !create) return draft;
  const path = p ? p.path : placementPath(draft);
  const def = p ? p.default : defaultName;
  const groups = p
    ? p.groups.map((g) => ({ name: g.name, body: { ...g.body, functions: g.listed.filter((f) => f !== fn) } as JsonObject }))
    : [{ name: def, body: {} as JsonObject }];
  if (create && !groups.some((g) => g.name === create.name)) groups.push({ name: create.name, body: { ...create.body } });
  if (group !== def) {
    const g = groups.find((x) => x.name === group);
    if (g) {
      const listed = asArray(g.body.functions).map((f) => str(f)).filter((f) => f && f !== fn);
      g.body = { ...g.body, functions: [...listed, fn] };
    }
  }
  return writePlacement(draft, path, def, groups);
}

/** Move `fn` into `group` (the default group: unlisted). Returns the new draft (unchanged without placement). */
export function moveFunction(draft: JsonObject, fn: string, group: string): JsonObject {
  if (!readPlacement(draft)) return draft;
  return assignFunction(draft, fn, group);
}

/** Keep placement in step with a function rename / delete (`to` null). */
export function renameInPlacement(draft: JsonObject, from: string, to: string | null): JsonObject {
  const p = readPlacement(draft);
  if (!p || !(from in p.listedIn)) return draft;
  const groups = p.groups.map((g) => ({
    name: g.name,
    body: { ...g.body, functions: g.listed.flatMap((f) => (f !== from ? [f] : to ? [to] : [])) },
  }));
  return writePlacement(draft, p.path, p.default, groups);
}

/** Drop `providers.onprem.options` / `providers.onprem` / `providers` when left empty. */
export function prune(draft: JsonObject): JsonObject {
  let out: Json = draft;
  for (const path of [["providers", "onprem", "options"], ["providers", "onprem"], ["providers"], ["provider", "options"]]) {
    const v = getIn(out, path);
    if (isObject(v) && !Object.keys(v).length) out = setIn(out, path, undefined);
  }
  return out as JsonObject;
}

export function nextGroupName(taken: string[]): string {
  for (const base of ["workers", "gpu", "batch"]) if (!taken.includes(base)) return base;
  let i = 2;
  while (taken.includes(`group-${i}`)) i++;
  return `group-${i}`;
}

// ------------------------------------------------------------------------------------------------ ports

/** The port a group's host listens on: its own `port`, else provider.options.port, else 8080. */
export function effectivePort(draft: JsonObject, body: JsonObject): number {
  if (typeof body.port === "number") return body.port;
  const port = getIn(draft, ["provider", "options", "port"]);
  return typeof port === "number" ? port : DEFAULT_PORT;
}

/**
 * Which machine a group runs on, for port clashes: "server:NAME", "local", or "" (a cluster, or unknown).
 * `defaultWhere` is the default group's machine when it has no target of its own (the deploy target).
 */
export function groupWhere(body: JsonObject, isDefault: boolean, defaultWhere = ""): string {
  if (body.server) return `server:${str(body.server)}`;
  if (body.local) return "local";
  if (body.cluster) return "";
  return isDefault ? defaultWhere : "";
}

/** The default group's machine without a target: provider.options.deploy (server, or a local deploy), else `fallback`. */
export function deployTargetWhere(draft: JsonObject, fallback = ""): string {
  const deploy = getIn(draft, ["provider", "options", "deploy"]);
  if (isObject(deploy)) {
    if (deploy.server) return `server:${str(deploy.server)}`;
    if (deploy.method === "local") return "local";
  }
  if (getIn(draft, ["provider", "options", "cluster"])) return "";
  return fallback;
}

export interface PortClash {
  /** The group already on that machine and port. */
  group: string;
  port: number;
  /** The next port no group on that machine uses. */
  suggestion: number;
}

/** Does a new group on `target` ("server:x" / "local" / "cluster:x") with `port` clash with an existing group? */
export function portClash(draft: JsonObject, target: string, port: number | undefined, defaultWhere = ""): PortClash | null {
  const where = groupWhere(targetBody(target), false);
  if (!where) return null;
  const p = readPlacement(draft);
  const groups = p ? p.groups.map((g) => ({ name: g.name, body: g.body, isDefault: g.name === p.default })) : [{ name: DEFAULT_GROUP, body: {}, isDefault: true }];
  const used = new Map<number, string>();
  for (const g of groups) {
    if (groupWhere(g.body, g.isDefault, defaultWhere) === where) used.set(effectivePort(draft, g.body), g.name);
  }
  const mine = port ?? effectivePort(draft, {});
  const clash = used.get(mine);
  if (!clash) return null;
  let suggestion = mine + 1;
  while (used.has(suggestion) && suggestion < 65535) suggestion++;
  return { group: clash, port: mine, suggestion };
}

// ------------------------------------------------------------------------------------------------ "Runs on"

/** The `<select>` value of "+ New group…". */
export const NEW_GROUP = "+new";

/** What the function editor's "Runs on" field holds. */
export interface RunsOnChoice {
  /** An existing group, "" for the deploy target without placement, or NEW_GROUP. */
  group: string;
  /** NEW_GROUP: its name, target ("server:x" / "cluster:x" / "local") and optional port. */
  name: string;
  target: string;
  port?: number;
  /** NEW_GROUP without placement yet: the name the current deploy target's group gets. */
  defaultName: string;
}

export function initialRunsOn(placement: Placement | null, fn: string): RunsOnChoice {
  return { group: groupOf(placement, fn), name: "", target: "", port: undefined, defaultName: DEFAULT_GROUP };
}

export interface RunsOnErrors {
  name?: string;
  target?: string;
  port?: string;
  defaultName?: string;
  /** Set with `port`: the next free port on that machine. */
  suggestPort?: number;
}

export function runsOnErrors(draft: JsonObject, choice: RunsOnChoice, defaultWhere = ""): RunsOnErrors {
  if (choice.group !== NEW_GROUP) return {};
  const out: RunsOnErrors = {};
  const p = readPlacement(draft);
  const taken = p ? p.groups.map((g) => g.name) : [];
  if (!GROUP_RE.test(choice.name)) out.name = GROUP_HINT;
  else if (taken.includes(choice.name)) out.name = `group ${choice.name} exists: pick it above`;
  else if (!p && choice.name === choice.defaultName) out.name = "the other group already has this name";
  if (!p) {
    if (!GROUP_RE.test(choice.defaultName)) out.defaultName = GROUP_HINT;
  }
  if (!targetValue(targetBody(choice.target))) out.target = "pick a server, a cluster or this machine";
  else {
    const clash = portClash(draft, choice.target, choice.port, defaultWhere);
    if (clash) {
      out.port = `group ${clash.group} already uses port ${clash.port} there: use another port, e.g. ${clash.suggestion}`;
      out.suggestPort = clash.suggestion;
    }
  }
  return out;
}

export function hasRunsOnErrors(errors: RunsOnErrors): boolean {
  return !!(errors.name || errors.target || errors.port || errors.defaultName);
}

/** Apply the "Runs on" choice for function `fn` to the draft (after any rename). */
export function applyRunsOn(draft: JsonObject, fn: string, choice: RunsOnChoice): JsonObject {
  if (choice.group === NEW_GROUP) {
    const body: JsonObject = { ...targetBody(choice.target) };
    if (typeof choice.port === "number") body.port = choice.port;
    return assignFunction(draft, fn, choice.name, { name: choice.name, body }, choice.defaultName || DEFAULT_GROUP);
  }
  if (!choice.group) return draft;
  return moveFunction(draft, fn, choice.group);
}

/** Terraform resource of a group's host: `host` (default group) or `host_<group with - as _>`. */
export function hostResource(group: string, def: string): string {
  return group === def ? "host" : `host_${group.replace(/-/g, "_")}`;
}

/** The placement group of a host resource key (`host`, `host_test_02`), or a readable name without placement. */
export function groupOfResource(key: string, placement: Placement | null): string {
  if (key === "host") return placement ? placement.default : "host";
  const x = key.replace(/^host_/, "");
  const found = placement?.groups.find((g) => g.name.replace(/-/g, "_") === x);
  return found ? found.name : x.replace(/_/g, "-");
}
