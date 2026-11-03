"use strict";
// node --test tests/runtime_js/adapter_cloudflare.test.js
// Uses Node's own fetch API classes (Request / Response / Headers), the same ones Workers expose.
const test = require("node:test");
const assert = require("node:assert");
const fs = require("fs");
const os = require("os");
const path = require("path");

const RT = path.join(__dirname, "..", "..", "src", "py_serverless_kit", "runtime_js");

const MANIFEST = {
  service: "svc",
  stage: "dev",
  provider: "cloudflare",
  functions: {
    api: { handler: "src.handlers.api", routes: [{ method: "GET", path: "/hi" }] },
    tick: { handler: "src.handlers.tick", routes: [] },
  },
};

function setup() {
  // The handlers module exists on disk too, so this works whether or not dispatch reads the registry.
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "pskit-cf-"));
  fs.mkdirSync(path.join(root, "src"));
  const source = `
exports.api = (event, ctx) => ({ hi: event.http.query.name, env: process.env.GREETING, fn: ctx.function });
exports.tick = (event) => { globalThis.__tick = [event.type, event.data, event.source]; return "done"; };
`;
  fs.writeFileSync(path.join(root, "src", "handlers.js"), source);
  process.env.PSKIT_BUNDLE_ROOT = root;
  require(path.join(RT, "dispatch")).clearHandlerCache();
  const mod = require(path.join(root, "src", "handlers.js"));
  const cf = require(path.join(RT, "adapters", "cloudflare"));
  return cf.worker({ function: "api", manifest: MANIFEST, schedules: { "*/5 * * * *": { n: 1 } }, modules: { "src.handlers": mod } });
}

test("fetch: bindings become process.env, response is a fetch Response", async () => {
  const worker = setup();
  const resp = await worker.fetch(new Request("https://w.example/hi?name=Ada"), { GREETING: "hello", KV: {} }, {});
  assert.ok(resp instanceof Response);
  assert.strictEqual(resp.status, 200);
  assert.deepStrictEqual(await resp.json(), { hi: "Ada", env: "hello", fn: "api" });
});

test("fetch with the __pskit envelope answers JSON", async () => {
  const worker = setup();
  process.env.PSKIT_FUNCTION = "tick";
  const cf = require(path.join(RT, "adapters", "cloudflare"));
  const tick = cf.worker({ function: "tick", manifest: MANIFEST });
  const resp = await tick.fetch(new Request("https://w/", { method: "POST", body: JSON.stringify({ __pskit: "invoke", data: 5 }) }), {}, {});
  assert.strictEqual(resp.status, 200);
  assert.strictEqual(await resp.json(), "done");
  assert.deepStrictEqual(globalThis.__tick, ["invoke", 5, null]);
  void worker;
});

test("scheduled passes the cron's input", async () => {
  const cf = require(path.join(RT, "adapters", "cloudflare"));
  setup();
  const tick = cf.worker({ function: "tick", manifest: MANIFEST, schedules: { "*/5 * * * *": { n: 1 } } });
  let waited = null;
  await tick.scheduled({ cron: "*/5 * * * *", scheduledTime: 1700000000000 }, {}, { waitUntil: (p) => (waited = p) });
  assert.ok(waited);
  assert.deepStrictEqual(globalThis.__tick, ["schedule", { n: 1 }, "*/5 * * * *"]);
});
