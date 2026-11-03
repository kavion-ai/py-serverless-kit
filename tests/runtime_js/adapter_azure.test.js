"use strict";
// node --test tests/runtime_js/adapter_azure.test.js
const test = require("node:test");
const assert = require("node:assert");
const fs = require("fs");
const os = require("os");
const path = require("path");

const RT = path.join(__dirname, "..", "..", "src", "py_serverless_kit", "runtime_js");

function bundle(functions, source) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "pskit-azure-"));
  fs.writeFileSync(path.join(root, "handlers.js"), source);
  fs.writeFileSync(path.join(root, "pskit_manifest.json"), JSON.stringify({ service: "svc", stage: "dev", provider: "azure", functions }));
  process.env.PSKIT_BUNDLE_ROOT = root;
  require(path.join(RT, "manifest")).setManifest(null);
  require(path.join(RT, "dispatch")).clearHandlerCache();
}

const HANDLERS = `
const { Response } = require(${JSON.stringify(path.join(RT, "index"))});
exports.api = (event) => Response.json({ id: event.http.pathParams.id, q: event.http.query.q, path: event.http.path }).setCookie("a", "1").setCookie("b", "2");
exports.task = (event) => { if (event.data === "boom") throw new Error("bad"); return { echo: event.data, type: event.type }; };
exports.seen = (event) => { globalThis.__seen = { type: event.type, data: event.data, records: event.records.map((r) => [r.id, r.text(), r.bucket, r.key, r.attributes]) }; };
`;
const FUNCTIONS = {
  api: { handler: "handlers.api", routes: [{ method: "GET", path: "/users/{id}" }] },
  task: { handler: "handlers.task", routes: [] },
  seen: { handler: "handlers.seen", routes: [] },
};

function request(method, url, body, headers = {}) {
  return {
    method,
    url,
    headers: new Map(Object.entries(headers)),
    params: { id: "9" },
    arrayBuffer: async () => Buffer.from(body || ""),
  };
}

test("HTTP returns HttpResponseInit and keeps every cookie", async () => {
  bundle(FUNCTIONS, HANDLERS);
  const azure = require(path.join(RT, "adapters", "azure"));
  const out = await azure.http(request("GET", "https://app.example/users/9?q=x"), { invocationId: "i1" }, "api");
  assert.strictEqual(out.status, 200);
  assert.deepStrictEqual(JSON.parse(out.body.toString()), { id: "9", q: "x", path: "/users/9" });
  assert.strictEqual(out.headers.filter(([k]) => k === "set-cookie").length, 2);
});

test("invoke route: envelope result and error contract", async () => {
  bundle(FUNCTIONS, HANDLERS);
  const azure = require(path.join(RT, "adapters", "azure"));
  const ok = await azure.http(request("POST", "https://app/_pskit/invoke/task", JSON.stringify({ __pskit: "workflow", data: 3 })), {}, "task");
  assert.deepStrictEqual(JSON.parse(ok.body), { echo: 3, type: "workflow" });
  const bad = await azure.http(request("POST", "https://app/_pskit/invoke/task", JSON.stringify({ __pskit: "invoke", data: "boom" })), {}, "task");
  assert.strictEqual(bad.status, 500);
  assert.deepStrictEqual(JSON.parse(bad.body), { errorType: "Error", cause: "bad" });
});

test("timer, queue, blob and service bus triggers", async () => {
  bundle(FUNCTIONS, HANDLERS);
  const azure = require(path.join(RT, "adapters", "azure"));
  await azure.timer({ isPastDue: false }, { invocationId: "t" }, "seen", { report: true });
  assert.deepStrictEqual(globalThis.__seen, { type: "schedule", data: { report: true }, records: [] });
  await azure.queue("hello", { triggerMetadata: { id: "q1", dequeueCount: 1, insertionTime: "2026-01-01T00:00:00Z" } }, "seen");
  assert.deepStrictEqual(globalThis.__seen.records, [["q1", "hello", null, null, { dequeue_count: 1, insertion_time: "2026-01-01T00:00:00Z" }]]);
  await azure.blob(Buffer.from("abc"), { triggerMetadata: { blobTrigger: "up/in/x.csv", uri: "https://u" } }, "seen", "up");
  assert.deepStrictEqual(globalThis.__seen.records, [["https://u", "", "up", "in/x.csv", { uri: "https://u" }]]);
  await azure.serviceBus({ a: 1 }, { triggerMetadata: { messageId: "m", applicationProperties: { k: "v" } } }, "seen");
  assert.deepStrictEqual(globalThis.__seen.type, "topic");
  assert.deepStrictEqual(globalThis.__seen.records, [["m", '{"a":1}', null, null, { k: "v" }]]);
});
