"use strict";
// The runtime must work without a filesystem, __dirname or process (Cloudflare Workers):
// handlers and the manifest are registered in memory. The runtime is loaded into a vm
// sandbox whose require() only knows the runtime's own files (fs, path, url, crypto throw).

const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { RUNTIME } = require("./helpers");

function sandbox(extraGlobals = {}) {
  const context = vm.createContext(
    Object.assign(
      {
        Buffer,
        console: { log: () => undefined, error: () => undefined, warn: () => undefined },
        crypto: globalThis.crypto,
        URL,
        URLSearchParams,
        TextEncoder,
        TextDecoder,
        setTimeout,
        clearTimeout,
        performance,
        AbortSignal,
        fetch,
      },
      extraGlobals,
    ),
  );
  const cache = new Map();
  const missing = [];
  function load(file) {
    if (cache.has(file)) return cache.get(file).exports;
    const module = { exports: {} };
    cache.set(file, module);
    if (file.endsWith(".json")) {
      module.exports = JSON.parse(fs.readFileSync(file, "utf8"));
      return module.exports;
    }
    const source = fs.readFileSync(file, "utf8");
    // No __dirname / __filename parameters: any unguarded use throws a ReferenceError.
    const fn = vm.runInContext(`(function (exports, require, module) {${source}\n})`, context, { filename: file });
    fn(module.exports, makeRequire(path.dirname(file)), module);
    return module.exports;
  }
  function makeRequire(dir) {
    return function sandboxRequire(name) {
      if (name.startsWith(".")) {
        let file = path.resolve(dir, name);
        if (!fs.existsSync(file) || fs.statSync(file).isDirectory()) file += ".js";
        return load(file);
      }
      missing.push(name);
      throw new Error(`Cannot find module '${name}' (sandbox has no ${name})`);
    };
  }
  return { context, load: (rel) => load(path.join(RUNTIME, rel)), missing };
}

const MANIFEST = {
  service: "edge",
  functions: {
    hello: { handler: "src.handlers.hello", routes: [{ method: "GET", path: "/hello/{name}", cors: true }] },
    nested: { handler: "lib.deep.mod:api.call" },
    "flow-orchestrator": { handler: "pskit_runtime.workflow.orchestrate" },
    step: { handler: "src.handlers.step" },
  },
  workflows: {
    flow: {
      orchestrator: "flow-orchestrator",
      definition: { start_at: "S", states: { S: { type: "task", function: "step", end: true } } },
    },
  },
};

test("registry-only handlers and manifest work without fs, __dirname or process", async () => {
  const { load, missing } = sandbox();
  const rt = load("index.js");
  const dispatch = load("dispatch.js");
  rt.registerManifest(MANIFEST);
  rt.registerModules({
    "src/handlers": {
      hello: (event, ctx) => ({ hi: event.http.pathParams.name, rid: typeof ctx.requestId }),
      step: (event) => Object.assign({}, event.data, { stepped: true }),
    },
    "lib.deep.mod.js": { api: { call: () => "dotted key with extension" } },
  });

  const event = new rt.Event({ type: "http", provider: "cloudflare", http: new rt.HttpRequest({ path: "/hello/ada" }) });
  const resp = await dispatch.execute(event, new rt.Context({ provider: "cloudflare" }), "hello");
  assert.equal(resp.status, 200);
  assert.equal(resp.body, '{"hi":"ada","rid":"string"}');
  assert.equal(resp.headers["access-control-allow-origin"], "*");

  assert.equal(await dispatch.execute(new rt.Event({ type: "invoke" }), new rt.Context(), "nested"), "dotted key with extension");

  // The embedded workflow engine is found without the filesystem too.
  const run = await dispatch.execute(new rt.Event({ type: "invoke", data: { a: 1 } }), new rt.Context(), "flow-orchestrator");
  assert.equal(run.status, "SUCCEEDED");
  assert.equal(JSON.stringify(run.output), '{"a":1,"stepped":true}');
  assert.match(run.execution_id, /^[0-9a-f]{28}$/);

  await assert.rejects(dispatch.resolveHandler("src.other.fn"), (err) => err.name === "HandlerNotFound" && /no registered module/.test(err.message));
  assert.ok(missing.every((m) => ["fs", "path", "url", "crypto"].includes(m)), `unexpected requires: ${missing}`);
});

test("globalThis.__PSKIT_MODULES__ and __PSKIT_MANIFEST__ are the fallback", async () => {
  const { load } = sandbox({
    __PSKIT_MANIFEST__: { functions: { ping: { handler: "app.ping" } } },
    __PSKIT_MODULES__: { app: { ping: () => "pong" } },
  });
  const rt = load("index.js");
  const dispatch = load("dispatch.js");
  assert.equal(await dispatch.execute(new rt.Event({ type: "invoke" }), new rt.Context(), "ping"), "pong");
});
