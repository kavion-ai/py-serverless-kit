"use strict";
// Port of tests/runtime/test_workflow_engine.py plus orchestrate(): same semantics as the Python engine.

const test = require("node:test");
const assert = require("node:assert/strict");
const { runtime, makeBundle } = require("./helpers");

const wf = runtime("workflow");
const { WorkflowEngine, WorkflowFailed, evaluateRule, getPath, setPath, CHOICE_OPERATORS } = wf;

class Flaky extends Error {}

function makeRunner(failTimes = {}) {
  const calls = [];
  const fails = Object.assign({}, failTimes);
  const run = async (fn, data) => {
    calls.push([fn, data]);
    if ((fails[fn] || 0) > 0) {
      fails[fn] -= 1;
      throw new Flaky(`${fn} failed`);
    }
    if (fn === "double") return data * 2;
    if (fn === "inc") return Object.assign({}, data, { n: (data.n || 0) + 1 });
    if (fn === "explode") throw new (wf.ValueError)("bad input");
    return data;
  };
  return { run, calls };
}

test("choice operators match the Python list", () => {
  assert.deepEqual([...CHOICE_OPERATORS], ["equals", "not_equals", "gt", "gte", "lt", "lte", "in", "contains", "matches", "is_null", "is_present"]);
});

test("paths", () => {
  const data = { a: { b: [1, { c: 2 }] } };
  assert.equal(getPath(data, "$.a.b[1].c"), 2);
  assert.equal(getPath(data, "$"), data);
  assert.equal(getPath(data, "$.x", null), null);
  assert.equal(getPath(data, "$.a.b[-1].c"), 2); // negative index, like Python
  assert.equal(getPath(data, "$['a']['b'][0]"), 1);
  assert.throws(() => getPath(data, "$.x"), (err) => err.name === "KeyError");
  assert.equal(setPath(data, "$.a.z", 5).a.z, 5);
  assert.equal(setPath(data, "$", 1), 1);
  assert.equal(setPath(data, null, 1), data);
  assert.ok(!("z" in data.a)); // original untouched
});

const RULES = [
  [{ variable: "$.n", gt: 1 }, true],
  [{ variable: "$.n", lte: 1 }, false],
  [{ variable: "$.s", matches: "ab*" }, true],
  [{ variable: "$.s", matches: "a?c" }, true],
  [{ variable: "$.s", matches: "[!x]bc" }, true],
  [{ variable: "$.s", contains: "c" }, true],
  [{ variable: "$.n", in: [1, 2, 3] }, true],
  [{ variable: "$.missing", is_present: false }, true],
  [{ variable: "$.none", is_null: true }, true],
  [{ and: [{ variable: "$.n", equals: 2 }, { not: { variable: "$.s", equals: "x" } }] }, true],
  [{ or: [{ variable: "$.n", equals: 9 }, { variable: "$.missing", equals: 1 }] }, false],
  [{ variable: "$.s", gt: 3 }, false], // type mismatch -> false, not crash
  [{ variable: "$.n", equals: 2.0 }, true],
  [{ variable: "$.flag", equals: 1 }, true], // Python: True == 1
  [{ variable: "$.obj", equals: { k: [1, 2] } }, true],
  [{ variable: "$.s", in: "xxabcxx" }, true],
  [{ variable: "$.n", in: "abc" }, false], // TypeError in Python -> false
  [{ variable: "$.s", lt: "abd" }, true],
];
RULES.forEach(([rule, expected], i) => {
  test(`rule ${i}: ${JSON.stringify(rule)}`, () => {
    assert.equal(evaluateRule(rule, { n: 2, s: "abc", none: null, flag: true, obj: { k: [1, 2] } }), expected);
  });
});

test("rule without an operator is an error", () => {
  assert.throws(() => evaluateRule({ variable: "$.n" }, {}), /no operator/);
});

