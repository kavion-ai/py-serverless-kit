"use strict";
// node --test tests/runtime_js/adapter_gcp.test.js
const test = require("node:test");
const assert = require("node:assert");
const fs = require("fs");
const os = require("os");
const path = require("path");

const RT = path.join(__dirname, "..", "..", "src", "py_serverless_kit", "runtime_js");

function bundle(functions, source) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "pskit-gcp-"));
  fs.writeFileSync(path.join(root, "handlers.js"), source);
  fs.writeFileSync(path.join(root, "pskit_manifest.json"), JSON.stringify({ service: "svc", stage: "dev", provider: "gcp", functions }));
  process.env.PSKIT_BUNDLE_ROOT = root;
  require(path.join(RT, "manifest")).setManifest(null);
  require(path.join(RT, "dispatch")).clearHandlerCache();
}

const HANDLERS = `
exports.api = (event) => ({ q: event.http.query.q, body: event.http.text() });
exports.task = (event) => { if (event.data && event.data.fail) throw new TypeError("nope"); return { got: event.data, type: event.type }; };
exports.sub = (event) => { globalThis.__seen = event.records.map((r) => [event.type, r.text(), r.attributes]); };
exports.obj = (event) => { globalThis.__seen = event.records.map((r) => [r.bucket, r.key, r.action, r.size]); };
`;
const FUNCTIONS = {
  api: { handler: "handlers.api", routes: [{ method: "POST", path: "/api" }] },
  task: { handler: "handlers.task", routes: [] },
  sub: { handler: "handlers.sub", routes: [] },
  obj: { handler: "handlers.obj", routes: [] },
};

function fakeRes() {
  const res = { statusCode: 0, headers: {}, appended: [], body: null };
  res.status = (s) => ((res.statusCode = s), res);
  res.set = (k, v) => ((res.headers[k.toLowerCase()] = v), res);
  res.append = (k, v) => (res.appended.push([k, v]), res);
  res.send = (b) => ((res.body = b), res);
  return res;
}

test("HTTP request through the Express-style req/res", async () => {
  bundle(FUNCTIONS, HANDLERS);
  process.env.PSKIT_FUNCTION = "api";
  const gcp = require(path.join(RT, "adapters", "gcp"));
  const res = fakeRes();
  await gcp.http({ method: "POST", path: "/api", query: { q: ["1", "2"] }, headers: { "content-type": "text/plain" }, rawBody: Buffer.from("hi") }, res);
  assert.strictEqual(res.statusCode, 200);
  assert.deepStrictEqual(JSON.parse(res.body.toString()), { q: "2", body: "hi" });
});

test("envelope: result as JSON, errors as 500 {errorType, cause}", async () => {
  bundle(FUNCTIONS, HANDLERS);
  process.env.PSKIT_FUNCTION = "task";
  const gcp = require(path.join(RT, "adapters", "gcp"));
  let res = fakeRes();
  await gcp.http({ method: "POST", path: "/", query: {}, headers: {}, rawBody: Buffer.from(JSON.stringify({ __pskit: "workflow", data: { a: 1 } })) }, res);
  assert.deepStrictEqual(JSON.parse(res.body.toString()), { got: { a: 1 }, type: "workflow" });
  res = fakeRes();
  await gcp.http({ method: "POST", path: "/", query: {}, headers: {}, rawBody: Buffer.from(JSON.stringify({ __pskit: "invoke", data: { fail: true } })) }, res);
  assert.strictEqual(res.statusCode, 500);
  assert.deepStrictEqual(JSON.parse(res.body.toString()), { errorType: "TypeError", cause: "nope" });
});

test("Pub/Sub CloudEvent: queue vs topic and scheduler envelope", async () => {
  bundle(FUNCTIONS, HANDLERS);
  process.env.PSKIT_FUNCTION = "sub";
  process.env.PSKIT_TRIGGER_KIND = "queue";
  const gcp = require(path.join(RT, "adapters", "gcp"));
  const msg = { message: { data: Buffer.from("hello").toString("base64"), messageId: "1", attributes: { k: "v" } } };
  await gcp.cloudEvent({ type: "google.cloud.pubsub.topic.v1.messagePublished", source: "s", id: "e1", data: msg });
  assert.deepStrictEqual(globalThis.__seen, [["queue", "hello", { k: "v" }]]);
  delete process.env.PSKIT_TRIGGER_KIND;
  const env = { message: { data: Buffer.from(JSON.stringify({ __pskit: "schedule", data: { r: 1 } })).toString("base64") } };
  process.env.PSKIT_FUNCTION = "task";
  const out = await gcp.cloudEvent({ type: "google.cloud.pubsub.topic.v1.messagePublished", data: env });
  assert.deepStrictEqual(out, { got: { r: 1 }, type: "schedule" });
});

test("Storage CloudEvent applies prefix/suffix filters", async () => {
  bundle(FUNCTIONS, HANDLERS);
  process.env.PSKIT_FUNCTION = "obj";
  process.env.PSKIT_STORAGE_SUFFIX = ".csv";
  const gcp = require(path.join(RT, "adapters", "gcp"));
  globalThis.__seen = null;
  assert.strictEqual(await gcp.cloudEvent({ type: "google.cloud.storage.object.v1.finalized", data: { bucket: "b", name: "x.txt" } }), null);
  await gcp.cloudEvent({ type: "google.cloud.storage.object.v1.deleted", data: { bucket: "b", name: "x.csv", size: "12" } });
  assert.deepStrictEqual(globalThis.__seen, [["b", "x.csv", "deleted", 12]]);
  delete process.env.PSKIT_STORAGE_SUFFIX;
});
