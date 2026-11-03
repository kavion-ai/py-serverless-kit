import type { EventType, Json, JsonObject } from "./types";

export type PathKey = string | number;
export type Path = PathKey[];

export function isObject(value: unknown): value is JsonObject {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

export function getIn(root: Json | undefined, path: Path): Json | undefined {
  let cur: Json | undefined = root;
  for (const key of path) {
    if (cur === null || cur === undefined) return undefined;
    if (typeof key === "number") {
      if (!Array.isArray(cur)) return undefined;
      cur = cur[key];
    } else {
      if (!isObject(cur)) return undefined;
      cur = cur[key];
    }
  }
  return cur;
}

/** Immutable set. `undefined` deletes the key (and prunes empty parents created on the way is NOT done on purpose). */
export function setIn(root: Json | undefined, path: Path, value: Json | undefined): Json {
  if (!path.length) return value === undefined ? null : value;
  const [key, ...rest] = path;
  if (typeof key === "number") {
    const arr = Array.isArray(root) ? [...root] : [];
    if (value === undefined && !rest.length) {
      arr.splice(key, 1);
      return arr;
    }
    arr[key] = setIn(arr[key], rest, value);
    return arr;
  }
  const obj: JsonObject = isObject(root) ? { ...root } : {};
  if (value === undefined && !rest.length) {
    delete obj[key];
    return obj;
  }
  obj[key] = setIn(obj[key], rest, value);
  return obj;
}

/** Remove keys whose value is undefined/empty-string/empty-object, recursively (keeps false/0/[]). */
export function compact(value: Json): Json {
  if (Array.isArray(value)) return value.map(compact);
  if (!isObject(value)) return value;
  const out: JsonObject = {};
  for (const [k, v] of Object.entries(value)) {
    if (v === undefined || v === "" || v === null) continue;
    const c = compact(v);
    if (isObject(c) && !Object.keys(c).length) continue;
    out[k] = c;
  }
  return out;
}

export function clone<T extends Json>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T;
}

export function deepEqual(a: Json | undefined, b: Json | undefined): boolean {
  return JSON.stringify(a) === JSON.stringify(b);
}

/** Parse a `where` string such as `functions.api.events[0].http` into a path. */
export function parseWhere(where: string): Path {
  const out: Path = [];
  for (const part of where.split(".")) {
    const re = /([^[\]]+)|\[(\d+)\]/g;
    let m: RegExpExecArray | null;
    while ((m = re.exec(part))) {
      if (m[1] !== undefined) out.push(m[1]);
      else out.push(Number(m[2]));
    }
  }
  return out;
}

export function pathKey(path: Path): string {
  return path
    .map((p, i) => (typeof p === "number" ? `[${p}]` : i === 0 ? p : `.${p}`))
    .join("");
}

// --------------------------------------------------------------------- naming

export const NAME_RE = /^[A-Za-z][A-Za-z0-9_-]{0,62}$/;
export const SERVICE_RE = /^[a-z][a-z0-9-]{1,31}$/;
export const HANDLER_RE = /^[A-Za-z_]\w*(\.[A-Za-z_]\w*)*[.:][A-Za-z_]\w*$/;
export const CLASS_RE = /^[A-Za-z_]\w*(\.[A-Za-z_]\w*)*:[A-Za-z_]\w*$/;
export const ENV_RE = /^[A-Za-z_][A-Za-z0-9_]*$/;

export function snake(name: string): string {
  const s = name
    .replace(/([a-z0-9])([A-Z])/g, "$1_$2")
    .replace(/[^A-Za-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "")
    .toLowerCase();
  return /^[a-z_]/.test(s) ? s : `fn_${s}`;
}

export function defaultHandler(name: string, language: "python" | "node" = "python"): string {
  return language === "node" ? `src.handlers.${camel(name) || "handler"}` : `app.handlers.${snake(name) || "handler"}`;
}

/** `my-function` -> `myFunction` (a valid JavaScript identifier). */
export function camel(name: string): string {
  const s = snake(name).replace(/_([a-z0-9])/g, (_m, c: string) => c.toUpperCase());
  return /^[A-Za-z_$]/.test(s) ? s : s ? `_${s}` : "";
}

/** `python` or `node`, from a runtime such as python3.12 / nodejs20. */
export function languageOf(runtime: string): "python" | "node" {
  return runtime.startsWith("nodejs") ? "node" : "python";
}

export function runtimeLabel(runtime: string): string {
  return runtime.startsWith("nodejs") ? `Node.js ${runtime.slice(6)} (${runtime})` : `Python ${runtime.slice(6)} (${runtime})`;
}

export function uniqueName(base: string, taken: Iterable<string>): string {
  const set = new Set(taken);
  if (!set.has(base)) return base;
  for (let i = 2; i < 1000; i++) if (!set.has(`${base}${i}`)) return `${base}${i}`;
  return `${base}-${Date.now()}`;
}

export function envRef(variable: string): string {
  return "${env:" + variable + "}";
}

export function parseEnvRef(value: Json | undefined): string | null {
  if (typeof value !== "string") return null;
  const m = /^\$\{env:([A-Za-z_][A-Za-z0-9_]*)(?:,[^}]*)?\}$/.exec(value.trim());
  return m ? m[1] : null;
}

