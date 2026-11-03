"use strict";
// node --test tests/runtime_js/adapter_huawei.test.js
const test = require("node:test");
const assert = require("node:assert");
const { bundle, envelope } = require("./_regional");

const ctx = {
  getRequestID: () => "req-1",
  getFunctionName: () => "svc-dev-api",
  getMemorySize: () => 256,
  getRemainingTimeInMilliSeconds: () => 5000,
};

test("APIG event and context accessors", async () => {
  const fg = bundle("huawei", "api");
  const evt = {
    httpMethod: "POST",
    path: "/items/3",
    headers: { "content-type": "text/plain" },
    queryStringParameters: { q: "z" },
    pathParameters: { id: "3" },
    body: Buffer.from("payload").toString("base64"),
    isBase64Encoded: true,
    requestContext: { sourceIp: "9.9.9.9" },
  };
  const out = await fg.handler(evt, ctx);
  assert.strictEqual(out.statusCode, 200);
  assert.deepStrictEqual(JSON.parse(out.body), { method: "POST", path: "/items/3", q: "z", body: "payload", id: "3" });
  const context = fg.toContext(ctx, "api");
  assert.strictEqual(context.requestId, "req-1");
  assert.strictEqual(context.memoryMb, 256);
  assert.ok(context.remainingTimeMs() <= 5000);
});

test("timer user_event envelope", async () => {
  const fg = bundle("huawei", "task");
  const timer = { trigger_type: "TIMER", trigger_name: "t", time: "2026-01-01T00:00:00Z", user_event: JSON.stringify(envelope("schedule", 5)) };
  assert.deepStrictEqual(await fg.handler(timer, ctx), { got: 5, type: "schedule" });
});

test("OBS and SMN triggers", async () => {
  const fg = bundle("huawei", "batch");
  await fg.handler({ Records: [{ eventName: "ObjectCreated:Put", obs: { bucket: { name: "b" }, object: { key: "x%20y", size: 1 } } }] }, ctx);
  assert.deepStrictEqual(globalThis.__seen.records, [{ bucket: "b", key: "x y", action: "created", body: "" }]);
  await fg.handler({ record: [{ smn: { message_id: "m", message: "hi", topic_urn: "urn:t", subject: "s" } }] }, ctx);
  assert.strictEqual(globalThis.__seen.type, "topic");
  assert.strictEqual(globalThis.__seen.source, "urn:t");
  assert.strictEqual(globalThis.__seen.records[0].body, "hi");
});
