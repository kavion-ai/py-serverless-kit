"use strict";
/**
 * Embedded workflow (state machine) engine: a port of runtime/workflow.py with
 * the same definition dialect, JSON paths, choice operators, retry / catch,
 * parallel and map states, timeout, cancellation and history records.
 *
 * Used by providers without a native orchestrator: the CLI deploys an extra
 * `<workflow>-orchestrator` function whose handler is
 * `pskit_runtime.workflow.orchestrate`, and which calls task handlers
 * in-process (they live in the same bundle).
 */

const { errorName, errorText } = require("./errors");
const { isoformat, round2, nowMs, deepCopy, isPlainObject, randomHex } = require("./util");

const ALL_ERRORS = ["*", "States.ALL"];
const TIMEOUT_ERROR = "States.Timeout";

class WorkflowFailed extends Error {
  constructor(error, cause = "", history = []) {
    super(cause ? `${error}: ${cause}` : error);
    this.name = "WorkflowFailed";
    this.error = error;
    this.cause = cause;
    this.history = history || [];
  }
}

/** Raised between states once `engine.cancel()` was requested. */
class WorkflowCancelled extends WorkflowFailed {
  constructor(history = []) {
    super("States.Cancelled", "execution was cancelled", history);
    this.name = "WorkflowCancelled";
  }
}

// Python exception names, so catch / retry rules written for the Python runtime match.
class KeyError extends Error {
  constructor(message) {
    super(message);
    this.name = "KeyError";
  }
}
class ValueError extends Error {
  constructor(message) {
    super(message);
    this.name = "ValueError";
  }
}
class IndexError extends Error {
  constructor(message) {
    super(message);
    this.name = "IndexError";
  }
}

let lastIdMs = 0;

/** Time-sortable hex id: millisecond timestamp (strictly increasing in this process) + random suffix. */
function newExecutionId() {
  lastIdMs = Math.max(Date.now(), lastIdMs + 1);
  return lastIdMs.toString(16).padStart(13, "0") + randomHex(15);
}

// --------------------------------------------------------------------- JSON path