// --------------------------------------------------------------------- events

export interface NormalEvent {
  type: EventType;
  config: JsonObject;
}

const RATE_RE = /^\s*(\d+)\s+(minute|minutes|hour|hours|day|days)\s*$/i;

/** Expand YAML shorthands (`http: GET /x`, `schedule: 5 minutes`, `queue: jobs`) into object form. */
export function normalizeEvent(raw: Json): NormalEvent | null {
  if (!isObject(raw)) return null;
  const keys = Object.keys(raw);
  if (keys.length !== 1) return null;
  const type = keys[0] as EventType;
  const body = raw[type];
  if (!["http", "schedule", "queue", "storage", "topic", "smtp"].includes(type)) return null;
  if (isObject(body)) return { type, config: { ...body } };
  if (typeof body === "string") {
    if (type === "http") {
      const [a, b] = body.trim().split(/\s+/, 2);
      return { type, config: b ? { method: a.toUpperCase(), path: b } : { path: a || "/" } };
    }
    if (type === "schedule") return { type, config: RATE_RE.test(body) ? { rate: body } : { cron: body } };
    if (type === "storage") return { type, config: { bucket: body } };
    if (type === "smtp") return { type, config: { resource: body } };
    return { type, config: { name: body } };
  }
  return { type, config: {} };
}

export function eventToRaw(ev: NormalEvent): JsonObject {
  return { [ev.type]: compact(ev.config) };
}

export function eventSummary(raw: Json): string {
  const ev = normalizeEvent(raw);
  if (!ev) return "?";
  const c = ev.config;
  switch (ev.type) {
    case "http":
      return `${String(c.method || "GET")} ${String(c.path || "/")}`;
    case "schedule":
      return c.rate ? `every ${String(c.rate)}` : `cron ${String(c.cron || "?")}`;
    case "queue":
      return `queue ${String(c.resource ? `@${c.resource}` : c.name || "?")}`;
    case "storage":
      return `bucket ${String(c.resource ? `@${c.resource}` : c.bucket || "?")}`;
    case "topic":
      return `topic ${String(c.resource ? `@${c.resource}` : c.name || "?")}`;
    case "smtp":
      return `mail @${String(c.resource || "?")}`;
    default:
      return ev.type;
  }
}

export function functionKind(fn: JsonObject): string {
  const events = Array.isArray(fn.events) ? fn.events : [];
  const types = new Set(events.map((e) => normalizeEvent(e)?.type).filter(Boolean));
  if (!types.size) return "invoke-only";
  if (types.size === 1 && types.has("http")) return "http";
  if (types.size === 1 && types.has("schedule")) return "scheduled";
  if (types.has("http")) return "http+event";
  return "event-driven";
}

export function pathParams(path: string): string[] {
  const out: string[] = [];
  const re = /\{([A-Za-z_]\w*)\+?\}/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(path))) out.push(m[1]);
  return out;
}

// --------------------------------------------------------------------- cron

const DOW = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];

/** Human description of a 5-field cron expression (best effort; never throws). */
export function describeCron(expr: string): string {
  const parts = expr.trim().split(/\s+/);
  if (parts.length !== 5) return "needs 5 fields: minute hour day-of-month month day-of-week";
  const [min, hour, dom, mon, dow] = parts;
  const any = (v: string) => v === "*" || v === "?";
  const step = (v: string) => (/^\*\/(\d+)$/.exec(v) || [])[1];
  if (step(min) && any(hour) && any(dom) && any(mon) && any(dow)) return `every ${step(min)} minutes`;
  if (min === "0" && step(hour) && any(dom) && any(mon) && any(dow)) return `every ${step(hour)} hours, on the hour`;
  const time = /^\d+$/.test(min) && /^\d+$/.test(hour) ? `at ${hour.padStart(2, "0")}:${min.padStart(2, "0")}` : null;
  if (time && any(dom) && any(mon) && any(dow)) return `every day ${time}`;
  if (time && any(dom) && any(mon) && /^[0-6](,[0-6])*$/.test(dow)) {
    return `${time} on ${dow
      .split(",")
      .map((d) => DOW[Number(d)])
      .join(", ")}`;
  }
  if (time && any(dom) && any(mon) && dow === "1-5") return `${time} on weekdays`;
  if (time && /^\d+$/.test(dom) && any(mon) && any(dow)) return `${time} on day ${dom} of every month`;
  return `minute ${min}, hour ${hour}, day ${dom}, month ${mon}, weekday ${dow}`;
}

