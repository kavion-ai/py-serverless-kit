"use strict";
// node --test tests/runtime_js/adapter_ibm.test.js
const test = require("node:test");
const assert = require("node:assert");
const { bundle, envelope } = require("./_regional");

test("Code Engine HTTP params (__ce_*)", async () => {
  const ce = bundle("ibm", "api");
  const out = await ce.main({
    __ce_method: "POST",
    __ce_path: "/items/4",
    __ce_headers: { "content-type": "text/plain", "x-request-id": "r9" },
    __ce_query: "q=1&q=2",
    __ce_body: "text",
  });
  assert.strictEqual(out.statusCode, 200);
  assert.deepStrictEqual(JSON.parse(out.body), { method: "POST", path: "/items/4", q: "2", body: "text", id: "4" });
});

test("merged JSON body is rebuilt from plain params", async () => {
  const ce = bundle("ibm", "api");
  const out = await ce.main({ __ce_method: "POST", __ce_path: "/", __ce_headers: { "content-type": "application/json" }, a: 1 });
  assert.deepStrictEqual(JSON.parse(JSON.parse(out.body).body), { a: 1 });
});

test("envelope over HTTP and direct params; errors as 500 JSON", async () => {
  const ce = bundle("ibm", "task");
  let out = await ce.main({ __ce_method: "POST", __ce_path: "/", __ce_headers: {}, __ce_body: JSON.stringify(envelope("workflow", { s: 1 })) });
  assert.deepStrictEqual(JSON.parse(out.body), { got: { s: 1 }, type: "workflow" });
  out = await ce.main(envelope("invoke", { fail: true }));
  assert.strictEqual(out.statusCode, 500);
  assert.deepStrictEqual(JSON.parse(out.body), { errorType: "TypeError", cause: "nope" });
  out = await ce.main({ hello: 1 });
  assert.deepStrictEqual(JSON.parse(out.body), { got: { hello: 1 }, type: "invoke" });
});
