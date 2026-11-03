"use strict";
// node --test tests/runtime_js/adapter_tencent.test.js
const test = require("node:test");
const assert = require("node:assert");
const { bundle, envelope } = require("./_regional");

test("API Gateway integrated response", async () => {
  const scf = bundle("tencent", "api");
  const evt = {
    httpMethod: "GET",
    path: "/items/9",
    headers: {},
    queryString: { q: "x" },
    pathParameters: { id: "9" },
    requestContext: { sourceIp: "1.1.1.1" },
    body: "",
    isBase64Encoded: false,
  };
  const out = await scf.main_handler(evt, { request_id: "r", function_name: "f", memory_limit_in_mb: 128, time_limit_in_ms: 3000 });
  assert.strictEqual(out.statusCode, 200);
  assert.deepStrictEqual(JSON.parse(out.body), { method: "GET", path: "/items/9", q: "x", body: "", id: "9" });
});

test("timer Message envelope and direct invoke", async () => {
  const scf = bundle("tencent", "task");
  const timer = { Type: "Timer", TriggerName: "t", Time: "2026-01-01T00:00:00Z", Message: JSON.stringify(envelope("schedule", { r: 1 })) };
  assert.deepStrictEqual(await scf.main_handler(timer, {}), { got: { r: 1 }, type: "schedule" });
  assert.deepStrictEqual(await scf.main_handler({ plain: true }, {}), { got: { plain: true }, type: "invoke" });
});

test("COS records strip the /<appid>/<bucket>/ prefix", async () => {
  const scf = bundle("tencent", "batch");
  const cos = {
    Records: [
      {
        cos: { cosBucket: { name: "up" }, cosObject: { key: "/1250000000/up/dir/a+b.csv", size: 4, meta: {} } },
        event: { eventName: "cos:ObjectRemove:Delete", eventTime: 1700000000 },
      },
    ],
  };
  await scf.main_handler(cos, {});
  assert.deepStrictEqual(globalThis.__seen.records, [{ bucket: "up", key: "dir/a b.csv", action: "deleted", body: "" }]);
});