function tokens(path) {
  if (path === "$" || path === "" || path === null || path === undefined) return [];
  if (!String(path).startsWith("$")) throw new ValueError(`JSON path must start with '$': '${path}'`);
  const out = [];
  for (const part of String(path).slice(1).replace(/\[/g, ".[").split(".")) {
    if (!part) continue;
    if (part.startsWith("[") && part.endsWith("]")) {
      const inner = part.slice(1, -1).replace(/^['"]+|['"]+$/g, "");
      out.push(/^\d+$/.test(inner.replace(/^-+/, "")) ? parseInt(inner, 10) : inner);
    } else {
      out.push(part);
    }
  }
  return out;
}

const MISSING = Symbol("missing"); // "no default given" marker for getPath
const ABSENT = Symbol("absent"); // "path not present" value used by choice rules

/** Python `current[tok]`: returns MISSING where Python raises KeyError / IndexError / TypeError. */
function index(current, tok) {
  if (typeof tok === "number") {
    if (Array.isArray(current) || typeof current === "string") {
      const i = tok < 0 ? current.length + tok : tok;
      return i >= 0 && i < current.length ? current[i] : MISSING;
    }
    if (isPlainObject(current) && Object.prototype.hasOwnProperty.call(current, String(tok))) return MISSING;
    return MISSING;
  }
  if (isPlainObject(current) && Object.prototype.hasOwnProperty.call(current, tok)) return current[tok];
  return MISSING;
}

function getPath(data, path, fallback = MISSING) {
  let current = data;
  for (const tok of tokens(path)) {
    current = index(current, tok);
    if (current === MISSING) {
      if (fallback === MISSING) throw new KeyError(`'${path}'`);
      return fallback;
    }
  }
  return current;
}

/** `data` with `value` written at `path` (`$` replaces; null discards). */
function setPath(data, path, value) {
  if (path === null || path === undefined) return data;
  const toks = tokens(path);
  if (!toks.length) return value;
  const root = isPlainObject(data) || Array.isArray(data) ? deepCopy(data) : {};
  let current = root;
  for (const tok of toks.slice(0, -1)) {
    if (isPlainObject(current)) {
      if (!Object.prototype.hasOwnProperty.call(current, tok)) current[tok] = {};
      current = current[tok];
    } else if (Array.isArray(current) && typeof tok === "number") {
      const i = tok < 0 ? current.length + tok : tok;
      if (i < 0 || i >= current.length) throw new IndexError("list index out of range");
      current = current[i];
    } else {
      throw new TypeError(`cannot write ${path}: '${tok}' is not a container`);
    }
  }
  const last = toks[toks.length - 1];
  if (isPlainObject(current)) current[last] = value;
  else if (Array.isArray(current) && typeof last === "number") {
    const i = last < 0 ? current.length + last : last;
    if (i < 0 || i >= current.length) throw new IndexError("list assignment index out of range");
    current[i] = value;
  } else {
    throw new TypeError(`cannot write ${path}: not a container`);
  }
  return root;
}

// --------------------------------------------------------------------- Python semantics for choice rules

class PyTypeError extends Error {}

function isNum(v) {
  return typeof v === "number" || typeof v === "boolean";
}

/** Python `==`. */
function pyEq(a, b) {
  if (isNum(a) && isNum(b)) return Number(a) === Number(b);
  if (Array.isArray(a) && Array.isArray(b)) return a.length === b.length && a.every((x, i) => pyEq(x, b[i]));
  if (isPlainObject(a) && isPlainObject(b)) {
    const ka = Object.keys(a);
    if (ka.length !== Object.keys(b).length) return false;
    return ka.every((k) => Object.prototype.hasOwnProperty.call(b, k) && pyEq(a[k], b[k]));
  }
  return a === b;
}

/** Python ordering: -1 / 0 / 1, or PyTypeError for unorderable types. */
function pyCmp(a, b) {
  if (isNum(a) && isNum(b)) return Number(a) < Number(b) ? -1 : Number(a) > Number(b) ? 1 : 0;
  if (typeof a === "string" && typeof b === "string") {
    const ca = Array.from(a);
    const cb = Array.from(b);
    for (let i = 0; i < Math.min(ca.length, cb.length); i++) {
      const x = ca[i].codePointAt(0);
      const y = cb[i].codePointAt(0);
      if (x !== y) return x < y ? -1 : 1;
    }
    return ca.length < cb.length ? -1 : ca.length > cb.length ? 1 : 0;
  }
  if (Array.isArray(a) && Array.isArray(b)) {
    for (let i = 0; i < Math.min(a.length, b.length); i++) {
      if (!pyEq(a[i], b[i])) return pyCmp(a[i], b[i]);
    }
    return a.length < b.length ? -1 : a.length > b.length ? 1 : 0;
  }
  throw new PyTypeError("unorderable");
}

/** Python `needle in haystack`. */
function pyIn(needle, haystack) {
  if (Array.isArray(haystack)) return haystack.some((x) => pyEq(needle, x));
  if (typeof haystack === "string") {
    if (typeof needle !== "string") throw new PyTypeError("'in <string>' requires string as left operand");
    return haystack.includes(needle);
  }
  if (isPlainObject(haystack)) {
    if (needle !== null && typeof needle === "object") throw new PyTypeError("unhashable type");
    return Object.prototype.hasOwnProperty.call(haystack, String(needle));
  }
  throw new PyTypeError("argument is not iterable");
}

/** Python `bool(value)`. */
function pyBool(v) {
  if (v === null || v === undefined || v === false || v === 0 || v === "") return false;
  if (Array.isArray(v)) return v.length > 0;
  if (isPlainObject(v)) return Object.keys(v).length > 0;
  return true;
}

/** Python `fnmatch.fnmatchcase`: `*`, `?`, `[seq]`, `[!seq]`. */
function globToRegex(pattern) {
  let out = "";
  let i = 0;
  const p = String(pattern);
  while (i < p.length) {
    const c = p[i++];
    if (c === "*") out += "[\\s\\S]*";
    else if (c === "?") out += "[\\s\\S]";
    else if (c === "[") {
      let j = i;
      if (j < p.length && p[j] === "!") j++;
      if (j < p.length && p[j] === "]") j++;
      while (j < p.length && p[j] !== "]") j++;
      if (j >= p.length) {
        out += "\\[";
      } else {
        let stuff = p.slice(i, j).replace(/\\/g, "\\\\");
        i = j + 1;
        if (stuff.startsWith("!")) stuff = "^" + stuff.slice(1);
        else if (stuff.startsWith("^")) stuff = "\\" + stuff;
        out += `[${stuff}]`;
      }
    } else out += c.replace(/[.*+?^${}()|[\]\\/]/g, "\\$&");
  }
  return new RegExp(`^(?:${out})$`, "u");
}

const OPS = {
  equals: (a, b) => pyEq(a, b),
  not_equals: (a, b) => !pyEq(a, b),
  gt: (a, b) => a !== null && pyCmp(a, b) > 0,
  gte: (a, b) => a !== null && pyCmp(a, b) >= 0,
  lt: (a, b) => a !== null && pyCmp(a, b) < 0,
  lte: (a, b) => a !== null && pyCmp(a, b) <= 0,
  in: (a, b) => pyIn(a, b),
  contains: (a, b) => a !== null && pyIn(b, a),
  matches: (a, b) => typeof a === "string" && globToRegex(b).test(a),
  is_null: (a, b) => (a === null) === pyBool(b),
  is_present: (a, b) => (a !== ABSENT) === pyBool(b),
};
const CHOICE_OPERATORS = Object.freeze(Object.keys(OPS));

function evaluateRule(rule, data) {
  if ("and" in rule) return rule.and.every((r) => evaluateRule(r, data));
  if ("or" in rule) return rule.or.some((r) => evaluateRule(r, data));
  if ("not" in rule) return !evaluateRule(rule.not, data);
  const variable = rule.variable === undefined ? "$" : rule.variable;
  for (const [op, fn] of Object.entries(OPS)) {
    if (!(op in rule)) continue;
    const value = getPath(data, variable, ABSENT);
    if (op === "is_present") return fn(value, rule[op]);
    if (value === ABSENT) return false;
    try {
      return !!fn(value, rule[op]);
    } catch (err) {
      if (err instanceof PyTypeError) return false;
      throw err;
    }
  }
  throw new ValueError(`Choice rule has no operator (one of ${CHOICE_OPERATORS.join(", ")}): ${JSON.stringify(rule)}`);
}

// --------------------------------------------------------------------- engine

function matches(errors, name) {
  return (errors && errors.length ? errors : ["*"]).some((e) => ALL_ERRORS.includes(e) || e === name);
}

function pyTypeName(v) {
  if (v === null || v === undefined) return "NoneType";
  if (Array.isArray(v)) return "list";
  if (typeof v === "string") return "str";
  if (typeof v === "boolean") return "bool";
  if (typeof v === "number") return Number.isInteger(v) ? "int" : "float";
  if (isPlainObject(v)) return "dict";
  return typeof v;
}

/** Settle every promise, then rethrow the first failure in order (like ThreadPoolExecutor.map). */
async function allInOrder(promises) {
  const settled = await Promise.allSettled(promises);
  const failed = settled.find((s) => s.status === "rejected");
  if (failed) throw failed.reason;
  return settled.map((s) => s.value);
}

async function mapLimit(items, limit, fn) {
  const results = new Array(items.length);
  const errors = new Array(items.length);
  let next = 0;
  async function worker() {
    while (next < items.length) {
      const i = next++;
      try {
        results[i] = await fn(items[i], i);
      } catch (err) {
        errors[i] = { err };
      }
    }
  }
  await Promise.all(Array.from({ length: Math.min(limit, items.length) }, worker));
  const failed = errors.find((e) => e !== undefined);
  if (failed) throw failed.err;
  return results;
}

class WorkflowEngine {
  /**
   * @param {object} definition `{start_at, states}`
   * @param {(fn: string, data: any) => any} taskRunner may return a promise
   * @param {{sleep?: (seconds: number) => any, maxSteps?: number, onChange?: (engine: WorkflowEngine) => void,
   *          deadline?: number|null}} [opts] deadline in unix epoch seconds
   */
  constructor(definition, taskRunner, opts = {}) {
    this.definition = definition;
    this.taskRunner = taskRunner;
    this.sleep = opts.sleep || null;
    this.maxSteps = opts.maxSteps || 10000;
    this.history = [];
    this.onChange = opts.onChange || null;
    this.deadline = opts.deadline === undefined ? null : opts.deadline;
    this.currentState = null;
    this.cancelled = false;
    this._wakers = new Set();
  }

  run(data = null) {
    return this._runMachine(this.definition, data);
  }

  /** Stop before the next state starts (a running task is not interrupted). */
  cancel() {
    this.cancelled = true;
    for (const wake of this._wakers) wake();
  }

  _record(state, kind, extra = {}) {
    this.history.push(Object.assign({ ts: isoformat(new Date()), state, type: kind }, extra));
    if (extra.event === "enter") this.currentState = state;
    if (this.onChange) {
      try {
        this.onChange(this);
      } catch (err) {
        // Tracking must never break the run.
      }
    }
  }

  _checkpoint() {
    if (this.cancelled) throw new WorkflowCancelled(this.history);
    if (this.deadline !== null && Date.now() / 1000 >= this.deadline) {
      throw new WorkflowFailed(TIMEOUT_ERROR, "workflow exceeded its timeout", this.history);
    }
  }

  async _pause(seconds) {
    if (seconds <= 0) return;
    if (this.sleep) {
      await this.sleep(seconds);
    } else {
      // Real waits wake up early on cancel and never outlive the deadline.
      // setTimeout may fire a millisecond early, so sleep again until the end has really passed.
      let end = Date.now() + seconds * 1000;
      if (this.deadline !== null) end = Math.min(end, this.deadline * 1000);
      while (!this.cancelled && Date.now() < end) {
        await new Promise((resolve) => {
          const wake = () => {
            clearTimeout(timer);
            this._wakers.delete(wake);
            resolve();
          };
          const timer = setTimeout(wake, Math.ceil(end - Date.now()));
          this._wakers.add(wake);
        });
      }
    }
    this._checkpoint();
  }

  async _runMachine(machine, data0) {
    let data = data0;
    const states = machine.states;
    let name = machine.start_at;
    let steps = 0;
    while (name !== null && name !== undefined) {
      steps += 1;
      if (steps > this.maxSteps) throw new WorkflowFailed("States.Runtime", `exceeded ${this.maxSteps} steps`, this.history);
      this._checkpoint();
      const state = states[name];
      const kind = state.type;
      this._record(name, kind, { event: "enter" });
      if (kind === "succeed") return data;
      if (kind === "fail") {
        this._record(name, kind, { event: "fail", error: state.error || "States.Fail" });
        throw new WorkflowFailed(state.error || "States.Fail", state.cause || "", this.history);
      }
      if (kind === "choice") {
        name = this._choose(state, data);
        continue;
      }
      const began = nowMs();
      try {
        data = await this._execute(state, data);
      } catch (err) {
        if (err instanceof WorkflowFailed) throw err;
        const errName = errorName(err);
        const handler = (state.catch || []).find((c) => matches(c.errors || ["*"], errName));
        if (!handler) {
          const failed = new WorkflowFailed(errName, errorText(err), this.history);
          failed.original = err;
          throw failed;
        }
        this._record(name, kind, { event: "caught", error: errName });
        const info = { error: errName, cause: errorText(err) };
        data = setPath(data, handler.result_path === undefined ? "$.error" : handler.result_path, info);
        name = handler.next;
        continue;
      }
      this._record(name, kind, { event: "exit", duration_ms: round2(nowMs() - began) });
      if (state.end || !state.next) return data;
      name = state.next;
    }
    return data;
  }

  _choose(state, data) {
    for (const rule of state.choices || []) if (evaluateRule(rule, data)) return rule.next;
    if (state.default) return state.default;
    throw new WorkflowFailed("States.NoChoiceMatched", "no choice rule matched and no default", this.history);
  }

  async _execute(state, data) {
    const kind = state.type;
    const input = state.input_path ? getPath(data, state.input_path) : data;
    let result;
    if (kind === "task") {
      result = await this._withRetry(state, () => this.taskRunner(state.function, input));
    } else if (kind === "pass") {
      result = "result" in state ? state.result : input;
    } else if (kind === "wait") {
      const raw = state.seconds_path ? getPath(data, state.seconds_path) : state.seconds === undefined ? 0 : state.seconds;
      const seconds = typeof raw === "boolean" ? Number(raw) : typeof raw === "number" ? raw : Number(String(raw).trim());
      if (raw === null || Number.isNaN(seconds) || (typeof raw === "string" && !String(raw).trim())) {
        throw new ValueError(`could not convert ${pyTypeName(raw)} to float: '${raw}'`);
      }
      await this._pause(seconds);
      result = input;
    } else if (kind === "parallel") {
      result = await allInOrder((state.branches || []).map((branch) => this._runMachine(branch, deepCopy(input))));
    } else if (kind === "map") {
      const items = getPath(input, state.items_path === undefined ? "$" : state.items_path);
      if (!Array.isArray(items)) throw new TypeError(`map items_path did not resolve to a list: ${pyTypeName(items)}`);
      const workers = parseInt(state.max_concurrency || 0, 10) || Math.min(32, Math.max(1, items.length));
      result = await mapLimit(items, workers, (item) => this._runMachine(state.iterator, item));
    } else {
      throw new WorkflowFailed("States.Runtime", `unknown state type '${kind}'`, this.history);
    }
    return setPath(data, state.result_path === undefined ? "$" : state.result_path, result);
  }

  async _withRetry(state, call) {
    const attempts = new Map();
    for (;;) {
      try {
        return await call();
      } catch (err) {
        const errName = errorName(err);
        const rules = state.retry || [];
        // Like ASL, the first retrier whose errors match is the one used.
        const idx = rules.findIndex((r) => matches(r.errors || ["*"], errName));
        if (idx < 0) throw err;
        const rule = rules[idx];
        const count = attempts.get(idx) || 0;
        if (count >= parseInt(rule.max_attempts === undefined ? 3 : rule.max_attempts, 10)) throw err;
        attempts.set(idx, count + 1);
        const interval = Number(rule.interval_seconds === undefined ? 1 : rule.interval_seconds);
        const backoff = Number(rule.backoff_rate === undefined ? 2.0 : rule.backoff_rate);
        const delay = interval * Math.pow(backoff, count);
        this._record(state.function || "?", "task", { event: "retry", attempt: count + 1, error: errName });
        const cap = rule.max_delay_seconds;
        await this._pause(Math.min(delay, Number(cap === undefined || cap === null ? 300 : cap)));
      }
    }
  }
}

/** Task runner that invokes handlers from the current bundle through the dispatcher. */
function inProcessRunner(provider = "local") {
  return (fn, data) => {
    const { execute } = require("./dispatch");
    const { Context } = require("./context");
    const { Event, EventType } = require("./event");
    const event = new Event({ type: EventType.WORKFLOW, provider, function: fn, data });
    return execute(event, new Context({ function: fn, provider }), fn);
  };
}

let EXECUTOR = null;

/** Route orchestrator calls through an executor with `knows(name)`, `start(name, data, opts)`, `resultBody(record)`. */
function installExecutor(executor) {
  EXECUTOR = executor || null;
}

function truthy(value) {
  return ["1", "true", "yes", "on"].includes(String(value || "").trim().toLowerCase());
}

/** HTTP callers opt into a synchronous run with `?wait=true` or `Prefer: wait`. */
function wantsWait(event) {
  if (!event.http) return true;
  const prefer = String(event.http.headers.get("prefer") || "").toLowerCase();
  return truthy(event.http.query.wait) || truthy(event.http.headers.get("x-pskit-wait")) || prefer.includes("wait");
}

/**
 * Handler of the generated `<workflow>-orchestrator` function
 * (`pskit_runtime.workflow.orchestrate`). The run is synchronous; the result
 * carries the `execution_id`.
 */
async function orchestrate(event, context) {
  const { loadManifest } = require("./manifest");
  const { Response } = require("./response");
  const manifest = loadManifest();
  const orchestrator = event.function || context.function;
  const target = Object.entries(manifest.workflows).find(([, wf]) => wf && wf.orchestrator === orchestrator);
  if (!target) {
    const { LookupError } = require("./errors");
    throw new LookupError(`No workflow is orchestrated by function '${event.function}'`);
  }
  const [name, wf] = target;
  let data;
  if (event.http) data = event.http.body.length ? event.http.json(null) : Object.assign({}, event.http.query);
  else data = event.data;

  if (EXECUTOR && EXECUTOR.knows(name)) {
    if (!wantsWait(event)) return Response.json(await EXECUTOR.start(name, data), 202);
    const record = await EXECUTOR.start(name, data, { wait: true, taskRunner: inProcessRunner(event.provider) });
    const result = EXECUTOR.resultBody(record);
    if (record.status !== "SUCCEEDED") {
      context.logger.error("workflow failed", { workflow: result.workflow, error: result.error, cause: result.cause });
      if (event.http) return Response.json(result, 500);
      throw new WorkflowFailed(String(record.error || "States.Runtime"), String(record.cause || ""));
    }
    return result;
  }

  const executionId = newExecutionId();
  const engine = new WorkflowEngine(wf.definition, inProcessRunner(event.provider));
  if (wf.timeout) engine.deadline = Date.now() / 1000 + Number(wf.timeout);
  const started = nowMs();
  let output;
  try {
    output = await engine.run(data);
  } catch (err) {
    if (!(err instanceof WorkflowFailed)) throw err;
    const failure = {
      execution_id: executionId,
      workflow: name,
      status: err.error === TIMEOUT_ERROR ? "TIMED_OUT" : "FAILED",
      error: err.error,
      cause: err.cause,
      duration_ms: round2(nowMs() - started),
    };
    context.logger.error("workflow failed", failure);
    if (event.http) return Response.json(failure, 500);
    throw err;
  }
  return {
    execution_id: executionId,
    workflow: name,
    status: "SUCCEEDED",
    output,
    duration_ms: round2(nowMs() - started),
  };
}

module.exports = {
  ALL_ERRORS,
  TIMEOUT_ERROR,
  CHOICE_OPERATORS,
  WorkflowEngine,
  WorkflowFailed,
  WorkflowCancelled,
  KeyError,
  ValueError,
  newExecutionId,
  tokens,
  getPath,
  setPath,
  evaluateRule,
  globToRegex,
  inProcessRunner,
  installExecutor,
  wantsWait,
  orchestrate,
};
