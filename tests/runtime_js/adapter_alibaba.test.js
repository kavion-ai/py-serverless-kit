"use strict";
// node --test tests/runtime_js/adapter_alibaba.test.js
const test = require("node:test");
const assert = require("node:assert");
const { bundle, envelope } = require("./_regional");

test("FC HTTP trigger (event as Buffer) with query and base64 body", async () => {
  const fc = bundle("alibaba", "api");
  const evt = {
    version: "v1",
    rawPath: "/items/7",
    headers: { "content-type": "text/plain" },
    queryParameters: { q: ["a", "b"] },
    body: Buffer.from("hi").toString("base64"),
    isBase64Encoded: true,
    requestContext: { http: { method: "POST", path: "/items/7", sourceIp: "1.2.3.4" } },
  };
  const out = await fc.handler(Buffer.from(JSON.stringify(evt)), { requestId: "r1", function: { name: "svc-dev-api", memory: 256, timeout: 30 } });
  assert.strictEqual(out.statusCode, 200);
  assert.deepStrictEqual(JSON.parse(out.body), { method: "POST", path: "/items/7", q: "b", body: "hi", id: "7" });
  assert.strictEqual(out.isBase64Encoded, false);
});

test("timer payload envelope, invoke envelope and errors", async () => {
  const fc = bundle("alibaba", "task");
  const timer = { triggerTime: "2026-01-01T00:00:00Z", triggerName: "t", payload: JSON.stringify(envelope("schedule", { x: 1 })) };
  assert.deepStrictEqual(await fc.handler(Buffer.from(JSON.stringify(timer)), null), { got: { x: 1 }, type: "schedule" });
  assert.deepStrictEqual(await fc.handler(Buffer.from(JSON.stringify(envelope("workflow", { a: 2 }))), null), { got: { a: 2 }, type: "workflow" });
  await assert.rejects(() => fc.handler(Buffer.from(JSON.stringify(envelope("invoke", { fail: true }))), null), TypeError);
});

test("OSS and MNS topic triggers", async () => {
  const fc = bundle("alibaba", "batch");
  const oss = { events: [{ eventName: "ObjectCreated:PutObject", eventTime: "2026-01-01T00:00:00Z", oss: { bucket: { name: "b" }, object: { key: "a.csv", size: 3 } } }] };
  await fc.handler(Buffer.from(JSON.stringify(oss)), null);
  assert.deepStrictEqual(globalThis.__seen.records, [{ bucket: "b", key: "a.csv", action: "created", body: "" }]);
  assert.strictEqual(globalThis.__seen.type, "storage");
  const mns = { TopicOwner: "1", TopicName: "events", MessageId: "m1", Message: "hello", PublishTime: 1700000000000 };
  await fc.handler(Buffer.from(JSON.stringify(mns)), null);
  assert.strictEqual(globalThis.__seen.type, "topic");
  assert.strictEqual(globalThis.__seen.records[0].body, "hello");
});