test("sequence, choice and pass", async () => {
  const definition = {
    start_at: "Inc",
    states: {
      Inc: { type: "task", function: "inc", next: "Check" },
      Check: { type: "choice", choices: [{ variable: "$.n", lt: 3, next: "Inc" }], default: "Tag" },
      Tag: { type: "pass", result: "done", result_path: "$.status", next: "End" },
      End: { type: "succeed" },
    },
  };
  const { run, calls } = makeRunner();
  const engine = new WorkflowEngine(definition, run);
  assert.deepEqual(await engine.run({ n: 0 }), { n: 3, status: "done" });
  assert.equal(calls.length, 3);
  const first = engine.history[0];
  assert.deepEqual(Object.keys(first), ["ts", "state", "type", "event"]);
  assert.match(first.ts, /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d\.\d{6}\+00:00$/);
  assert.deepEqual(engine.history.map((h) => [h.state, h.event]).slice(0, 3), [["Inc", "enter"], ["Inc", "exit"], ["Check", "enter"]]);
});

test("retry then success", async () => {
  const definition = {
    start_at: "T",
    states: { T: { type: "task", function: "inc", retry: [{ errors: ["Flaky"], max_attempts: 2 }], end: true } },
  };
  const { run, calls } = makeRunner({ inc: 2 });
  const sleeps = [];
  const out = await new WorkflowEngine(definition, run, { sleep: (s) => sleeps.push(s) }).run({ n: 0 });
  assert.deepEqual(out, { n: 1 });
  assert.equal(calls.length, 3);
  assert.deepEqual(sleeps, [1, 2]);
});

test("retry exhausted then catch", async () => {
  const definition = {
    start_at: "T",
    states: {
      T: {
        type: "task",
        function: "inc",
        retry: [{ errors: ["*"], max_attempts: 1, interval_seconds: 0 }],
        catch: [{ errors: ["Flaky"], next: "Handle", result_path: "$.err" }],
        next: "Never",
      },
      Never: { type: "fail", error: "ShouldNotRun" },
      Handle: { type: "succeed" },
    },
  };
  const { run, calls } = makeRunner({ inc: 5 });
  const out = await new WorkflowEngine(definition, run, { sleep: () => undefined }).run({ n: 0 });
  assert.deepEqual(out.err, { error: "Flaky", cause: "inc failed" });
  assert.equal(calls.length, 2);
});

test("uncaught failure and fail state", async () => {
  const { run } = makeRunner();
  await assert.rejects(
    new WorkflowEngine({ start_at: "T", states: { T: { type: "task", function: "explode", end: true } } }, run).run({}),
    (err) => err instanceof WorkflowFailed && err.error === "ValueError" && err.cause === "bad input",
  );
  await assert.rejects(
    new WorkflowEngine({ start_at: "F", states: { F: { type: "fail", error: "Nope", cause: "c" } } }, run).run({}),
    (err) => err.error === "Nope" && err.cause === "c",
  );
});

test("no choice matched", async () => {
  const { run } = makeRunner();
  const d = { start_at: "C", states: { C: { type: "choice", choices: [{ variable: "$.x", equals: 1, next: "C" }] } } };
  await assert.rejects(new WorkflowEngine(d, run).run({ x: 2 }), /NoChoiceMatched/);
});

test("parallel and map", async () => {
  const branch = { start_at: "D", states: { D: { type: "task", function: "double", end: true } } };
  const definition = {
    start_at: "P",
    states: {
      P: { type: "parallel", branches: [branch, branch], result_path: "$.par", next: "M" },
      M: { type: "map", items_path: "$.items", iterator: branch, result_path: "$.mapped", max_concurrency: 2, end: true },
    },
  };
  const { run } = makeRunner();
  let active = 0;
  let peak = 0;
  const runner = async (fn, data) => {
    if (fn === "double" && data && typeof data === "object") return 0;
    active += 1;
    peak = Math.max(peak, active);
    await new Promise((r) => setTimeout(r, 5));
    active -= 1;
    return run(fn, data);
  };
  const out = await new WorkflowEngine(definition, runner).run({ items: [1, 2, 3] });
  assert.deepEqual(out.mapped, [2, 4, 6]);
  assert.deepEqual(out.par, [0, 0]);
  assert.ok(peak <= 2, `max_concurrency respected (peak ${peak})`);
});

