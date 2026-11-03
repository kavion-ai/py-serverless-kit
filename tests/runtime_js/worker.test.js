"use strict";
// The JSON-lines worker protocol (deploy_docs/NODE_RUNTIME.md), driven as a real child process.

const test = require("node:test");
const assert = require("node:assert/strict");
const path = require("node:path");
const readline = require("node:readline");
const { spawn } = require("node:child_process");
const { makeBundle, RUNTIME } = require("./helpers");

function startWorker(root) {
  const child = spawn(process.execPath, [path.join(RUNTIME, "worker.js")], {
    cwd: root,
    env: Object.assign({}, process.env, { PSKIT_BUNDLE_ROOT: root, PSKIT_LOG_LEVEL: "INFO" }),
    stdio: ["pipe", "pipe", "pipe"],
  });
  const waiting = new Map();
  const stderr = [];
  readline.createInterface({ input: child.stdout }).on("line", (line) => {
    const msg = JSON.parse(line);
    const resolve = waiting.get(msg.id);
    waiting.delete(msg.id);
    if (resolve) resolve(msg);
  });
  child.stderr.on("data", (d) => stderr.push(String(d)));
  const send = (msg) =>
    new Promise((resolve) => {
      waiting.set(msg.id, resolve);
      child.stdin.write(JSON.stringify(msg) + "\n");
    });
  return { child, send, stderr };
}

function wireHttp(method, p, body = "") {
  return {
    type: "http",
    provider: "onprem",
    function: "",
    time: "2026-01-01T00:00:00+00:00",
    http: { method, path: p, headers: {}, query: {}, multi_query: {}, path_params: {}, body_b64: Buffer.from(body).toString("base64") },
    records: [],
  };
}

test("worker answers http, value, batch, errors and ping; logs go to stderr", async () => {
  const root = makeBundle({
    "pskit_manifest.json": JSON.stringify({
      functions: {
        hello: { handler: "app.hello", routes: [{ method: "GET", path: "/hello/{name}" }] },
        slow: { handler: "app.slow" },
        batch: { handler: "app.batch" },
        boom: { handler: "app.boom" },
      },
    }),
    "app.js": `
      const { Response, BatchResult } = require(${JSON.stringify(RUNTIME)});
      exports.hello = (e, ctx) => { console.log("printed by handler"); ctx.logger.info("hi"); return Response.json({ hi: e.http.pathParams.name }).setCookie("c", "1"); };
      exports.slow = async (e) => { await new Promise((r) => setTimeout(r, e.data.ms)); return { ms: e.data.ms }; };
      exports.batch = (e) => BatchResult.of(e.records.filter((r) => r.text() === "bad"));
      exports.boom = () => { throw new RangeError("nope"); };
    `,
  });
  const { child, send, stderr } = startWorker(root);
  try {
    assert.deepEqual(await send({ id: "p", op: "ping" }), { id: "p", ok: true, kind: "pong" });

    const http = await send({ id: "h", function: "hello", event: wireHttp("GET", "/hello/ada"), context: { request_id: "rq" } });
    assert.equal(http.kind, "http");
    assert.equal(http.status, 200);
    assert.equal(Buffer.from(http.body_b64, "base64").toString(), '{"hi":"ada"}');
    assert.deepEqual(http.cookies, ["c=1; Path=/; SameSite=Lax; HttpOnly; Secure"]);

    const notAllowed = await send({ id: "h2", function: "hello", event: wireHttp("POST", "/hello/ada") });
    assert.equal(notAllowed.status, 405);

    // Concurrent: the slow one is sent first and answers last.
    const [slow, fast] = await Promise.all([
      send({ id: "s1", function: "slow", event: { type: "invoke", data: { ms: 150 } } }),
      send({ id: "s2", function: "slow", event: { type: "invoke", data: { ms: 1 } } }),
    ]);
    assert.deepEqual(slow.value, { ms: 150 });
    assert.deepEqual(fast.value, { ms: 1 });

    const batch = await send({
      id: "b",
      function: "batch",
      event: { type: "queue", provider: "onprem", records: [{ id: "1", body: "ok" }, { id: "2", body: "bad" }] },
    });
    assert.deepEqual(batch, { id: "b", ok: true, kind: "batch", failed: ["2"] });

    const err = await send({ id: "e", function: "boom", event: { type: "invoke" } });
    assert.equal(err.ok, false);
    assert.equal(err.error.type, "RangeError");
    assert.equal(err.error.message, "nope");

    const httpErr = await send({ id: "e2", function: "boom", event: wireHttp("GET", "/x") });
    assert.equal(httpErr.status, 500);

    const unknown = await send({ id: "u", function: "nope", event: { type: "invoke" } });
    assert.equal(unknown.error.type, "LookupError");
  } finally {
    child.stdin.end();
  }
  const code = await new Promise((r) => child.on("exit", r));
  assert.equal(code, 0);
  const logs = stderr.join("");
  assert.match(logs, /printed by handler/);
  assert.match(logs, /"message":"hi"/);
});