export function validCron(expr: string): boolean {
  const parts = expr.trim().split(/\s+/);
  return parts.length === 5 && parts.every((p) => /^[\d*/,?LW#A-Za-z-]+$/.test(p));
}

// --------------------------------------------------------------------- YAML preview

const PLAIN = /^[A-Za-z_/.][\w./@:{}+-]*( [\w./@:{}+-]+)*$/;
const RESERVED = /^(true|false|yes|no|on|off|null|~|y|n)$/i;

function scalar(value: Json): string {
  if (value === null) return "null";
  if (typeof value === "boolean" || typeof value === "number") return String(value);
  const s = String(value);
  if (s === "") return '""';
  if (PLAIN.test(s) && !RESERVED.test(s) && !/^[\d.+-]/.test(s) && !s.includes(": ") && !s.includes(" #")) return s;
  return JSON.stringify(s);
}

function keyText(key: string): string {
  return /^[A-Za-z_][\w-]*$/.test(key) && !RESERVED.test(key) ? key : JSON.stringify(key);
}

/** Readable YAML for previews and diffs. The server produces the authoritative file. */
export function toYaml(value: Json, indent = 0): string {
  const pad = "  ".repeat(indent);
  if (Array.isArray(value)) {
    if (!value.length) return "[]";
    return value
      .map((item) => {
        if (isObject(item) && Object.keys(item).length) {
          const inner = toYaml(item, indent + 1).replace(/^\s+/, "");
          return `${pad}- ${inner}`;
        }
        if (Array.isArray(item) && item.length) return `${pad}-\n${toYaml(item, indent + 1)}`;
        return `${pad}- ${isObject(item) ? "{}" : Array.isArray(item) ? "[]" : scalar(item)}`;
      })
      .join("\n");
  }
  if (isObject(value)) {
    const keys = Object.keys(value);
    if (!keys.length) return "{}";
    return keys
      .map((k) => {
        const v = value[k];
        if ((isObject(v) && Object.keys(v).length) || (Array.isArray(v) && v.length)) {
          return `${pad}${keyText(k)}:\n${toYaml(v, indent + 1)}`;
        }
        const s = isObject(v) ? "{}" : Array.isArray(v) ? "[]" : scalar(v);
        return `${pad}${keyText(k)}: ${s}`;
      })
      .join("\n");
  }
  return pad + scalar(value);
}

// --------------------------------------------------------------------- diff

export interface DiffLine {
  kind: "same" | "add" | "del";
  text: string;
}

/** Line diff (LCS). Inputs are capped so a huge file can't freeze the page. */
export function diffLines(before: string, after: string): DiffLine[] {
  const a = before.split("\n").slice(0, 3000);
  const b = after.split("\n").slice(0, 3000);
  const n = a.length;
  const m = b.length;
  const dp: Uint16Array[] = [];
  for (let i = 0; i <= n; i++) dp.push(new Uint16Array(m + 1));
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      dp[i][j] = a[i] === b[j] ? dp[i + 1][j + 1] + 1 : Math.max(dp[i + 1][j], dp[i][j + 1]);
    }
  }
  const out: DiffLine[] = [];
  let i = 0;
  let j = 0;
  while (i < n && j < m) {
    if (a[i] === b[j]) {
      out.push({ kind: "same", text: a[i] });
      i++;
      j++;
    } else if (dp[i + 1][j] >= dp[i][j + 1]) {
      out.push({ kind: "del", text: a[i++] });
    } else {
      out.push({ kind: "add", text: b[j++] });
    }
  }
  while (i < n) out.push({ kind: "del", text: a[i++] });
  while (j < m) out.push({ kind: "add", text: b[j++] });
  return out;
}

export function stripAnsi(text: string): string {
  // eslint-disable-next-line no-control-regex
  return text.replace(/\u001b\[[0-9;?]*[ -/]*[@-~]/g, "").replace(/\r(?!\n)/g, "");
}

export function asObject(value: Json | undefined): JsonObject {
  return isObject(value) ? value : {};
}

export function asArray(value: Json | undefined): Json[] {
  return Array.isArray(value) ? value : [];
}

export function str(value: Json | undefined, fallback = ""): string {
  return value === undefined || value === null ? fallback : String(value);
}