test("map over a non-list fails like Python", async () => {
  const branch = { start_at: "D", states: { D: { type: "pass", end: true } } };
  const d = { start_at: "M", states: { M: { type: "map", items_path: "$.items", iterator: branch, end: true } } };
  await assert.rejects(new WorkflowEngine(d, makeRunner().run).run({ items: { a: 1 } }), (err) => err.error === "TypeError" && /dict/.test(err.cause));
});

test("wait and input_path", async () => {
  const slept = [];
  const d = {
    start_at: "W",
    states: {
      W: { type: "wait", seconds_path: "$.delay", next: "T" },
      T: { type: "task", function: "double", input_path: "$.v", result_path: "$.v2", end: true },
    },
  };
  const out = await new WorkflowEngine(d, makeRunner().run, { sleep: (s) => slept.push(s) }).run({ delay: 3, v: 4 });
  assert.equal(out.v2, 8);
  assert.deepEqual(slept, [3]);
});

test("max steps guard", async () => {
  const d = { start_at: "L", states: { L: { type: "pass", next: "L" } } };
  await assert.rejects(new WorkflowEngine(d, makeRunner().run, { maxSteps: 10 }).run({}), /exceeded/);
});

test("timeout and cancel", async () => {
  const d = { start_at: "W", states: { W: { type: "wait", seconds: 30, end: true } } };
  const timed = new WorkflowEngine(d, makeRunner().run, { deadline: Date.now() / 1000 + 0.05 });
  await assert.rejects(timed.run({}), (err) => err.error === "States.Timeout");
  const engine = new WorkflowEngine(d, makeRunner().run);
  const running = engine.run({});
  setTimeout(() => engine.cancel(), 20);
  await assert.rejects(running, (err) => err.error === "States.Cancelled");
});

test("execution ids are time-sortable and unique", () => {
  const ids = Array.from({ length: 50 }, () => wf.newExecutionId());
  assert.equal(new Set(ids).size, 50);
  assert.deepEqual([...ids].sort(), ids);
  assert.match(ids[0], /^[0-9a-f]{28}$/);
});

test("orchestrate runs the workflow with in-process tasks", async () => {
  const { RUNTIME } = require("./helpers");
  makeBundle({ "tasks.js": "exports.inc = (e) => ({ n: (e.data.n || 0) + 1 });\nexports.boom = () => { throw new TypeError('nope'); };\n" });
  const dispatch = runtime("dispatch");
  const manifest = runtime("manifest");
  const { Event, Context, HttpRequest } = runtime();
  dispatch.clearHandlerCache();
  const definition = { start_at: "A", states: { A: { type: "task", function: "inc", next: "B" }, B: { type: "task", function: "inc", end: true } } };
  manifest.setManifest({
    functions: {
      inc: { handler: "tasks.inc" },
      boom: { handler: "tasks.boom" },
      "flow-orchestrator": { handler: "pskit_runtime.workflow.orchestrate" },
      "bad-orchestrator": { handler: "pskit_runtime.workflow.orchestrate" },
    },
    workflows: {
      flow: { orchestrator: "flow-orchestrator", definition },
      bad: { orchestrator: "bad-orchestrator", definition: { start_at: "X", states: { X: { type: "task", function: "boom", end: true } } } },
    },
  });
  assert.ok(RUNTIME);
  const out = await dispatch.execute(new Event({ type: "invoke", data: { n: 1 } }), new Context(), "flow-orchestrator");
  assert.equal(out.status, "SUCCEEDED");
  assert.deepEqual(out.output, { n: 3 });
  assert.equal(out.workflow, "flow");
  const resp = await dispatch.execute(
    new Event({ type: "http", http: new HttpRequest({ method: "POST", path: "/workflows/bad", body: "{}" }) }),
    new Context(),
    "bad-orchestrator",
  );
  assert.equal(resp.status, 500);
  const body = JSON.parse(resp.body);
  assert.equal(body.status, "FAILED");
  assert.equal(body.error, "TypeError");
  assert.equal(body.cause, "nope");
});
