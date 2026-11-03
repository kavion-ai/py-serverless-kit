"use strict";
// node --test tests/runtime_js/adapter_digitalocean.test.js
const test = require("node:test");
const assert = require("node:assert");
const { bundle, envelope } = require("./_regional");

test("web: raw request with base64 body", async () => {
  const fn = bundle("digitalocean", "api");
  const out = await fn.main(
    {
      http: {
        method: "PUT",
        path: "/items/5",
        headers: { "content-type": "application/octet-stream" },
        queryString: "q=7",
        body: Buffer.from("bin").toString("base64"),
        isBase64Encoded: true,
      },
    },
    { activationId: "a1", getRemainingTimeInMillis: () => 1000 },
  );
  assert.strictEqual(out.statusCode, 200);
  assert.deepStrictEqual(JSON.parse(out.body), { method: "PUT", path: "/items/5", q: "7", body: "bin", id: "5" });
});

test("scheduler withBody envelope and invoke errors", async () => {
  const fn = bundle("digitalocean", "task");
  let out = await fn.main(envelope("schedule", { n: 1 }, { source: "digitalocean.scheduler" }), {});
  assert.deepStrictEqual(JSON.parse(out.body), { got: { n: 1 }, type: "schedule" });
  out = await fn.main(envelope("invoke", { fail: true }), {});
  assert.strictEqual(out.statusCode, 500);
  assert.strictEqual(JSON.parse(out.body).errorType, "TypeError");
});

test("context deadline from getRemainingTimeInMillis", () => {
  const fn = bundle("digitalocean", "task");
  const ctx = fn.toContext({ activationId: "x", getRemainingTimeInMillis: () => 2000 }, "task");
  assert.strictEqual(ctx.requestId, "x");
  assert.ok(ctx.remainingTimeMs() <= 2000);
});
