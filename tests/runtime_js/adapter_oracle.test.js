"use strict";
// node --test tests/runtime_js/adapter_oracle.test.js
const test = require("node:test");
const assert = require("node:assert");
const { bundle, envelope } = require("./_regional");

function fakeCtx(extra = {}) {
  const ctx = { callID: "call-1", headers: {}, responseHeaders: {}, responseContentType: null };
  ctx.setResponseHeader = (k, v) => (ctx.responseHeaders[k] = v);
  return Object.assign(ctx, extra);
}

test("API Gateway through ctx.httpGateway sets status and content type", async () => {
  const oci = bundle("oracle", "api");
  const gw = { method: "POST", requestURL: "/items/8?q=w", headers: { "Content-Type": ["text/plain"] }, statusCode: 0, set: {} };
  gw.setResponseHeader = (k, v) => (gw.set[k] = v);
  const ctx = fakeCtx({ httpGateway: gw });
  const out = await oci.handler(Buffer.from("body!"), ctx);
  assert.strictEqual(gw.statusCode, 200);
  assert.strictEqual(ctx.responseContentType, "application/json");
  assert.deepStrictEqual(JSON.parse(out), { method: "POST", path: "/items/8", q: "w", body: "body!", id: "8" });
});

test("Fn-Http-* protocol headers without httpGateway", async () => {
  const oci = bundle("oracle", "api");
  const ctx = fakeCtx({ headers: { "Fn-Http-Method": ["GET"], "Fn-Http-Request-Url": ["/items/1"], "Fn-Http-H-Accept": ["*/*"] } });
  const out = await oci.handler(Buffer.alloc(0), ctx);
  assert.strictEqual(ctx.responseHeaders["Fn-Http-Status"], "200");
  assert.strictEqual(JSON.parse(out).id, "1");
});

test("envelope invoke and object-storage CloudEvent", async () => {
  let oci = bundle("oracle", "task");
  const out = await oci.handler(Buffer.from(JSON.stringify(envelope("workflow", { k: 1 }))), fakeCtx());
  assert.deepStrictEqual(JSON.parse(out), { got: { k: 1 }, type: "workflow" });
  oci = bundle("oracle", "batch");
  const ce = {
    eventType: "com.oraclecloud.objectstorage.createobject",
    eventID: "e1",
    eventTime: "2026-01-01T00:00:00Z",
    data: { resourceName: "f.csv", additionalDetails: { bucketName: "bk", namespace: "ns" } },
  };
  await oci.handler(Buffer.from(JSON.stringify(ce)), fakeCtx());
  assert.deepStrictEqual(globalThis.__seen.records, [{ bucket: "bk", key: "f.csv", action: "created", body: "" }]);
});
